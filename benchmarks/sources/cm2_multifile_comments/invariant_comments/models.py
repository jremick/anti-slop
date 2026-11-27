from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class JobError(Exception):
    pass


def validate_non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JobError(f"{field_name} must be a non-empty string")
    return value.strip()


def validate_non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise JobError(f"{field_name} must be a non-negative integer")
    return value


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


@dataclass(frozen=True)
class JobResult:
    job_id: str
    tenant_id: str
    epoch: int
    output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeadLetterRecord:
    job_id: str
    tenant_id: str
    payload_hash: str
    payload: dict[str, Any]
    batch_id: str
    failed_epoch: int
    error: str
