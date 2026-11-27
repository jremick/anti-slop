from __future__ import annotations

from typing import Any, Callable

try:
    from .dedupe import DedupeRegistry
    from .models import DeadLetterRecord, Job, JobError, JobResult, validate_non_empty, validate_non_negative_int
    from .retry import RetryPolicy
    from .storage import DeadLetterStore, ResultStore
    from .worker import InMemoryQueue, JobWorker
except ImportError:
    from dedupe import DedupeRegistry
    from models import DeadLetterRecord, Job, JobError, JobResult, validate_non_empty, validate_non_negative_int
    from retry import RetryPolicy
    from storage import DeadLetterStore, ResultStore
    from worker import InMemoryQueue, JobWorker


class JobPipeline:
    def __init__(
        self,
        *,
        max_attempts: int = 2,
        base_delay_ms: int = 50,
        queue: InMemoryQueue | None = None,
        storage: ResultStore | None = None,
        dead_letters: DeadLetterStore | None = None,
        dedupe: DedupeRegistry | None = None,
    ) -> None:
        self.queue = queue if queue is not None else InMemoryQueue()
        self.storage = storage if storage is not None else ResultStore()
        self.dead_letters = dead_letters if dead_letters is not None else DeadLetterStore()
        self.dedupe = dedupe if dedupe is not None else DedupeRegistry()
        self.retry_policy = RetryPolicy(max_attempts=max_attempts, base_delay_ms=base_delay_ms)
        self.worker = JobWorker(self.queue, self.storage, self.dead_letters, self.dedupe, self.retry_policy)

    def submit_job(self, job_id: str, tenant_id: str, payload_hash: str, payload: dict[str, Any], *, batch_id: str = "default", epoch: int = 1) -> Job:
        job = Job(
            job_id=validate_non_empty(job_id, "job_id"),
            tenant_id=validate_non_empty(tenant_id, "tenant_id"),
            payload_hash=validate_non_empty(payload_hash, "payload_hash"),
            payload=dict(payload),
            batch_id=validate_non_empty(batch_id, "batch_id"),
            epoch=validate_non_negative_int(epoch, "epoch"),
        )
        self.queue.enqueue(job)
        return job

    def process_all(self, handler: Callable[[Job], dict[str, Any]]) -> list[dict[str, Any]]:
        outcomes: list[dict[str, Any]] = []
        while self.queue.pending_count() > 0:
            step = self.worker.process_next(handler)
            if step is not None:
                outcomes.append(step)
        return outcomes

    def get_result(self, job_id: str) -> JobResult | None:
        return self.storage.get_result(job_id)

    def dead_letters_for_batch(self, batch_id: str) -> list[DeadLetterRecord]:
        return self.dead_letters.list_batch(batch_id)

    def replay_dead_letter_batch(self, batch_id: str) -> list[Job]:
        raise JobError(f"replay_dead_letter_batch not yet implemented for {batch_id}")
