"""Independent bounded execution and category-level evidence sufficiency."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.agent.planning import MAX_PROVIDER_CALLS, EvidencePlan
from app.domain import (
    CategoryOutcome,
    CategoryStatus,
    Citation,
    ErrorCode,
    EvidenceCategory,
    EvidenceItem,
    EvidenceKind,
    Instrument,
    InsufficiencyReason,
    Limitation,
    LimitationCode,
    ProviderKind,
    ProviderPlan,
    SourceType,
)
from app.providers.search_gateway import SearchRequest
from app.services.event_timeline import event_window_evidence


class PriceEvidenceProvider(Protocol):
    async def outcome(
        self, *, instrument: Instrument, start_date: date, end_date: date
    ) -> CategoryOutcome: ...


class SearchEvidenceProvider(Protocol):
    async def outcome(self, request: SearchRequest) -> CategoryOutcome: ...


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_provider_calls: int = Field(default=MAX_PROVIDER_CALLS, ge=0, le=MAX_PROVIDER_CALLS)
    max_evidence_chars: int = Field(default=16000, ge=1000, le=50000)


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    category_outcomes: list[CategoryOutcome] = Field(default_factory=list)
    required_categories: list[EvidenceCategory] = Field(default_factory=list)
    current_claim_verified: bool = True
    sufficient: bool
    complete: bool
    terminal_error: ErrorCode | None = None


class ConstrainedToolExecutor:
    def __init__(
        self,
        *,
        price_provider: PriceEvidenceProvider | None,
        search_provider: SearchEvidenceProvider | None,
        budget: ExecutionBudget | None = None,
    ) -> None:
        self._price = price_provider
        self._search = search_provider
        self._budget = budget or ExecutionBudget()

    async def execute(self, plan: EvidencePlan) -> ToolExecutionResult:
        if len(plan.calls) > self._budget.max_provider_calls:
            raise ValueError("provider call budget exceeded")
        if not plan.calls:
            return ToolExecutionResult(sufficient=True, complete=True)

        outcomes = list(await asyncio.gather(*(self._execute(call) for call in plan.calls)))
        outcomes = [
            self._enforce_boundary(call, outcome)
            for call, outcome in zip(plan.calls, outcomes, strict=True)
        ]
        outcomes = self._add_event_windows(plan, outcomes)
        required = [call.category for call in plan.calls if call.required]
        sufficient_categories = {
            outcome.category for outcome in outcomes if outcome.status is CategoryStatus.SUFFICIENT
        }
        complete = set(required) <= sufficient_categories
        sufficient = bool(sufficient_categories)
        limitations = [
            _limitation(outcome)
            for outcome in outcomes
            if outcome.status is not CategoryStatus.SUFFICIENT
        ]
        evidence = [item for outcome in outcomes for item in outcome.evidence]
        citations = [item for outcome in outcomes for item in outcome.citations]
        evidence, citations, truncated = self._apply_size_limit(evidence, citations)
        if truncated:
            complete = False
        if truncated:
            limitations.append(
                Limitation(
                    code=LimitationCode.PARTIAL_DATA,
                    message="证据超过单次编排大小限制，已保留可验证子集。",
                    affected_categories=["evidence_context"],
                )
            )
        search_required = any(call.provider is ProviderKind.DOUBAO_SEARCH for call in plan.calls)
        search_sufficient = any(item.source_type is SourceType.WEB for item in citations)
        terminal_error = None
        if not sufficient:
            terminal_error = (
                ErrorCode.SEARCH_UNAVAILABLE
                if search_required
                and all(call.provider is ProviderKind.DOUBAO_SEARCH for call in plan.calls)
                else ErrorCode.MARKET_DATA_UNAVAILABLE
            )
        return ToolExecutionResult(
            evidence=evidence,
            citations=citations,
            limitations=limitations,
            category_outcomes=outcomes,
            required_categories=required,
            current_claim_verified=not search_required or search_sufficient,
            sufficient=sufficient,
            complete=complete,
            terminal_error=terminal_error,
        )

    @staticmethod
    def _add_event_windows(
        plan: EvidencePlan,
        outcomes: list[CategoryOutcome],
    ) -> list[CategoryOutcome]:
        if plan.instrument is None:
            return outcomes
        price = next(
            (item for item in outcomes if item.category is EvidenceCategory.PRICE_DAILY),
            None,
        )
        event = next(
            (item for item in outcomes if item.category is EvidenceCategory.CORPORATE_EVENT),
            None,
        )
        if (
            price is None
            or event is None
            or price.status is not CategoryStatus.SUFFICIENT
            or event.status is not CategoryStatus.SUFFICIENT
            or not price.records
        ):
            return outcomes
        computed = event_window_evidence(
            event.citations,
            price.records,
            instrument=plan.instrument,
        )
        return [
            item.model_copy(update={"evidence": [*item.evidence, *computed]})
            if item is event
            else item
            for item in outcomes
        ]

    async def _execute(self, call: ProviderPlan) -> CategoryOutcome:
        if call.provider is ProviderKind.TUSHARE:
            if (
                self._price is None
                or call.instrument is None
                or not call.start_date
                or not call.end_date
            ):
                return _unavailable(call)
            return await self._price.outcome(
                instrument=call.instrument,
                start_date=call.start_date,
                end_date=call.end_date,
            )
        if self._search is None or call.query is None:
            return _unavailable(call)
        return await self._search.outcome(
            SearchRequest(
                query=call.query,
                category=call.category,
                instrument=call.instrument,
                result_limit=call.result_limit,
                start_date=call.start_date,
                end_date=call.end_date,
            )
        )

    @staticmethod
    def _enforce_boundary(call: ProviderPlan, outcome: CategoryOutcome) -> CategoryOutcome:
        mismatch = outcome.category is not call.category or outcome.provider is not call.provider
        invalid_price = call.category is EvidenceCategory.PRICE_DAILY and (
            outcome.provider is not ProviderKind.TUSHARE
            or any(item.kind is EvidenceKind.WEB_FACT for item in outcome.evidence)
        )
        invalid_market = any(
            item.kind is EvidenceKind.MARKET_FACT
            and item.category is not EvidenceCategory.PRICE_DAILY
            for item in outcome.evidence
        )
        category_mismatch = any(
            item.category not in {None, call.category} for item in outcome.evidence
        ) or any(item.category not in {None, call.category} for item in outcome.citations)
        if mismatch or invalid_price or invalid_market or category_mismatch:
            return CategoryOutcome(
                category=call.category,
                provider=call.provider,
                status=CategoryStatus.INVALID,
                reason=InsufficiencyReason.CATEGORY_MISMATCH,
                detail="提供方证据未通过类别和来源边界校验。",
            )
        return outcome

    def _apply_size_limit(
        self,
        evidence: list[EvidenceItem],
        citations: list[Citation],
    ) -> tuple[list[EvidenceItem], list[Citation], bool]:
        remaining = self._budget.max_evidence_chars
        selected: list[EvidenceItem] = []
        citation_by_id = {item.id: item for item in citations}
        selected_citations: list[Citation] = []
        selected_citation_ids: set[str] = set()
        truncated = False
        for item in evidence:
            needed_citations = [
                citation_by_id[identifier]
                for identifier in item.source_ids
                if identifier in citation_by_id and identifier not in selected_citation_ids
            ]
            size = len(item.model_dump_json()) + sum(
                len(citation.model_dump_json()) for citation in needed_citations
            )
            if size > remaining:
                truncated = True
                continue
            selected.append(item)
            selected_citations.extend(needed_citations)
            selected_citation_ids.update(citation.id for citation in needed_citations)
            remaining -= size
        return selected, selected_citations, truncated


def _unavailable(call: ProviderPlan) -> CategoryOutcome:
    return CategoryOutcome(
        category=call.category,
        provider=call.provider,
        status=CategoryStatus.UNAVAILABLE,
        reason=InsufficiencyReason.PROVIDER_UNAVAILABLE,
        detail="该证据类别的提供方当前不可用。",
    )


def _limitation(outcome: CategoryOutcome) -> Limitation:
    code = (
        LimitationCode.QUOTA_EXHAUSTED
        if outcome.reason is InsufficiencyReason.QUOTA_EXHAUSTED
        else LimitationCode.SEARCH_UNVERIFIED
        if outcome.provider is ProviderKind.DOUBAO_SEARCH
        else LimitationCode.DATA_UNAVAILABLE
    )
    return Limitation(
        code=code,
        message=outcome.detail or "该证据类别不足。",
        affected_categories=[outcome.category.value],
        recoverable=outcome.reason is not InsufficiencyReason.UNSUPPORTED,
    )
