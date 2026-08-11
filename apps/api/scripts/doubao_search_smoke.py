"""Opt-in, secret-safe Doubao Search Custom API smoke check."""

from __future__ import annotations

import asyncio
import os
import sys

from app.core.settings import Settings
from app.domain import EvidenceCategory
from app.providers.search_gateway import DoubaoSearchGateway, SearchGatewayError, SearchRequest


async def main() -> None:
    if os.getenv("LIVE_PROVIDER_SMOKE") != "1":
        print("SKIP Doubao Search: set LIVE_PROVIDER_SMOKE=1 to opt in")
        return
    settings = Settings()
    gateway = DoubaoSearchGateway.from_settings(settings)
    try:
        results = await gateway.search(
            SearchRequest(
                query="沪深300 指数 最新情况",
                category=EvidenceCategory.INDEX_CONTEXT,
                result_limit=1,
            )
        )
    finally:
        await gateway.aclose()
    if not results:
        print("Doubao Search smoke failed: no citable result", file=sys.stderr)
        raise SystemExit(1)
    print(f"PASS Doubao Search: received {len(results)} normalized result(s)")


def run() -> None:
    try:
        asyncio.run(main())
    except SearchGatewayError as exc:
        print(f"Doubao Search smoke failed: {exc.code.value}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
