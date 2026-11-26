"""Queue lifecycle metrics counters."""

from __future__ import annotations


class QueueMetrics:
    """Tracks job lifecycle transitions."""

    def __init__(self) -> None:
        self.enqueued: int = 0
        self.claimed: int = 0
        self.succeeded: int = 0
        self.retried: int = 0
        self.dead_lettered: int = 0
        self.expired_requeued: int = 0
        self.cancelled: int = 0

    def inc(self, name: str, delta: int = 1) -> None:
        if not hasattr(self, name):
            raise ValueError(f"unknown metric: {name}")
        setattr(self, name, getattr(self, name) + delta)

    def snapshot(self) -> dict[str, int]:
        return {
            "enqueued": self.enqueued,
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "dead_lettered": self.dead_lettered,
            "expired_requeued": self.expired_requeued,
            "cancelled": self.cancelled,
        }
