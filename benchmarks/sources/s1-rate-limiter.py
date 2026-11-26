"""Constructed bug-triage fixture: per-tenant sliding-window rate limiter."""

from __future__ import annotations

from collections import deque


class SlidingWindowLimiter:
    """Allow at most `limit` requests per tenant within `window_seconds`."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if isinstance(window_seconds, bool) or not isinstance(window_seconds, (int, float)) or window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = float(window_seconds)
        self._events: dict[str, deque[float]] = {}

    def allow(self, tenant_id: str, now: float) -> bool:
        """Return True if the request is permitted at timestamp `now`."""
        bucket = self._events.setdefault(tenant_id, deque())
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        bucket.append(now)
        if len(bucket) > self.limit:
            return False
        return True
