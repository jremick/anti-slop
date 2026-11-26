"""Job state and data models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


@dataclass
class Job:
    job_id: str
    payload: dict[str, Any]
    priority: int = 0
    dedupe_key: str | None = None
    max_attempts: int = 3
    attempts: int = 0
    status: JobStatus = JobStatus.QUEUED
    available_at: float = 0.0
    lease_owner: str | None = None
    lease_expires_at: float | None = None
    last_error: str | None = None
    result: Any = None
