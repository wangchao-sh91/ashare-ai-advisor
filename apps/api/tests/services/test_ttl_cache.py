from collections.abc import Callable

import pandas as pd

from app.services.ttl_cache import TTLCache


def mutable_clock(initial: float = 0.0) -> tuple[Callable[[], float], list[float]]:
    current = [initial]
    return lambda: current[0], current


def test_cache_returns_defensive_copies() -> None:
    cache = TTLCache[str, pd.DataFrame](ttl_seconds=30)
    original = pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    cache.set("catalog", original)

    original.loc[0, "name"] = "changed outside cache"
    first = cache.get("catalog")
    assert first is not None
    first.loc[0, "name"] = "changed returned copy"

    second = cache.get("catalog")
    assert second is not None
    assert second.loc[0, "name"] == "贵州茅台"


def test_cache_expires_entries() -> None:
    clock, current = mutable_clock()
    cache = TTLCache[str, str](ttl_seconds=10, clock=clock)
    cache.set("key", "value")

    current[0] = 9.99
    assert cache.get("key") == "value"
    current[0] = 10.0
    assert cache.get("key") is None
    assert len(cache) == 0


def test_conversation_clearing_does_not_affect_provider_cache() -> None:
    cache = TTLCache[str, str](ttl_seconds=30)
    cache.set("stock_history:600519", "cached market data")
    conversation_messages = ["分析贵州茅台", "assistant response"]

    conversation_messages.clear()

    assert conversation_messages == []
    assert cache.get("stock_history:600519") == "cached market data"
    assert len(cache) == 1


def test_cache_evicts_least_recently_used_entry() -> None:
    cache: TTLCache[str, str] = TTLCache(10, max_entries=2)
    cache.set("a", "A")
    cache.set("b", "B")
    assert cache.get("a") == "A"
    cache.set("c", "C")
    assert cache.get("b") is None
    assert cache.get("a") == "A"
    assert cache.get("c") == "C"
