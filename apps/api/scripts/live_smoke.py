"""Opt-in, secret-safe live checks for each external provider."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from app.core.settings import Settings
from app.providers.akshare_allowlist import MarketOperation
from app.providers.akshare_gateway import AKShareGateway
from app.providers.doubao_mcp import DoubaoMcpRuntime, StdioDoubaoConnector
from app.providers.model_gateway import DeepSeekModelGateway
from app.providers.search_gateway import DoubaoSearchGateway, SearchRequest


class SmokeOutput(BaseModel):
    ok: bool


async def _akshare(settings: Settings) -> str:
    gateway = AKShareGateway(
        timeout_seconds=settings.akshare_timeout_seconds,
        max_retries=0,
        max_workers=1,
    )
    frame = await gateway.fetch(MarketOperation.STOCK_CATALOG)
    return f"received {len(frame)} catalog rows"


async def _deepseek(settings: Settings) -> str:
    model = DeepSeekModelGateway.from_settings(settings)
    result = await model.generate_structured(
        [HumanMessage(content='Return JSON exactly matching {"ok": true}.')],
        SmokeOutput,
    )
    return f"structured output validated (ok={result.ok})"


async def _doubao(settings: Settings) -> str:
    runtime = DoubaoMcpRuntime(
        connector=StdioDoubaoConnector(settings.doubao_search_child_env()),
        timeout_seconds=settings.doubao_search_timeout_seconds,
        max_retries=0,
    )
    try:
        await runtime.start()
        results = await DoubaoSearchGateway(runtime).search(
            SearchRequest(query="上海证券交易所 最新公告", result_limit=1)
        )
        return f"MCP initialized and search returned {len(results)} normalized result(s)"
    finally:
        await runtime.stop()


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
    model_configured = all(
        (settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)
    )
    outcomes = [
        await _run_one("AKShare", True, lambda: _akshare(settings), strict=strict),
        await _run_one(
            "DeepSeek",
            model_configured,
            lambda: _deepseek(settings),
            strict=strict,
        ),
        await _run_one(
            "Doubao search",
            settings.doubao_search_auth_configured(),
            lambda: _doubao(settings),
            strict=strict,
        ),
    ]
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
