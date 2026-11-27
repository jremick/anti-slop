"""Stdlib-only tests for CM1 controlled comment-hygiene ablation fixtures and mechanical grader."""

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

from benchmarks.graders import grade_cm1  # noqa: E402


def _load_benchmark_module():
    spec = importlib.util.spec_from_file_location("benchmark", REPO_ROOT / "scripts" / "benchmark.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _check_map(report: dict) -> dict[str, dict]:
    return {c["id"]: c for c in report["checks"]}


CLEAN_WEBHOOKS_BODY = """from __future__ import annotations

from typing import Any

try:
    from .models import Subscription, WebhookError, WebhookEvent
except ImportError:
    from models import Subscription, WebhookError, WebhookEvent


def compute_fee_cents(amount_cents: int, fee_bps: int) -> int:
    if isinstance(amount_cents, bool) or not isinstance(amount_cents, int) or amount_cents < 0:
        raise WebhookError("amount_cents must be a non-negative integer")
    if isinstance(fee_bps, bool) or not isinstance(fee_bps, int) or fee_bps < 0 or fee_bps > 10000:
        raise WebhookError("fee_bps must be an integer between 0 and 10000")
    # INVARIANT: Keep exact integer half-up cent arithmetic.
    return (amount_cents * fee_bps + 5000) // 10000


class WebhookProcessor:
    def __init__(self) -> None:
        self.subscriptions: dict[str, Subscription] = {}
        self.processed_event_ids: set[str] = set()

    def register_subscription(self, subscription: Subscription) -> None:
        if not isinstance(subscription.subscription_id, str) or not subscription.subscription_id.strip():
            raise WebhookError("subscription_id must be a non-empty string")
        self.subscriptions[subscription.subscription_id] = subscription

    def get_subscription(self, subscription_id: str) -> Subscription:
        if subscription_id not in self.subscriptions:
            raise WebhookError(f"unknown subscription_id: {subscription_id}")
        return self.subscriptions[subscription_id]

    def handle_event(self, event: WebhookEvent) -> dict[str, Any]:
        if not isinstance(event.event_id, str) or not event.event_id.strip():
            raise WebhookError("event_id must be a non-empty string")
        if isinstance(event.created_at, bool) or not isinstance(event.created_at, int) or event.created_at < 0:
            raise WebhookError("created_at must be a non-negative integer")
        sub = self.get_subscription(event.subscription_id)

        if event.event_id in self.processed_event_ids:
            return {
                "applied": False,
                "reason": "duplicate",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.created_at < sub.last_event_at:
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": False,
                "reason": "stale_event",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.event_type == "invoice.paid":
            fee_cents = compute_fee_cents(event.amount_cents, event.fee_bps)
            sub.balance_due_cents = max(0, sub.balance_due_cents - event.amount_cents)
            sub.status = "active"
            sub.failed_attempts = 0
            sub.last_event_at = event.created_at
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": True,
                "reason": "applied",
                "fee_cents": fee_cents,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.event_type == "invoice.payment_failed":
            fee_cents = compute_fee_cents(event.amount_cents, event.fee_bps)
            sub.balance_due_cents += event.amount_cents + fee_cents
            sub.failed_attempts += 1
            sub.status = "past_due"
            sub.last_event_at = event.created_at
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": True,
                "reason": "applied",
                "fee_cents": fee_cents,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        if event.event_type == "subscription.canceled":
            sub.status = "canceled"
            sub.last_event_at = event.created_at
            self.processed_event_ids.add(event.event_id)
            return {
                "applied": True,
                "reason": "applied",
                "fee_cents": 0,
                "subscription_status": sub.status,
                "balance_due_cents": sub.balance_due_cents,
                "failed_attempts": sub.failed_attempts,
            }

        raise WebhookError(f"unsupported event type: {event.event_type}")
"""


class CM1CommentAblationTests(unittest.TestCase):
    def test_case_manifest_and_ablation_fixtures_validate(self) -> None:
        benchmark = _load_benchmark_module()
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        self.assertIn(("CM1", "0.7.0"), cases)
        pilot = benchmark.read_json(REPO_ROOT / "benchmarks" / "pilot-comments-v0.7.0.json")
        validated = benchmark.validate_pilot(pilot, cases, "benchmarks/pilot-comments-v0.7.0.json")
        self.assertEqual(validated["experiment_id"], "pilot-comments-v0.7.0")
        self.assertEqual(validated["conditions"], ["no-comments", "invariant-comments", "comment-traps"])

        fixture_check = grade_cm1.verify_ablation_fixtures(REPO_ROOT)
        self.assertTrue(fixture_check["ok"], msg=fixture_check)
        self.assertTrue(fixture_check["identical_executable_ast"])
        self.assertEqual(fixture_check["comment_counts"]["no_comments"], 0)
        self.assertEqual(fixture_check["comment_counts"]["invariant_comments"], 3)
        self.assertEqual(fixture_check["commented_code_blocks"]["invariant_comments"], 0)
        self.assertGreaterEqual(fixture_check["commented_code_blocks"]["comment_traps"], 2)

    def test_starter_fixtures_fail_grader_and_visible_checks(self) -> None:
        for variant in grade_cm1.VALID_VARIANTS:
            with self.subTest(variant=variant):
                report = grade_cm1.grade(REPO_ROOT, variant=variant)
                self.assertFalse(report["passed"])
                cmap = _check_map(report)
                self.assertFalse(cmap["feature_and_idempotency_verified"]["passed"])
                self.assertTrue(cmap["out_of_order_invariant_preserved"]["passed"] or not cmap["feature_and_idempotency_verified"]["passed"])
                if variant == "comment_traps":
                    self.assertFalse(cmap["commented_code_cleaned_and_readonly_intact"]["passed"])
                else:
                    self.assertTrue(cmap["commented_code_cleaned_and_readonly_intact"]["passed"])

                run_checks = REPO_ROOT / "benchmarks" / "sources" / "cm1_comment_ablation" / variant / "run_checks.py"
                proc = subprocess.run([sys.executable, "-B", str(run_checks)], capture_output=True, text=True, check=False)
                self.assertNotEqual(proc.returncode, 0)

    def test_clean_solution_passes_all_three_variants_and_all_traps_are_caught(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # 1. Clean solution passes all 4 mechanical checks + visible run_checks.py on every variant.
            for variant in grade_cm1.VALID_VARIANTS:
                work = grade_cm1.prepare_variant_workspace(variant, tmp_path / f"clean_{variant}", repo_root=REPO_ROOT)
                (work / "webhooks.py").write_text(CLEAN_WEBHOOKS_BODY, encoding="utf-8")
                vis = subprocess.run(
                    [sys.executable, "-B", str(work / "run_checks.py")],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(vis.returncode, 0, msg=vis.stderr + vis.stdout)
                report = grade_cm1.grade(work, variant=variant)
                self.assertTrue(report["passed"], msg=report)

            # 2. Trap A: Removing the out-of-order guard (trusting the stale comment) STILL passes
            #    visible run_checks.py, while grade_cm1 mechanically catches the invariant break!
            stale_work = grade_cm1.prepare_variant_workspace("comment_traps", tmp_path / "trap_stale", repo_root=REPO_ROOT)
            stale_code = CLEAN_WEBHOOKS_BODY.replace(
                "if event.created_at < sub.last_event_at:",
                "if False and event.created_at < sub.last_event_at:",
            )
            (stale_work / "webhooks.py").write_text(stale_code, encoding="utf-8")
            vis_stale = subprocess.run([sys.executable, "-B", str(stale_work / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis_stale.returncode, 0, msg=vis_stale.stderr)
            rep_stale = grade_cm1.grade(stale_work, variant="comment_traps")
            self.assertFalse(rep_stale["passed"])
            self.assertFalse(_check_map(rep_stale)["out_of_order_invariant_preserved"]["passed"])

            # 3. Trap B: Adopting the commented-out float formula STILL passes visible run_checks.py,
            #    while grade_cm1 mechanically catches integer-cent precision loss!
            float_work = grade_cm1.prepare_variant_workspace("comment_traps", tmp_path / "trap_float", repo_root=REPO_ROOT)
            float_code = CLEAN_WEBHOOKS_BODY.replace(
                "return (amount_cents * fee_bps + 5000) // 10000",
                "return int(amount_cents * (fee_bps / 10000.0))",
            )
            (float_work / "webhooks.py").write_text(float_code, encoding="utf-8")
            vis_float = subprocess.run([sys.executable, "-B", str(float_work / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis_float.returncode, 0, msg=vis_float.stderr)
            rep_float = grade_cm1.grade(float_work, variant="comment_traps")
            self.assertFalse(rep_float["passed"])
            self.assertFalse(_check_map(rep_float)["integer_cent_precision_preserved"]["passed"])

            # 4. Trap C: Leaving a commented-out code block behind STILL passes visible run_checks.py,
            #    while grade_cm1 catches commented-out code cleanup failure!
            cmt_work = grade_cm1.prepare_variant_workspace("comment_traps", tmp_path / "trap_cmt", repo_root=REPO_ROOT)
            cmt_code = (
                CLEAN_WEBHOOKS_BODY
                + "\n# def old_helper(x):\n#     y = x + 1\n#     return y\n"
            )
            (cmt_work / "webhooks.py").write_text(cmt_code, encoding="utf-8")
            vis_cmt = subprocess.run([sys.executable, "-B", str(cmt_work / "run_checks.py")], capture_output=True, text=True, check=False)
            self.assertEqual(vis_cmt.returncode, 0, msg=vis_cmt.stderr)
            rep_cmt = grade_cm1.grade(cmt_work, variant="comment_traps")
            self.assertFalse(rep_cmt["passed"])
            self.assertFalse(_check_map(rep_cmt)["commented_code_cleaned_and_readonly_intact"]["passed"])

            # 5. Trap D: Editing read-only test file fails readonly integrity.
            ro_work = grade_cm1.prepare_variant_workspace("no_comments", tmp_path / "trap_ro", repo_root=REPO_ROOT)
            (ro_work / "webhooks.py").write_text(CLEAN_WEBHOOKS_BODY, encoding="utf-8")
            (ro_work / "tests" / "test_webhooks.py").write_text("# tampered\n", encoding="utf-8")
            rep_ro = grade_cm1.grade(ro_work, variant="no_comments")
            self.assertFalse(rep_ro["passed"])
            self.assertFalse(_check_map(rep_ro)["commented_code_cleaned_and_readonly_intact"]["passed"])

    def test_cli_fixture_check_and_prepare_variant(self) -> None:
        cli = [sys.executable, "-B", str(REPO_ROOT / "benchmarks" / "graders" / "grade_cm1.py")]
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
            self.assertTrue((out_dir / "webhooks.py").is_file())
            shutil.rmtree(out_dir)


if __name__ == "__main__":
    unittest.main()
