from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from app.agent.execution import ConstrainedToolExecutor, ExecutionBudget
from app.agent.planning import EvidencePlan, MarketCallPlan
from app.agent.routing import IntentKind
from app.domain import (
    Citation,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    MarketDataCategory,
    SourceType,
)
from app.providers.akshare_allowlist import MarketOperation
from app.providers.search_gateway import SearchRequest, SearchResult
from app.services.evidence_aggregation import CategoryOutcome, CategoryStatus

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def fact(identifier: str, text: str = "validated fact") -> EvidenceItem:
    return EvidenceItem(
        id=identifier,
        kind=EvidenceKind.MARKET_FACT,
        claim=text,
        source_ids=["market:source"],
        retrieved_at=NOW,
    )


class FakeMarket:
    def __init__(self, outcomes: dict[MarketDataCategory, CategoryOutcome | BaseException]):
        self.outcomes = outcomes
        self.calls: list[MarketDataCategory] = []

    async def execute(self, call: MarketCallPlan, instrument: Instrument) -> CategoryOutcome:
        assert instrument is STOCK
        self.calls.append(call.category)
        outcome = self.outcomes[call.category]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeSearch:
    def __init__(self, outcome: list[SearchResult] | BaseException):
        self.outcome = outcome
        self.calls = 0

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        self.calls += 1
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def market_call(category: MarketDataCategory, operation: MarketOperation) -> MarketCallPlan:
    return MarketCallPlan(operation=operation, category=category)


@pytest.mark.asyncio
async def test_partial_market_failure_preserves_independent_evidence() -> None:
    market = FakeMarket(
        {
            MarketDataCategory.PRICE: CategoryOutcome(
                category=MarketDataCategory.PRICE,
                status=CategoryStatus.AVAILABLE,
                evidence=[fact("price")],
            ),
            MarketDataCategory.VALUATION: RuntimeError("private upstream detail"),
        }
    )
    plan = EvidencePlan(
        intent=IntentKind.SINGLE_STOCK,
        instrument=STOCK,
        market_calls=[
            market_call(MarketDataCategory.PRICE, MarketOperation.STOCK_HISTORY),
            market_call(MarketDataCategory.VALUATION, MarketOperation.VALUATION_HISTORY),
        ],
    )

    result = await ConstrainedToolExecutor(market_tool=market, search_tool=None).execute(plan)

    assert [item.id for item in result.evidence] == ["price"]
    assert result.sufficient
    assert result.limitations
    assert "private upstream" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_search_is_ranked_converted_and_bounded() -> None:
    citation = Citation(
        id="web:1",
        source_type=SourceType.WEB,
        title="证监会公告",
        supported_claim="current verified claim",
        url=HttpUrl("https://www.csrc.gov.cn/a"),
        retrieved_at=NOW,
    )
    search = FakeSearch([SearchResult(citation=citation, snippet="current verified claim")])
    plan = EvidencePlan(
        intent=IntentKind.STABLE_KNOWLEDGE,
        search_calls=[SearchRequest(query="current rule")],
    )

    result = await ConstrainedToolExecutor(market_tool=None, search_tool=search).execute(plan)

    assert result.current_claim_verified
    assert result.evidence[0].kind is EvidenceKind.WEB_FACT
    assert result.citations[0].id == "web:1"


@pytest.mark.asyncio
async def test_search_failure_is_not_misreported_as_absence() -> None:
    result = await ConstrainedToolExecutor(
        market_tool=None,
        search_tool=FakeSearch(RuntimeError("credential")),
    ).execute(
        EvidencePlan(
            intent=IntentKind.STABLE_KNOWLEDGE,
            search_calls=[SearchRequest(query="current rule")],
        )
    )

    assert not result.sufficient
    assert not result.current_claim_verified
    assert result.limitations[0].message.endswith("search failed")
    assert "credential" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_total_evidence_size_is_enforced() -> None:
    market = FakeMarket(
        {
            MarketDataCategory.PRICE: CategoryOutcome(
                category=MarketDataCategory.PRICE,
                status=CategoryStatus.AVAILABLE,
                evidence=[fact("large", "x" * 1900), fact("small")],
            )
        }
    )
    result = await ConstrainedToolExecutor(
        market_tool=market,
        search_tool=None,
        budget=ExecutionBudget(max_evidence_chars=1000),
    ).execute(
        EvidencePlan(
            intent=IntentKind.SINGLE_STOCK,
            instrument=STOCK,
            market_calls=[market_call(MarketDataCategory.PRICE, MarketOperation.STOCK_HISTORY)],
        )
    )

    assert [item.id for item in result.evidence] == ["small"]
    assert any("truncated" in limitation.message for limitation in result.limitations)
