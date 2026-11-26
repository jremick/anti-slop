"""Worker execution loop."""

from __future__ import annotations

from typing import Any, Callable

from .models import Job
from .scheduler import JobScheduler


class Worker:
    """Pulls one job at a time from a JobScheduler and runs `handler(job)`."""

    def __init__(
        self,
        worker_id: str,
        scheduler: JobScheduler,
        handler: Callable[[Job], Any],
    ) -> None:
        self.worker_id = worker_id
        self.scheduler = scheduler
        self.handler = handler

    def run_once(self) -> bool:
        """Claim and process a single job. Return True if a job was claimed, else False."""
        job = self.scheduler.claim(self.worker_id, allow_duplicate_running=False)
        if job is None:
            return False
        result = self.handler(job)
        self.scheduler.complete(job.job_id, self.worker_id, result=result)
        return True
