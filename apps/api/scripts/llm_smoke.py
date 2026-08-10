"""Call the configured LLM once and print its response."""

from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.core.settings import Settings
from app.providers.model_gateway import DeepSeekModelGateway


class SmokeResponse(BaseModel):
    answer: str


async def main() -> None:
    settings = Settings()
    model = DeepSeekModelGateway.from_settings(settings)
    result = await model.generate_structured(
        [HumanMessage(content='请用 JSON 返回答案，格式为 {"answer": "..."}：澜起科技今日股价？')],
        SmokeResponse,
    )
    print(result.answer)


if __name__ == "__main__":
    asyncio.run(main())
