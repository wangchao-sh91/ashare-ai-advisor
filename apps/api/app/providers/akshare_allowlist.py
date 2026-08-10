"""Version-tested AKShare interface allowlist."""

from dataclasses import dataclass
from enum import StrEnum

AKSHARE_VERSION = "1.18.82"


class MarketOperation(StrEnum):
    STOCK_CATALOG = "stock_catalog"
    INDEX_CATALOG = "index_catalog"
    STOCK_HISTORY = "stock_history"
    INDEX_HISTORY = "index_history"
    FINANCIAL_OVERVIEW = "financial_overview"
    VALUATION_HISTORY = "valuation_history"
    OWNERSHIP = "ownership"
    PLEDGE = "pledge"


@dataclass(frozen=True, slots=True)
class InterfaceSpec:
    operation: MarketOperation
    interface: str
    allowed_parameters: frozenset[str]
    required_columns: frozenset[str]
    upstream_source: str


AKSHARE_INTERFACES: dict[MarketOperation, InterfaceSpec] = {
    MarketOperation.STOCK_CATALOG: InterfaceSpec(
        operation=MarketOperation.STOCK_CATALOG,
        interface="stock_info_a_code_name",
        allowed_parameters=frozenset(),
        required_columns=frozenset({"code", "name"}),
        upstream_source="Shanghai, Shenzhen, and Beijing exchanges via AKShare",
    ),
    MarketOperation.INDEX_CATALOG: InterfaceSpec(
        operation=MarketOperation.INDEX_CATALOG,
        interface="index_stock_info",
        allowed_parameters=frozenset(),
        required_columns=frozenset({"index_code", "display_name", "publish_date"}),
        upstream_source="JoinQuant public index directory via AKShare",
    ),
    MarketOperation.STOCK_HISTORY: InterfaceSpec(
        operation=MarketOperation.STOCK_HISTORY,
        interface="stock_zh_a_hist",
        allowed_parameters=frozenset(
            {"symbol", "period", "start_date", "end_date", "adjust", "timeout"}
        ),
        required_columns=frozenset({"日期", "股票代码", "开盘", "收盘", "最高", "最低", "成交量"}),
        upstream_source="Eastmoney historical A-share quotes via AKShare",
    ),
    MarketOperation.INDEX_HISTORY: InterfaceSpec(
        operation=MarketOperation.INDEX_HISTORY,
        interface="index_zh_a_hist",
        allowed_parameters=frozenset({"symbol", "period", "start_date", "end_date"}),
        required_columns=frozenset({"日期", "开盘", "收盘", "最高", "最低", "成交量"}),
        upstream_source="Eastmoney historical index quotes via AKShare",
    ),
    MarketOperation.FINANCIAL_OVERVIEW: InterfaceSpec(
        operation=MarketOperation.FINANCIAL_OVERVIEW,
        interface="stock_financial_abstract",
        allowed_parameters=frozenset({"symbol"}),
        required_columns=frozenset({"选项", "指标"}),
        upstream_source="Sina Finance company financial summary via AKShare",
    ),
    MarketOperation.VALUATION_HISTORY: InterfaceSpec(
        operation=MarketOperation.VALUATION_HISTORY,
        interface="stock_value_em",
        allowed_parameters=frozenset({"symbol"}),
        required_columns=frozenset({"数据日期", "PE(TTM)", "PE(静)", "市净率", "市销率"}),
        upstream_source="Eastmoney valuation analysis via AKShare",
    ),
    MarketOperation.OWNERSHIP: InterfaceSpec(
        operation=MarketOperation.OWNERSHIP,
        interface="stock_main_stock_holder",
        allowed_parameters=frozenset({"stock"}),
        required_columns=frozenset({"截至日期", "公告日期", "股东名称", "持股数量", "持股比例"}),
        upstream_source="Sina Finance major shareholder data via AKShare",
    ),
    MarketOperation.PLEDGE: InterfaceSpec(
        operation=MarketOperation.PLEDGE,
        interface="stock_gpzy_individual_pledge_ratio_detail_em",
        allowed_parameters=frozenset({"symbol"}),
        required_columns=frozenset(
            {"股票代码", "股东名称", "质押股份数量", "占总股本比例", "公告日期"}
        ),
        upstream_source="Eastmoney equity pledge details via AKShare",
    ),
}


def interface_for(operation: MarketOperation) -> InterfaceSpec:
    """Resolve only explicitly approved operations."""
    return AKSHARE_INTERFACES[operation]
