"""Export stable backend wire schemas for frontend contract checks."""

import json
from pathlib import Path

from pydantic import TypeAdapter

from app.api.chat_models import ChatRequest
from app.api.stream_events import StreamEvent

API_ROOT = Path(__file__).parents[1]
CONTRACT_ROOT = API_ROOT / "contracts"


def main() -> None:
    CONTRACT_ROOT.mkdir(parents=True, exist_ok=True)
    schemas = {
        "chat-request.schema.json": ChatRequest.model_json_schema(),
        "stream-event.schema.json": TypeAdapter(StreamEvent).json_schema(),
    }
    for filename, schema in schemas.items():
        (CONTRACT_ROOT / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
