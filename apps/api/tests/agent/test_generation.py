from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TypeVar, cast

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.agent.execution import ToolExecutionResult
from app.agent.generation import AnswerDraft, AnswerGenerationError, AnswerGenerator
from app.agent.routing import IntentKind, QuestionNormalization
from app.domain import EvidenceCategory, EvidenceItem, EvidenceKind

StructuredT = TypeVar("StructuredT", bound=BaseModel)

NOW = datetime(2026, 8, 7, tzinfo=UTC)
FACT = EvidenceItem(
    id="fact:1",
    kind=EvidenceKind.MARKET_FACT,
    category=EvidenceCategory.PRICE_DAILY,
    claim="validated close",
    source_ids=["daily:1"],
    retrieved_at=NOW,
)
NORMALIZATION = QuestionNormalization(
    rewritten_question="分析股票价格",
    intent=IntentKind.SINGLE_STOCK,
    clarification_required=True,
    clarification_question="test-only",
    rationale="test",
)


class FakeModel:
    def __init__(self, draft: AnswerDraft) -> None:
        self.draft = draft
        self.messages: Sequence[BaseMessage] = []

    async def generate_structured(
        self, messages: Sequence[BaseMessage], schema: type[StructuredT]
    ) -> StructuredT:
        self.messages = messages
        assert schema is AnswerDraft
        return cast(StructuredT, self.draft)


@pytest.mark.asyncio
async def test_generator_maps_only_allowlisted_evidence() -> None:
    model = FakeModel(AnswerDraft(summary="summary", fact_ids=[FACT.id]))
    answer = await AnswerGenerator(model).generate(
        "question",
        NORMALIZATION,
        ToolExecutionResult(evidence=[FACT], sufficient=True, complete=True),
    )
    assert answer.facts == [FACT]
    assert "UNTRUSTED_WEB_EVIDENCE" in model.messages[1].content


@pytest.mark.asyncio
async def test_generator_rejects_invented_evidence_ids() -> None:
    model = FakeModel(AnswerDraft(summary="summary", fact_ids=["invented"]))
    with pytest.raises(AnswerGenerationError):
        await AnswerGenerator(model).generate(
            "question",
            NORMALIZATION,
            ToolExecutionResult(evidence=[FACT], sufficient=True, complete=True),
        )
