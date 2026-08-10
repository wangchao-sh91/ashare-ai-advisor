"""Deterministic calculations over validated normalized market records."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from app.domain import Instrument, NormalizedMarketRecord, QualityFlag

TRADING_DAYS_PER_YEAR = Decimal(252)
PERCENT = Decimal(100)


class AnalyticsErrorCode(StrEnum):
    INSUFFICIENT_INPUTS = "insufficient_inputs"
    INVALID_VALUE = "invalid_value"
    INCOMPATIBLE_UNITS = "incompatible_units"
    NO_ALIGNED_DATES = "no_aligned_dates"


class AnalyticsError(ValueError):
    """Typed calculation failure safe for conversion to a limitation."""

    def __init__(self, code: AnalyticsErrorCode, metric: str, detail: str) -> None:
        self.code = code
        self.metric = metric
        self.detail = detail
        super().__init__(f"{metric}: {detail}")


@dataclass(frozen=True, slots=True)
class MetricResult:
    """A deterministic metric and all metadata needed to create evidence."""

    metric: str
    value: Decimal
    unit: str
    period_start: date
    period_end: date
    formula: str
    source_ids: tuple[str, ...]
    benchmark: Instrument | None = None
    quality_flags: tuple[QualityFlag, ...] = field(default_factory=tuple)


def _decimal_value(record: NormalizedMarketRecord, field_name: str, metric: str) -> Decimal:
    value = record.values.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise AnalyticsError(
            AnalyticsErrorCode.INVALID_VALUE,
            metric,
            f"{field_name} must be numeric",
        )
    return Decimal(value)


def _ordered_in_range(
    records: list[NormalizedMarketRecord],
    *,
    start: date | None,
    end: date | None,
) -> list[NormalizedMarketRecord]:
    return sorted(
        (
            record
            for record in records
            if (start is None or record.observed_at >= start)
            and (end is None or record.observed_at <= end)
        ),
        key=lambda record: record.observed_at,
    )


def _require_price_unit(
    records: list[NormalizedMarketRecord], field_name: str, metric: str
) -> None:
    units = {record.units.get(field_name) for record in records}
    if len(units) != 1 or None in units:
        raise AnalyticsError(
            AnalyticsErrorCode.INCOMPATIBLE_UNITS,
            metric,
            f"{field_name} units must be present and identical",
        )


def _return_between(
    start_record: NormalizedMarketRecord,
    end_record: NormalizedMarketRecord,
    *,
    field_name: str,
    metric: str,
) -> Decimal:
    start_value = _decimal_value(start_record, field_name, metric)
    end_value = _decimal_value(end_record, field_name, metric)
    if start_value == 0:
        raise AnalyticsError(AnalyticsErrorCode.INVALID_VALUE, metric, "start value cannot be zero")
    return (end_value / start_value - Decimal(1)) * PERCENT


def interval_return(
    records: list[NormalizedMarketRecord],
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
    field_name: str = "close",
) -> MetricResult:
    """Calculate percentage return over the effective available trading-date range."""
    metric = "interval_return"
    selected = _ordered_in_range(records, start=requested_start, end=requested_end)
    if len(selected) < 2:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "at least two observations are required",
        )
    start_record, end_record = selected[0], selected[-1]
    if start_record.observed_at == end_record.observed_at:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "two distinct trading dates are required",
        )
    _require_price_unit([start_record, end_record], field_name, metric)
    return MetricResult(
        metric=metric,
        value=_return_between(
            start_record,
            end_record,
            field_name=field_name,
            metric=metric,
        ),
        unit="percent",
        period_start=start_record.observed_at,
        period_end=end_record.observed_at,
        formula=f"({field_name}_end / {field_name}_start - 1) * 100",
        source_ids=(start_record.id, end_record.id),
    )


def benchmark_relative_return(
    asset_records: list[NormalizedMarketRecord],
    benchmark_records: list[NormalizedMarketRecord],
    *,
    benchmark: Instrument,
    requested_start: date | None = None,
    requested_end: date | None = None,
    field_name: str = "close",
) -> MetricResult:
    """Subtract benchmark return after aligning both series to common trading dates."""
    metric = "benchmark_relative_return"
    assets = {
        record.observed_at: record
        for record in _ordered_in_range(
            asset_records,
            start=requested_start,
            end=requested_end,
        )
    }
    benchmarks = {
        record.observed_at: record
        for record in _ordered_in_range(
            benchmark_records,
            start=requested_start,
            end=requested_end,
        )
    }
    common_dates = sorted(assets.keys() & benchmarks.keys())
    if len(common_dates) < 2:
        raise AnalyticsError(
            AnalyticsErrorCode.NO_ALIGNED_DATES,
            metric,
            "at least two common trading dates are required",
        )
    period_start, period_end = common_dates[0], common_dates[-1]
    asset_pair = [assets[period_start], assets[period_end]]
    benchmark_pair = [benchmarks[period_start], benchmarks[period_end]]
    _require_price_unit(asset_pair, field_name, metric)
    _require_price_unit(benchmark_pair, field_name, metric)
    asset_return = _return_between(
        asset_pair[0], asset_pair[1], field_name=field_name, metric=metric
    )
    benchmark_return = _return_between(
        benchmark_pair[0], benchmark_pair[1], field_name=field_name, metric=metric
    )
    return MetricResult(
        metric=metric,
        value=asset_return - benchmark_return,
        unit="percentage_points",
        period_start=period_start,
        period_end=period_end,
        formula="asset_interval_return - benchmark_interval_return on common trading dates",
        source_ids=tuple(record.id for record in asset_pair + benchmark_pair),
        benchmark=benchmark,
    )


def moving_average(
    records: list[NormalizedMarketRecord],
    *,
    window: int,
    field_name: str = "close",
) -> MetricResult:
    """Calculate a trailing simple moving average over the latest observations."""
    metric = f"moving_average_{window}"
    if window <= 0:
        raise AnalyticsError(AnalyticsErrorCode.INVALID_VALUE, metric, "window must be positive")
    ordered = _ordered_in_range(records, start=None, end=None)
    if len(ordered) < window:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            f"at least {window} observations are required",
        )
    selected = ordered[-window:]
    _require_price_unit(selected, field_name, metric)
    values = [_decimal_value(record, field_name, metric) for record in selected]
    return MetricResult(
        metric=metric,
        value=sum(values, Decimal(0)) / Decimal(window),
        unit=selected[0].units[field_name],
        period_start=selected[0].observed_at,
        period_end=selected[-1].observed_at,
        formula=f"sum(last {window} {field_name} values) / {window}",
        source_ids=tuple(record.id for record in selected),
    )


def volume_change(
    records: list[NormalizedMarketRecord],
    *,
    requested_start: date | None = None,
    requested_end: date | None = None,
) -> MetricResult:
    """Calculate volume change between effective first and last trading dates."""
    metric = "volume_change"
    selected = _ordered_in_range(records, start=requested_start, end=requested_end)
    if len(selected) < 2:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "at least two observations are required",
        )
    start_record, end_record = selected[0], selected[-1]
    _require_price_unit([start_record, end_record], "volume", metric)
    return MetricResult(
        metric=metric,
        value=_return_between(
            start_record,
            end_record,
            field_name="volume",
            metric=metric,
        ),
        unit="percent",
        period_start=start_record.observed_at,
        period_end=end_record.observed_at,
        formula="(volume_end / volume_start - 1) * 100",
        source_ids=(start_record.id, end_record.id),
    )


def historical_volatility(
    records: list[NormalizedMarketRecord],
    *,
    field_name: str = "close",
    annualization_days: int = 252,
) -> MetricResult:
    """Calculate annualized sample volatility from consecutive simple daily returns."""
    metric = "historical_volatility"
    if annualization_days <= 0:
        raise AnalyticsError(
            AnalyticsErrorCode.INVALID_VALUE,
            metric,
            "annualization_days must be positive",
        )
    ordered = _ordered_in_range(records, start=None, end=None)
    if len(ordered) < 3:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "at least three price observations are required",
        )
    _require_price_unit(ordered, field_name, metric)
    prices = [_decimal_value(record, field_name, metric) for record in ordered]
    if any(price <= 0 for price in prices):
        raise AnalyticsError(
            AnalyticsErrorCode.INVALID_VALUE,
            metric,
            f"{field_name} values must be positive",
        )
    returns = [
        current / previous - Decimal(1)
        for previous, current in zip(prices, prices[1:], strict=False)
    ]
    mean = sum(returns, Decimal(0)) / Decimal(len(returns))
    variance = sum((value - mean) ** 2 for value in returns) / Decimal(len(returns) - 1)
    value = variance.sqrt() * Decimal(annualization_days).sqrt() * PERCENT
    return MetricResult(
        metric=metric,
        value=value,
        unit="percent_annualized",
        period_start=ordered[0].observed_at,
        period_end=ordered[-1].observed_at,
        formula=(
            f"sample_stddev(consecutive {field_name} returns) * sqrt({annualization_days}) * 100"
        ),
        source_ids=tuple(record.id for record in ordered),
    )


def financial_yoy_change(
    records: list[NormalizedMarketRecord],
    *,
    metric_name: str,
    latest_period: date | None = None,
) -> MetricResult:
    """Calculate year-over-year change between matching financial report periods."""
    metric = f"financial_yoy_{metric_name}"
    matching = sorted(
        (
            record
            for record in records
            if record.values.get("metric") == metric_name
            and (latest_period is None or record.observed_at <= latest_period)
        ),
        key=lambda record: record.observed_at,
    )
    if not matching:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "no matching financial observations are available",
        )
    current = matching[-1]
    if latest_period is not None and current.observed_at != latest_period:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "the requested report period is unavailable",
        )
    previous = next(
        (
            record
            for record in reversed(matching[:-1])
            if record.observed_at.year == current.observed_at.year - 1
            and (record.observed_at.month, record.observed_at.day)
            == (current.observed_at.month, current.observed_at.day)
        ),
        None,
    )
    if previous is None:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            "the matching prior-year report period is unavailable",
        )
    _require_price_unit([previous, current], "value", metric)
    value = _return_between(previous, current, field_name="value", metric=metric)
    return MetricResult(
        metric=metric,
        value=value,
        unit="percent",
        period_start=previous.observed_at,
        period_end=current.observed_at,
        formula=f"({metric_name}_current / {metric_name}_prior_year - 1) * 100",
        source_ids=(previous.id, current.id),
    )


def valuation_percentile(
    records: list[NormalizedMarketRecord],
    *,
    field_name: str,
    min_observations: int,
    as_of: date | None = None,
) -> MetricResult:
    """Calculate the current value's empirical percentile in its trailing history."""
    metric = f"valuation_percentile_{field_name}"
    if min_observations <= 0:
        raise AnalyticsError(
            AnalyticsErrorCode.INVALID_VALUE,
            metric,
            "min_observations must be positive",
        )
    selected = _ordered_in_range(records, start=None, end=as_of)
    if len(selected) < min_observations:
        raise AnalyticsError(
            AnalyticsErrorCode.INSUFFICIENT_INPUTS,
            metric,
            f"at least {min_observations} observations are required",
        )
    _require_price_unit(selected, field_name, metric)
    values = [_decimal_value(record, field_name, metric) for record in selected]
    current = values[-1]
    rank = Decimal(sum(value <= current for value in values)) / Decimal(len(values)) * PERCENT
    return MetricResult(
        metric=metric,
        value=rank,
        unit="percentile",
        period_start=selected[0].observed_at,
        period_end=selected[-1].observed_at,
        formula=f"count({field_name} <= current) / observation_count * 100",
        source_ids=tuple(record.id for record in selected),
    )
