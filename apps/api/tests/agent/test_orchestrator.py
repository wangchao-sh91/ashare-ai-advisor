from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import HttpUrl

from app.agent.execution import ConstrainedToolExecutor, ToolExecutionResult
from app.agent.orchestrator import (
    ControlledOrchestrator,
    OrchestrationResult,
    OrchestrationStatus,
)
from app.agent.planning import EvidencePlanner
from app.agent.routing import IntentKind, QuestionNormalization
from app.api.chat_models import ChatRequest
from app.domain import (
    INVESTMENT_DISCLAIMER,
    AnswerKind,
    CategoryOutcome,
    CategoryStatus,
    Citation,
    EvidenceCategory,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    InsufficiencyReason,
    NormalizedMarketRecord,
    ProviderKind,
    SourceType,
    StructuredAnswer,
)
from app.providers.search_gateway import SearchRequest

NOW = datetime(2026, 8, 7, tzinfo=UTC)
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


class StubNormalizer:
    def __init__(self, result: QuestionNormalization) -> None:
        self.result = result
        self.calls = 0

    async def normalize(self, question: str, context: object) -> QuestionNormalization:
        del question, context
        self.calls += 1
        return self.result


class StubProvider:
    def __init__(self, outcomes: dict[EvidenceCategory, CategoryOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[EvidenceCategory] = []

    async def outcome(
        self, request: SearchRequest | None = None, **kwargs: object
    ) -> CategoryOutcome:
        del kwargs
        category = request.category if request is not None else EvidenceCategory.PRICE_DAILY
        self.calls.append(category)
        return self.outcomes[category]


class StubGenerator:
    async def generate(
        self,
        question: str,
        normalization: QuestionNormalization,
        execution: ToolExecutionResult,
    ) -> StructuredAnswer:
        del question
        kind = (
            AnswerKind.KNOWLEDGE
            if normalization.intent is IntentKind.STABLE_KNOWLEDGE
            else AnswerKind.MIXED
            if normalization.intent is IntentKind.MIXED
            else AnswerKind.RESEARCH
        )
        return StructuredAnswer(
            kind=kind,
            summary="基于已验证证据形成结论。",
            facts=execution.evidence,
            analysis=["仅解释已验证事实，不补充未经证实的数据。"],
            risks=[] if kind is AnswerKind.KNOWLEDGE else ["市场存在不确定性。"],
            citations=execution.citations,
            answered_at=NOW,
            disclaimer=INVESTMENT_DISCLAIMER,
            limitations=execution.limitations,
        )


def success(category: EvidenceCategory, provider: ProviderKind) -> CategoryOutcome:
    citation = None
    if provider is ProviderKind.DOUBAO_SEARCH:
        citation = Citation(
            id=f"web:{category.value}",
            source_type=SourceType.WEB,
            title="权威资料",
            supported_claim="公开事实",
            category=category,
            url=HttpUrl(f"https://example.com/{category.value}"),
            published_at=(
                datetime(2026, 8, 1, 10, tzinfo=UTC)
                if category is EvidenceCategory.CORPORATE_EVENT
                else None
            ),
            retrieved_at=NOW,
        )
    evidence = EvidenceItem(
        id=f"evidence:{category.value}",
        kind=(
            EvidenceKind.MARKET_FACT if provider is ProviderKind.TUSHARE else EvidenceKind.WEB_FACT
        ),
        category=category,
        claim=f"{category.value} fact",
        instrument=STOCK if category is not EvidenceCategory.INDEX_CONTEXT else INDEX,
        source_ids=[citation.id if citation else "daily:1"],
        retrieved_at=NOW,
    )
    records = []
    if provider is ProviderKind.TUSHARE:
        trading_dates = [
            date(2026, 8, 1),
            date(2026, 8, 2),
            date(2026, 8, 3),
            date(2026, 8, 4),
            date(2026, 8, 5),
            date(2026, 8, 6),
            date(2026, 8, 7),
        ]
        records = [
            NormalizedMarketRecord(
                id=f"daily:{observed.isoformat()}",
                instrument=STOCK,
                observed_at=observed,
                values={"close": Decimal(100 + index), "volume": 1000 + index * 10},
                units={"close": "CNY", "volume": "shares"},
                cutoff=NOW,
                retrieved_at=NOW,
            )
            for index, observed in enumerate(trading_dates)
        ]
    return CategoryOutcome(
        category=category,
        provider=provider,
        status=CategoryStatus.SUFFICIENT,
        evidence=[evidence],
        citations=[citation] if citation else [],
        records=records,
    )


def failure(category: EvidenceCategory, provider: ProviderKind) -> CategoryOutcome:
    return CategoryOutcome(
        category=category,
        provider=provider,
        status=CategoryStatus.UNAVAILABLE,
        reason=InsufficiencyReason.PROVIDER_UNAVAILABLE,
        detail=f"{category.value} unavailable",
    )


def normalization(
    categories: list[EvidenceCategory],
    *,
    instrument: Instrument = STOCK,
    intent: IntentKind = IntentKind.SINGLE_STOCK,
) -> QuestionNormalization:
    return QuestionNormalization(
        rewritten_question="规范后的研究问题",
        intent=intent,
        instrument=instrument,
        requested_categories=categories,
        analysis_start=date(2026, 8, 1),
        analysis_end=date(2026, 8, 7),
        time_sensitive=any(item is not EvidenceCategory.PRICE_DAILY for item in categories),
        rationale="test",
    )


async def run(
    normalized: QuestionNormalization,
    price_outcome: CategoryOutcome | None,
    search_outcomes: dict[EvidenceCategory, CategoryOutcome],
) -> tuple[OrchestrationResult, StubProvider, StubProvider]:
    price = StubProvider(
        {EvidenceCategory.PRICE_DAILY: price_outcome} if price_outcome is not None else {}
    )
    search = StubProvider(search_outcomes)
    orchestrator = ControlledOrchestrator(
        normalizer=StubNormalizer(normalized),  # type: ignore[arg-type]
        planner=EvidencePlanner(today=date(2026, 8, 10)),
        executor=ConstrainedToolExecutor(
            price_provider=price if price_outcome is not None else None,
            search_provider=search if search_outcomes else None,
        ),
        generator=StubGenerator(),  # type: ignore[arg-type]
    )
    result = await orchestrator.run(ChatRequest(question="原始问题"))
    return result, price, search


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("categories", "price_ok", "search_ok", "answered", "complete"),
    [
        ([EvidenceCategory.PRICE_DAILY], True, [], True, True),
        (
            [EvidenceCategory.PRICE_DAILY, EvidenceCategory.VALUATION],
            True,
            [EvidenceCategory.VALUATION],
            True,
            True,
        ),
        ([EvidenceCategory.PRICE_DAILY, EvidenceCategory.VALUATION], True, [], True, False),
        (
            [EvidenceCategory.PRICE_DAILY, EvidenceCategory.VALUATION],
            False,
            [EvidenceCategory.VALUATION],
            True,
            False,
        ),
        ([EvidenceCategory.PRICE_DAILY, EvidenceCategory.VALUATION], False, [], False, False),
    ],
)
async def test_price_partial_and_all_failure_flows(
    categories: list[EvidenceCategory],
    price_ok: bool,
    search_ok: list[EvidenceCategory],
    answered: bool,
    complete: bool,
) -> None:
    price_result = (
        success(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE)
        if price_ok
        else failure(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE)
    )
    searches: dict[EvidenceCategory, CategoryOutcome] = {
        category: (
            success(category, ProviderKind.DOUBAO_SEARCH)
            if category in search_ok
            else failure(category, ProviderKind.DOUBAO_SEARCH)
        )
        for category in categories
        if category is not EvidenceCategory.PRICE_DAILY
    }
    result, _, _ = await run(normalization(categories), price_result, searches)
    assert (result.status is OrchestrationStatus.ANSWERED) is answered
    if result.execution:
        assert result.execution.complete is complete


@pytest.mark.asyncio
async def test_search_only_index_and_mixed_knowledge_route() -> None:
    index_norm = normalization(
        [EvidenceCategory.INDEX_CONTEXT],
        instrument=INDEX,
        intent=IntentKind.BROAD_INDEX,
    )
    result, price, search = await run(
        index_norm,
        None,
        {
            EvidenceCategory.INDEX_CONTEXT: success(
                EvidenceCategory.INDEX_CONTEXT, ProviderKind.DOUBAO_SEARCH
            )
        },
    )
    assert result.status is OrchestrationStatus.ANSWERED
    assert price.calls == []
    assert search.calls == [EvidenceCategory.INDEX_CONTEXT]

    mixed = normalization(
        [EvidenceCategory.PRICE_DAILY],
        intent=IntentKind.MIXED,
    )
    mixed_result, _, _ = await run(
        mixed,
        success(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE),
        {},
    )
    assert mixed_result.answer and mixed_result.answer.kind is AnswerKind.MIXED


@pytest.mark.asyncio
async def test_search_quota_failure_preserves_price_as_partial_answer() -> None:
    quota = CategoryOutcome(
        category=EvidenceCategory.CORPORATE_EVENT,
        provider=ProviderKind.DOUBAO_SEARCH,
        status=CategoryStatus.UNAVAILABLE,
        reason=InsufficiencyReason.QUOTA_EXHAUSTED,
        detail="search quota unavailable",
    )
    result, _, _ = await run(
        normalization([EvidenceCategory.PRICE_DAILY, EvidenceCategory.CORPORATE_EVENT]),
        success(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE),
        {EvidenceCategory.CORPORATE_EVENT: quota},
    )
    assert result.status is OrchestrationStatus.ANSWERED
    assert result.execution and not result.execution.complete
    assert result.answer and result.answer.limitations[0].code.value == "quota_exhausted"


@pytest.mark.asyncio
async def test_combined_daily_and_event_success_adds_deterministic_windows() -> None:
    result, _, _ = await run(
        normalization([EvidenceCategory.PRICE_DAILY, EvidenceCategory.CORPORATE_EVENT]),
        success(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE),
        {
            EvidenceCategory.CORPORATE_EVENT: success(
                EvidenceCategory.CORPORATE_EVENT,
                ProviderKind.DOUBAO_SEARCH,
            )
        },
    )
    assert result.status is OrchestrationStatus.ANSWERED
    assert result.execution
    windows = [
        item for item in result.execution.evidence if item.id.startswith("metric:event_window")
    ]
    assert [item.period_end for item in windows] == [
        date(2026, 8, 2),
        date(2026, 8, 4),
        date(2026, 8, 6),
    ]


@pytest.mark.asyncio
async def test_clarification_stops_before_providers() -> None:
    normalized = QuestionNormalization(
        rewritten_question="分析000001",
        intent=IntentKind.SINGLE_STOCK,
        clarification_required=True,
        clarification_question="请明确股票或指数。",
        rationale="ambiguous",
    )
    result, price, search = await run(normalized, None, {})
    assert result.status is OrchestrationStatus.CLARIFICATION_REQUIRED
    assert price.calls == [] and search.calls == []
