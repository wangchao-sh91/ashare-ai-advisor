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
    benchmark_relative_return,
    interval_return,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="示例股票", code="600001", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)
BENCHMARK = Instrument(
    name="沪深300",
    code="000300",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.BROAD_INDEX,
)


def price(
    instrument: Instrument,
    observed_at: date,
    close: Decimal | int,
    *,
    unit: str = "CNY",
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        id=f"price:{instrument.code}:{observed_at.isoformat()}",
        instrument=instrument,
        category=(
            MarketDataCategory.PRICE
            if instrument.instrument_type is InstrumentType.STOCK
            else MarketDataCategory.INDEX_PRICE
        ),
        observed_at=observed_at,
        values={"close": close},
        units={"close": unit},
        interface="fixture",
        upstream_source="fixture",
        cutoff=NOW,
        retrieved_at=NOW,
    )


def test_interval_return_uses_effective_trading_dates() -> None:
    records = [
        price(STOCK, date(2026, 8, 3), 90),
        price(STOCK, date(2026, 8, 5), 100),
        price(STOCK, date(2026, 8, 7), 110),
        price(STOCK, date(2026, 8, 10), 120),
    ]

    result = interval_return(
        records,
        requested_start=date(2026, 8, 4),
        requested_end=date(2026, 8, 8),
    )

    assert result.value == Decimal("10.0")
    assert result.period_start == date(2026, 8, 5)
    assert result.period_end == date(2026, 8, 7)
    assert result.source_ids == (
        "price:600001:2026-08-05",
        "price:600001:2026-08-07",
    )


@pytest.mark.parametrize(
    ("records", "code"),
    [
        ([], AnalyticsErrorCode.INSUFFICIENT_INPUTS),
        ([price(STOCK, date(2026, 8, 7), 100)], AnalyticsErrorCode.INSUFFICIENT_INPUTS),
        (
            [price(STOCK, date(2026, 8, 6), 0), price(STOCK, date(2026, 8, 7), 100)],
            AnalyticsErrorCode.INVALID_VALUE,
        ),
        (
            [
                price(STOCK, date(2026, 8, 6), 100, unit="CNY"),
                price(STOCK, date(2026, 8, 7), 110, unit="USD"),
            ],
            AnalyticsErrorCode.INCOMPATIBLE_UNITS,
        ),
    ],
)
def test_interval_return_rejects_invalid_inputs(
    records: list[NormalizedMarketRecord], code: AnalyticsErrorCode
) -> None:
    with pytest.raises(AnalyticsError) as raised:
        interval_return(records)
    assert raised.value.code is code


def test_relative_return_aligns_to_common_dates_and_names_benchmark() -> None:
    asset = [
        price(STOCK, date(2026, 8, 3), 95),
        price(STOCK, date(2026, 8, 4), 100),
        price(STOCK, date(2026, 8, 6), 120),
        price(STOCK, date(2026, 8, 7), 130),
    ]
    benchmark = [
        price(BENCHMARK, date(2026, 8, 4), 200),
        price(BENCHMARK, date(2026, 8, 5), 210),
        price(BENCHMARK, date(2026, 8, 6), 220),
    ]

    result = benchmark_relative_return(asset, benchmark, benchmark=BENCHMARK)

    assert result.value == Decimal("10.0")
    assert result.period_start == date(2026, 8, 4)
    assert result.period_end == date(2026, 8, 6)
    assert result.benchmark == BENCHMARK
    assert result.unit == "percentage_points"


def test_relative_return_rejects_unaligned_series() -> None:
    asset = [price(STOCK, date(2026, 8, 4), 100), price(STOCK, date(2026, 8, 6), 110)]
    benchmark = [
        price(BENCHMARK, date(2026, 8, 5), 200),
        price(BENCHMARK, date(2026, 8, 7), 210),
    ]

    with pytest.raises(AnalyticsError) as raised:
        benchmark_relative_return(asset, benchmark, benchmark=BENCHMARK)
    assert raised.value.code is AnalyticsErrorCode.NO_ALIGNED_DATES
