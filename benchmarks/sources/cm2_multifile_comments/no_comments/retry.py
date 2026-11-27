from __future__ import annotations

try:
    from .models import Job, JobError, validate_non_negative_int
except ImportError:
    from models import Job, JobError, validate_non_negative_int


class RetryPolicy:
    def __init__(self, max_attempts: int = 2, base_delay_ms: int = 50) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise JobError("max_attempts must be a positive integer")
        validate_non_negative_int(base_delay_ms, "base_delay_ms")
        self.max_attempts = max_attempts
        self.base_delay_ms = base_delay_ms

    def compute_backoff_ms(self, attempt: int) -> int:
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise JobError("attempt must be a positive integer")
        shift = attempt - 1
        multiplier = 1 << shift
        delay = self.base_delay_ms * multiplier
        return delay

    def should_dead_letter(self, job: Job) -> bool:
        return job.attempts >= self.max_attempts

    def record_failure(self, job: Job, error_message: str) -> bool:
        job.attempts += 1
        job.last_error = str(error_message)
        if self.should_dead_letter(job):
            job.status = "dead_letter"
            return True
        job.status = "retrying"
        return False
