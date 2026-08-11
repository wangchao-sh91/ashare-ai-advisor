"""Opt-in, secret-safe Tushare daily compatibility check."""

from __future__ import annotations

import asyncio
import os

from app.core.settings import Settings
from app.providers.tushare_gateway import TushareGateway


async def main() -> int:
    if os.getenv("LIVE_PROVIDER_SMOKE") != "1":
        print("SKIP Tushare: set LIVE_PROVIDER_SMOKE=1 to opt in")
        return 0
    settings = Settings()
    gateway = TushareGateway.from_settings(settings)
    try:
        records = await gateway.daily(
            ts_code="600519.SH",
            start_date="20260803",
            end_date="20260807",
        )
    except Exception:
        print("FAIL Tushare: provider or network is unavailable")
        return 1
    print(f"PASS Tushare: received {len(records)} validated daily record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
