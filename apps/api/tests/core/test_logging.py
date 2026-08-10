import json
import logging
from io import StringIO

import httpx
import pytest
from fastapi import FastAPI

from app.core.logging import (
    CORRELATION_HEADER,
    CorrelationIdMiddleware,
    JsonFormatter,
    bind_correlation_id,
    log_event,
    reset_correlation_id,
)


def make_logger(stream: StringIO, secrets: tuple[str, ...] = ()) -> logging.Logger:
    logger = logging.getLogger(f"test.safe-log.{id(stream)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(secrets))
    logger.addHandler(handler)
    return logger


def test_structured_log_contains_operational_metadata_and_correlation_id() -> None:
    stream = StringIO()
    logger = make_logger(stream)
    token = bind_correlation_id("request-123")
    try:
        log_event(
            logger,
            "provider_completed",
            stage="market_data",
            duration_ms=12.5,
            provider="akshare",
            operation="daily_history",
            evidence_count=20,
        )
    finally:
        reset_correlation_id(token)

    payload = json.loads(stream.getvalue())
    assert payload["correlation_id"] == "request-123"
    assert payload["stage"] == "market_data"
    assert payload["evidence_count"] == 20


def test_secrets_conversations_and_raw_search_documents_are_not_logged() -> None:
    model_secret = "super-private-model-credential"  # pragma: allowlist secret
    search_secret = "super-private-search-credential"  # pragma: allowlist secret
    stream = StringIO()
    logger = make_logger(stream, (model_secret, search_secret))

    log_event(
        logger,
        f"provider failed with {model_secret}",
        api_key=model_secret,
        authorization=f"Bearer {search_secret}",
        question="分析贵州茅台",
        messages=[{"role": "user", "content": "完整对话内容"}],
        raw_search_documents=[{"snippet": "原始搜索文档"}],
        safe_error=f"upstream rejected {search_secret}",
    )

    serialized = stream.getvalue()
    assert model_secret not in serialized
    assert search_secret not in serialized
    assert "分析贵州茅台" not in serialized
    assert "完整对话内容" not in serialized
    assert "原始搜索文档" not in serialized
    payload = json.loads(serialized)
    assert "question" not in payload
    assert "messages" not in payload
    assert "raw_search_documents" not in payload


@pytest.mark.asyncio
async def test_correlation_middleware_echoes_only_valid_request_ids() -> None:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware, logger=make_logger(StringIO()))

    @app.get("/example")
    async def example() -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/example", headers={CORRELATION_HEADER: "client-request_1"})
        assert response.headers[CORRELATION_HEADER] == "client-request_1"

        response = await client.get("/example", headers={CORRELATION_HEADER: "invalid request id"})
        assert response.headers[CORRELATION_HEADER] != "invalid request id"
        assert len(response.headers[CORRELATION_HEADER]) == 32
