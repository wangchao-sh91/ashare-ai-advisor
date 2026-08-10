from datetime import UTC, datetime

import pandas as pd

from app.domain import Exchange, Instrument, InstrumentType, MarketDataCategory
from app.services.market_normalizer import (
    normalize_financial_overview,
    normalize_ownership,
    normalize_pledges,
    normalize_price_history,
    normalize_valuation,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def test_normalizes_stock_and_index_history_with_provenance_and_units() -> None:
    frame = pd.DataFrame(
        [
            {
                "日期": "2026-08-06",
                "开盘": 1400,
                "收盘": 1420,
                "最高": 1430,
                "最低": 1390,
                "成交量": 1000,
            },
            {
                "日期": "2026-08-07",
                "开盘": 1420,
                "收盘": 1410,
                "最高": 1425,
                "最低": 1400,
                "成交量": 1200,
            },
        ]
    )
    records = normalize_price_history(
        frame,
        instrument=STOCK,
        category=MarketDataCategory.PRICE,
        interface="stock_zh_a_hist",
        upstream_source="Eastmoney via AKShare",
        retrieved_at=NOW,
    )

    assert len(records) == 2
    assert records[0].values["close"] == 1420
    assert records[0].units["volume"] == "shares"
    assert records[0].period_end is not None
    assert records[0].interface == "stock_zh_a_hist"
    assert not any("日期" in key for key in records[0].values)


def test_normalizes_only_approved_financial_metrics() -> None:
    frame = pd.DataFrame(
        [
            {"选项": "常用指标", "指标": "营业收入", "2025-12-31": "1000"},
            {"选项": "未知", "指标": "不稳定上游指标", "2025-12-31": "5"},
        ]
    )
    records = normalize_financial_overview(
        frame,
        instrument=STOCK,
        interface="stock_financial_abstract",
        upstream_source="Sina via AKShare",
        retrieved_at=NOW,
    )

    assert len(records) == 1
    assert records[0].values == {"metric": "revenue", "value": 1000}


def test_normalizes_valuation_ownership_and_pledge_without_provider_columns() -> None:
    valuation = normalize_valuation(
        pd.DataFrame(
            [{"数据日期": "2026-08-06", "PE(TTM)": 20, "PE(静)": 21, "市净率": 5, "市销率": 8}]
        ),
        instrument=STOCK,
        interface="stock_value_em",
        upstream_source="Eastmoney via AKShare",
        retrieved_at=NOW,
    )[0]
    ownership = normalize_ownership(
        pd.DataFrame(
            [
                {
                    "截至日期": "2026-06-30",
                    "公告日期": "2026-07-20",
                    "股东名称": "示例股东",
                    "持股数量": 10,
                    "持股比例": 5,
                }
            ]
        ),
        instrument=STOCK,
        interface="stock_main_stock_holder",
        upstream_source="Sina via AKShare",
        retrieved_at=NOW,
    )[0]
    pledge = normalize_pledges(
        pd.DataFrame(
            [
                {
                    "公告日期": "2026-07-21",
                    "股东名称": "示例股东",
                    "质押股份数量": 2,
                    "占总股本比例": 1,
                    "状态": "进行中",
                }
            ]
        ),
        instrument=STOCK,
        interface="stock_gpzy_individual_pledge_ratio_detail_em",
        upstream_source="Eastmoney via AKShare",
        retrieved_at=NOW,
    )[0]

    assert valuation.values["pe_ttm"] == 20
    assert ownership.values["holding_pct"] == 5
    assert pledge.values["pledged_pct_total"] == 1
    provider_columns = {"PE(TTM)", "持股比例", "占总股本比例"}
    assert provider_columns.isdisjoint(valuation.values | ownership.values | pledge.values)
