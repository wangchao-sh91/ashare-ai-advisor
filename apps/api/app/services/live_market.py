"""Production market-evidence adapter over approved AKShare operations."""

from datetime import UTC, date, datetime, timedelta

from app.agent.planning import MarketCallPlan
from app.domain import EvidenceItem, Instrument, MarketDataCategory, NormalizedMarketRecord
from app.providers.akshare_allowlist import MarketOperation, interface_for
from app.providers.akshare_gateway import AKShareGateway
from app.services.analytics import AnalyticsError, interval_return
from app.services.evidence_aggregation import CategoryOutcome, CategoryStatus
from app.services.evidence_builder import market_fact_to_evidence, metric_to_evidence
from app.services.market_normalizer import (
    normalize_financial_overview,
    normalize_ownership,
    normalize_pledges,
    normalize_price_history,
    normalize_valuation,
)
from app.services.market_validation import DataValidationResult, validate_market_records


class LiveMarketEvidenceTool:
    """Fetch, normalize, validate, and summarize one planned market category."""

    def __init__(self, gateway: AKShareGateway) -> None:
        self._gateway = gateway

    async def execute(
        self,
        call: MarketCallPlan,
        instrument: Instrument,
    ) -> CategoryOutcome:
        try:
            records = await self._records(call.operation, call.category, instrument)
            validation = self._validate(call.category, records)
            if not validation.usable:
                return CategoryOutcome(
                    category=call.category,
                    status=CategoryStatus.INVALID,
                    detail="market data failed schema or sample validation",
                )
            evidence = self._evidence(call.category, records, instrument)
            if not evidence:
                return CategoryOutcome(
                    category=call.category,
                    status=CategoryStatus.INVALID,
                    detail="market data contained no approved evidence fields",
                )
            return CategoryOutcome(
                category=call.category,
                status=CategoryStatus.AVAILABLE,
                evidence=evidence,
            )
        except Exception:
            return CategoryOutcome(
                category=call.category,
                status=CategoryStatus.UNAVAILABLE,
                detail="approved market-data operation is temporarily unavailable",
            )

    async def _records(
        self,
        operation: MarketOperation,
        category: MarketDataCategory,
        instrument: Instrument,
    ) -> list[NormalizedMarketRecord]:
        spec = interface_for(operation)
        retrieved_at = datetime.now(UTC)
        today = date.today()
        start = today - timedelta(days=370)
        if operation in {MarketOperation.STOCK_HISTORY, MarketOperation.INDEX_HISTORY}:
            parameters: dict[str, object] = {
                "symbol": instrument.code,
                "period": "daily",
                "start_date": start.strftime("%Y%m%d"),
                "end_date": today.strftime("%Y%m%d"),
            }
            if operation is MarketOperation.STOCK_HISTORY:
                parameters["adjust"] = ""
            frame = await self._gateway.fetch(operation, **parameters)
            return normalize_price_history(
                frame,
                instrument=instrument,
                category=category,
                interface=spec.interface,
                upstream_source=spec.upstream_source,
                retrieved_at=retrieved_at,
            )

        parameter_name = "stock" if operation is MarketOperation.OWNERSHIP else "symbol"
        frame = await self._gateway.fetch(operation, **{parameter_name: instrument.code})
        if operation is MarketOperation.FINANCIAL_OVERVIEW:
            return normalize_financial_overview(
                frame,
                instrument=instrument,
                interface=spec.interface,
                upstream_source=spec.upstream_source,
                retrieved_at=retrieved_at,
            )
        if operation is MarketOperation.VALUATION_HISTORY:
            return normalize_valuation(
                frame,
                instrument=instrument,
                interface=spec.interface,
                upstream_source=spec.upstream_source,
                retrieved_at=retrieved_at,
            )
        if operation is MarketOperation.OWNERSHIP:
            return normalize_ownership(
                frame,
                instrument=instrument,
                interface=spec.interface,
                upstream_source=spec.upstream_source,
                retrieved_at=retrieved_at,
            )
        if operation is MarketOperation.PLEDGE:
            return normalize_pledges(
                frame,
                instrument=instrument,
                interface=spec.interface,
                upstream_source=spec.upstream_source,
                retrieved_at=retrieved_at,
            )
        raise ValueError("unsupported live market operation")

    @staticmethod
    def _validate(
        category: MarketDataCategory,
        records: list[NormalizedMarketRecord],
    ) -> DataValidationResult:
        if category in {MarketDataCategory.PRICE, MarketDataCategory.INDEX_PRICE}:
            return validate_market_records(
                records,
                required_fields={"close", "volume"},
                numeric_fields={"close", "volume"},
                expected_units={"close": "CNY", "volume": "shares"},
                min_observations=2,
            )
        return validate_market_records(
            records,
            required_fields=set(),
            numeric_fields=set(),
            expected_units={},
            min_observations=1,
            unique_dates=False,
        )

    @staticmethod
    def _evidence(
        category: MarketDataCategory,
        records: list[NormalizedMarketRecord],
        instrument: Instrument,
    ) -> list[EvidenceItem]:
        ordered = sorted(records, key=lambda item: item.observed_at)
        latest = ordered[-1]
        evidence: list[EvidenceItem] = []
        if category in {MarketDataCategory.PRICE, MarketDataCategory.INDEX_PRICE}:
            evidence.append(
                market_fact_to_evidence(latest, field_name="close", claim="最新可用收盘价")
            )
            try:
                metric = interval_return(ordered)
                evidence.append(
                    metric_to_evidence(
                        metric,
                        instrument=instrument,
                        claim="可用区间收益率",
                        source_records=ordered,
                    )
                )
            except AnalyticsError:
                pass
            return evidence

        fields = {
            MarketDataCategory.FINANCIAL: ("value", "最新财务指标"),
            MarketDataCategory.VALUATION: ("pe_ttm", "最新滚动市盈率"),
            MarketDataCategory.OWNERSHIP: ("holding_pct", "主要股东持股比例"),
            MarketDataCategory.PLEDGE: ("pledged_pct_total", "股东质押占总股本比例"),
        }
        field_name, claim = fields[category]
        candidates = [item for item in reversed(ordered) if field_name in item.values]
        return [
            market_fact_to_evidence(item, field_name=field_name, claim=claim)
            for item in candidates[:5]
        ]
