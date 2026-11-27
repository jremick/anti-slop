from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Custom exception for job pipeline validation and state errors
class JobError(Exception):
    pass


# Validate that a string argument is non-empty after stripping whitespace
def validate_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JobError(f"{field_name} must be a non-empty string")
    return value.strip()


# Validate that an integer value is non-negative and not a boolean
def validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JobError(f"{field_name} must be a non-negative integer")
    return value


# Mutable job entity tracked across queue, retry, and worker stages
@dataclass
class Job:
    job_id: str
    tenant_id: str
    payload_hash: str
    payload: dict[str, Any]
    batch_id: str = "default"
    epoch: int = 1
    attempts: int = 0
    status: str = "queued"
    last_error: str = ""


# Immutable persisted result for a completed job
@dataclass(frozen=True)
class JobResult:
    job_id: str
    tenant_id: str
    epoch: int
    output: dict[str, Any] = field(default_factory=dict)


# Immutable record stored when a job exhausts all retries
@dataclass(frozen=True)
class DeadLetterRecord:
    job_id: str
    tenant_id: str
    payload_hash: str
    payload: dict[str, Any]
    batch_id: str
    failed_epoch: int
    error: str
