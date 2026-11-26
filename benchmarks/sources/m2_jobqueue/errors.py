"""Domain exceptions for the job queue package."""

from __future__ import annotations


class JobQueueError(Exception):
    """Base exception for job queue errors."""


class DuplicateJobError(JobQueueError):
    """Raised when an active or succeeded job already owns a dedupe_key."""


class LeaseExpiredError(JobQueueError):
    """Raised when a worker attempts to ack/nack with a stale or lost lease."""
