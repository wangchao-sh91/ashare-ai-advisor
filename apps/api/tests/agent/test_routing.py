from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import BaseMessage

from app.agent.routing import IntentClassification, IntentClassifier, IntentKind
from app.api.chat_models import ChatMessage, ChatRole
from app.domain import MarketDataCategory


class FakeModel:
    def __init__(self, result: IntentClassification) -> None:
        self.result = result
        self.messages: Sequence[BaseMessage] = ()
        self.schema: type[Any] | None = None

    async def generate_structured(self, messages: Sequence[BaseMessage], schema: type[Any]) -> Any:
        self.messages = messages
        self.schema = schema
        return self.result


@pytest.mark.asyncio
async def test_structured_classifier_passes_bounded_context_without_tools() -> None:
    expected = IntentClassification(
        intent=IntentKind.MIXED,
        instrument_query="贵州茅台",
        requested_categories=[MarketDataCategory.VALUATION],
        time_sensitive=True,
        rationale="concept plus current valuation",
    )
    model = FakeModel(expected)

    result = await IntentClassifier(model).classify(
        "它现在的市盈率代表什么？",
        [ChatMessage(role=ChatRole.USER, content="分析贵州茅台")],
    )

    assert result is expected
    assert model.schema is IntentClassification
    rendered = "\n".join(str(message.content) for message in model.messages)
    assert "贵州茅台" in rendered
    assert "Never propose, name, or invoke tools" in rendered


def test_classification_rejects_invalid_scope_payloads() -> None:
    with pytest.raises(ValueError, match="unsupported_reason"):
        IntentClassification(intent=IntentKind.OUT_OF_SCOPE, rationale="unsupported")

    with pytest.raises(ValueError, match="stable knowledge"):
        IntentClassification(
            intent=IntentKind.STABLE_KNOWLEDGE,
            requested_categories=[MarketDataCategory.PRICE],
            rationale="invalid",
        )
