from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain import (
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    MarketDataCategory,
    NormalizedMarketRecord,
    QualityFlag,
    QualityFlagCode,
)
from app.services.analytics import MetricResult
from app.services.evidence_builder import market_fact_to_evidence, metric_to_evidence

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="示例股票", code="600001", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)


def price(day: int, close: int, *, retrieved_offset: int = 0) -> NormalizedMarketRecord:
    observed_at = date(2026, 8, day)
    return NormalizedMarketRecord(
        id=f"price:{day}",
        instrument=STOCK,
        category=MarketDataCategory.PRICE,
        observed_at=observed_at,
        values={"close": close},
        units={"close": "CNY"},
        interface="fixture",
        upstream_source="fixture",
        cutoff=datetime(2026, 8, day, tzinfo=UTC),
        retrieved_at=NOW + timedelta(seconds=retrieved_offset),
    )


def test_market_fact_evidence_carries_source_period_unit_and_freshness() -> None:
    record = price(7, 101)

    evidence = market_fact_to_evidence(record, field_name="close", claim="最新收盘价为 101 元")

    assert evidence.kind is EvidenceKind.MARKET_FACT
    assert evidence.value == Decimal(101)
    assert evidence.unit == "CNY"
    assert evidence.period_start == date(2026, 8, 7)
    assert evidence.source_ids == ["price:7"]
    assert evidence.cutoff == datetime(2026, 8, 7, tzinfo=UTC)


def test_metric_evidence_carries_formula_inputs_cutoff_and_quality_flags() -> None:
    first, second = price(6, 100), price(7, 110, retrieved_offset=5)
    flag = QualityFlag(
        code=QualityFlagCode.PARTIAL_COVERAGE,
        detail="available observations start after the requested date",
    )
    metric = MetricResult(
        metric="interval_return",
        value=Decimal(10),
        unit="percent",
        period_start=date(2026, 8, 6),
        period_end=date(2026, 8, 7),
        formula="(close_end / close_start - 1) * 100",
        source_ids=(first.id, second.id),
        quality_flags=(flag,),
    )

    evidence = metric_to_evidence(
        metric,
        instrument=STOCK,
        claim="区间上涨 10%",
        source_records=[first, second],
    )

    assert evidence.kind is EvidenceKind.COMPUTED_METRIC
    assert evidence.formula == metric.formula
    assert evidence.source_ids == ["price:6", "price:7"]
    assert evidence.cutoff == datetime(2026, 8, 6, tzinfo=UTC)
    assert evidence.retrieved_at == NOW + timedelta(seconds=5)
    assert evidence.quality_flags == [flag]


def test_evidence_builder_rejects_missing_fields_and_metric_inputs() -> None:
    record = price(7, 101)
    with pytest.raises(ValueError, match="volume"):
        market_fact_to_evidence(record, field_name="volume", claim="成交量")

    metric = MetricResult(
        metric="interval_return",
        value=Decimal(10),
        unit="percent",
        period_start=date(2026, 8, 6),
        period_end=date(2026, 8, 7),
        formula="formula",
        source_ids=("missing",),
    )
    with pytest.raises(ValueError, match="missing"):
        metric_to_evidence(metric, instrument=STOCK, claim="区间收益", source_records=[record])
