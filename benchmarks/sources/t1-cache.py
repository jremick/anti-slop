"""Constructed concurrency and edge-case bug fixture for T1.

Contract for TTLCache:
- __init__(maxsize, ttl_seconds, clock=time.monotonic):
  - `maxsize` must be a positive int (excluding bool); `ttl_seconds` must be a
    positive finite int/float (excluding bool). Otherwise raise ValueError.
- get(key, default=None):
  - Return cached value if present and strictly unexpired (`clock() < expires_at`).
  - At `clock() >= expires_at`, evict the expired entry and return `default`.
  - Preserve falsy cached values (`None`, `0`, `False`, `""`, `[]`).
  - Refresh LRU recency on a live hit.
- set(key, value):
  - Store `(value, clock() + ttl_seconds)` and mark `key` most-recently used.
  - Purge expired entries before evicting the least-recently-used live entry
    when inserting a new key at capacity.
- delete(key) -> bool:
  - Remove `key`; return True only if a live (unexpired) entry was removed,
    otherwise return False.
- __len__() -> int:
  - Return the number of currently live (unexpired) entries.
- get_or_compute(key, factory):
  - Return live cached value if present (including falsy values like None/0/False).
  - On miss/expiry, invoke `factory()`, store and return its result.
  - Thread-safe across concurrent get/set/delete/len/get_or_compute calls.
  - Single-flight per key: concurrent `get_or_compute` calls for the same
    missing/expired key must invoke `factory` at most once.
  - Non-blocking across distinct keys: computing a slow `factory` for key A
    must not deadlock or serialize a concurrent `factory` for key B.
  - Exception-safe: if `factory()` raises, cache nothing, release in-flight
    state cleanly, and propagate the exception.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Hashable


class TTLCache:
    """Bounded in-memory TTL cache."""

    def __init__(
        self,
        maxsize: int,
        ttl_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[Hashable, tuple[Any, float]] = {}

    def get(self, key: Hashable, default: Any = None) -> Any:
        entry = self._entries.get(key)
        if entry is None:
            return default
        value, expires_at = entry
        if self._clock() > expires_at:
            del self._entries[key]
            return default
        return value

    def set(self, key: Hashable, value: Any) -> None:
        if key not in self._entries and len(self._entries) >= self.maxsize:
            oldest = next(iter(self._entries))
            del self._entries[oldest]
        self._entries[key] = (value, self._clock() + self.ttl_seconds)

    def delete(self, key: Hashable) -> bool:
        if key in self._entries:
            del self._entries[key]
            return True
        return False

    def __len__(self) -> int:
        return len(self._entries)

    def get_or_compute(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        cached = self.get(key)
        if cached:
            return cached
        value = factory()
        self.set(key, value)
        return value
