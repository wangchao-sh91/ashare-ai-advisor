from datetime import date

from app.agent.planning import EvidencePlanner
from app.agent.routing import IntentKind, QuestionNormalization
from app.domain import (
    EvidenceCategory,
    Exchange,
    Instrument,
    InstrumentType,
    ProviderKind,
)

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
PLANNER = EvidencePlanner(today=date(2026, 8, 10), search_result_limit=3)


def normalized(
    *,
    intent: IntentKind,
    instrument: Instrument | None = None,
    categories: list[EvidenceCategory] | None = None,
) -> QuestionNormalization:
    return QuestionNormalization(
        rewritten_question="规范问题",
        intent=intent,
        instrument=instrument,
        requested_categories=categories or [],
        rationale="test",
    )


def test_stable_knowledge_has_no_provider_calls() -> None:
    assert PLANNER.build(normalized(intent=IntentKind.STABLE_KNOWLEDGE)).calls == []


def test_stock_price_routes_only_to_tushare() -> None:
    plan = PLANNER.build(normalized(intent=IntentKind.SINGLE_STOCK, instrument=STOCK))
    assert len(plan.calls) == 1
    assert plan.calls[0].category is EvidenceCategory.PRICE_DAILY
    assert plan.calls[0].provider is ProviderKind.TUSHARE
    assert plan.calls[0].query is None


def test_stock_nonprice_and_combined_categories_route_to_fixed_search_queries() -> None:
    plan = PLANNER.build(
        normalized(
            intent=IntentKind.SINGLE_STOCK,
            instrument=STOCK,
            categories=[
                EvidenceCategory.PRICE_DAILY,
                EvidenceCategory.VALUATION,
                EvidenceCategory.CORPORATE_EVENT,
            ],
        )
    )
    assert [call.provider for call in plan.calls] == [
        ProviderKind.TUSHARE,
        ProviderKind.DOUBAO_SEARCH,
        ProviderKind.DOUBAO_SEARCH,
    ]
    assert all("贵州茅台" in (call.query or "") for call in plan.search_calls)
    queries = {call.category: call.query or "" for call in plan.search_calls}
    assert "600519.SH" in queries[EvidenceCategory.VALUATION]
    assert "600519 最新公告 官方" in queries[EvidenceCategory.CORPORATE_EVENT]


def test_broad_index_is_search_only() -> None:
    plan = PLANNER.build(
        normalized(
            intent=IntentKind.BROAD_INDEX,
            instrument=INDEX,
            categories=[EvidenceCategory.INDEX_CONTEXT],
        )
    )
    assert plan.market_calls == []
    assert plan.search_calls[0].category is EvidenceCategory.INDEX_CONTEXT
