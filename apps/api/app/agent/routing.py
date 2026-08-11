"""One-call structured question normalization without model-selected tools."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from typing import Protocol, Self, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.chat_models import ChatMessage
from app.domain import EvidenceCategory, Instrument, InstrumentType
from app.providers.model_gateway import ModelErrorCode, ModelGatewayError

StructuredT = TypeVar("StructuredT", bound=BaseModel)


class IntentKind(StrEnum):
    SINGLE_STOCK = "single_stock"
    BROAD_INDEX = "broad_index"
    STABLE_KNOWLEDGE = "stable_knowledge"
    MIXED = "mixed"
    OUT_OF_SCOPE = "out_of_scope"


class QuestionNormalization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rewritten_question: str = Field(min_length=1, max_length=500)
    intent: IntentKind
    instrument: Instrument | None = None
    requested_categories: list[EvidenceCategory] = Field(default_factory=list, max_length=7)
    analysis_start: date | None = None
    analysis_end: date | None = None
    time_sensitive: bool = False
    clarification_required: bool = False
    clarification_question: str | None = Field(default=None, max_length=500)
    comparison_requested: bool = False
    unsupported_reason: str | None = Field(default=None, max_length=300)
    rationale: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_contract(self) -> Self:
        categories = self.requested_categories
        if len(categories) != len(set(categories)):
            raise ValueError("requested_categories must be unique")
        if self.analysis_start and self.analysis_end and self.analysis_start > self.analysis_end:
            raise ValueError("analysis_start must not be after analysis_end")
        research = self.intent in {
            IntentKind.SINGLE_STOCK,
            IntentKind.BROAD_INDEX,
            IntentKind.MIXED,
        }
        if research and self.instrument is None and not self.clarification_required:
            raise ValueError("research intent requires a canonical instrument or clarification")
        if self.clarification_required and not self.clarification_question:
            raise ValueError("clarification requires a question")
        if self.intent is IntentKind.STABLE_KNOWLEDGE and (self.instrument or categories):
            raise ValueError("stable knowledge cannot require instrument evidence")
        if self.intent is IntentKind.OUT_OF_SCOPE and not self.unsupported_reason:
            raise ValueError("out-of-scope normalization requires unsupported_reason")
        if self.instrument:
            if self.instrument.instrument_type is InstrumentType.BROAD_INDEX and any(
                category is not EvidenceCategory.INDEX_CONTEXT for category in categories
            ):
                raise ValueError("broad indexes are search-only")
            if self.instrument.instrument_type is InstrumentType.STOCK and (
                EvidenceCategory.INDEX_CONTEXT in categories
            ):
                raise ValueError("stock request cannot use index context category")
        return self

    @property
    def instrument_query(self) -> str | None:
        return self.instrument.name if self.instrument else None


IntentClassification = QuestionNormalization


class StructuredModelGateway(Protocol):
    async def generate_structured(
        self,
        messages: Sequence[BaseMessage],
        schema: type[StructuredT],
    ) -> StructuredT: ...


_NORMALIZER_SYSTEM_PROMPT = """Normalize one Chinese finance question into the exact schema.
Rewrite it as a self-contained request using only bounded current-page context. Return a canonical
instrument name, six-digit code, exchange, type, and therefore an unambiguous Tushare ts_code for
one A-share stock. Supported broad indexes are search-only. Evidence categories are price_daily,
financial, valuation, ownership, pledge, corporate_event, and index_context. A request combining
daily prices with news or announcements must include price_daily and corporate_event with one
shared analysis period. Stable knowledge uses no provider category. Multiple instruments and
unsupported assets are out_of_scope. If identity is ambiguous or name/code/context conflict,
request clarification and do not guess. Never name providers, URLs, SDK methods, or tools."""


class QuestionNormalizer:
    def __init__(self, model: StructuredModelGateway) -> None:
        self._model = model

    async def normalize(
        self,
        question: str,
        context: Sequence[ChatMessage] = (),
    ) -> QuestionNormalization:
        compact_context = "\n".join(
            f"{message.role.value}: {message.content}" for message in context[-8:]
        )
        content = f"Current question:\n{question}"
        if compact_context:
            content += f"\n\nCurrent-page context:\n{compact_context}"
        try:
            return await self._model.generate_structured(
                [SystemMessage(content=_NORMALIZER_SYSTEM_PROMPT), HumanMessage(content=content)],
                QuestionNormalization,
            )
        except ModelGatewayError as exc:
            if exc.code is not ModelErrorCode.INVALID_STRUCTURED_OUTPUT:
                raise
            return QuestionNormalization(
                rewritten_question=question,
                intent=IntentKind.SINGLE_STOCK,
                clarification_required=True,
                clarification_question="问题解析结果不完整，请明确一个股票名称和代码及分析需求。",
                rationale="结构化解析失败，未调用任何数据提供方",
            )


IntentClassifier = QuestionNormalizer
