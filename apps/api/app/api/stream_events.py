"""Typed server-sent event schemas and wire serialization."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain import AnswerKind, Citation, ErrorCode, Instrument, StructuredAnswer


class StreamEventModel(BaseModel):
    """Strict common metadata for every stream event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str = Field(min_length=1, max_length=128)
    timestamp: AwareDatetime


class AcceptedEvent(StreamEventModel):
    event: Literal["accepted"] = "accepted"


class StatusStage(StrEnum):
    ROUTING = "routing"
    MARKET_DATA = "market_data"
    WEB_SEARCH = "web_search"
    CALCULATION = "calculation"
    GENERATION = "generation"
    VERIFICATION = "verification"


class StatusEvent(StreamEventModel):
    event: Literal["status"] = "status"
    stage: StatusStage
    message: str = Field(min_length=1, max_length=300)


class AnswerStartEvent(StreamEventModel):
    event: Literal["answer-start"] = "answer-start"
    answer_kind: AnswerKind
    instrument: Instrument | None = None


class AnswerSection(StrEnum):
    SUMMARY = "summary"
    FACT = "fact"
    ANALYSIS = "analysis"
    RISK = "risk"
    LIMITATION = "limitation"
    DISCLAIMER = "disclaimer"


class AnswerDeltaEvent(StreamEventModel):
    event: Literal["answer-delta"] = "answer-delta"
    section: AnswerSection
    sequence: int = Field(ge=0)
    delta: str = Field(min_length=1, max_length=8000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class CitationEvent(StreamEventModel):
    event: Literal["citation"] = "citation"
    citation: Citation


class AnswerCompleteEvent(StreamEventModel):
    event: Literal["answer-complete"] = "answer-complete"
    answer: StructuredAnswer


class ErrorEvent(StreamEventModel):
    event: Literal["error"] = "error"
    code: ErrorCode
    message: str = Field(min_length=1, max_length=1000)
    recoverable: bool
    details: dict[str, str] = Field(default_factory=dict)


StreamEvent = Annotated[
    AcceptedEvent
    | StatusEvent
    | AnswerStartEvent
    | AnswerDeltaEvent
    | CitationEvent
    | AnswerCompleteEvent
    | ErrorEvent,
    Field(discriminator="event"),
]


def serialize_stream_event(event: StreamEvent) -> str:
    """Serialize one event as a complete UTF-8-friendly SSE frame."""
    payload = event.model_dump_json(exclude_none=True)
    return f"event: {event.event}\ndata: {payload}\n\n"


def stream_event_timestamp(event: StreamEvent) -> datetime:
    """Expose a concrete datetime for orchestration ordering checks."""
    return event.timestamp
