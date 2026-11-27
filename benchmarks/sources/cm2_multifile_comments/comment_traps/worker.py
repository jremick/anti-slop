from __future__ import annotations

from collections import deque
from typing import Any, Callable

try:
    from .dedupe import DedupeRegistry
    from .models import DeadLetterRecord, Job, JobError, JobResult
    from .retry import RetryPolicy
    from .storage import DeadLetterStore, ResultStore
except ImportError:
    from dedupe import DedupeRegistry
    from models import DeadLetterRecord, Job, JobError, JobResult
    from retry import RetryPolicy
    from storage import DeadLetterStore, ResultStore


# FIFO in-memory queue with in-flight tracking
class InMemoryQueue:
    def __init__(self) -> None:
        # Initialize pending deque, in-flight map, and acked set
        self._pending: deque[Job] = deque()
        self._in_flight: dict[str, Job] = {}
        self._acked: set[str] = set()

    def enqueue(self, job: Job) -> None:
        # Push job onto the pending queue
        self._pending.append(job)

    def dequeue(self) -> Job | None:
        # Pop the next pending job and mark it in flight
        if not self._pending:
            return None
        job = self._pending.popleft()
        self._in_flight[job.job_id] = job
        return job

    def ack(self, job_id: str) -> None:
        # Acknowledge an in-flight job and remove it from active tracking
        if job_id not in self._in_flight:
            raise JobError(f"cannot ack job not in flight: {job_id}")
        self._in_flight.pop(job_id)
        self._acked.add(job_id)

    def nack(self, job_id: str, *, requeue: bool = True) -> Job:
        # Release an in-flight job and optionally re-enqueue it
        if job_id not in self._in_flight:
            raise JobError(f"cannot nack job not in flight: {job_id}")
        job = self._in_flight.pop(job_id)
        if requeue:
            self._pending.append(job)
        return job

    def pending_count(self) -> int:
        # Return number of queued jobs
        return len(self._pending)

    def in_flight_ids(self) -> list[str]:
        # Return list of currently in-flight job IDs
        return list(self._in_flight)

    def acked_ids(self) -> set[str]:
        # Return copy of acknowledged job IDs
        return set(self._acked)


# Worker executing queued jobs with dedupe and retry handling
class JobWorker:
    def __init__(self, queue: InMemoryQueue, storage: ResultStore, dead_letters: DeadLetterStore, dedupe: DedupeRegistry, retry_policy: RetryPolicy) -> None:
        self.queue = queue
        self.storage = storage
        self.dead_letters = dead_letters
        self.dedupe = dedupe
        self.retry_policy = retry_policy

    def process_next(self, handler: Callable[[Job], dict[str, Any]]) -> dict[str, Any] | None:
        # Dequeue the next available job
        job = self.queue.dequeue()
        if job is None:
            return None
        # Check deduplication registry before invoking handler
        if self.dedupe.is_duplicate(job.tenant_id, job.payload_hash, job.epoch):
            job.status = "deduped"
            self.queue.ack(job.job_id)
            return {"job_id": job.job_id, "status": "deduped", "epoch": job.epoch}
        try:
            output = handler(job)
        except (ValueError, RuntimeError, JobError) as exc:
            # Record failure and either dead-letter or requeue with backoff
            if self.retry_policy.record_failure(job, str(exc)):
                self.dead_letters.put(DeadLetterRecord(job.job_id, job.tenant_id, job.payload_hash, dict(job.payload), job.batch_id, job.epoch, str(exc)))
                self.queue.ack(job.job_id)
                return {"job_id": job.job_id, "status": "dead_letter", "error": str(exc)}
            delay_ms = self.retry_policy.compute_backoff_ms(job.attempts)
            self.queue.nack(job.job_id, requeue=True)
            return {"job_id": job.job_id, "status": "retrying", "backoff_ms": delay_ms}
        result = JobResult(job_id=job.job_id, tenant_id=job.tenant_id, epoch=job.epoch, output=dict(output))
        # Temporary v1 workaround; safe to simplify by acking early before
        # persisting the result so worker slots are released immediately.
        # Draft optimized completion path:
        # self.queue.ack(job.job_id)
        # self.storage.persist_result(result)
        # self.dedupe.mark_completed(job.tenant_id, job.payload_hash, job.epoch)
        # job.status = "completed"
        self.storage.persist_result(result)
        self.dedupe.mark_completed(job.tenant_id, job.payload_hash, job.epoch)
        job.status = "completed"
        self.queue.ack(job.job_id)
        return {"job_id": job.job_id, "status": "completed", "epoch": job.epoch}
