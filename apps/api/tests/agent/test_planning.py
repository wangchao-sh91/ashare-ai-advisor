from app.agent.planning import EvidencePlanner
from app.agent.routing import IntentClassification, IntentKind
from app.domain import Exchange, Instrument, InstrumentType, MarketDataCategory
from app.providers.akshare_allowlist import MarketOperation

STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)
INDEX = Instrument(
    name="沪深300",
    code="000300",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.BROAD_INDEX,
)


def classification(
    intent: IntentKind,
    *,
    categories: list[MarketDataCategory] | None = None,
    current: bool = False,
) -> IntentClassification:
    return IntentClassification(
        intent=intent,
        requested_categories=categories or [],
        time_sensitive=current,
        rationale="test",
    )


def test_stable_knowledge_has_no_mandatory_tools() -> None:
    plan = EvidencePlanner().build(
        "什么是市盈率？",
        classification(IntentKind.STABLE_KNOWLEDGE),
        None,
    )
    assert plan.market_calls == []
    assert plan.search_calls == []


def test_stock_categories_map_only_to_approved_operations() -> None:
    plan = EvidencePlanner().build(
        "分析贵州茅台走势和估值",
        classification(
            IntentKind.SINGLE_STOCK,
            categories=[MarketDataCategory.PRICE, MarketDataCategory.VALUATION],
        ),
        STOCK,
    )
    assert [call.operation for call in plan.market_calls] == [
        MarketOperation.STOCK_HISTORY,
        MarketOperation.VALUATION_HISTORY,
    ]


def test_index_uses_index_history_and_rejects_company_categories() -> None:
    plan = EvidencePlanner().build(
        "沪深300走势和股东情况",
        classification(
            IntentKind.BROAD_INDEX,
            categories=[MarketDataCategory.PRICE, MarketDataCategory.OWNERSHIP],
        ),
        INDEX,
    )
    assert [call.operation for call in plan.market_calls] == [MarketOperation.INDEX_HISTORY]
    assert plan.unsupported_categories == [MarketDataCategory.OWNERSHIP]


def test_time_sensitive_claim_gets_one_bounded_search() -> None:
    plan = EvidencePlanner().build(
        "贵州茅台最近有什么公告？" * 20,
        classification(IntentKind.SINGLE_STOCK, current=True),
        STOCK,
    )
    assert len(plan.search_calls) == 1
    assert len(plan.search_calls[0].query) <= 100
    assert plan.search_calls[0].authority_intent
