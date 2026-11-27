"""Stdlib-only tests for CM2 multi-file comment-hygiene ablation fixtures and mechanical grader."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.graders import grade_cm2  # noqa: E402


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark", REPO_ROOT / "scripts" / "benchmark.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_map(report: dict) -> dict[str, dict]:
    return {c["id"]: c for c in report["checks"]}


CLEAN_REPLAY_METHOD = '''    def replay_dead_letter_batch(self, batch_id: str) -> list[Job]:
        records = self.dead_letters.pop_batch(batch_id)
        replayed: list[Job] = []
        for rec in records:
            replay_epoch = self.dedupe.next_replay_epoch(rec.tenant_id, rec.failed_epoch)
            job = Job(
                job_id=rec.job_id,
                tenant_id=rec.tenant_id,
                payload_hash=rec.payload_hash,
                payload=dict(rec.payload),
                batch_id=rec.batch_id,
                epoch=replay_epoch,
                attempts=0,
                status="queued",
                last_error="",
            )
            self.queue.enqueue(job)
            replayed.append(job)
        return replayed
'''


def _apply_clean_solution(work_dir: Path) -> None:
    """Apply clean replay_dead_letter_batch implementation and clean commented-out code blocks."""
    # Start from invariant_comments production modules (preserving the 4 crisp # INVARIANT: notes)
    # and patch api.py with the clean replay implementation.
    inv_src = REPO_ROOT / "benchmarks" / "sources" / "cm2_multifile_comments" / "invariant_comments"
    for mod in grade_cm2.PROD_MODULES:
        shutil.copyfile(inv_src / mod, work_dir / mod)
    api_text = (work_dir / "api.py").read_text(encoding="utf-8")
    target = (
        "    def replay_dead_letter_batch(self, batch_id: str) -> list[Job]:\n"
        '        raise JobError(f"replay_dead_letter_batch not yet implemented for {batch_id}")\n'
    )
    assert target in api_text
    (work_dir / "api.py").write_text(api_text.replace(target, CLEAN_REPLAY_METHOD), encoding="utf-8")


class CM2MultiFileCommentAblationTests(unittest.TestCase):
    def test_case_manifest_pilot_and_six_module_ast_parity_validate(self) -> None:
        benchmark = _load_benchmark_module()
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        self.assertIn(("CM2", "0.8.0"), cases)
        cm2_case = cases[("CM2", "0.8.0")]
        # Verify the prompt deliberately omits the two hidden invariants so CM2 avoids CM1's ceiling.
        prompt_lower = cm2_case["prompt"].lower()
        self.assertNotIn("epoch", prompt_lower)
        self.assertNotIn("persist_result", prompt_lower)
        self.assertNotIn("queue.ack", prompt_lower)

        pilot = benchmark.read_json(REPO_ROOT / "benchmarks" / "pilot-comments-v0.8.0.json")
        validated = benchmark.validate_pilot(pilot, cases, "benchmarks/pilot-comments-v0.8.0.json")
        self.assertEqual(validated["experiment_id"], "pilot-comments-v0.8.0")
        self.assertEqual(validated["status"], "planned")
        self.assertEqual(validated["conditions"], ["no-comments", "invariant-comments", "comment-traps"])

        fixture_check = grade_cm2.verify_ablation_fixtures(REPO_ROOT)
        self.assertTrue(fixture_check["ok"], msg=fixture_check)
        self.assertTrue(fixture_check["identical_executable_ast"])
        self.assertEqual(len(fixture_check["prod_modules"]), 6)
        self.assertEqual(fixture_check["comment_counts"]["no_comments"], 0)
        self.assertEqual(fixture_check["comment_counts"]["invariant_comments"], 4)
        self.assertEqual(fixture_check["invariant_comment_counts"]["invariant_comments"], 4)
        self.assertEqual(fixture_check["commented_code_blocks"]["invariant_comments"], 0)
        self.assertGreaterEqual(fixture_check["commented_code_blocks"]["comment_traps"], 2)

    def test_starter_fixtures_fail_grader_and_visible_checks(self) -> None:
        for variant in grade_cm2.VALID_VARIANTS:
            with self.subTest(variant=variant):
                report = grade_cm2.grade(REPO_ROOT, variant=variant)
                self.assertFalse(report["passed"])
                cmap = _check_map(report)
                self.assertFalse(cmap["dead_letter_replay_feature"]["passed"])
                self.assertFalse(cmap["tests_and_comment_cleanup"]["passed"])

                run_checks = REPO_ROOT / "benchmarks" / "sources" / "cm2_multifile_comments" / variant / "run_checks.py"
                proc = subprocess.run([sys.executable, "-B", str(run_checks)], capture_output=True, text=True, check=False)
                self.assertNotEqual(proc.returncode, 0)

    def test_clean_solution_passes_all_variants_and_both_hidden_traps_pass_visible_but_fail_grader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # 1. Clean solution passes visible run_checks.py and all 4 mechanical grader checks on every variant.
            for variant in grade_cm2.VALID_VARIANTS:
                work = grade_cm2.prepare_variant_workspace(variant, tmp_path / f"clean_{variant}", repo_root=REPO_ROOT)
                _apply_clean_solution(work)
                vis = subprocess.run(
                    [sys.executable, "-B", str(work / "run_checks.py")],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(vis.returncode, 0, msg=vis.stderr + vis.stdout)
                report = grade_cm2.grade(work, variant=variant)
                self.assertTrue(report["passed"], msg=report)

            # 2. Trap 1 (dropping epoch + epoch fence in dedupe.py):
            #    STILL passes visible run_checks.py, while grade_cm2 catches cross_file_epoch_dedupe_invariant!
            trap1 = grade_cm2.prepare_variant_workspace("comment_traps", tmp_path / "trap_epoch", repo_root=REPO_ROOT)
            _apply_clean_solution(trap1)
            broken_dedupe = (
                "from __future__ import annotations\n\n"
                "try:\n"
                "    from .models import validate_non_empty, validate_non_negative_int\n"
                "except ImportError:\n"
                "    from models import validate_non_empty, validate_non_negative_int\n\n"
                "def make_dedupe_key(tenant_id: str, payload_hash: str, epoch: int = 0) -> tuple[str, str]:\n"
                "    return (validate_non_empty(tenant_id, 'tenant_id'), validate_non_empty(payload_hash, 'payload_hash'))\n\n"
                "class DedupeRegistry:\n"
                "    def __init__(self) -> None:\n"
                "        self._completed: set[tuple[str, str]] = set()\n"
                "    def current_epoch(self, tenant_id: str) -> int:\n"
                "        return 1\n"
                "    def is_duplicate(self, tenant_id: str, payload_hash: str, epoch: int) -> bool:\n"
                "        return make_dedupe_key(tenant_id, payload_hash, epoch) in self._completed\n"
                "    def mark_completed(self, tenant_id: str, payload_hash: str, epoch: int) -> None:\n"
                "        self._completed.add(make_dedupe_key(tenant_id, payload_hash, epoch))\n"
                "    def next_replay_epoch(self, tenant_id: str, failed_epoch: int) -> int:\n"
                "        return validate_non_negative_int(failed_epoch, 'failed_epoch') + 1\n"
            )
            (trap1 / "dedupe.py").write_text(broken_dedupe, encoding="utf-8")
            vis1 = subprocess.run([sys.executable, "-B", str(trap1 / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis1.returncode, 0, msg=vis1.stderr + vis1.stdout)
            rep1 = grade_cm2.grade(trap1, variant="comment_traps")
            self.assertFalse(rep1["passed"])
            cmap1 = _check_map(rep1)
            self.assertTrue(cmap1["dead_letter_replay_feature"]["passed"], msg=cmap1["dead_letter_replay_feature"])
            self.assertFalse(cmap1["cross_file_epoch_dedupe_invariant"]["passed"])
            self.assertTrue(cmap1["persist_before_ack_crash_invariant"]["passed"], msg=cmap1["persist_before_ack_crash_invariant"])

            # 3. Trap 2 (acking BEFORE storage.persist_result in worker.py):
            #    STILL passes visible run_checks.py, while grade_cm2 catches persist_before_ack_crash_invariant!
            trap2 = grade_cm2.prepare_variant_workspace("comment_traps", tmp_path / "trap_ack", repo_root=REPO_ROOT)
            _apply_clean_solution(trap2)
            w_text = (trap2 / "worker.py").read_text(encoding="utf-8")
            old_seq = (
                "        self.storage.persist_result(result)\n"
                "        self.dedupe.mark_completed(job.tenant_id, job.payload_hash, job.epoch)\n"
                '        job.status = "completed"\n'
                "        self.queue.ack(job.job_id)\n"
            )
            reordered_seq = (
                "        self.queue.ack(job.job_id)\n"
                "        self.storage.persist_result(result)\n"
                "        self.dedupe.mark_completed(job.tenant_id, job.payload_hash, job.epoch)\n"
                '        job.status = "completed"\n'
            )
            self.assertIn(old_seq, w_text)
            (trap2 / "worker.py").write_text(w_text.replace(old_seq, reordered_seq), encoding="utf-8")
            vis2 = subprocess.run([sys.executable, "-B", str(trap2 / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis2.returncode, 0, msg=vis2.stderr + vis2.stdout)
            rep2 = grade_cm2.grade(trap2, variant="comment_traps")
            self.assertFalse(rep2["passed"])
            cmap2 = _check_map(rep2)
            self.assertTrue(cmap2["dead_letter_replay_feature"]["passed"], msg=cmap2["dead_letter_replay_feature"])
            self.assertTrue(cmap2["cross_file_epoch_dedupe_invariant"]["passed"], msg=cmap2["cross_file_epoch_dedupe_invariant"])
            self.assertFalse(cmap2["persist_before_ack_crash_invariant"]["passed"])

            # 4. Trap 3 (leaving commented-out code blocks behind in comment_traps):
            #    STILL passes visible run_checks.py, while grade_cm2 catches tests_and_comment_cleanup!
            trap3 = grade_cm2.prepare_variant_workspace("comment_traps", tmp_path / "trap_comments", repo_root=REPO_ROOT)
            api_trap3 = (trap3 / "api.py").read_text(encoding="utf-8")
            target = (
                "    def replay_dead_letter_batch(self, batch_id: str) -> list[Job]:\n"
                "        # Replay handler placeholder error until implemented\n"
                '        raise JobError(f"replay_dead_letter_batch not yet implemented for {batch_id}")\n'
            )
            self.assertIn(target, api_trap3)
            (trap3 / "api.py").write_text(api_trap3.replace(target, CLEAN_REPLAY_METHOD), encoding="utf-8")
            vis3 = subprocess.run([sys.executable, "-B", str(trap3 / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis3.returncode, 0, msg=vis3.stderr + vis3.stdout)
            rep3 = grade_cm2.grade(trap3, variant="comment_traps")
            self.assertFalse(rep3["passed"])
            self.assertFalse(_check_map(rep3)["tests_and_comment_cleanup"]["passed"])

    def test_cli_fixture_check_and_prepare_variant(self) -> None:
        cli = [sys.executable, "-B", str(REPO_ROOT / "benchmarks" / "graders" / "grade_cm2.py")]
        p_chk = subprocess.run(cli + ["--check-ablation-fixtures"], capture_output=True, text=True, check=False)
        self.assertEqual(p_chk.returncode, 0, msg=p_chk.stderr + p_chk.stdout)
        self.assertTrue(json.loads(p_chk.stdout)["ok"])

        with tempfile.TemporaryDirectory() as tmp:
            p_prep = subprocess.run(
                cli + ["--prepare-variant", "invariant_comments", "--dest", tmp],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(p_prep.returncode, 0, msg=p_prep.stderr + p_prep.stdout)
            out_dir = Path(json.loads(p_prep.stdout)["path"])
            self.assertTrue((out_dir / "worker.py").is_file())
            self.assertTrue((out_dir / "dedupe.py").is_file())
            shutil.rmtree(out_dir)


if __name__ == "__main__":
    unittest.main()
