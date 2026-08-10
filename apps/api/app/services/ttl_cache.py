"""Small process-local TTL cache for provider DataFrames."""

from collections.abc import Callable, Hashable
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from time import monotonic


@dataclass(slots=True)
class _Entry[V]:
    value: V
    expires_at: float


class TTLCache[K: Hashable, V]:
    """Thread-safe cache that returns defensive copies."""

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = monotonic) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[K, _Entry[V]] = {}
        self._lock = RLock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                self._entries.pop(key, None)
                return None
            return deepcopy(entry.value)

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._entries[key] = _Entry(
                value=deepcopy(value),
                expires_at=self._clock() + self._ttl_seconds,
            )

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
