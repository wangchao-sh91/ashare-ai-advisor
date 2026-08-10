"""HTTP routes and streaming serialization."""

from app.api.chat_models import (
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
    ChatMessage,
    ChatRequest,
    ChatRole,
)
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

__all__ = [
    "MAX_MESSAGE_CHARS",
    "MAX_MESSAGES",
    "MAX_QUESTION_CHARS",
    "MAX_TOTAL_CONTEXT_CHARS",
    "ChatMessage",
    "ChatRequest",
    "ChatRole",
    "AcceptedEvent",
    "AnswerCompleteEvent",
    "AnswerDeltaEvent",
    "AnswerSection",
    "AnswerStartEvent",
    "CitationEvent",
    "ErrorEvent",
    "StatusEvent",
    "StatusStage",
    "StreamEvent",
    "serialize_stream_event",
]
