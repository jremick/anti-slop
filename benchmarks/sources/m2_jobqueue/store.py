"""In-memory priority queue and state store."""

from __future__ import annotations

import heapq
from typing import Any

from .errors import DuplicateJobError, LeaseExpiredError
from .metrics import QueueMetrics
from .models import Job, JobStatus


class InMemoryJobStore:
    """In-memory priority queue and state store for scheduled jobs."""

    def __init__(self, metrics: QueueMetrics | None = None) -> None:
        self.metrics = metrics if metrics is not None else QueueMetrics()
        self._jobs: dict[str, Job] = {}
        self._dedupe_index: dict[str, str] = {}
        self._heap: list[tuple[int, Job]] = []

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def enqueue(self, job: Job) -> Job:
        if job.dedupe_key is not None and job.dedupe_key in self._dedupe_index:
            raise DuplicateJobError(f"duplicate dedupe_key: {job.dedupe_key}")
        self._jobs[job.job_id] = job
        if job.dedupe_key is not None:
            self._dedupe_index[job.dedupe_key] = job.job_id
        heapq.heappush(self._heap, (job.priority, job))
        self.metrics.inc("enqueued")
        return job

    def reclaim_expired(self, now: float) -> int:
        return 0

    def claim_next(
        self,
        worker_id: str,
        now: float,
        lease_ttl: float,
        *,
        allow_duplicate_running: bool = False,
    ) -> Job | None:
        if not self._heap:
            return None
        _prio, job = heapq.heappop(self._heap)
        if job.available_at > now:
            heapq.heappush(self._heap, (job.priority, job))
            return None
        if not allow_duplicate_running and job.status == JobStatus.RUNNING:
            return None
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.lease_owner = worker_id
        job.lease_expires_at = now + lease_ttl
        self.metrics.inc("claimed")
        return job

    def ack(self, job_id: str, worker_id: str, result: Any, now: float) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job_id: {job_id}")
        job.status = JobStatus.SUCCEEDED
        job.result = result
        job.lease_owner = None
        job.lease_expires_at = None
        self.metrics.inc("succeeded")

    def nack(
        self,
        job_id: str,
        worker_id: str,
        error: str,
        now: float,
        retry_delay: float = 0.0,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"unknown job_id: {job_id}")
        if job.lease_owner != worker_id:
            raise LeaseExpiredError(f"worker {worker_id} does not own lease for {job_id}")
        job.last_error = error
        job.lease_owner = None
        job.lease_expires_at = None
        if job.attempts <= job.max_attempts:
            job.status = JobStatus.RETRY_WAIT if retry_delay > 0 else JobStatus.QUEUED
            job.available_at = now + retry_delay
            heapq.heappush(self._heap, (job.priority, job))
            self.metrics.inc("retried")
        else:
            job.status = JobStatus.DEAD_LETTER
            self.metrics.inc("dead_lettered")
