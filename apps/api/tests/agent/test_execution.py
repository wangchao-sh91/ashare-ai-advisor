from datetime import UTC, date, datetime

import pytest
from pydantic import HttpUrl

from app.agent.execution import ConstrainedToolExecutor, ExecutionBudget
from app.agent.planning import EvidencePlan
from app.agent.routing import IntentKind
from app.domain import (
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
    LimitationCode,
    ProviderKind,
    ProviderPlan,
    SourceType,
)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)


def evidence(category: EvidenceCategory, kind: EvidenceKind, source: str) -> EvidenceItem:
    return EvidenceItem(
        id=f"evidence:{category.value}",
        kind=kind,
        category=category,
        claim=f"{category.value} fact",
        instrument=STOCK,
        source_ids=[source],
        retrieved_at=NOW,
    )


def citation(category: EvidenceCategory) -> Citation:
    return Citation(
        id=f"web:{category.value}",
        source_type=SourceType.WEB,
        title="公开资料",
        supported_claim="经过核验的事实",
        category=category,
        url=HttpUrl("https://example.com/fact"),
        retrieved_at=NOW,
    )


class FakePrice:
    def __init__(self, outcome: CategoryOutcome) -> None:
        self.result = outcome
        self.calls = 0

    async def outcome(self, **kwargs: object) -> CategoryOutcome:
        del kwargs
        self.calls += 1
        return self.result


class FakeSearch:
    def __init__(self, outcomes: dict[EvidenceCategory, CategoryOutcome]) -> None:
        self.outcomes = outcomes
        self.categories: list[EvidenceCategory] = []

    async def outcome(self, request: object) -> CategoryOutcome:
        category = request.category  # type: ignore[attr-defined]
        self.categories.append(category)
        return self.outcomes[category]


def successful(category: EvidenceCategory, provider: ProviderKind) -> CategoryOutcome:
    if provider is ProviderKind.TUSHARE:
        return CategoryOutcome(
            category=category,
            provider=provider,
            status=CategoryStatus.SUFFICIENT,
            evidence=[evidence(category, EvidenceKind.MARKET_FACT, "daily:1")],
        )
    web_citation = citation(category)
    return CategoryOutcome(
        category=category,
        provider=provider,
        status=CategoryStatus.SUFFICIENT,
        evidence=[evidence(category, EvidenceKind.WEB_FACT, web_citation.id)],
        citations=[web_citation],
    )


def failed(category: EvidenceCategory, provider: ProviderKind) -> CategoryOutcome:
    return CategoryOutcome(
        category=category,
        provider=provider,
        status=CategoryStatus.UNAVAILABLE,
        reason=InsufficiencyReason.PROVIDER_UNAVAILABLE,
        detail=f"{category.value} unavailable",
    )


def plan(*calls: ProviderPlan) -> EvidencePlan:
    return EvidencePlan(intent=IntentKind.SINGLE_STOCK, instrument=STOCK, calls=list(calls))


def call(category: EvidenceCategory, provider: ProviderKind) -> ProviderPlan:
    return ProviderPlan(
        category=category,
        provider=provider,
        instrument=STOCK,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 7),
        query="贵州茅台 600519.SH 资料" if provider is ProviderKind.DOUBAO_SEARCH else None,
    )


@pytest.mark.asyncio
async def test_partial_failure_preserves_independent_category_evidence() -> None:
    price = successful(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE)
    search_failure = failed(EvidenceCategory.VALUATION, ProviderKind.DOUBAO_SEARCH)
    result = await ConstrainedToolExecutor(
        price_provider=FakePrice(price),
        search_provider=FakeSearch({EvidenceCategory.VALUATION: search_failure}),
    ).execute(
        plan(
            call(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE),
            call(EvidenceCategory.VALUATION, ProviderKind.DOUBAO_SEARCH),
        )
    )
    assert result.sufficient and not result.complete
    assert [item.category for item in result.evidence] == [EvidenceCategory.PRICE_DAILY]
    assert result.limitations[0].affected_categories == ["valuation"]


@pytest.mark.asyncio
async def test_price_cannot_be_satisfied_by_web_or_mismatched_category() -> None:
    web_price = successful(EvidenceCategory.PRICE_DAILY, ProviderKind.DOUBAO_SEARCH)
    wrong = FakePrice(web_price)
    result = await ConstrainedToolExecutor(price_provider=wrong, search_provider=None).execute(
        plan(call(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE))
    )
    assert not result.sufficient
    assert result.category_outcomes[0].reason is InsufficiencyReason.CATEGORY_MISMATCH


@pytest.mark.asyncio
async def test_all_failures_stop_generation_and_quota_is_visible() -> None:
    quota = CategoryOutcome(
        category=EvidenceCategory.CORPORATE_EVENT,
        provider=ProviderKind.DOUBAO_SEARCH,
        status=CategoryStatus.UNAVAILABLE,
        reason=InsufficiencyReason.QUOTA_EXHAUSTED,
        detail="quota unavailable",
    )
    result = await ConstrainedToolExecutor(
        price_provider=FakePrice(failed(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE)),
        search_provider=FakeSearch({EvidenceCategory.CORPORATE_EVENT: quota}),
    ).execute(
        plan(
            call(EvidenceCategory.PRICE_DAILY, ProviderKind.TUSHARE),
            call(EvidenceCategory.CORPORATE_EVENT, ProviderKind.DOUBAO_SEARCH),
        )
    )
    assert not result.sufficient
    assert any(item.code is LimitationCode.QUOTA_EXHAUSTED for item in result.limitations)


@pytest.mark.asyncio
async def test_search_success_never_converts_to_market_fact() -> None:
    outcome = successful(EvidenceCategory.VALUATION, ProviderKind.DOUBAO_SEARCH)
    result = await ConstrainedToolExecutor(
        price_provider=None,
        search_provider=FakeSearch({EvidenceCategory.VALUATION: outcome}),
    ).execute(plan(call(EvidenceCategory.VALUATION, ProviderKind.DOUBAO_SEARCH)))
    assert result.complete
    assert all(item.kind is EvidenceKind.WEB_FACT for item in result.evidence)


@pytest.mark.asyncio
async def test_context_budget_keeps_web_evidence_and_its_citation_together() -> None:
    categories = [EvidenceCategory.FINANCIAL, EvidenceCategory.VALUATION]
    outcomes: dict[EvidenceCategory, CategoryOutcome] = {}
    for category in categories:
        web_citation = citation(category).model_copy(
            update={"supported_claim": "引用" * 250, "snippet": "摘要" * 450}
        )
        outcomes[category] = CategoryOutcome(
            category=category,
            provider=ProviderKind.DOUBAO_SEARCH,
            status=CategoryStatus.SUFFICIENT,
            evidence=[
                evidence(category, EvidenceKind.WEB_FACT, web_citation.id).model_copy(
                    update={"claim": "事实" * 450}
                )
            ],
            citations=[web_citation],
        )

    result = await ConstrainedToolExecutor(
        price_provider=None,
        search_provider=FakeSearch(outcomes),
        budget=ExecutionBudget(max_evidence_chars=5000),
    ).execute(plan(*(call(category, ProviderKind.DOUBAO_SEARCH) for category in categories)))

    assert result.evidence
    citation_ids = {item.id for item in result.citations}
    assert {
        source_id
        for item in result.evidence
        for source_id in item.source_ids
        if source_id.startswith("web:")
    } <= citation_ids
    assert not result.complete
