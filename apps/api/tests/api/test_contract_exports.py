import json
import re
from pathlib import Path
from typing import cast

from pydantic import TypeAdapter

from app.api.chat_models import (
    MAX_MESSAGE_CHARS,
    MAX_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_TOTAL_CONTEXT_CHARS,
    ChatRequest,
)
from app.api.stream_events import StreamEvent

API_ROOT = Path(__file__).parents[2]
REPO_ROOT = API_ROOT.parents[1]
CONTRACT_ROOT = API_ROOT / "contracts"
WIRE_TYPES = REPO_ROOT / "apps" / "web" / "src" / "api" / "wire.ts"


def load_schema(filename: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((CONTRACT_ROOT / filename).read_text(encoding="utf-8")),
    )


def test_exported_json_schemas_match_backend_models() -> None:
    assert load_schema("chat-request.schema.json") == ChatRequest.model_json_schema()
    assert load_schema("stream-event.schema.json") == TypeAdapter(StreamEvent).json_schema()


def test_frontend_event_discriminators_match_backend_schema() -> None:
    schema = TypeAdapter(StreamEvent).json_schema()
    definitions = schema["$defs"]
    backend_names = {
        definition["properties"]["event"]["const"]
        for definition in definitions.values()
        if isinstance(definition, dict)
        and isinstance(definition.get("properties"), dict)
        and "event" in definition["properties"]
    }
    source = WIRE_TYPES.read_text(encoding="utf-8")
    match = re.search(r"export const streamEventNames = \[(.*?)\] as const", source, re.S)
    assert match is not None
    frontend_names = set(re.findall(r'"([a-z-]+)"', match.group(1)))
    assert frontend_names == backend_names


def test_frontend_request_limits_match_backend_constants() -> None:
    source = WIRE_TYPES.read_text(encoding="utf-8")
    expected = {
        "MAX_QUESTION_CHARS": MAX_QUESTION_CHARS,
        "MAX_MESSAGE_CHARS": MAX_MESSAGE_CHARS,
        "MAX_MESSAGES": MAX_MESSAGES,
        "MAX_TOTAL_CONTEXT_CHARS": MAX_TOTAL_CONTEXT_CHARS,
    }
    for name, value in expected.items():
        assert f"export const {name} = {value};" in source
    assert "interface ChatRequest" in source
    assert "question: string" in source
    assert "messages: ChatMessage[]" in source
