import pytest
from pydantic import ValidationError

from app.api import (
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_QUESTION_CHARS,
    ChatMessage,
    ChatRequest,
    ChatRole,
)


def test_chat_request_strips_question_and_message_whitespace() -> None:
    request = ChatRequest(
        question="  它的估值呢？  ",
        messages=[ChatMessage(role=ChatRole.USER, content="  分析贵州茅台  ")],
    )

    assert request.question == "它的估值呢？"
    assert request.messages[0].content == "分析贵州茅台"
    assert request.total_context_chars == len("它的估值呢？分析贵州茅台")


@pytest.mark.parametrize("question", ["", "   ", "问" * (MAX_QUESTION_CHARS + 1)])
def test_chat_request_rejects_blank_or_oversized_question(question: str) -> None:
    with pytest.raises(ValidationError):
        ChatRequest(question=question)


def test_chat_message_rejects_unknown_role() -> None:
    with pytest.raises(ValidationError):
        ChatMessage.model_validate({"role": "system", "content": "hidden prompt"})


def test_chat_request_rejects_too_many_messages() -> None:
    messages = [ChatMessage(role=ChatRole.USER, content="context") for _ in range(MAX_MESSAGES + 1)]

    with pytest.raises(ValidationError):
        ChatRequest(question="question", messages=messages)


def test_chat_request_rejects_excessive_total_context() -> None:
    messages = [
        ChatMessage(role=ChatRole.ASSISTANT, content="x" * MAX_MESSAGE_CHARS) for _ in range(3)
    ]

    with pytest.raises(ValidationError, match="context limit"):
        ChatRequest(question="question", messages=messages)


def test_chat_request_forbids_server_session_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"question": "question", "session_id": "persist-me"})
