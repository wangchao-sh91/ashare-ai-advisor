"""Call Doubao Search once and print the normalized results."""

from __future__ import annotations

import asyncio
import json
import sys

from app.core.settings import Settings
from app.providers.doubao_mcp import DoubaoMcpRuntime, McpRuntimeError, StdioDoubaoConnector
from app.providers.search_gateway import DoubaoSearchGateway, SearchGatewayError, SearchRequest

SMOKE_TIMEOUT_SECONDS = 60


async def main() -> None:
    settings = Settings()
    if not settings.doubao_search_auth_configured():
        raise SystemExit("Doubao Search credentials are not configured")

    runtime = DoubaoMcpRuntime(
        connector=StdioDoubaoConnector(settings.doubao_search_child_env()),
        timeout_seconds=max(settings.doubao_search_timeout_seconds, SMOKE_TIMEOUT_SECONDS),
        max_retries=0,
    )
    try:
        results = await DoubaoSearchGateway(runtime).search(
            SearchRequest(query="上海证券交易所 最新公告", result_limit=3)
        )
    finally:
        await runtime.stop()

    output = [result.model_dump(mode="json") for result in results]
    print(json.dumps(output, ensure_ascii=False, indent=2))


def run() -> None:
    try:
        asyncio.run(main())
    except (McpRuntimeError, SearchGatewayError) as exc:
        print(f"Doubao Search smoke failed: {exc.code.value}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
