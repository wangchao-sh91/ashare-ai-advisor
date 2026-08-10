"""Constrained execution of explicit application-owned evidence plans."""

from __future__ import annotations

from typing import Protocol

from anyio import fail_after
from anyio.lowlevel import checkpoint
from pydantic import BaseModel, ConfigDict, Field

from app.agent.planning import EvidencePlan, MarketCallPlan
from app.domain import (
    Citation,
    ErrorCode,
    EvidenceItem,
    EvidenceKind,
    Instrument,
    Limitation,
    LimitationCode,
)
from app.providers.search_gateway import SearchRequest, SearchResult
from app.services.evidence_aggregation import (
    CategoryOutcome,
    CategoryStatus,
    aggregate_category_evidence,
)
from app.services.search_quality import rank_and_deduplicate


class MarketEvidenceTool(Protocol):
    async def execute(
        self,
        call: MarketCallPlan,
        instrument: Instrument,
    ) -> CategoryOutcome: ...


class SearchEvidenceTool(Protocol):
    async def search(self, request: SearchRequest) -> list[SearchResult]: ...


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_market_calls: int = Field(default=6, ge=0, le=6)
    max_search_calls: int = Field(default=1, ge=0, le=1)
    timeout_seconds: float = Field(default=30, gt=0, le=120)
    retries_per_call: int = Field(default=0, ge=0, le=2)
    max_evidence_chars: int = Field(default=16000, ge=1000, le=50000)


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence: list[EvidenceItem] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    limitations: list[Limitation] = Field(default_factory=list)
    category_outcomes: list[CategoryOutcome] = Field(default_factory=list)
    current_claim_verified: bool = True
    sufficient: bool
    terminal_error: ErrorCode | None = None


class ConstrainedToolExecutor:
    def __init__(
        self,
        *,
        market_tool: MarketEvidenceTool | None,
        search_tool: SearchEvidenceTool | None,
        budget: ExecutionBudget | None = None,
    ) -> None:
        self._market_tool = market_tool
        self._search_tool = search_tool
        self._budget = budget or ExecutionBudget()

    async def execute(self, plan: EvidencePlan) -> ToolExecutionResult:
        if len(plan.market_calls) > self._budget.max_market_calls:
            raise ValueError("market call budget exceeded")
        if len(plan.search_calls) > self._budget.max_search_calls:
            raise ValueError("search call budget exceeded")

        outcomes = [await self._execute_market(plan.instrument, call) for call in plan.market_calls]
        required = {call.category for call in plan.market_calls if call.required}
        aggregation = aggregate_category_evidence(outcomes, required_categories=required)
        limitations = list(aggregation.limitations)
        limitations.extend(
            Limitation(
                code=LimitationCode.UNSUPPORTED_CATEGORY,
                message="requested category is unsupported for the resolved instrument",
                affected_categories=[category.value],
                recoverable=False,
            )
            for category in plan.unsupported_categories
        )

        web_evidence: list[EvidenceItem] = []
        citations: list[Citation] = []
        search_failed = False
        for request in plan.search_calls:
            try:
                results = await self._retry_search(request)
            except Exception:
                search_failed = True
                limitations.append(
                    Limitation(
                        code=LimitationCode.SEARCH_UNVERIFIED,
                        message="current information could not be verified because search failed",
                        affected_categories=["web_search"],
                    )
                )
                continue
            ranked = rank_and_deduplicate(results)
            if not ranked:
                limitations.append(
                    Limitation(
                        code=LimitationCode.SEARCH_UNVERIFIED,
                        message="search completed but found no sufficient credible evidence",
                        affected_categories=["web_search"],
                    )
                )
            for ranked_result in ranked:
                result = ranked_result.result
                citations.append(result.citation)
                web_evidence.append(
                    EvidenceItem(
                        id=f"evidence:{result.citation.id}",
                        kind=EvidenceKind.WEB_FACT,
                        claim=result.snippet,
                        source_ids=[result.citation.id],
                        cutoff=result.citation.published_at or result.citation.retrieved_at,
                        retrieved_at=result.citation.retrieved_at,
                    )
                )

        evidence, citations, truncated = self._apply_size_limit(
            [*aggregation.evidence, *web_evidence], citations
        )
        if truncated:
            limitations.append(
                Limitation(
                    code=LimitationCode.PARTIAL_DATA,
                    message="evidence was truncated to the orchestration size budget",
                    affected_categories=["evidence_context"],
                )
            )

        current_verified = not plan.search_calls or bool(web_evidence)
        stable_knowledge = not plan.market_calls and not plan.search_calls
        sufficient = stable_knowledge or bool(evidence)
        terminal_error: ErrorCode | None = None
        if not sufficient:
            terminal_error = (
                ErrorCode.SEARCH_UNAVAILABLE
                if plan.search_calls and search_failed
                else ErrorCode.MARKET_DATA_UNAVAILABLE
            )
        return ToolExecutionResult(
            evidence=evidence,
            citations=citations,
            limitations=limitations,
            category_outcomes=outcomes,
            current_claim_verified=current_verified,
            sufficient=sufficient,
            terminal_error=terminal_error,
        )

    async def _execute_market(
        self,
        instrument: Instrument | None,
        call: MarketCallPlan,
    ) -> CategoryOutcome:
        if self._market_tool is None or instrument is None:
            return CategoryOutcome(
                category=call.category,
                status=CategoryStatus.UNAVAILABLE,
                detail="market evidence tool is unavailable",
            )
        for attempt in range(self._budget.retries_per_call + 1):
            try:
                with fail_after(self._budget.timeout_seconds):
                    return await self._market_tool.execute(call, instrument)
            except Exception:
                if attempt == self._budget.retries_per_call:
                    return CategoryOutcome(
                        category=call.category,
                        status=CategoryStatus.UNAVAILABLE,
                        detail="market data operation failed or timed out",
                    )
                await checkpoint()
        raise AssertionError("unreachable market retry state")

    async def _retry_search(self, request: SearchRequest) -> list[SearchResult]:
        if self._search_tool is None:
            raise RuntimeError("search tool unavailable")
        for attempt in range(self._budget.retries_per_call + 1):
            try:
                with fail_after(self._budget.timeout_seconds):
                    return await self._search_tool.search(request)
            except Exception:
                if attempt == self._budget.retries_per_call:
                    raise
                await checkpoint()
        raise AssertionError("unreachable search retry state")

    def _apply_size_limit(
        self,
        evidence: list[EvidenceItem],
        citations: list[Citation],
    ) -> tuple[list[EvidenceItem], list[Citation], bool]:
        remaining = self._budget.max_evidence_chars
        selected_evidence: list[EvidenceItem] = []
        selected_citations: list[Citation] = []
        truncated = False
        for item in evidence:
            size = len(item.model_dump_json())
            if size > remaining:
                truncated = True
                continue
            selected_evidence.append(item)
            remaining -= size
        selected_source_ids = {
            source_id for item in selected_evidence for source_id in item.source_ids
        }
        for citation in citations:
            if citation.id not in selected_source_ids:
                continue
            size = len(citation.model_dump_json())
            if size > remaining:
                truncated = True
                selected_evidence = [
                    item for item in selected_evidence if citation.id not in item.source_ids
                ]
                continue
            selected_citations.append(citation)
            remaining -= size
        return selected_evidence, selected_citations, truncated
