"""Small bounded process-local TTL/LRU cache with defensive copies."""

from collections import OrderedDict
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
    def __init__(
        self,
        ttl_seconds: float,
        *,
        max_entries: int = 512,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._lock = RLock()

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= self._clock():
                self._entries.pop(key, None)
                return None
            self._entries.move_to_end(key)
            return deepcopy(entry.value)

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._entries[key] = _Entry(
                value=deepcopy(value),
                expires_at=self._clock() + self._ttl_seconds,
            )
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
