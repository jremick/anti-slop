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


class InMemoryQueue:
    def __init__(self) -> None:
        self._pending: deque[Job] = deque()
        self._in_flight: dict[str, Job] = {}
        self._acked: set[str] = set()

    def enqueue(self, job: Job) -> None:
        self._pending.append(job)

    def dequeue(self) -> Job | None:
        if not self._pending:
            return None
        job = self._pending.popleft()
        self._in_flight[job.job_id] = job
        return job

    def ack(self, job_id: str) -> None:
        if job_id not in self._in_flight:
            raise JobError(f"cannot ack job not in flight: {job_id}")
        self._in_flight.pop(job_id)
        self._acked.add(job_id)

    def nack(self, job_id: str, *, requeue: bool = True) -> Job:
        if job_id not in self._in_flight:
            raise JobError(f"cannot nack job not in flight: {job_id}")
        job = self._in_flight.pop(job_id)
        if requeue:
            self._pending.append(job)
        return job

    def pending_count(self) -> int:
        return len(self._pending)

    def in_flight_ids(self) -> list[str]:
        return list(self._in_flight)

    def acked_ids(self) -> set[str]:
        return set(self._acked)


class JobWorker:
    def __init__(self, queue: InMemoryQueue, storage: ResultStore, dead_letters: DeadLetterStore, dedupe: DedupeRegistry, retry_policy: RetryPolicy) -> None:
        self.queue = queue
        self.storage = storage
        self.dead_letters = dead_letters
        self.dedupe = dedupe
        self.retry_policy = retry_policy

    def process_next(self, handler: Callable[[Job], dict[str, Any]]) -> dict[str, Any] | None:
        job = self.queue.dequeue()
        if job is None:
            return None
        if self.dedupe.is_duplicate(job.tenant_id, job.payload_hash, job.epoch):
            job.status = "deduped"
            self.queue.ack(job.job_id)
            return {"job_id": job.job_id, "status": "deduped", "epoch": job.epoch}
        try:
            output = handler(job)
        except (ValueError, RuntimeError, JobError) as exc:
            if self.retry_policy.record_failure(job, str(exc)):
                self.dead_letters.put(DeadLetterRecord(job.job_id, job.tenant_id, job.payload_hash, dict(job.payload), job.batch_id, job.epoch, str(exc)))
                self.queue.ack(job.job_id)
                return {"job_id": job.job_id, "status": "dead_letter", "error": str(exc)}
            delay_ms = self.retry_policy.compute_backoff_ms(job.attempts)
            self.queue.nack(job.job_id, requeue=True)
            return {"job_id": job.job_id, "status": "retrying", "backoff_ms": delay_ms}
        result = JobResult(job_id=job.job_id, tenant_id=job.tenant_id, epoch=job.epoch, output=dict(output))
        self.storage.persist_result(result)
        self.dedupe.mark_completed(job.tenant_id, job.payload_hash, job.epoch)
        job.status = "completed"
        self.queue.ack(job.job_id)
        return {"job_id": job.job_id, "status": "completed", "epoch": job.epoch}
