from datetime import UTC, date, datetime

from app.domain import (
    Exchange,
    Instrument,
    InstrumentType,
    MarketDataCategory,
    NormalizedMarketRecord,
)
from app.domain.models import MarketValue
from app.services.market_validation import (
    DataValidationResult,
    ValidationSeverity,
    validate_market_records,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台", code="600519", exchange=Exchange.SSE, instrument_type=InstrumentType.STOCK
)


def record(
    day: int, *, values: dict[str, MarketValue] | None = None, unit: str = "CNY"
) -> NormalizedMarketRecord:
    observed = date(2026, 8, day)
    return NormalizedMarketRecord(
        id=f"price-{day}",
        instrument=STOCK,
        category=MarketDataCategory.PRICE,
        observed_at=observed,
        values=values or {"close": 100},
        units={"close": unit},
        interface="stock_zh_a_hist",
        upstream_source="fixture",
        cutoff=NOW,
        retrieved_at=NOW,
    )


def validate(
    records: list[NormalizedMarketRecord],
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
) -> DataValidationResult:
    return validate_market_records(
        records,
        required_fields={"close"},
        numeric_fields={"close"},
        expected_units={"close": "CNY"},
        min_observations=2,
        requested_start=requested_start,
        requested_end=requested_end,
    )


def test_valid_records_are_usable() -> None:
    result = validate([record(6), record(7)])
    assert result.usable
    assert result.issues == []


def test_schema_types_units_duplicates_and_sample_size_are_rejected() -> None:
    cases = [
        [],
        [record(6)],
        [record(6), record(6)],
        [record(7), record(6)],
        [record(6, values={"other": 1}), record(7)],
        [record(6, values={"close": "bad"}), record(7)],
        [record(6, unit="USD"), record(7)],
    ]
    for records in cases:
        result = validate(records)
        assert not result.usable
        assert any(issue.severity is ValidationSeverity.ERROR for issue in result.issues)


def test_incomplete_requested_coverage_is_visible_but_usable() -> None:
    result = validate(
        [record(6), record(7)], requested_start=date(2026, 8, 5), requested_end=date(2026, 8, 8)
    )
    assert result.usable
    assert {issue.code for issue in result.issues} == {
        "partial_start_coverage",
        "partial_end_coverage",
    }
