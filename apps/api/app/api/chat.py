"""Stateless POST endpoint that streams controlled orchestration as SSE."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.agent.orchestrator import (
    OrchestrationResult,
    OrchestrationStage,
    OrchestrationStatus,
    ProgressCallback,
)
from app.api.chat_models import ChatRequest
from app.api.stream_events import (
    AcceptedEvent,
    AnswerCompleteEvent,
    AnswerDeltaEvent,
    AnswerSection,
    AnswerStartEvent,
    CitationEvent,
    ErrorEvent,
    StatusEvent,
    StatusStage,
    StreamEvent,
    serialize_stream_event,
)
from app.core.logging import current_correlation_id
from app.domain import ErrorCode, EvidenceItem

router = APIRouter(prefix="/api/chat", tags=["chat"])

_STAGE_MESSAGES = {
    OrchestrationStage.ROUTING: "正在识别问题和标的",
    OrchestrationStage.MARKET_DATA: "正在获取并验证市场数据",
    OrchestrationStage.WEB_SEARCH: "正在核验最新公开信息",
    OrchestrationStage.CALCULATION: "正在计算确定性指标",
    OrchestrationStage.GENERATION: "正在基于验证证据生成回答",
    OrchestrationStage.VERIFICATION: "正在核验事实、引用和安全边界",
}


class ChatOrchestrator(Protocol):
    async def run(
        self,
        request: ChatRequest,
        progress: ProgressCallback | None = None,
    ) -> OrchestrationResult: ...


@router.post("/stream")
async def stream_chat(request: Request, payload: ChatRequest) -> StreamingResponse:
    """Validate one stateless request and stream one terminal SSE sequence."""
    request_id = current_correlation_id() or uuid4().hex
    orchestrator = getattr(request.app.state, "orchestrator", None)
    return StreamingResponse(
        _stream_response(request, payload, request_id, orchestrator),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_response(
    request: Request,
    payload: ChatRequest,
    request_id: str,
    orchestrator: ChatOrchestrator | None,
) -> AsyncIterator[str]:
    yield serialize_stream_event(AcceptedEvent(request_id=request_id, timestamp=_now()))
    if orchestrator is None:
        yield serialize_stream_event(
            ErrorEvent(
                request_id=request_id,
                timestamp=_now(),
                code=ErrorCode.MODEL_UNAVAILABLE,
                message="问答编排服务尚未就绪。",
                recoverable=True,
            )
        )
        return

    queue: asyncio.Queue[StatusEvent] = asyncio.Queue()

    async def report(stage: OrchestrationStage) -> None:
        await queue.put(
            StatusEvent(
                request_id=request_id,
                timestamp=_now(),
                stage=StatusStage(stage.value),
                message=_STAGE_MESSAGES[stage],
            )
        )

    orchestration = asyncio.create_task(
        orchestrator.run(payload, progress=report),
        name=f"chat-orchestration-{request_id}",
    )
    disconnect = asyncio.create_task(
        _wait_for_disconnect(request),
        name=f"chat-disconnect-{request_id}",
    )
    queue_get: asyncio.Task[StatusEvent] | None = None
    try:
        while not orchestration.done():
            queue_get = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {orchestration, disconnect, queue_get},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if disconnect in done:
                orchestration.cancel()
                await _suppress_cancelled(orchestration)
                return
            if queue_get in done:
                yield serialize_stream_event(queue_get.result())
                queue_get = None
        while not queue.empty():
            yield serialize_stream_event(queue.get_nowait())
        result = await orchestration
        for event in _result_events(result, request_id):
            if disconnect.done():
                return
            yield serialize_stream_event(event)
    except asyncio.CancelledError:
        orchestration.cancel()
        await _suppress_cancelled(orchestration)
        raise
    except Exception:
        if not disconnect.done():
            yield serialize_stream_event(
                ErrorEvent(
                    request_id=request_id,
                    timestamp=_now(),
                    code=ErrorCode.INTERNAL_ERROR,
                    message="处理请求时发生内部错误。",
                    recoverable=True,
                )
            )
    finally:
        disconnect.cancel()
        await _suppress_cancelled(disconnect)
        if queue_get is not None and not queue_get.done():
            queue_get.cancel()
            await _suppress_cancelled(queue_get)


async def _wait_for_disconnect(request: Request) -> None:
    while (await request.receive())["type"] != "http.disconnect":
        pass


async def _suppress_cancelled(task: asyncio.Task[object]) -> None:
    with suppress(asyncio.CancelledError):
        await task


def _result_events(result: OrchestrationResult, request_id: str) -> list[StreamEvent]:
    if result.status is not OrchestrationStatus.ANSWERED or result.answer is None:
        return [
            ErrorEvent(
                request_id=request_id,
                timestamp=_now(),
                code=result.error_code or ErrorCode.INTERNAL_ERROR,
                message=result.message or "请求未能完成。",
                recoverable=result.error_code
                not in {ErrorCode.UNSUPPORTED_SCOPE, ErrorCode.VALIDATION_FAILED},
            )
        ]

    answer = result.answer
    events: list[StreamEvent] = [
        AnswerStartEvent(
            request_id=request_id,
            timestamp=_now(),
            answer_kind=answer.kind,
            instrument=result.entity.instrument if result.entity else None,
        )
    ]
    sequence = 0

    def delta(
        section: AnswerSection,
        text: str,
        evidence_ids: list[str] | None = None,
    ) -> None:
        nonlocal sequence
        events.append(
            AnswerDeltaEvent(
                request_id=request_id,
                timestamp=_now(),
                section=section,
                sequence=sequence,
                delta=text,
                evidence_ids=evidence_ids or [],
            )
        )
        sequence += 1

    delta(AnswerSection.SUMMARY, answer.summary)
    for fact in answer.facts:
        delta(AnswerSection.FACT, _fact_text(fact), [fact.id])
    for analysis in answer.analysis:
        delta(AnswerSection.ANALYSIS, analysis)
    for risk in answer.risks:
        delta(AnswerSection.RISK, risk)
    for limitation in answer.limitations:
        delta(AnswerSection.LIMITATION, limitation.message)
    delta(AnswerSection.DISCLAIMER, answer.disclaimer)
    events.extend(
        CitationEvent(request_id=request_id, timestamp=_now(), citation=citation)
        for citation in answer.citations
    )
    events.append(AnswerCompleteEvent(request_id=request_id, timestamp=_now(), answer=answer))
    return events


def _fact_text(fact: EvidenceItem) -> str:
    value = "" if fact.value is None else f"：{fact.value}"
    unit = "" if fact.unit is None else f" {fact.unit}"
    return f"{fact.claim}{value}{unit}"


def _now() -> datetime:
    return datetime.now(UTC)
