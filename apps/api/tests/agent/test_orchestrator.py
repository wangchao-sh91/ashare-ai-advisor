from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import HttpUrl

from app.agent.entity_resolution import ContextualEntityResolver
from app.agent.execution import ConstrainedToolExecutor, ToolExecutionResult
from app.agent.orchestrator import ControlledOrchestrator, OrchestrationStatus
from app.agent.planning import EvidencePlanner, MarketCallPlan
from app.agent.routing import IntentClassification, IntentKind
from app.api.chat_models import ChatMessage, ChatRequest, ChatRole
from app.domain import (
    AnswerKind,
    Citation,
    ErrorCode,
    EvidenceItem,
    EvidenceKind,
    MarketDataCategory,
    SourceType,
    StructuredAnswer,
)
from app.providers.akshare_allowlist import MarketOperation
from app.providers.model_gateway import ModelErrorCode, ModelGatewayError
from app.providers.search_gateway import SearchRequest, SearchResult
from app.services.evidence_aggregation import CategoryOutcome, CategoryStatus
from app.services.instrument_resolver import InstrumentResolver

NOW = datetime(2026, 8, 7, tzinfo=UTC)


class FakeClassifier:
    def __init__(self, result: IntentClassification) -> None:
        self.result = result

    async def classify(self, question: str, context: list[ChatMessage]) -> IntentClassification:
        return self.result


class FakeMarket:
    def __init__(self, failed: set[MarketDataCategory] | None = None) -> None:
        self.failed = failed or set()
        self.operations: list[MarketOperation] = []

    async def execute(self, call: MarketCallPlan, instrument: object) -> CategoryOutcome:
        self.operations.append(call.operation)
        if call.category in self.failed:
            return CategoryOutcome(
                category=call.category,
                status=CategoryStatus.UNAVAILABLE,
                detail="category unavailable",
            )
        return CategoryOutcome(
            category=call.category,
            status=CategoryStatus.AVAILABLE,
            evidence=[
                EvidenceItem(
                    id=f"evidence:{call.category.value}",
                    kind=EvidenceKind.MARKET_FACT,
                    claim=f"validated {call.category.value} fact",
                    source_ids=[f"source:{call.category.value}"],
                    retrieved_at=NOW,
                )
            ],
        )


class FakeSearch:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.requests: list[SearchRequest] = []

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        self.requests.append(request)
        return self.results


class FailingSearch:
    async def search(self, request: SearchRequest) -> list[SearchResult]:
        del request
        raise TimeoutError("fake search timeout")


class FakeGenerator:
    async def generate(
        self,
        question: str,
        classification: IntentClassification,
        execution: ToolExecutionResult,
    ) -> StructuredAnswer:
        facts = execution.evidence
        citations = execution.citations
        kind = {
            IntentKind.STABLE_KNOWLEDGE: AnswerKind.KNOWLEDGE,
            IntentKind.MIXED: AnswerKind.MIXED,
        }.get(classification.intent, AnswerKind.RESEARCH)
        return StructuredAnswer(
            kind=kind,
            summary="基于已验证信息的结论",
            facts=facts,
            analysis=["解释与事实分开展示"],
            risks=["结论存在不确定性"],
            citations=citations,
            answered_at=NOW,
            limitations=execution.limitations,
        )


class FailingGenerator:
    async def generate(
        self,
        question: str,
        classification: IntentClassification,
        execution: ToolExecutionResult,
    ) -> StructuredAnswer:
        del question, classification, execution
        raise ModelGatewayError(ModelErrorCode.TIMEOUT)


def classification(
    intent: IntentKind,
    *,
    instrument: str | None = None,
    categories: list[MarketDataCategory] | None = None,
    current: bool = False,
    comparison: bool = False,
) -> IntentClassification:
    return IntentClassification(
        intent=intent,
        instrument_query=instrument,
        requested_categories=categories or [],
        time_sensitive=current,
        comparison_requested=comparison,
        unsupported_reason="unsupported" if intent is IntentKind.OUT_OF_SCOPE else None,
        rationale="test route",
    )


def search_result(identifier: str, url: str, claim: str) -> SearchResult:
    return SearchResult(
        citation=Citation(
            id=identifier,
            source_type=SourceType.WEB,
            title=identifier,
            supported_claim=claim,
            url=HttpUrl(url),
            retrieved_at=NOW,
        ),
        snippet=claim,
    )


def orchestrator(
    route: IntentClassification,
    *,
    market: FakeMarket | None = None,
    search: FakeSearch | FailingSearch | None = None,
    generator: FakeGenerator | FailingGenerator | None = None,
) -> ControlledOrchestrator:
    resolver = InstrumentResolver(
        pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台"},
                {"code": "000001", "name": "平安银行"},
            ]
        )
    )
    return ControlledOrchestrator(
        classifier=FakeClassifier(route),  # type: ignore[arg-type]
        entity_resolver=ContextualEntityResolver(resolver),
        planner=EvidencePlanner(),
        executor=ConstrainedToolExecutor(market_tool=market, search_tool=search),
        generator=generator or FakeGenerator(),  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "question", "operation", "kind"),
    [
        (
            classification(IntentKind.SINGLE_STOCK, instrument="贵州茅台"),
            "分析贵州茅台走势",
            MarketOperation.STOCK_HISTORY,
            AnswerKind.RESEARCH,
        ),
        (
            classification(IntentKind.BROAD_INDEX, instrument="沪深300"),
            "分析沪深300走势",
            MarketOperation.INDEX_HISTORY,
            AnswerKind.RESEARCH,
        ),
        (
            classification(IntentKind.MIXED, instrument="贵州茅台"),
            "解释趋势并分析贵州茅台",
            MarketOperation.STOCK_HISTORY,
            AnswerKind.MIXED,
        ),
    ],
)
async def test_all_research_routes_select_expected_tool(
    route: IntentClassification,
    question: str,
    operation: MarketOperation,
    kind: AnswerKind,
) -> None:
    market = FakeMarket()
    result = await orchestrator(route, market=market).run(ChatRequest(question=question))
    assert result.status is OrchestrationStatus.ANSWERED
    assert result.answer is not None and result.answer.kind is kind
    assert market.operations == [operation]


@pytest.mark.asyncio
async def test_stable_knowledge_route_uses_no_tools() -> None:
    market = FakeMarket()
    search = FakeSearch()
    result = await orchestrator(
        classification(IntentKind.STABLE_KNOWLEDGE), market=market, search=search
    ).run(ChatRequest(question="什么是市盈率？"))
    assert result.answer is not None and result.answer.kind is AnswerKind.KNOWLEDGE
    assert market.operations == [] and search.requests == []


@pytest.mark.asyncio
async def test_current_question_uses_search_grounding_with_market_evidence() -> None:
    market = FakeMarket()
    search = FakeSearch(
        [search_result("web:announcement", "https://example.com/notice", "latest notice")]
    )
    result = await orchestrator(
        classification(
            IntentKind.SINGLE_STOCK,
            instrument="贵州茅台",
            current=True,
        ),
        market=market,
        search=search,
    ).run(ChatRequest(question="贵州茅台最近有什么公告？"))

    assert result.status is OrchestrationStatus.ANSWERED
    assert result.answer is not None
    assert [citation.id for citation in result.answer.citations] == ["web:announcement"]
    assert len(search.requests) == 1


@pytest.mark.asyncio
async def test_follow_up_resolution_and_explicit_override() -> None:
    result = await orchestrator(
        classification(IntentKind.SINGLE_STOCK, instrument="平安银行"), market=FakeMarket()
    ).run(
        ChatRequest(
            question="改看平安银行的估值",
            messages=[ChatMessage(role=ChatRole.USER, content="之前分析贵州茅台")],
        )
    )
    assert result.entity is not None and result.entity.instrument is not None
    assert result.entity.instrument.name == "平安银行"


@pytest.mark.asyncio
async def test_pronoun_follow_up_resolves_from_current_page_context() -> None:
    result = await orchestrator(classification(IntentKind.SINGLE_STOCK), market=FakeMarket()).run(
        ChatRequest(
            question="它的估值呢？",
            messages=[
                ChatMessage(role=ChatRole.USER, content="分析贵州茅台近期走势"),
                ChatMessage(role=ChatRole.ASSISTANT, content="贵州茅台走势分析摘要"),
            ],
        )
    )
    assert result.status is OrchestrationStatus.ANSWERED
    assert result.entity is not None and result.entity.instrument is not None
    assert result.entity.instrument.name == "贵州茅台"


@pytest.mark.asyncio
async def test_partial_failure_and_conflicting_search_sources_are_preserved() -> None:
    market = FakeMarket(failed={MarketDataCategory.VALUATION})
    search = FakeSearch(
        [
            search_result("web:one", "https://one.example/a", "source one says A"),
            search_result("web:two", "https://two.example/a", "source two says B"),
        ]
    )
    result = await orchestrator(
        classification(
            IntentKind.SINGLE_STOCK,
            instrument="贵州茅台",
            categories=[MarketDataCategory.PRICE, MarketDataCategory.VALUATION],
            current=True,
        ),
        market=market,
        search=search,
    ).run(ChatRequest(question="贵州茅台最新走势和估值"))
    assert result.status is OrchestrationStatus.ANSWERED
    assert result.answer is not None
    assert len(result.answer.citations) == 2
    assert result.answer.limitations


@pytest.mark.asyncio
async def test_unsupported_scope_is_refused_before_tools() -> None:
    market = FakeMarket()
    result = await orchestrator(
        classification(IntentKind.OUT_OF_SCOPE, comparison=True), market=market
    ).run(ChatRequest(question="比较贵州茅台和五粮液"))
    assert result.status is OrchestrationStatus.REFUSED
    assert result.error_code is ErrorCode.UNSUPPORTED_SCOPE
    assert market.operations == []


@pytest.mark.asyncio
async def test_ambiguous_instrument_requests_clarification() -> None:
    result = await orchestrator(
        classification(IntentKind.SINGLE_STOCK, instrument="000001"), market=FakeMarket()
    ).run(ChatRequest(question="分析000001"))
    assert result.status is OrchestrationStatus.CLARIFICATION_REQUIRED
    assert result.error_code is ErrorCode.AMBIGUOUS_INSTRUMENT


@pytest.mark.asyncio
async def test_no_evidence_refuses_generation() -> None:
    result = await orchestrator(
        classification(IntentKind.SINGLE_STOCK, instrument="贵州茅台"),
        market=FakeMarket(failed={MarketDataCategory.PRICE}),
    ).run(ChatRequest(question="分析贵州茅台走势"))
    assert result.status is OrchestrationStatus.FAILED
    assert result.error_code is ErrorCode.MARKET_DATA_UNAVAILABLE
    assert result.answer is None


@pytest.mark.asyncio
async def test_search_failure_preserves_market_answer_with_explicit_limitation() -> None:
    result = await orchestrator(
        classification(
            IntentKind.SINGLE_STOCK,
            instrument="贵州茅台",
            current=True,
        ),
        market=FakeMarket(),
        search=FailingSearch(),
    ).run(ChatRequest(question="贵州茅台最近有什么变化？"))

    assert result.status is OrchestrationStatus.ANSWERED
    assert result.answer is not None
    assert result.execution is not None and not result.execution.current_claim_verified
    assert any(item.code.value == "search_unverified" for item in result.answer.limitations)


@pytest.mark.asyncio
async def test_model_failure_returns_typed_terminal_outcome() -> None:
    result = await orchestrator(
        classification(IntentKind.SINGLE_STOCK, instrument="贵州茅台"),
        market=FakeMarket(),
        generator=FailingGenerator(),
    ).run(ChatRequest(question="分析贵州茅台走势"))

    assert result.status is OrchestrationStatus.FAILED
    assert result.error_code is ErrorCode.MODEL_UNAVAILABLE
    assert result.answer is None
