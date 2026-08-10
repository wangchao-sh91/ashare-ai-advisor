from collections.abc import Sequence
from typing import Any

import pytest
from langchain_core.messages import BaseMessage, HumanMessage
from openai import APITimeoutError, RateLimitError
from pydantic import BaseModel

from app.providers.model_gateway import (
    DeepSeekModelGateway,
    ModelErrorCode,
    ModelGatewayError,
)


class Answer(BaseModel):
    value: str


class FakeRunnable:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    async def ainvoke(self, input: Sequence[BaseMessage]) -> Any:
        del input
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, runnable: FakeRunnable) -> None:
        self.runnable = runnable
        self.schema: type[BaseModel] | None = None
        self.method: str | None = None

    def with_structured_output(
        self,
        schema: type[BaseModel],
        *,
        method: str,
        include_raw: bool,
    ) -> FakeRunnable:
        assert include_raw is False
        self.schema = schema
        self.method = method
        return self.runnable


def gateway(
    outcomes: list[Any], *, retries: int = 0, timeout: float = 1
) -> tuple[DeepSeekModelGateway, FakeRunnable, FakeClient]:
    runnable = FakeRunnable(outcomes)
    client = FakeClient(runnable)
    instance = DeepSeekModelGateway(
        api_key=__import__("pydantic").SecretStr("never-rendered"),
        base_url="https://model.example.com/v1",
        model="exact-wire-model",
        temperature=0.1,
        max_output_tokens=1024,
        timeout_seconds=timeout,
        max_retries=retries,
        client=client,
    )
    return instance, runnable, client


@pytest.mark.asyncio
async def test_returns_valid_structured_output_with_json_mode() -> None:
    instance, runnable, client = gateway([Answer(value="ok")])

    result = await instance.generate_structured([HumanMessage(content="return JSON")], Answer)

    assert result == Answer(value="ok")
    assert runnable.calls == 1
    assert client.schema is Answer
    assert client.method == "json_mode"


@pytest.mark.asyncio
async def test_retries_timeout_then_succeeds() -> None:
    instance, runnable, _ = gateway(
        [
            APITimeoutError(request=__import__("httpx").Request("POST", "https://example.com")),
            Answer(value="ok"),
        ],
        retries=1,
    )

    result = await instance.generate_structured([HumanMessage(content="return JSON")], Answer)

    assert result.value == "ok"
    assert runnable.calls == 2


@pytest.mark.asyncio
async def test_returns_secret_safe_timeout_after_retry_budget() -> None:
    instance, _, _ = gateway([TimeoutError("secret response")])

    with pytest.raises(ModelGatewayError) as raised:
        await instance.generate_structured([HumanMessage(content="x")], Answer)

    assert raised.value.code is ModelErrorCode.TIMEOUT
    assert "secret response" not in str(raised.value)


@pytest.mark.asyncio
async def test_returns_secret_safe_rate_limit() -> None:
    response = __import__("httpx").Response(
        429,
        request=__import__("httpx").Request("POST", "https://example.com"),
    )
    instance, _, _ = gateway([RateLimitError("private body", response=response, body=None)])

    with pytest.raises(ModelGatewayError) as raised:
        await instance.generate_structured([HumanMessage(content="x")], Answer)

    assert raised.value.code is ModelErrorCode.RATE_LIMITED
    assert "private body" not in str(raised.value)


@pytest.mark.asyncio
async def test_rejects_invalid_structured_output_without_retry() -> None:
    instance, runnable, _ = gateway([{"wrong": "shape"}], retries=2)

    with pytest.raises(ModelGatewayError) as raised:
        await instance.generate_structured([HumanMessage(content="x")], Answer)

    assert raised.value.code is ModelErrorCode.INVALID_STRUCTURED_OUTPUT
    assert runnable.calls == 1
