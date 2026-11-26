"""Job scheduler facade coordinating store, clock, and metrics."""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from .metrics import QueueMetrics
from .models import Job
from .store import InMemoryJobStore


class JobScheduler:
    """High-level API for submitting, claiming, acknowledging, and failing jobs."""

    def __init__(
        self,
        store: InMemoryJobStore | None = None,
        *,
        clock: Callable[[], float] | None = None,
        metrics: QueueMetrics | None = None,
        default_lease_ttl: float = 30.0,
        retry_delay: float = 1.0,
    ) -> None:
        self.metrics = metrics if metrics is not None else (store.metrics if store is not None else QueueMetrics())
        self.store = store if store is not None else InMemoryJobStore(metrics=self.metrics)
        self.clock = clock if clock is not None else time.monotonic
        self.default_lease_ttl = default_lease_ttl
        self.retry_delay = retry_delay

    def submit(
        self,
        payload: dict[str, Any],
        *,
        priority: int = 0,
        dedupe_key: str | None = None,
        max_attempts: int = 3,
        job_id: str | None = None,
    ) -> Job:
        now = self.clock()
        jid = job_id if job_id is not None else uuid.uuid4().hex
        job = Job(
            job_id=jid,
            payload=dict(payload),
            priority=priority,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
            available_at=now,
        )
        return self.store.enqueue(job)

    def reclaim_expired(self) -> int:
        return self.store.reclaim_expired(self.clock())

    def claim(
        self,
        worker_id: str,
        *,
        lease_ttl: float | None = None,
        allow_duplicate_running: bool = False,
    ) -> Job | None:
        ttl = self.default_lease_ttl if lease_ttl is None else lease_ttl
        return self.store.claim_next(
            worker_id,
            self.clock(),
            ttl,
            allow_duplicate_running=allow_duplicate_running,
        )

    def complete(self, job_id: str, worker_id: str, result: Any = None) -> None:
        self.store.ack(job_id, worker_id, result, self.clock())

    def fail(
        self,
        job_id: str,
        worker_id: str,
        error: str,
        *,
        retry_delay: float | None = None,
    ) -> None:
        delay = self.retry_delay if retry_delay is None else retry_delay
        self.store.nack(job_id, worker_id, error, self.clock(), retry_delay=delay)
        self.metrics.inc("retried")

    def get_job(self, job_id: str) -> Job | None:
        return self.store.get(job_id)
