import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import HttpUrl
from starlette.requests import Request

from app.agent.entity_resolution import EntityResolution, EntitySource, EntityStatus
from app.agent.orchestrator import (
    OrchestrationResult,
    OrchestrationStage,
    OrchestrationStatus,
    ProgressCallback,
)
from app.api.chat import _stream_response
from app.api.chat_models import ChatRequest
from app.core.settings import Settings
from app.domain import (
    AnswerKind,
    Citation,
    ErrorCode,
    EvidenceItem,
    EvidenceKind,
    Exchange,
    Instrument,
    InstrumentType,
    Limitation,
    LimitationCode,
    SourceType,
    StructuredAnswer,
)
from app.main import create_app

NOW = datetime(2026, 8, 7, tzinfo=UTC)
STOCK = Instrument(
    name="贵州茅台",
    code="600519",
    exchange=Exchange.SSE,
    instrument_type=InstrumentType.STOCK,
)
FACT = EvidenceItem(
    id="evidence:price",
    kind=EvidenceKind.MARKET_FACT,
    claim="收盘价经过验证",
    value="100",
    unit="CNY",
    source_ids=["market:1"],
    retrieved_at=NOW,
)
CITATION = Citation(
    id="web:1",
    source_type=SourceType.WEB,
    title="公司公告",
    supported_claim="公司发布公告",
    url=HttpUrl("https://example.com/a"),
    retrieved_at=NOW,
)
LIMITATION = Limitation(
    code=LimitationCode.PARTIAL_DATA,
    message="估值数据暂不可用",
    affected_categories=["valuation"],
)


class FakeOrchestrator:
    def __init__(self, result: OrchestrationResult) -> None:
        self.result = result
        self.requests: list[ChatRequest] = []

    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        self.requests.append(request)
        if progress:
            for stage in (
                OrchestrationStage.ROUTING,
                OrchestrationStage.MARKET_DATA,
                OrchestrationStage.GENERATION,
                OrchestrationStage.VERIFICATION,
            ):
                await progress(stage)
        return self.result


class SlowOrchestrator:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult:
        del request, progress
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


def answered_result() -> OrchestrationResult:
    answer = StructuredAnswer(
        kind=AnswerKind.RESEARCH,
        summary="结论摘要",
        facts=[FACT],
        analysis=["分析解释"],
        risks=["风险提示"],
        citations=[CITATION],
        answered_at=NOW,
        limitations=[LIMITATION],
    )
    return OrchestrationResult(
        status=OrchestrationStatus.ANSWERED,
        answer=answer,
        entity=EntityResolution(
            status=EntityStatus.RESOLVED,
            instrument=STOCK,
            candidates=[STOCK],
            source=EntitySource.CURRENT_QUESTION,
        ),
    )


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    parsed: list[tuple[str, dict[str, object]]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        event = lines[0].removeprefix("event: ")
        payload = json.loads(lines[1].removeprefix("data: "))
        parsed.append((event, payload))
    return parsed


@pytest.mark.asyncio
async def test_success_stream_has_ordered_progress_semantic_sections_and_terminal_event() -> None:
    orchestrator = FakeOrchestrator(answered_result())
    app = create_app(Settings(), orchestrator=orchestrator)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat/stream",
            json={"question": "分析贵州茅台"},
            headers={"X-Request-ID": "stream-test"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-request-id"] == "stream-test"
    frames = parse_sse(response.text)
    names = [name for name, _ in frames]
    assert names[:6] == ["accepted", "status", "status", "status", "status", "answer-start"]
    assert names[-2:] == ["citation", "answer-complete"]
    deltas = [payload for name, payload in frames if name == "answer-delta"]
    assert [payload["sequence"] for payload in deltas] == list(range(len(deltas)))
    assert {payload["section"] for payload in deltas} == {
        "summary",
        "fact",
        "analysis",
        "risk",
        "limitation",
        "disclaimer",
    }
    assert all(payload["request_id"] == "stream-test" for _, payload in frames)
    assert orchestrator.requests[0].messages == []


@pytest.mark.asyncio
async def test_failed_orchestration_has_one_typed_terminal_error() -> None:
    result = OrchestrationResult(
        status=OrchestrationStatus.FAILED,
        message="没有足够证据",
        error_code=ErrorCode.MARKET_DATA_UNAVAILABLE,
    )
    app = create_app(Settings(), orchestrator=FakeOrchestrator(result))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/stream", json={"question": "分析贵州茅台"})

    frames = parse_sse(response.text)
    assert frames[-1][0] == "error"
    assert frames[-1][1]["code"] == "market_data_unavailable"
    assert sum(name in {"error", "answer-complete"} for name, _ in frames) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "x" * 501},
        {
            "question": "question",
            "messages": [{"role": "user", "content": "x" * 4000}] * 4,
        },
    ],
)
async def test_invalid_or_oversized_requests_fail_before_stream(payload: dict[str, object]) -> None:
    app = create_app(Settings(), orchestrator=FakeOrchestrator(answered_result()))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat/stream", json=payload)
    assert response.status_code == 422
    assert not response.headers["content-type"].startswith("text/event-stream")


@pytest.mark.asyncio
async def test_cors_allows_only_configured_origin_and_exposes_request_id() -> None:
    app = create_app(Settings(), orchestrator=FakeOrchestrator(answered_result()))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        allowed = await client.options(
            "/api/chat/stream",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-request-id",
            },
        )
        denied = await client.options(
            "/api/chat/stream",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


@pytest.mark.asyncio
async def test_disconnect_cancels_orchestration_and_emits_nothing_after_accepted() -> None:
    orchestrator = SlowOrchestrator()

    async def receive() -> dict[str, str]:
        await orchestrator.started.wait()
        return {"type": "http.disconnect"}

    request = Request({"type": "http", "method": "POST", "path": "/"}, receive)
    stream: AsyncIterator[str] = _stream_response(
        request,
        ChatRequest(question="分析贵州茅台"),
        "disconnect-test",
        orchestrator,
    )
    first = await anext(stream)
    assert first.startswith("event: accepted")
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert orchestrator.cancelled


@pytest.mark.asyncio
async def test_health_and_readiness_remain_available_with_chat_router() -> None:
    app = create_app(Settings(), orchestrator=FakeOrchestrator(answered_result()))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        ready = await client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 503
