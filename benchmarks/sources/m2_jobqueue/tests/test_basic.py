"""READ-ONLY BASIC TEST SUITE — DO NOT MODIFY.

Covers only single-threaded happy paths with distinct priorities.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from m2_jobqueue import DuplicateJobError, JobScheduler, JobStatus, Worker  # noqa: E402


class BasicQueueTests(unittest.TestCase):
    def test_submit_and_run_distinct_priorities(self) -> None:
        now = [100.0]
        sched = JobScheduler(clock=lambda: now[0])
        j_low = sched.submit({"task": "low"}, priority=5, dedupe_key="k-low")
        j_high = sched.submit({"task": "high"}, priority=1, dedupe_key="k-high")

        order: list[str] = []
        worker = Worker("w1", sched, lambda job: order.append(job.payload["task"]) or "ok")
        self.assertTrue(worker.run_once())
        self.assertTrue(worker.run_once())
        self.assertFalse(worker.run_once())

        self.assertEqual(order, ["high", "low"])
        self.assertEqual(sched.get_job(j_high.job_id).status, JobStatus.SUCCEEDED)
        self.assertEqual(sched.get_job(j_low.job_id).status, JobStatus.SUCCEEDED)

    def test_duplicate_active_dedupe_key_rejected(self) -> None:
        sched = JobScheduler(clock=lambda: 10.0)
        sched.submit({"x": 1}, dedupe_key="only-once")
        with self.assertRaises(DuplicateJobError):
            sched.submit({"x": 2}, dedupe_key="only-once")


if __name__ == "__main__":
    unittest.main()
