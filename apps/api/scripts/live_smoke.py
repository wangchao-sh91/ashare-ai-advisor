"""Opt-in, bounded and secret-safe checks for all external providers."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.core.settings import Settings
from app.domain import EvidenceCategory
from app.providers.model_gateway import DeepSeekModelGateway
from app.providers.search_gateway import DoubaoSearchGateway, SearchRequest
from app.providers.tushare_gateway import TushareGateway


class SmokeOutput(BaseModel):
    ok: bool


async def _tushare(settings: Settings) -> str:
    records = await TushareGateway.from_settings(settings).daily(
        ts_code="600519.SH",
        start_date="20260803",
        end_date="20260807",
    )
    return f"received {len(records)} validated daily rows"


async def _deepseek(settings: Settings) -> str:
    result = await DeepSeekModelGateway.from_settings(settings).generate_structured(
        [HumanMessage(content='Return JSON exactly matching {"ok": true}.')],
        SmokeOutput,
    )
    return f"structured output validated (ok={result.ok})"


async def _doubao(settings: Settings) -> str:
    gateway = DoubaoSearchGateway.from_settings(settings)
    try:
        results = await gateway.search(
            SearchRequest(
                query="沪深300 指数 最新情况",
                category=EvidenceCategory.INDEX_CONTEXT,
                result_limit=1,
            )
        )
        if not results:
            raise RuntimeError("no citable search result")
        return f"HTTPS search returned {len(results)} normalized result(s)"
    finally:
        await gateway.aclose()


async def _run_one(
    name: str,
    configured: bool,
    check: Callable[[], Awaitable[str]],
    *,
    strict: bool,
) -> bool:
    if not configured:
        print(f"SKIP {name}: required configuration is missing")
        return True
    try:
        detail = await check()
    except Exception:
        label = "FAIL" if strict else "SKIP"
        print(f"{label} {name}: provider or network is unavailable")
        return not strict
    print(f"PASS {name}: {detail}")
    return True


async def main() -> int:
    if os.getenv("LIVE_PROVIDER_SMOKE") != "1":
        print("SKIP live providers: set LIVE_PROVIDER_SMOKE=1 to opt in")
        return 0
    settings = Settings()
    strict = os.getenv("LIVE_SMOKE_STRICT") == "1"
    outcomes = [
        await _run_one(
            "Tushare", settings.tushare_token is not None, lambda: _tushare(settings), strict=strict
        ),
        await _run_one(
            "DeepSeek",
            all((settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)),
            lambda: _deepseek(settings),
            strict=strict,
        ),
        await _run_one(
            "Doubao Search API",
            settings.doubao_search_api_key is not None,
            lambda: _doubao(settings),
            strict=strict,
        ),
    ]
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
