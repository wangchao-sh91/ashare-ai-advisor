"""Normalize approved AKShare DataFrames into canonical domain records."""

from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation

import pandas as pd

from app.domain import Instrument, MarketDataCategory, NormalizedMarketRecord
from app.domain.models import MarketValue

_PRICE_FIELDS = {
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "turnover",
    "振幅": "amplitude_pct",
    "涨跌幅": "change_pct",
    "涨跌额": "change",
    "换手率": "turnover_rate_pct",
}
_PRICE_UNITS = {
    "open": "CNY",
    "close": "CNY",
    "high": "CNY",
    "low": "CNY",
    "volume": "shares",
    "turnover": "CNY",
    "amplitude_pct": "percent",
    "change_pct": "percent",
    "change": "CNY",
    "turnover_rate_pct": "percent",
}
_FINANCIAL_METRICS = {
    "营业收入": ("revenue", "CNY"),
    "归属于母公司股东的净利润": ("net_profit_attributable", "CNY"),
    "基本每股收益": ("basic_eps", "CNY/share"),
    "净资产收益率": ("roe_pct", "percent"),
    "资产负债率": ("debt_to_assets_pct", "percent"),
}
_VALUATION_FIELDS = {
    "当日收盘价": ("close", "CNY"),
    "总市值": ("market_cap", "CNY"),
    "流通市值": ("free_float_market_cap", "CNY"),
    "PE(TTM)": ("pe_ttm", "ratio"),
    "PE(静)": ("pe_static", "ratio"),
    "市净率": ("pb", "ratio"),
    "PEG值": ("peg", "ratio"),
    "市现率": ("pcf", "ratio"),
    "市销率": ("ps_ttm", "ratio"),
}


def _as_date(value: object) -> date:
    parsed = pd.to_datetime(str(value), errors="raise")
    if isinstance(parsed, pd.Timestamp):
        return parsed.date()
    raise ValueError("value is not a scalar date")


def _as_decimal(value: object) -> Decimal | None:
    if value is None or pd.isna(value):  # type: ignore[call-overload]
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("%", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("value is not numeric") from exc


def _cutoff(observed_at: date) -> datetime:
    return datetime.combine(observed_at, time.min, tzinfo=UTC)


def normalize_price_history(
    frame: pd.DataFrame,
    *,
    instrument: Instrument,
    category: MarketDataCategory,
    interface: str,
    upstream_source: str,
    retrieved_at: datetime,
) -> list[NormalizedMarketRecord]:
    """Normalize stock or index OHLCV history."""
    if frame.empty:
        return []
    dates = [_as_date(value) for value in frame["日期"]]
    period_start, period_end = min(dates), max(dates)
    records: list[NormalizedMarketRecord] = []
    for position, (_, row) in enumerate(frame.iterrows()):
        observed_at = dates[position]
        values: dict[str, MarketValue] = {
            canonical: _as_decimal(row[source])
            for source, canonical in _PRICE_FIELDS.items()
            if source in frame.columns
        }
        records.append(
            NormalizedMarketRecord(
                id=f"{category.value}:{instrument.symbol}:{observed_at.isoformat()}",
                instrument=instrument,
                category=category,
                observed_at=observed_at,
                values=values,
                units={key: _PRICE_UNITS[key] for key in values},
                interface=interface,
                upstream_source=upstream_source,
                period_start=period_start,
                period_end=period_end,
                cutoff=_cutoff(period_end),
                retrieved_at=retrieved_at,
            )
        )
    return records


def normalize_financial_overview(
    frame: pd.DataFrame,
    *,
    instrument: Instrument,
    interface: str,
    upstream_source: str,
    retrieved_at: datetime,
) -> list[NormalizedMarketRecord]:
    """Normalize approved financial metrics from a wide reporting-period table."""
    records: list[NormalizedMarketRecord] = []
    period_columns: list[tuple[str, date]] = []
    for column in frame.columns:
        column_name = str(column)
        if column_name not in {"选项", "指标"}:
            try:
                period_columns.append((column_name, _as_date(column_name)))
            except (ValueError, TypeError):
                continue
    for _, row in frame.iterrows():
        metric = _FINANCIAL_METRICS.get(str(row["指标"]).strip())
        if metric is None:
            continue
        metric_name, unit = metric
        for column, observed_at in period_columns:
            value = _as_decimal(row[column])
            if value is None:
                continue
            records.append(
                NormalizedMarketRecord(
                    id=f"financial:{instrument.symbol}:{metric_name}:{observed_at.isoformat()}",
                    instrument=instrument,
                    category=MarketDataCategory.FINANCIAL,
                    observed_at=observed_at,
                    values={"metric": metric_name, "value": value},
                    units={"value": unit},
                    interface=interface,
                    upstream_source=upstream_source,
                    period_start=observed_at,
                    period_end=observed_at,
                    cutoff=_cutoff(observed_at),
                    retrieved_at=retrieved_at,
                )
            )
    return records


def normalize_valuation(
    frame: pd.DataFrame,
    *,
    instrument: Instrument,
    interface: str,
    upstream_source: str,
    retrieved_at: datetime,
) -> list[NormalizedMarketRecord]:
    records: list[NormalizedMarketRecord] = []
    for _, row in frame.iterrows():
        observed_at = _as_date(row["数据日期"])
        values: dict[str, MarketValue] = {}
        units: dict[str, str] = {}
        for source, (canonical, unit) in _VALUATION_FIELDS.items():
            if source in frame.columns:
                values[canonical] = _as_decimal(row[source])
                units[canonical] = unit
        records.append(
            NormalizedMarketRecord(
                id=f"valuation:{instrument.symbol}:{observed_at.isoformat()}",
                instrument=instrument,
                category=MarketDataCategory.VALUATION,
                observed_at=observed_at,
                values=values,
                units=units,
                interface=interface,
                upstream_source=upstream_source,
                cutoff=_cutoff(observed_at),
                retrieved_at=retrieved_at,
            )
        )
    return records


def normalize_ownership(
    frame: pd.DataFrame,
    *,
    instrument: Instrument,
    interface: str,
    upstream_source: str,
    retrieved_at: datetime,
) -> list[NormalizedMarketRecord]:
    records: list[NormalizedMarketRecord] = []
    for index, row in frame.iterrows():
        observed_at = _as_date(row["截至日期"])
        announced_at = _as_date(row["公告日期"])
        records.append(
            NormalizedMarketRecord(
                id=f"ownership:{instrument.symbol}:{observed_at.isoformat()}:{index}",
                instrument=instrument,
                category=MarketDataCategory.OWNERSHIP,
                observed_at=observed_at,
                values={
                    "shareholder_name": str(row["股东名称"]).strip(),
                    "shares_held": _as_decimal(row["持股数量"]),
                    "holding_pct": _as_decimal(row["持股比例"]),
                },
                units={"shares_held": "shares", "holding_pct": "percent"},
                interface=interface,
                upstream_source=upstream_source,
                cutoff=_cutoff(announced_at),
                retrieved_at=retrieved_at,
            )
        )
    return records


def normalize_pledges(
    frame: pd.DataFrame,
    *,
    instrument: Instrument,
    interface: str,
    upstream_source: str,
    retrieved_at: datetime,
) -> list[NormalizedMarketRecord]:
    records: list[NormalizedMarketRecord] = []
    for index, row in frame.iterrows():
        announced_at = _as_date(row["公告日期"])
        values: dict[str, MarketValue] = {
            "shareholder_name": str(row["股东名称"]).strip(),
            "pledged_shares": _as_decimal(row["质押股份数量"]),
            "pledged_pct_total": _as_decimal(row["占总股本比例"]),
            "status": str(row.get("状态", "")).strip(),
        }
        records.append(
            NormalizedMarketRecord(
                id=f"pledge:{instrument.symbol}:{announced_at.isoformat()}:{index}",
                instrument=instrument,
                category=MarketDataCategory.PLEDGE,
                observed_at=announced_at,
                values=values,
                units={"pledged_shares": "shares", "pledged_pct_total": "percent"},
                interface=interface,
                upstream_source=upstream_source,
                cutoff=_cutoff(announced_at),
                retrieved_at=retrieved_at,
            )
        )
    return records
