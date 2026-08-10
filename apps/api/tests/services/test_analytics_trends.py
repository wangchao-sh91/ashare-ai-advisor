from collections.abc import Callable
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
    MetricResult,
    historical_volatility,
    moving_average,
    volume_change,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="示例股票", code="600001", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)


def observation(day: int, close: Decimal | int, volume: int) -> NormalizedMarketRecord:
    observed_at = date(2026, 8, day)
    return NormalizedMarketRecord(
        id=f"price:{day}",
        instrument=STOCK,
        category=MarketDataCategory.PRICE,
        observed_at=observed_at,
        values={"close": close, "volume": volume},
        units={"close": "CNY", "volume": "shares"},
        interface="fixture",
        upstream_source="fixture",
        cutoff=NOW,
        retrieved_at=NOW,
    )


def test_moving_average_uses_latest_window_and_metadata() -> None:
    records = [observation(4, 10, 100), observation(5, 20, 120), observation(6, 30, 150)]

    result = moving_average(records, window=2)

    assert result.value == Decimal(25)
    assert result.unit == "CNY"
    assert result.period_start == date(2026, 8, 5)
    assert result.period_end == date(2026, 8, 6)
    assert result.source_ids == ("price:5", "price:6")


def test_volume_change_uses_effective_range() -> None:
    records = [observation(4, 10, 100), observation(5, 20, 120), observation(6, 30, 150)]

    result = volume_change(
        records,
        requested_start=date(2026, 8, 5),
        requested_end=date(2026, 8, 7),
    )

    assert result.value == Decimal(25)
    assert result.period_start == date(2026, 8, 5)
    assert result.period_end == date(2026, 8, 6)


def test_historical_volatility_is_annualized_sample_standard_deviation() -> None:
    records = [observation(4, 100, 100), observation(5, 110, 120), observation(6, 99, 150)]

    result = historical_volatility(records)

    expected = Decimal("0.02").sqrt() * Decimal(252).sqrt() * Decimal(100)
    assert result.value == expected
    assert result.unit == "percent_annualized"
    assert result.period_start == date(2026, 8, 4)
    assert result.period_end == date(2026, 8, 6)


@pytest.mark.parametrize(
    "calculation",
    [
        lambda records: moving_average(records, window=4),
        lambda records: volume_change(records[:1]),
        lambda records: historical_volatility(records[:2]),
    ],
)
def test_trend_metrics_reject_insufficient_samples(
    calculation: Callable[[list[NormalizedMarketRecord]], MetricResult],
) -> None:
    records = [observation(4, 100, 100), observation(5, 110, 120), observation(6, 99, 150)]
    with pytest.raises(AnalyticsError) as raised:
        calculation(records)
    assert raised.value.code is AnalyticsErrorCode.INSUFFICIENT_INPUTS


def test_historical_volatility_rejects_non_positive_prices() -> None:
    records = [observation(4, 100, 100), observation(5, 0, 120), observation(6, 99, 150)]
    with pytest.raises(AnalyticsError) as raised:
        historical_volatility(records)
    assert raised.value.code is AnalyticsErrorCode.INVALID_VALUE
