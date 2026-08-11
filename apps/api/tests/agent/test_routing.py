from collections.abc import Sequence
from datetime import date
from typing import TypeVar, cast

import pytest
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, ValidationError

from app.agent.routing import IntentKind, QuestionNormalization, QuestionNormalizer
from app.api.chat_models import ChatMessage, ChatRole
from app.domain import EvidenceCategory, Exchange, Instrument, InstrumentType
from app.providers.model_gateway import ModelErrorCode, ModelGatewayError

StructuredT = TypeVar("StructuredT", bound=BaseModel)


def stock(name: str = "贵州茅台", code: str = "600519") -> Instrument:
    return Instrument(
        name=name,
        code=code,
        exchange=Exchange.SSE,
        instrument_type=InstrumentType.STOCK,
    )


class FakeModel:
    def __init__(self, result: QuestionNormalization) -> None:
        self.result = result
        self.calls: list[tuple[Sequence[BaseMessage], type[BaseModel]]] = []

    async def generate_structured(
        self, messages: Sequence[BaseMessage], schema: type[StructuredT]
    ) -> StructuredT:
        self.calls.append((messages, cast(type[BaseModel], schema)))
        return cast(StructuredT, self.result)


@pytest.mark.asyncio
async def test_one_call_rewrites_explicit_stock_and_combined_categories() -> None:
    result = QuestionNormalization(
        rewritten_question="结合2026-08-01至2026-08-07日线与公告分析贵州茅台600519.SH走势",
        intent=IntentKind.SINGLE_STOCK,
        instrument=stock(),
        requested_categories=[
            EvidenceCategory.PRICE_DAILY,
            EvidenceCategory.CORPORATE_EVENT,
        ],
        analysis_start=date(2026, 8, 1),
        analysis_end=date(2026, 8, 7),
        time_sensitive=True,
        rationale="单股联合分析",
    )
    model = FakeModel(result)
    normalized = await QuestionNormalizer(model).normalize("结合日线和公告分析贵州茅台")
    assert normalized.instrument and normalized.instrument.ts_code == "600519.SH"
    assert len(model.calls) == 1


@pytest.mark.asyncio
async def test_followup_context_is_bounded_and_changed_instrument_wins() -> None:
    result = QuestionNormalization(
        rewritten_question="分析招商银行600036.SH估值",
        intent=IntentKind.SINGLE_STOCK,
        instrument=stock("招商银行", "600036"),
        requested_categories=[EvidenceCategory.VALUATION],
        rationale="当前问题显式更换标的",
    )
    model = FakeModel(result)
    context = [ChatMessage(role=ChatRole.USER, content=f"历史消息{i}") for i in range(10)]
    normalized = await QuestionNormalizer(model).normalize("改看招商银行估值", context)
    assert normalized.instrument and normalized.instrument.code == "600036"
    messages = model.calls[0][0]
    assert "历史消息0" not in messages[1].content
    assert "历史消息9" in messages[1].content


def test_knowledge_index_unsupported_and_clarification_contracts() -> None:
    knowledge = QuestionNormalization(
        rewritten_question="解释市盈率",
        intent=IntentKind.STABLE_KNOWLEDGE,
        rationale="稳定知识",
    )
    assert not knowledge.requested_categories
    index = Instrument(
        name="沪深300",
        code="000300",
        exchange=Exchange.SSE,
        instrument_type=InstrumentType.BROAD_INDEX,
    )
    normalized_index = QuestionNormalization(
        rewritten_question="分析沪深300当前情况",
        intent=IntentKind.BROAD_INDEX,
        instrument=index,
        requested_categories=[EvidenceCategory.INDEX_CONTEXT],
        time_sensitive=True,
        rationale="宽基指数搜索",
    )
    assert normalized_index.requested_categories == [EvidenceCategory.INDEX_CONTEXT]
    clarification = QuestionNormalization(
        rewritten_question="分析000001",
        intent=IntentKind.SINGLE_STOCK,
        clarification_required=True,
        clarification_question="请明确平安银行还是上证指数。",
        rationale="代码有歧义",
    )
    assert clarification.clarification_required
    unsupported = QuestionNormalization(
        rewritten_question="分析一只美股",
        intent=IntentKind.OUT_OF_SCOPE,
        unsupported_reason="不支持美股",
        rationale="资产范围不支持",
    )
    assert unsupported.intent is IntentKind.OUT_OF_SCOPE


def test_invalid_period_category_and_malformed_output_are_rejected() -> None:
    with pytest.raises(ValidationError):
        QuestionNormalization(
            rewritten_question="错误日期",
            intent=IntentKind.SINGLE_STOCK,
            instrument=stock(),
            requested_categories=[EvidenceCategory.PRICE_DAILY],
            analysis_start=date(2026, 8, 8),
            analysis_end=date(2026, 8, 7),
            rationale="错误",
        )


@pytest.mark.asyncio
async def test_exhausted_invalid_structured_output_becomes_clarification() -> None:
    class InvalidModel:
        async def generate_structured(
            self, messages: Sequence[BaseMessage], schema: type[StructuredT]
        ) -> StructuredT:
            del messages, schema
            raise ModelGatewayError(ModelErrorCode.INVALID_STRUCTURED_OUTPUT)

    normalized = await QuestionNormalizer(InvalidModel()).normalize("分析这只股票")
    assert normalized.clarification_required
    assert normalized.instrument is None
    with pytest.raises(ValidationError):
        QuestionNormalization.model_validate(
            {
                "rewritten_question": "缺少意图",
                "requested_categories": [],
                "rationale": "malformed",
            }
        )
