from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain import (
    Exchange,
    Instrument,
    InstrumentType,
    MarketDataCategory,
    NormalizedMarketRecord,
)
from app.services.analytics import (
    AnalyticsError,
    AnalyticsErrorCode,
    financial_yoy_change,
    valuation_percentile,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="示例股票", code="600001", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)


def financial(
    period: date, metric: str, value: Decimal | int, unit: str = "CNY"
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        id=f"financial:{metric}:{period.isoformat()}",
        instrument=STOCK,
        category=MarketDataCategory.FINANCIAL,
        observed_at=period,
        values={"metric": metric, "value": value},
        units={"value": unit},
        interface="fixture",
        upstream_source="fixture",
        cutoff=NOW,
        retrieved_at=NOW,
    )


def valuation(day: int, value: Decimal | int, unit: str = "ratio") -> NormalizedMarketRecord:
    observed_at = date(2026, 8, day)
    return NormalizedMarketRecord(
        id=f"valuation:pe_ttm:{day}",
        instrument=STOCK,
        category=MarketDataCategory.VALUATION,
        observed_at=observed_at,
        values={"pe_ttm": value},
        units={"pe_ttm": unit},
        interface="fixture",
        upstream_source="fixture",
        cutoff=NOW,
        retrieved_at=NOW,
    )


def test_financial_yoy_matches_the_same_reporting_period() -> None:
    records = [
        financial(date(2024, 12, 31), "revenue", 80),
        financial(date(2025, 9, 30), "revenue", 90),
        financial(date(2025, 12, 31), "revenue", 100),
        financial(date(2025, 12, 31), "roe_pct", 12, "percent"),
    ]

    result = financial_yoy_change(
        records,
        metric_name="revenue",
        latest_period=date(2025, 12, 31),
    )

    assert result.value == Decimal(25)
    assert result.period_start == date(2024, 12, 31)
    assert result.period_end == date(2025, 12, 31)
    assert result.source_ids == (
        "financial:revenue:2024-12-31",
        "financial:revenue:2025-12-31",
    )


def test_financial_yoy_rejects_missing_comparable_period() -> None:
    records = [
        financial(date(2024, 9, 30), "revenue", 80),
        financial(date(2025, 12, 31), "revenue", 100),
    ]
    with pytest.raises(AnalyticsError) as raised:
        financial_yoy_change(records, metric_name="revenue")
    assert raised.value.code is AnalyticsErrorCode.INSUFFICIENT_INPUTS


def test_valuation_percentile_uses_only_history_through_as_of_date() -> None:
    records = [
        valuation(3, 10),
        valuation(4, 20),
        valuation(5, 30),
        valuation(6, 20),
        valuation(7, 100),
    ]

    result = valuation_percentile(
        records,
        field_name="pe_ttm",
        min_observations=4,
        as_of=date(2026, 8, 6),
    )

    assert result.value == Decimal(75)
    assert result.period_start == date(2026, 8, 3)
    assert result.period_end == date(2026, 8, 6)
    assert result.unit == "percentile"


def test_valuation_percentile_rejects_insufficient_or_incompatible_history() -> None:
    records = [valuation(3, 10), valuation(4, 20), valuation(5, 30)]
    with pytest.raises(AnalyticsError) as insufficient:
        valuation_percentile(records, field_name="pe_ttm", min_observations=4)
    assert insufficient.value.code is AnalyticsErrorCode.INSUFFICIENT_INPUTS

    incompatible = [valuation(3, 10), valuation(4, 20, "percent")]
    with pytest.raises(AnalyticsError) as units:
        valuation_percentile(incompatible, field_name="pe_ttm", min_observations=2)
    assert units.value.code is AnalyticsErrorCode.INCOMPATIBLE_UNITS
