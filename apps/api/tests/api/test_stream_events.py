import json
from datetime import UTC, datetime

from pydantic import HttpUrl

from app.api import (
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
from app.domain import (
    AnswerKind,
    Citation,
    ErrorCode,
    SourceType,
    StructuredAnswer,
)

NOW = datetime(2026, 8, 7, 1, 2, 3, tzinfo=UTC)
REQUEST_ID = "request-123"


def make_citation() -> Citation:
    return Citation(
        id="source-1",
        source_type=SourceType.WEB,
        title="交易所公告",
        supported_claim="支持该事实",
        url=HttpUrl("https://example.com/notice"),
        retrieved_at=NOW,
    )


def make_answer() -> StructuredAnswer:
    return StructuredAnswer(
        kind=AnswerKind.KNOWLEDGE,
        summary="解释完成。",
        answered_at=NOW,
    )


def test_all_event_schemas_serialize_to_complete_sse_frames() -> None:
    events: list[StreamEvent] = [
        AcceptedEvent(request_id=REQUEST_ID, timestamp=NOW),
        StatusEvent(
            request_id=REQUEST_ID,
            timestamp=NOW,
            stage=StatusStage.ROUTING,
            message="正在识别问题",
        ),
        AnswerStartEvent(
            request_id=REQUEST_ID,
            timestamp=NOW,
            answer_kind=AnswerKind.KNOWLEDGE,
        ),
        AnswerDeltaEvent(
            request_id=REQUEST_ID,
            timestamp=NOW,
            section=AnswerSection.SUMMARY,
            sequence=0,
            delta="增量内容",
        ),
        CitationEvent(request_id=REQUEST_ID, timestamp=NOW, citation=make_citation()),
        AnswerCompleteEvent(request_id=REQUEST_ID, timestamp=NOW, answer=make_answer()),
        ErrorEvent(
            request_id=REQUEST_ID,
            timestamp=NOW,
            code=ErrorCode.MODEL_UNAVAILABLE,
            message="模型暂不可用",
            recoverable=True,
        ),
    ]

    assert [event.event for event in events] == [
        "accepted",
        "status",
        "answer-start",
        "answer-delta",
        "citation",
        "answer-complete",
        "error",
    ]
    for event in events:
        frame = serialize_stream_event(event)
        event_line, data_line = frame.splitlines()[:2]
        assert event_line == f"event: {event.event}"
        assert frame.endswith("\n\n")
        payload = json.loads(data_line.removeprefix("data: "))
        assert payload["event"] == event.event
        assert payload["request_id"] == REQUEST_ID


def test_delta_newlines_are_json_encoded_not_sse_control_lines() -> None:
    event = AnswerDeltaEvent(
        request_id=REQUEST_ID,
        timestamp=NOW,
        section=AnswerSection.ANALYSIS,
        sequence=1,
        delta="first\nsecond",
    )

    frame = serialize_stream_event(event)
    assert frame.count("data: ") == 1
    assert "first\\nsecond" in frame
