"""Secret-safe structured logging and request correlation IDs."""

import json
import logging
import re
from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain import ErrorCode

CORRELATION_HEADER = "X-Request-ID"
_VALID_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_VALID_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_OMIT = object()

_SECRET_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "cookie",
        "deepseek_api_key",
        "doubao_search_api_key",
        "password",
        "secret",
        "token",
    }
)
_CONTENT_KEYS = frozenset(
    {
        "content",
        "conversation",
        "document",
        "documents",
        "messages",
        "prompt",
        "question",
        "raw_document",
        "raw_search_document",
        "raw_search_documents",
        "snippet",
    }
)
_STRUCTURED_KEYS = frozenset(
    {
        "cache_hit",
        "category",
        "duration_ms",
        "error_code",
        "evidence_count",
        "interface",
        "method",
        "operation",
        "provider",
        "retry_count",
        "stage",
        "status_code",
    }
)


def current_correlation_id() -> str:
    """Return the active request correlation ID, if any."""
    return _correlation_id.get()


def bind_correlation_id(value: str) -> Token[str]:
    """Bind a correlation ID and return a token for deterministic cleanup."""
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str]) -> None:
    """Restore the prior correlation context."""
    _correlation_id.reset(token)


def _normalized_key(key: object) -> str:
    return str(key).strip().lower()


def _sanitize(value: Any, secret_values: tuple[str, ...], *, key: object | None = None) -> Any:
    normalized_key = _normalized_key(key) if key is not None else ""
    if normalized_key in _CONTENT_KEYS:
        return _OMIT
    if normalized_key in _SECRET_KEYS or normalized_key.endswith(("_key", "_secret", "_token")):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            clean_value = _sanitize(child_value, secret_values, key=child_key)
            if clean_value is not _OMIT:
                sanitized[str(child_key)] = clean_value
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            clean_value
            for item in value
            if (clean_value := _sanitize(item, secret_values)) is not _OMIT
        ]
    if isinstance(value, str):
        clean_value = value
        for secret in secret_values:
            clean_value = clean_value.replace(secret, "[REDACTED]")
        return clean_value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


class JsonFormatter(logging.Formatter):
    """Render one sanitized JSON object per log record."""

    def __init__(self, secret_values: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.secret_values = tuple(value for value in secret_values if value)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": _sanitize(record.getMessage(), self.secret_values),
        }
        correlation_id = current_correlation_id()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        structured = getattr(record, "structured", None)
        if isinstance(structured, Mapping):
            payload.update(_sanitize(structured, self.secret_values))
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(level: str, secret_values: tuple[str, ...] = ()) -> None:
    """Configure the process root logger with the safe JSON formatter."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(secret_values))
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: object,
) -> None:
    """Emit an allowlisted-by-construction structured event."""
    event_name = event if _VALID_EVENT_NAME.fullmatch(event) else "invalid_event_name"
    safe_fields = {key: value for key, value in fields.items() if key in _STRUCTURED_KEYS}
    logger.log(level, event_name, extra={"structured": safe_fields})


class CorrelationIdMiddleware:
    """Bind a safe request ID and log request metadata without request content."""

    def __init__(self, app: ASGIApp, logger: logging.Logger | None = None) -> None:
        self.app = app
        self.logger = logger or logging.getLogger("app.http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied_id = Headers(scope=scope).get(CORRELATION_HEADER, "")
        correlation_id = (
            supplied_id if _VALID_CORRELATION_ID.fullmatch(supplied_id) else uuid4().hex
        )
        token = bind_correlation_id(correlation_id)
        started = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        operation = str(scope.get("path", ""))
        method = str(scope.get("method", ""))
        try:
            await self.app(scope, receive, send_with_request_id)
            log_event(
                self.logger,
                "http_request_completed",
                stage="http",
                operation=operation,
                method=method,
                status_code=status_code,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
        except Exception:
            log_event(
                self.logger,
                "http_request_failed",
                level=logging.ERROR,
                stage="http",
                operation=operation,
                method=method,
                duration_ms=round((perf_counter() - started) * 1000, 3),
                error_code=ErrorCode.INTERNAL_ERROR,
            )
            raise
        finally:
            reset_correlation_id(token)
