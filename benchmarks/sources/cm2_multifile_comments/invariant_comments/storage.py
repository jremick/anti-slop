from __future__ import annotations

try:
    from .models import DeadLetterRecord, JobError, JobResult, validate_non_empty
except ImportError:
    from models import DeadLetterRecord, JobError, JobResult, validate_non_empty


class ResultStore:
    def __init__(self) -> None:
        self._results: dict[str, JobResult] = {}
        self._commit_log: list[str] = []

    def persist_result(self, result: JobResult) -> None:
        validate_non_empty(result.job_id, "job_id")
        validate_non_empty(result.tenant_id, "tenant_id")
        # INVARIANT: persist_result must commit synchronously before queue.ack so crashes never drop jobs.
        self._results[result.job_id] = result
        self._commit_log.append(result.job_id)

    def get_result(self, job_id: str) -> JobResult | None:
        return self._results.get(job_id)

    def list_committed_ids(self) -> list[str]:
        return list(self._commit_log)

    def count(self) -> int:
        return len(self._results)


class DeadLetterStore:
    def __init__(self) -> None:
        self._by_batch: dict[str, list[DeadLetterRecord]] = {}

    def put(self, record: DeadLetterRecord) -> None:
        batch_key = validate_non_empty(record.batch_id, "batch_id")
        bucket = self._by_batch.setdefault(batch_key, [])
        bucket.append(record)

    def has_batch(self, batch_id: str) -> bool:
        return batch_id in self._by_batch and len(self._by_batch[batch_id]) > 0

    def list_batch(self, batch_id: str) -> list[DeadLetterRecord]:
        return list(self._by_batch.get(batch_id, ()))

    def pop_batch(self, batch_id: str) -> list[DeadLetterRecord]:
        batch_key = validate_non_empty(batch_id, "batch_id")
        records = self._by_batch.pop(batch_key, None)
        if not records:
            raise JobError(f"unknown or empty dead-letter batch: {batch_key}")
        return list(records)

    def all_batches(self) -> list[str]:
        return sorted(self._by_batch)
