"""Bounded Tushare `pro.daily` gateway and canonical daily normalization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from functools import partial
from typing import Any, Protocol

import tushare as ts
from anyio import CapacityLimiter, fail_after, sleep, to_thread
from pydantic import SecretStr

from app.domain import (
    CategoryOutcome,
    CategoryStatus,
    Citation,
    EvidenceCategory,
    Exchange,
    Instrument,
    InstrumentType,
    InsufficiencyReason,
    NormalizedMarketRecord,
    ProviderKind,
    SourceType,
)
from app.services.analytics import AnalyticsError, interval_return
from app.services.evidence_builder import market_fact_to_evidence, metric_to_evidence
from app.services.ttl_cache import TTLCache

TUSHARE_SCHEMA_VERSION = "daily-v1"
REQUIRED_DAILY_FIELDS = {
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "pre_close",
    "change",
    "pct_chg",
    "vol",
    "amount",
}


class TushareErrorCode(StrEnum):
    TIMEOUT = "tushare_timeout"
    AUTHENTICATION = "tushare_authentication"
    INVALID_RESPONSE = "tushare_invalid_response"
    UNAVAILABLE = "tushare_unavailable"
    INSUFFICIENT_SAMPLE = "tushare_insufficient_sample"


class TushareGatewayError(RuntimeError):
    def __init__(self, code: TushareErrorCode) -> None:
        self.code = code
        super().__init__(f"Tushare daily request failed with {code.value}")


class ProClient(Protocol):
    def daily(self, **kwargs: Any) -> Any: ...


class TushareGateway:
    def __init__(
        self,
        *,
        token: SecretStr,
        timeout_seconds: float = 20,
        max_retries: int = 1,
        max_workers: int = 4,
        cache: TTLCache[tuple[str, str, str, str], list[NormalizedMarketRecord]] | None = None,
        client: ProClient | None = None,
        thread_runner: Callable[[Callable[[], Any], CapacityLimiter], Awaitable[Any]] | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._max_retries = max_retries
        self._limiter = CapacityLimiter(max_workers)
        self._cache = cache
        self._client = client or ts.pro_api(token.get_secret_value())
        self._thread_runner = thread_runner or _run_in_thread

    @classmethod
    def from_settings(cls, settings: Any) -> TushareGateway:
        if settings.tushare_token is None:
            raise ValueError("Tushare provider configuration is incomplete")
        return cls(
            token=settings.tushare_token,
            timeout_seconds=settings.tushare_timeout_seconds,
            max_retries=settings.tushare_max_retries,
            max_workers=settings.tushare_max_workers,
            cache=TTLCache(
                settings.price_cache_ttl_seconds,
                max_entries=settings.provider_cache_max_entries,
            ),
        )

    async def daily(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
        instrument: Instrument | None = None,
        min_observations: int = 2,
    ) -> list[NormalizedMarketRecord]:
        normalized_code = _validate_ts_code(ts_code)
        start = _parse_compact_date(start_date)
        end = _parse_compact_date(end_date)
        if start > end:
            raise ValueError("start_date must not be after end_date")
        resolved = instrument or _instrument_from_ts_code(normalized_code)
        if (
            resolved.ts_code != normalized_code
            or resolved.instrument_type is not InstrumentType.STOCK
        ):
            raise ValueError("instrument does not match the requested A-share ts_code")
        key = (TUSHARE_SCHEMA_VERSION, normalized_code, start_date, end_date)
        if self._cache is not None and (cached := self._cache.get(key)) is not None:
            return cached

        frame = await self._call_daily(normalized_code, start_date, end_date)
        records = normalize_daily_frame(
            frame,
            instrument=resolved,
            requested_start=start,
            requested_end=end,
            min_observations=min_observations,
        )
        if self._cache is not None:
            self._cache.set(key, records)
        return records

    async def outcome(
        self,
        *,
        instrument: Instrument,
        start_date: date,
        end_date: date,
    ) -> CategoryOutcome:
        try:
            records = await self.daily(
                ts_code=instrument.ts_code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                instrument=instrument,
            )
        except TushareGatewayError as exc:
            reason = (
                InsufficiencyReason.INSUFFICIENT_SAMPLE
                if exc.code is TushareErrorCode.INSUFFICIENT_SAMPLE
                else InsufficiencyReason.INVALID_SCHEMA
                if exc.code is TushareErrorCode.INVALID_RESPONSE
                else InsufficiencyReason.PROVIDER_UNAVAILABLE
            )
            return CategoryOutcome(
                category=EvidenceCategory.PRICE_DAILY,
                provider=ProviderKind.TUSHARE,
                status=CategoryStatus.INSUFFICIENT,
                reason=reason,
                detail="Tushare 日线证据不可用；价格不会由搜索结果替代。",
            )

        latest = records[-1]
        evidence = [market_fact_to_evidence(latest, field_name="close", claim="最新可用收盘价")]
        with suppress(AnalyticsError):
            evidence.append(
                metric_to_evidence(
                    interval_return(records),
                    instrument=instrument,
                    claim="可用区间收益率",
                    source_records=records,
                )
            )
        citation = Citation(
            id=f"tushare:daily:{instrument.ts_code}:{records[-1].observed_at.isoformat()}",
            source_type=SourceType.TUSHARE,
            title=f"Tushare {instrument.name}日线",
            supported_claim="未复权 A 股日线及成交量数据",
            category=EvidenceCategory.PRICE_DAILY,
            interface="pro.daily",
            publisher="Tushare",
            retrieved_at=records[-1].retrieved_at,
        )
        return CategoryOutcome(
            category=EvidenceCategory.PRICE_DAILY,
            provider=ProviderKind.TUSHARE,
            status=CategoryStatus.SUFFICIENT,
            evidence=evidence,
            citations=[citation],
            records=records,
        )

    async def _call_daily(self, ts_code: str, start_date: str, end_date: str) -> Any:
        for attempt in range(self._max_retries + 1):
            try:
                call = partial(
                    self._client.daily,
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                )
                with fail_after(self._timeout):
                    return await self._thread_runner(call, self._limiter)
            except TimeoutError as exc:
                code = TushareErrorCode.TIMEOUT
                cause: BaseException = exc
            except Exception as exc:
                message = str(exc).lower()
                code = (
                    TushareErrorCode.AUTHENTICATION
                    if any(term in message for term in ("token", "权限", "permission"))
                    else TushareErrorCode.UNAVAILABLE
                )
                cause = exc
            if attempt == self._max_retries or code is TushareErrorCode.AUTHENTICATION:
                raise TushareGatewayError(code) from cause
            await sleep(min(0.1 * (2**attempt), 1.0))
        raise AssertionError("unreachable")


def normalize_daily_frame(
    frame: Any,
    *,
    instrument: Instrument,
    requested_start: date,
    requested_end: date,
    min_observations: int = 2,
    retrieved_at: datetime | None = None,
) -> list[NormalizedMarketRecord]:
    columns = set(getattr(frame, "columns", []))
    if not columns >= REQUIRED_DAILY_FIELDS:
        raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
    raw_rows = frame.to_dict(orient="records")
    if not isinstance(raw_rows, list):
        raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)

    by_date: dict[date, Mapping[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, Mapping) or row.get("ts_code") != instrument.ts_code:
            raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
        observed_at = _parse_compact_date(str(row["trade_date"]))
        if not requested_start <= observed_at <= requested_end:
            raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
        existing = by_date.get(observed_at)
        if existing is not None and dict(existing) != dict(row):
            raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
        by_date[observed_at] = row
    if len(by_date) < min_observations:
        raise TushareGatewayError(TushareErrorCode.INSUFFICIENT_SAMPLE)

    fetched_at = retrieved_at or datetime.now(UTC)
    period_start, period_end = min(by_date), max(by_date)
    records: list[NormalizedMarketRecord] = []
    for observed_at in sorted(by_date):
        row = by_date[observed_at]
        values: dict[str, Decimal | int | str | date | None] = {
            "open": _decimal(row["open"]),
            "high": _decimal(row["high"]),
            "low": _decimal(row["low"]),
            "close": _decimal(row["close"]),
            "pre_close": _decimal(row["pre_close"]),
            "change": _decimal(row["change"]),
            "change_pct": _decimal(row["pct_chg"]),
            "volume": _decimal(row["vol"]) * Decimal(100),
            "turnover": _decimal(row["amount"]) * Decimal(1000),
        }
        records.append(
            NormalizedMarketRecord(
                id=f"price_daily:{instrument.ts_code}:{observed_at.isoformat()}",
                instrument=instrument,
                observed_at=observed_at,
                values=values,
                units={
                    "open": "CNY",
                    "high": "CNY",
                    "low": "CNY",
                    "close": "CNY",
                    "pre_close": "CNY",
                    "change": "CNY",
                    "change_pct": "percent",
                    "volume": "shares",
                    "turnover": "CNY",
                },
                period_start=period_start,
                period_end=period_end,
                cutoff=datetime.combine(period_end, time.min, tzinfo=UTC),
                retrieved_at=fetched_at,
            )
        )
    return records


def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE) from exc
    if not result.is_finite():
        raise TushareGatewayError(TushareErrorCode.INVALID_RESPONSE)
    return result


def _parse_compact_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError as exc:
        raise ValueError("dates must use YYYYMMDD") from exc


def _validate_ts_code(value: str) -> str:
    code = value.strip().upper()
    if (
        len(code) != 9
        or code[6] != "."
        or not code[:6].isdigit()
        or code[7:]
        not in {
            "SH",
            "SZ",
            "BJ",
        }
    ):
        raise ValueError("ts_code must use 000000.SH/SZ/BJ format")
    return code


def _instrument_from_ts_code(ts_code: str) -> Instrument:
    suffix = ts_code[-2:]
    exchange = {"SH": Exchange.SSE, "SZ": Exchange.SZSE, "BJ": Exchange.BSE}[suffix]
    return Instrument(
        name=ts_code,
        code=ts_code[:6],
        exchange=exchange,
        instrument_type=InstrumentType.STOCK,
    )


async def _run_in_thread(call: Callable[[], Any], limiter: CapacityLimiter) -> Any:
    return await to_thread.run_sync(call, limiter=limiter, abandon_on_cancel=True)
