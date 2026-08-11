from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain import (
    EvidenceCategory,
    Exchange,
    Instrument,
    InstrumentType,
    NormalizedMarketRecord,
)
from app.services.analytics import AnalyticsError, AnalyticsErrorCode, interval_return

STOCK = Instrument(
    name="贵州茅台", code="600519", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)
NOW = datetime(2026, 8, 7, tzinfo=UTC)


def price(observed: date, close: int, unit: str = "CNY") -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        id=f"daily:{observed.isoformat()}",
        instrument=STOCK,
        category=EvidenceCategory.PRICE_DAILY,
        observed_at=observed,
        values={"close": Decimal(close), "volume": 1000},
        units={"close": unit, "volume": "shares"},
        cutoff=NOW,
        retrieved_at=NOW,
    )


def test_interval_return_uses_effective_trading_dates() -> None:
    result = interval_return(
        [price(date(2026, 8, 3), 100), price(date(2026, 8, 5), 105), price(date(2026, 8, 7), 110)],
        requested_start=date(2026, 8, 2),
        requested_end=date(2026, 8, 8),
    )
    assert result.value == Decimal(10)
    assert result.period_start == date(2026, 8, 3)
    assert result.period_end == date(2026, 8, 7)


@pytest.mark.parametrize(
    ("records", "code"),
    [
        ([price(date(2026, 8, 7), 100)], AnalyticsErrorCode.INSUFFICIENT_INPUTS),
        (
            [price(date(2026, 8, 6), 0), price(date(2026, 8, 7), 100)],
            AnalyticsErrorCode.INVALID_VALUE,
        ),
        (
            [price(date(2026, 8, 6), 100), price(date(2026, 8, 7), 101, "USD")],
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
