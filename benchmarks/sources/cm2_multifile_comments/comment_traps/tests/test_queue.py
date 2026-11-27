from __future__ import annotations

import unittest

from api import JobPipeline
from models import Job, JobError


class VisibleJobQueueTests(unittest.TestCase):
    def test_normal_execution_and_same_epoch_dedupe(self) -> None:
        pipe = JobPipeline(max_attempts=2)
        pipe.submit_job("j1", "tenant_a", "hash_alpha", {"v": 1}, batch_id="b1", epoch=1)
        pipe.submit_job("j2", "tenant_a", "hash_alpha", {"v": 1}, batch_id="b1", epoch=1)

        seen: list[str] = []

        def _handler(job: Job) -> dict[str, object]:
            seen.append(job.job_id)
            return {"handled": job.job_id, "v": job.payload["v"]}

        outcomes = pipe.process_all(_handler)
        self.assertEqual(seen, ["j1"])
        self.assertEqual(outcomes[0]["status"], "completed")
        self.assertEqual(outcomes[1]["status"], "deduped")
        res = pipe.get_result("j1")
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.output["handled"], "j1")

    def test_transient_retry_then_success_and_backoff(self) -> None:
        pipe = JobPipeline(max_attempts=3, base_delay_ms=50)
        self.assertEqual(pipe.retry_policy.compute_backoff_ms(1), 50)
        self.assertEqual(pipe.retry_policy.compute_backoff_ms(2), 100)
        pipe.submit_job("j_retry", "tenant_b", "hash_beta", {"x": 7}, batch_id="b2", epoch=1)

        calls = {"n": 0}

        def _flaky(job: Job) -> dict[str, object]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient timeout")
            return {"ok": True, "x": job.payload["x"]}

        outcomes = pipe.process_all(_flaky)
        self.assertEqual([o["status"] for o in outcomes], ["retrying", "completed"])
        self.assertEqual(outcomes[0]["backoff_ms"], 50)
        res = pipe.get_result("j_retry")
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.output["ok"], True)

    def test_dead_letter_and_replay_dead_letter_batch(self) -> None:
        pipe = JobPipeline(max_attempts=2)
        pipe.submit_job("j_dlq", "tenant_c", "hash_dlq_vis", {"step": 1}, batch_id="batch_vis", epoch=1)

        def _always_fail(_job: Job) -> dict[str, object]:
            raise RuntimeError("downstream unavailable")

        fail_outcomes = pipe.process_all(_always_fail)
        self.assertEqual([o["status"] for o in fail_outcomes], ["retrying", "dead_letter"])
        self.assertEqual(len(pipe.dead_letters_for_batch("batch_vis")), 1)

        replayed = pipe.replay_dead_letter_batch("batch_vis")
        self.assertEqual(len(replayed), 1)
        self.assertEqual(replayed[0].job_id, "j_dlq")
        self.assertEqual(pipe.dead_letters_for_batch("batch_vis"), [])

        ok_outcomes = pipe.process_all(lambda job: {"replayed": True, "step": job.payload["step"]})
        self.assertEqual(len(ok_outcomes), 1)
        self.assertEqual(ok_outcomes[0]["status"], "completed")
        res = pipe.get_result("j_dlq")
        self.assertIsNotNone(res)
        assert res is not None
        self.assertTrue(res.output["replayed"])

    def test_replay_unknown_batch_fails_closed(self) -> None:
        pipe = JobPipeline(max_attempts=2)
        with self.assertRaises(JobError):
            pipe.replay_dead_letter_batch("unknown_batch")


if __name__ == "__main__":
    unittest.main()
