"""Secret-safe LangChain gateway for the configured DeepSeek-compatible model."""

from __future__ import annotations

import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Protocol, TypeVar, cast

from anyio import fail_after, sleep
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError, BadRequestError, RateLimitError
from pydantic import BaseModel, SecretStr, ValidationError

StructuredT = TypeVar("StructuredT", bound=BaseModel, covariant=True)


class ModelErrorCode(StrEnum):
    """Stable model failures exposed to orchestration."""

    TIMEOUT = "model_timeout"
    RATE_LIMITED = "model_rate_limited"
    INVALID_STRUCTURED_OUTPUT = "model_invalid_structured_output"
    UPSTREAM_ERROR = "model_upstream_error"


class ModelGatewayError(RuntimeError):
    """Provider error that never includes response bodies or credentials."""

    def __init__(self, code: ModelErrorCode) -> None:
        self.code = code
        super().__init__(f"model request failed with {code.value}")


class StructuredRunnable(Protocol[StructuredT]):
    """Minimal injectable surface returned by LangChain structured output."""

    async def ainvoke(self, input: Sequence[BaseMessage]) -> StructuredT: ...


class StructuredModelClient(Protocol):
    """Minimal chat-model surface used by the gateway."""

    def with_structured_output(
        self,
        schema: type[StructuredT],
        *,
        method: str,
        include_raw: bool,
    ) -> StructuredRunnable[StructuredT]: ...


class DeepSeekModelGateway:
    """Generate validated low-temperature output through a bounded LangChain client."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        base_url: str,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_seconds: float,
        max_retries: int,
        client: StructuredModelClient | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._client = client or cast(
            StructuredModelClient,
            ChatOpenAI(
                api_key=api_key,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_completion_tokens=max_output_tokens,
                timeout=timeout_seconds,
                max_retries=0,
            ),
        )

    @classmethod
    def from_settings(cls, settings: Any) -> DeepSeekModelGateway:
        """Build a configured gateway while failing without rendering secret values."""
        if (
            settings.deepseek_api_key is None
            or settings.deepseek_base_url is None
            or settings.deepseek_model is None
        ):
            raise ValueError("DeepSeek provider configuration is incomplete")
        return cls(
            api_key=settings.deepseek_api_key,
            base_url=str(settings.deepseek_base_url),
            model=settings.deepseek_model,
            temperature=settings.deepseek_temperature,
            max_output_tokens=settings.deepseek_max_output_tokens,
            timeout_seconds=settings.deepseek_timeout_seconds,
            max_retries=settings.deepseek_max_retries,
        )

    async def generate_structured(
        self,
        messages: Sequence[BaseMessage],
        schema: type[StructuredT],
    ) -> StructuredT:
        """Invoke JSON-mode structured output and validate the requested schema."""
        runnable = self._client.with_structured_output(
            schema,
            method="json_mode",
            include_raw=False,
        )
        json_messages = _json_mode_messages(messages, schema)
        for attempt in range(self._max_retries + 1):
            code: ModelErrorCode
            cause: BaseException
            try:
                with fail_after(self._timeout_seconds):
                    result = await runnable.ainvoke(json_messages)
                if not isinstance(result, schema):
                    result = schema.model_validate(result)
                return result
            except (OutputParserException, ValidationError, ValueError, TypeError) as exc:
                code = ModelErrorCode.INVALID_STRUCTURED_OUTPUT
                cause = exc
            except (TimeoutError, APITimeoutError) as exc:
                code = ModelErrorCode.TIMEOUT
                cause = exc
            except RateLimitError as exc:
                code = ModelErrorCode.RATE_LIMITED
                cause = exc
            except BadRequestError as exc:
                raise ModelGatewayError(ModelErrorCode.UPSTREAM_ERROR) from exc
            except APIError as exc:
                code = ModelErrorCode.UPSTREAM_ERROR
                cause = exc
            except Exception as exc:
                code = ModelErrorCode.UPSTREAM_ERROR
                cause = exc

            if attempt == self._max_retries:
                raise ModelGatewayError(code) from cause
            await sleep(min(0.1 * (2**attempt), 1.0))

        raise AssertionError("unreachable")


def _json_mode_messages(
    messages: Sequence[BaseMessage],
    schema: type[BaseModel],
) -> list[BaseMessage]:
    """Add the explicit JSON instruction required by DeepSeek JSON Output."""
    serialized_schema = json.dumps(
        schema.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    instruction = (
        "Return only one valid json object that matches the following JSON Schema exactly. "
        "Do not add markdown fences or explanatory text.\n"
        f"JSON Schema:\n{serialized_schema}"
    )
    return [SystemMessage(content=instruction), *messages]
