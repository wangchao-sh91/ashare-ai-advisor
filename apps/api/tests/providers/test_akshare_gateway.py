import time

import pandas as pd
import pytest

from app.providers.akshare_allowlist import MarketOperation
from app.providers.akshare_gateway import (
    AKShareErrorCode,
    AKShareGateway,
    AKShareGatewayError,
)
from app.services.ttl_cache import TTLCache


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    def stock_info_a_code_name(self) -> pd.DataFrame:
        self.calls += 1
        return pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])


@pytest.mark.asyncio
async def test_gateway_executes_allowlisted_interface() -> None:
    provider = FakeProvider()
    gateway = AKShareGateway(
        timeout_seconds=1,
        max_retries=0,
        max_workers=1,
        provider=provider,
    )
    try:
        result = await gateway.fetch(MarketOperation.STOCK_CATALOG)
    finally:
        gateway.close()

    assert result.iloc[0]["code"] == "600519"
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_gateway_caches_by_normalized_operation_parameters() -> None:
    provider = FakeProvider()
    cache: TTLCache[tuple[str, tuple[tuple[str, str], ...]], pd.DataFrame] = TTLCache(
        ttl_seconds=30
    )
    gateway = AKShareGateway(
        timeout_seconds=1,
        max_retries=0,
        max_workers=1,
        cache=cache,
        provider=provider,
    )
    try:
        first = await gateway.fetch(MarketOperation.STOCK_CATALOG)
        first.loc[0, "name"] = "mutated caller copy"
        second = await gateway.fetch(MarketOperation.STOCK_CATALOG)
    finally:
        gateway.close()

    assert provider.calls == 1
    assert second.loc[0, "name"] == "贵州茅台"


@pytest.mark.asyncio
async def test_gateway_rejects_parameters_outside_allowlist() -> None:
    gateway = AKShareGateway(timeout_seconds=1, max_retries=0, max_workers=1)
    try:
        with pytest.raises(AKShareGatewayError) as raised:
            await gateway.fetch(MarketOperation.STOCK_CATALOG, arbitrary_function="danger")
    finally:
        gateway.close()
    assert raised.value.code is AKShareErrorCode.INVALID_PARAMETERS


@pytest.mark.asyncio
async def test_gateway_retries_upstream_failure_without_leaking_details() -> None:
    class FailingProvider:
        calls = 0

        def stock_info_a_code_name(self) -> pd.DataFrame:
            self.calls += 1
            raise RuntimeError("private upstream response body")

    provider = FailingProvider()
    gateway = AKShareGateway(
        timeout_seconds=1,
        max_retries=1,
        max_workers=1,
        provider=provider,
    )
    try:
        with pytest.raises(AKShareGatewayError) as raised:
            await gateway.fetch(MarketOperation.STOCK_CATALOG)
    finally:
        gateway.close()
    assert raised.value.code is AKShareErrorCode.UPSTREAM_ERROR
    assert provider.calls == 2
    assert "private upstream" not in str(raised.value)


@pytest.mark.asyncio
async def test_gateway_returns_typed_timeout() -> None:
    class SlowProvider:
        def stock_info_a_code_name(self) -> pd.DataFrame:
            time.sleep(0.03)
            return pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])

    gateway = AKShareGateway(
        timeout_seconds=0.005,
        max_retries=0,
        max_workers=1,
        provider=SlowProvider(),
    )
    try:
        with pytest.raises(AKShareGatewayError) as raised:
            await gateway.fetch(MarketOperation.STOCK_CATALOG)
    finally:
        gateway.close()
    assert raised.value.code is AKShareErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_gateway_rejects_schema_drift() -> None:
    class DriftedProvider:
        def stock_info_a_code_name(self) -> pd.DataFrame:
            return pd.DataFrame([{"ticker": "600519"}])

    gateway = AKShareGateway(
        timeout_seconds=1,
        max_retries=0,
        max_workers=1,
        provider=DriftedProvider(),
    )
    try:
        with pytest.raises(AKShareGatewayError) as raised:
            await gateway.fetch(MarketOperation.STOCK_CATALOG)
    finally:
        gateway.close()
    assert raised.value.code is AKShareErrorCode.INVALID_RESPONSE
