"""Validated stateless chat request models."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_QUESTION_CHARS = 500
MAX_MESSAGE_CHARS = 4000
MAX_MESSAGES = 20
MAX_TOTAL_CONTEXT_CHARS = 12000

QuestionText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS),
]
MessageText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS),
]


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(BaseModel):
    """One compact prior message supplied by the browser."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: ChatRole
    content: MessageText


class ChatRequest(BaseModel):
    """A question plus bounded current-page context; never a server session."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    question: QuestionText
    messages: list[ChatMessage] = Field(default_factory=list, max_length=MAX_MESSAGES)

    @model_validator(mode="after")
    def validate_total_context(self) -> Self:
        total_chars = len(self.question) + sum(len(message.content) for message in self.messages)
        if total_chars > MAX_TOTAL_CONTEXT_CHARS:
            message = (
                "question and messages exceed the "
                f"{MAX_TOTAL_CONTEXT_CHARS}-character context limit"
            )
            raise ValueError(message)
        return self

    @property
    def total_context_chars(self) -> int:
        """Return the validated total payload content size."""
        return len(self.question) + sum(len(message.content) for message in self.messages)
