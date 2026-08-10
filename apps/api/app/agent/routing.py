"""Structured model-assisted intent routing without model-selected tools."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.chat_models import ChatMessage
from app.domain import MarketDataCategory

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class IntentKind(StrEnum):
    SINGLE_STOCK = "single_stock"
    BROAD_INDEX = "broad_index"
    STABLE_KNOWLEDGE = "stable_knowledge"
    MIXED = "mixed"
    OUT_OF_SCOPE = "out_of_scope"


class IntentClassification(BaseModel):
    """Validated routing output; it is a hint to deterministic policy, not a tool call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: IntentKind
    instrument_query: str | None = Field(default=None, max_length=100)
    requested_categories: list[MarketDataCategory] = Field(default_factory=list, max_length=6)
    time_sensitive: bool = False
    comparison_requested: bool = False
    unsupported_reason: str | None = Field(default=None, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_scope_fields(self) -> IntentClassification:
        if self.intent is IntentKind.OUT_OF_SCOPE and not self.unsupported_reason:
            raise ValueError("out-of-scope classification requires unsupported_reason")
        if self.intent is IntentKind.STABLE_KNOWLEDGE and self.requested_categories:
            raise ValueError("stable knowledge cannot request market-data categories")
        if len(self.requested_categories) != len(set(self.requested_categories)):
            raise ValueError("requested_categories must be unique")
        return self


class StructuredModelGateway(Protocol):
    async def generate_structured(
        self,
        messages: Sequence[BaseMessage],
        schema: type[StructuredT],
    ) -> StructuredT: ...


_CLASSIFIER_SYSTEM_PROMPT = """You classify one Chinese A-share research question.
Return only the requested structured schema. Choose exactly one intent:
- single_stock: research about one mainland-listed A-share
- broad_index: research about one approved broad-based mainland index
- stable_knowledge: foundational knowledge requiring no current facts
- mixed: a concept explanation plus research about one supported instrument
- out_of_scope: multiple-instrument comparisons, funds, industries/concepts, bonds,
  futures, Hong Kong/US stocks, portfolios, files, trading, or unsupported assets
Extract only a concise instrument name/code explicitly present in the current question.
Pronouns may leave instrument_query null; deterministic context resolution happens later.
Mark time_sensitive for latest/current/recent events, rules, policies, or market facts.
Requested categories may only be price, index_price, financial, valuation, ownership, pledge.
Never propose, name, or invoke tools."""


class IntentClassifier:
    def __init__(self, model: StructuredModelGateway) -> None:
        self._model = model

    async def classify(
        self,
        question: str,
        context: Sequence[ChatMessage] = (),
    ) -> IntentClassification:
        compact_context = "\n".join(
            f"{message.role.value}: {message.content}" for message in context
        )
        user_content = f"Current question:\n{question}"
        if compact_context:
            user_content += f"\n\nCurrent-page context (reference only):\n{compact_context}"
        return await self._model.generate_structured(
            [SystemMessage(content=_CLASSIFIER_SYSTEM_PROMPT), HumanMessage(content=user_content)],
            IntentClassification,
        )
