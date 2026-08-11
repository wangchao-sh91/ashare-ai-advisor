import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import SecretStr

from app.domain import (
    CategoryStatus,
    Exchange,
    Instrument,
    InstrumentType,
    NormalizedMarketRecord,
)
from app.providers.tushare_gateway import (
    REQUIRED_DAILY_FIELDS,
    TushareErrorCode,
    TushareGateway,
    TushareGatewayError,
    normalize_daily_frame,
)
from app.services.ttl_cache import TTLCache

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tushare" / "daily.json"
NOW = datetime(2026, 8, 8, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def fixture_frame() -> pd.DataFrame:
    payload = json.loads(FIXTURE.read_text())
    return pd.DataFrame(payload["rows"])


class FakePro:
    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.result = result if result is not None else fixture_frame()
        self.error = error
        self.calls: list[dict[str, object]] = []

    def daily(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


async def direct_runner(call: object, limiter: object) -> object:
    del limiter
    return call()  # type: ignore[operator]


def gateway(
    client: FakePro,
    *,
    cache: TTLCache[tuple[str, str, str, str], list[NormalizedMarketRecord]] | None = None,
) -> TushareGateway:
    return TushareGateway(
        token=SecretStr("redacted-token"),
        client=client,
        thread_runner=direct_runner,
        max_retries=0,
        cache=cache,
    )


@pytest.mark.asyncio
async def test_daily_uses_canonical_inclusive_parameters_and_orders_records() -> None:
    client = FakePro()
    records = await gateway(client).daily(
        ts_code="600519.SH",
        start_date="20260803",
        end_date="20260807",
        instrument=STOCK,
    )
    assert client.calls == [
        {"ts_code": "600519.SH", "start_date": "20260803", "end_date": "20260807"}
    ]
    assert [item.observed_at for item in records] == [date(2026, 8, 6), date(2026, 8, 7)]
    assert records[-1].interface == "pro.daily"


def test_fixture_contract_and_unit_conversion() -> None:
    payload = json.loads(FIXTURE.read_text())
    assert payload["sdk_version"] == "1.4.29"
    assert set(payload["rows"][0]) >= REQUIRED_DAILY_FIELDS
    latest = normalize_daily_frame(
        fixture_frame(),
        instrument=STOCK,
        requested_start=date(2026, 8, 3),
        requested_end=date(2026, 8, 7),
        retrieved_at=NOW,
    )[-1]
    assert latest.values["volume"] == 1234567
    assert latest.values["turnover"] == 1743210500
    assert latest.units["volume"] == "shares"
    assert latest.units["turnover"] == "CNY"


@pytest.mark.parametrize("mutation", ["missing", "code", "numeric", "date"])
def test_schema_code_numeric_and_date_failures_are_rejected(mutation: str) -> None:
    frame = fixture_frame()
    if mutation == "missing":
        frame = frame.drop(columns=["close"])
    elif mutation == "code":
        frame.loc[0, "ts_code"] = "000001.SZ"
    elif mutation == "numeric":
        frame["close"] = frame["close"].astype(object)
        frame.loc[0, "close"] = "not-a-number"
    else:
        frame.loc[0, "trade_date"] = "2026-08-07"
    with pytest.raises((TushareGatewayError, ValueError)):
        normalize_daily_frame(
            frame,
            instrument=STOCK,
            requested_start=date(2026, 8, 3),
            requested_end=date(2026, 8, 7),
        )


def test_identical_duplicate_is_deduplicated_but_conflict_is_invalid() -> None:
    frame = fixture_frame()
    duplicated = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    records = normalize_daily_frame(
        duplicated,
        instrument=STOCK,
        requested_start=date(2026, 8, 3),
        requested_end=date(2026, 8, 7),
    )
    assert len(records) == 2
    conflict = duplicated.copy()
    conflict.loc[2, "close"] = 1
    with pytest.raises(TushareGatewayError) as raised:
        normalize_daily_frame(
            conflict,
            instrument=STOCK,
            requested_start=date(2026, 8, 3),
            requested_end=date(2026, 8, 7),
        )
    assert raised.value.code is TushareErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_cache_is_versioned_defensive_and_distinguishes_ranges() -> None:
    client = FakePro()
    instance = gateway(client, cache=TTLCache(60, max_entries=4))
    first = await instance.daily(
        ts_code="600519.SH",
        start_date="20260803",
        end_date="20260807",
        instrument=STOCK,
    )
    changed = first[0].model_copy(update={"values": {**first[0].values, "close": 0}})
    first[0] = changed
    second = await instance.daily(
        ts_code="600519.SH",
        start_date="20260803",
        end_date="20260807",
        instrument=STOCK,
    )
    assert len(client.calls) == 1
    assert second[0].values["close"] != 0
    await instance.daily(
        ts_code="600519.SH",
        start_date="20260804",
        end_date="20260807",
        instrument=STOCK,
    )
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_timeout_auth_and_empty_errors_are_secret_safe() -> None:
    async def timeout_runner(call: object, limiter: object) -> object:
        del call, limiter
        raise TimeoutError

    with pytest.raises(TushareGatewayError) as timed_out:
        await TushareGateway(
            token=SecretStr("redacted-token"),
            client=FakePro(),
            max_retries=0,
            timeout_seconds=0.001,
            thread_runner=timeout_runner,
        ).daily(
            ts_code="600519.SH",
            start_date="20260803",
            end_date="20260807",
            instrument=STOCK,
        )
    assert timed_out.value.code is TushareErrorCode.TIMEOUT
    assert "redacted-token" not in str(timed_out.value)

    with pytest.raises(TushareGatewayError) as auth:
        await gateway(FakePro(error=RuntimeError("token has no permission"))).daily(
            ts_code="600519.SH",
            start_date="20260803",
            end_date="20260807",
            instrument=STOCK,
        )
    assert auth.value.code is TushareErrorCode.AUTHENTICATION

    empty = pd.DataFrame(columns=sorted(REQUIRED_DAILY_FIELDS))
    with pytest.raises(TushareGatewayError) as insufficient:
        await gateway(FakePro(result=empty)).daily(
            ts_code="600519.SH",
            start_date="20260803",
            end_date="20260807",
            instrument=STOCK,
        )
    assert insufficient.value.code is TushareErrorCode.INSUFFICIENT_SAMPLE


@pytest.mark.asyncio
async def test_failure_outcome_has_no_search_fallback_evidence() -> None:
    outcome = await gateway(FakePro(error=RuntimeError("offline"))).outcome(
        instrument=STOCK,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 7),
    )
    assert outcome.status is CategoryStatus.INSUFFICIENT
    assert outcome.evidence == []
    assert "不会由搜索结果替代" in (outcome.detail or "")
