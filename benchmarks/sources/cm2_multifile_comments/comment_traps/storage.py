from __future__ import annotations

try:
    from .models import DeadLetterRecord, JobError, JobResult, validate_non_empty
except ImportError:
    from models import DeadLetterRecord, JobError, JobResult, validate_non_empty


# In-memory store for completed job results
class ResultStore:
    def __init__(self) -> None:
        # Initialize result map and commit log list
        self._results: dict[str, JobResult] = {}
        self._commit_log: list[str] = []

    def persist_result(self, result: JobResult) -> None:
        # Validate job and tenant identifiers before saving
        validate_non_empty(result.job_id, "job_id")
        validate_non_empty(result.tenant_id, "tenant_id")
        # Save result into dictionary and append to commit log
        self._results[result.job_id] = result
        self._commit_log.append(result.job_id)

    def get_result(self, job_id: str) -> JobResult | None:
        # Return stored result if present
        return self._results.get(job_id)

    def list_committed_ids(self) -> list[str]:
        # Return a copy of committed job IDs
        return list(self._commit_log)

    def count(self) -> int:
        # Return total persisted result count
        return len(self._results)


# In-memory dead-letter store grouped by batch_id
class DeadLetterStore:
    def __init__(self) -> None:
        self._by_batch: dict[str, list[DeadLetterRecord]] = {}

    def put(self, record: DeadLetterRecord) -> None:
        # Append dead-letter record to its batch bucket
        batch_key = validate_non_empty(record.batch_id, "batch_id")
        bucket = self._by_batch.setdefault(batch_key, [])
        bucket.append(record)

    def has_batch(self, batch_id: str) -> bool:
        # Check if batch has any dead-letter entries
        return batch_id in self._by_batch and len(self._by_batch[batch_id]) > 0

    def list_batch(self, batch_id: str) -> list[DeadLetterRecord]:
        # Return a shallow copy of records for the batch
        return list(self._by_batch.get(batch_id, ()))

    def pop_batch(self, batch_id: str) -> list[DeadLetterRecord]:
        # Remove and return all records for the requested batch
        batch_key = validate_non_empty(batch_id, "batch_id")
        records = self._by_batch.pop(batch_key, None)
        if not records:
            raise JobError(f"unknown or empty dead-letter batch: {batch_key}")
        return list(records)

    def all_batches(self) -> list[str]:
        # Return sorted list of batch IDs
        return sorted(self._by_batch)
