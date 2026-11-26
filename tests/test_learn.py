"""Stdlib-only tests for Pillar 2: verified human-gated self-learning loop (gates/learn.py)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gates import diff_check  # noqa: E402
from gates import learn  # noqa: E402
from gates import review  # noqa: E402


def _codes(items) -> set[str]:
    return {item["code"] for item in items}


class SelfLearningLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src/money.py").write_text(
            "def add_cents(a: int, b: int) -> int:\n    return a + b\n",
            encoding="utf-8",
        )
        self.store = self.root / ".anti-slop/learned/rules.json"

    def test_full_lifecycle_capture_propose_verify_approve_enforce_retire(self) -> None:
        # 1. Capture a slipped slop pattern (using float() for money calculations).
        cap = learn.capture_pattern(
            self.store,
            title="Float math on money amounts",
            bad_example="total_dollars = float(cents) / 100.0\n",
            desired_outcome="Use integer cents or Decimal for currency math.",
            valid_neighbouring_case="ratio = float(elapsed_ms) / 1000.0\n",
            why_it_matters="Float rounding silently drops pennies in billing totals.",
            file_glob="*.py",
        )
        self.assertEqual(cap["id"], "L-001")
        self.assertEqual(cap["status"], "captured")

        # Suggest recommends deterministic_check first.
        sug = learn.suggest_prevention(cap)
        self.assertEqual(sug["recommended_layer"], "deterministic_check")
        self.assertTrue(sug["candidate_pattern"])

        # Cannot approve before propose + verify!
        with self.assertRaises(learn.LearnError):
            learn.approve_rule(self.store, "L-001", approved_by="reviewer")

        # 2. Propose a deterministic regex check.
        prop = learn.propose_prevention(
            self.store,
            "L-001",
            layer="deterministic_check",
            severity="error",
            pattern=r"\bfloat\s*\(\s*\w*(?:cent|dollar|price|amount)\w*\s*\)",
            remediation="Keep monetary math in integer cents or Decimal.",
            retirement_trigger="Retire once mypy custom NewType(Cents) enforces integer-only math.",
        )
        self.assertEqual(prop["status"], "proposed")

        # Cannot approve before verify!
        with self.assertRaises(learn.LearnError):
            learn.approve_rule(self.store, "L-001", approved_by="reviewer")

        # Unapproved rule is NOT enforced yet.
        bad_diff = (
            "diff --git a/src/checkout.py b/src/checkout.py\n"
            "--- /dev/null\n"
            "+++ b/src/checkout.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def bill(amount_cents):\n"
            "+    return float(amount_cents) / 100.0\n"
        )
        pre_res = learn.check_learned_rules_in_diff(bad_diff, self.store, repo_root=self.root)
        self.assertTrue(pre_res["ok"])
        self.assertEqual(pre_res["errors"], [])

        # 3. Verify against bad case, valid neighbour, AND existing repo.
        ver = learn.verify_rule(self.store, "L-001", repo_root=self.root)
        self.assertEqual(ver["status"], "verified")
        self.assertTrue(ver["verification"]["passed"])
        self.assertTrue(ver["verification"]["bad_case_caught"])
        self.assertTrue(ver["verification"]["valid_neighbour_clean"])
        self.assertEqual(ver["verification"]["repo_scan_hits"], 0)
        self.assertGreaterEqual(ver["verification"]["repo_scan_files"], 1)

        # 4. Human approval activates enforcement.
        app = learn.approve_rule(
            self.store, "L-001", approved_by="maintainer", note="Verified clean on repo."
        )
        self.assertEqual(app["status"], "approved")

        # Now enforced in learn.check, diff_check --learned-rules, AND review.review_diff (auto-detected)!
        post_res = diff_check.check_diff(
            bad_diff,
            repo_root=self.root,
            no_budget=True,
            learned_rules=self.store,
        )
        self.assertFalse(post_res["ok"])
        self.assertIn("LEARNED-L-001", _codes(post_res["errors"]))

        rev_res = review.review_diff(bad_diff, repo_root=self.root)
        self.assertFalse(rev_res["ok"])
        self.assertIn("LEARNED-L-001", _codes(rev_res["errors"]))
        learned_err = next(e for e in rev_res["errors"] if e["code"] == "LEARNED-L-001")
        self.assertIn("Float math on money amounts", learned_err["explanation"]["title"])

        # Valid neighbouring diff passes cleanly!
        good_diff = (
            "diff --git a/src/metrics.py b/src/metrics.py\n"
            "--- /dev/null\n"
            "+++ b/src/metrics.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def seconds(elapsed_ms):\n"
            "+    return float(elapsed_ms) / 1000.0\n"
        )
        good_res = diff_check.check_diff(
            good_diff, repo_root=self.root, no_budget=True, learned_rules=self.store
        )
        self.assertTrue(good_res["ok"], msg=good_res["errors"])

        # 5. Retire L-001: stops enforcing, keeps captured regression examples, leaves ID gap forever!
        ret = learn.retire_rule(
            self.store, "L-001", reason="Replaced by strict Cents static type."
        )
        self.assertEqual(ret["status"], "retired")
        self.assertIn("float(cents)", ret["captured"]["bad_example"])

        after_retire = diff_check.check_diff(
            bad_diff, repo_root=self.root, no_budget=True, learned_rules=self.store
        )
        self.assertTrue(after_retire["ok"])

        # Next capture gets L-002 (never reuses L-001!).
        cap2 = learn.capture_pattern(
            self.store,
            title="Another pattern",
            bad_example="x = eval(user_input)\n",
            desired_outcome="Use ast.literal_eval or json.loads.",
            valid_neighbouring_case="x = json.loads(user_input)\n",
        )
        self.assertEqual(cap2["id"], "L-002")

        # Cannot re-approve or re-propose a retired rule.
        with self.assertRaises(learn.LearnError):
            learn.approve_rule(self.store, "L-001", approved_by="maintainer")

    def test_verification_rejects_bad_miss_valid_fp_and_repo_fp(self) -> None:
        # Repo already contains `legacy_call()` in src/existing.py.
        (self.root / "src/existing.py").write_text("val = helper_call(1)\n", encoding="utf-8")

        learn.capture_pattern(
            self.store,
            title="Test verification gates",
            bad_example="res = bad_call(1)\n",
            desired_outcome="Use safe_call.",
            valid_neighbouring_case="res = safe_call(1)\n",
        )

        # Case A: pattern misses bad_example.
        learn.propose_prevention(
            self.store, "L-001", layer="deterministic_check",
            pattern=r"\bnever_matches_anything\b",
            remediation="fix", retirement_trigger="never",
        )
        v_miss = learn.verify_rule(self.store, "L-001", repo_root=self.root)
        self.assertEqual(v_miss["status"], "verification_failed")
        self.assertFalse(v_miss["verification"]["bad_case_caught"])

        # Case B: pattern falsely matches valid_neighbouring_case.
        learn.propose_prevention(
            self.store, "L-001", layer="deterministic_check",
            pattern=r"_call\(",
            remediation="fix", retirement_trigger="never",
        )
        v_fp = learn.verify_rule(self.store, "L-001", repo_root=self.root)
        self.assertEqual(v_fp["status"], "verification_failed")
        self.assertFalse(v_fp["verification"]["valid_neighbour_clean"])

        # Case C: pattern matches existing repo file (> max_repo_hits=0).
        learn.capture_pattern(
            self.store,
            title="Repo FP check",
            bad_example="val = helper_call(1)\n",
            desired_outcome="Avoid helper_call.",
            valid_neighbouring_case="val = new_call(1)\n",
        )
        learn.propose_prevention(
            self.store, "L-002", layer="deterministic_check",
            pattern=r"\bhelper_call\(",
            remediation="Use new_call.", retirement_trigger="After migration.",
        )
        v_repo = learn.verify_rule(self.store, "L-002", repo_root=self.root, max_repo_hits=0)
        self.assertEqual(v_repo["status"], "verification_failed")
        self.assertEqual(v_repo["verification"]["repo_scan_hits"], 1)
        self.assertTrue(any("src/existing.py:1" in s for s in v_repo["verification"]["repo_sample_hits"]))

        # Overbroad catch-all regex is rejected at proposal time.
        with self.assertRaises(learn.LearnError):
            learn.propose_prevention(
                self.store, "L-001", layer="deterministic_check",
                pattern=".*", remediation="fix", retirement_trigger="later",
            )

    def test_tampered_approved_rule_fails_closed_and_prompt_rule_guards_work(self) -> None:
        # 1. Tampering with pattern after approval disables enforcement (fail-closed).
        learn.capture_pattern(
            self.store,
            title="No raw eval",
            bad_example="x = eval(s)\n",
            desired_outcome="Use json.loads.",
            valid_neighbouring_case="x = json.loads(s)\n",
        )
        learn.propose_prevention(
            self.store, "L-001", layer="deterministic_check",
            pattern=r"\beval\s*\(", remediation="Use json.loads.", retirement_trigger="Always.",
        )
        learn.verify_rule(self.store, "L-001", repo_root=self.root)
        learn.approve_rule(self.store, "L-001", approved_by="alice")
        self.assertEqual(len(learn.load_active_deterministic_rules(self.store)), 1)

        # Mutate pattern directly in JSON without re-verifying/re-approving.
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        raw["rules"][0]["proposal"]["pattern"] = r"\bexec\s*\("
        self.store.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        self.assertEqual(learn.load_active_deterministic_rules(self.store), [])

        # 2. Prompt rule requires why_not_deterministic and <= 45 words.
        learn.capture_pattern(
            self.store,
            title="Check business invariant before caching",
            bad_example="# cached error response",
            desired_outcome="Only cache validated 2xx responses.",
            valid_neighbouring_case="# cached verified 200 payload",
        )
        with self.assertRaises(learn.LearnError):
            learn.propose_prevention(
                self.store, "L-002", layer="prompt_rule",
                rule_text="Never cache non-2xx responses.",
                why_not_deterministic="",
                remediation="Validate status before cache write.",
                retirement_trigger="Once cache client enforces typed OkResponse.",
            )
        with self.assertRaises(learn.LearnError):
            learn.propose_prevention(
                self.store, "L-002", layer="prompt_rule",
                rule_text=" ".join(["word"] * 50),
                why_not_deterministic="Semantic HTTP flow spans multiple helper calls.",
                remediation="Validate status.",
                retirement_trigger="Typed cache wrapper.",
            )

        learn.propose_prevention(
            self.store, "L-002", layer="prompt_rule",
            rule_text="Only write to the response cache after verifying an HTTP 2xx status unless explicitly caching a documented negative lookup.",
            why_not_deterministic="Status check and cache write can live across different helper modules.",
            remediation="Gate cache writes on verified 2xx status.",
            retirement_trigger="Retire once CacheClient.put requires VerifiedResponse type.",
        )
        ver = learn.verify_rule(self.store, "L-002", repo_root=self.root)
        self.assertEqual(ver["status"], "verified")
        self.assertFalse(ver["verification"]["mechanical"])
        learn.approve_rule(self.store, "L-002", approved_by="alice")
        exported = learn.export_approved_prompt_rules(self.store)
        self.assertIn("L-002", exported)
        self.assertIn("standard/core.md", exported)

    def test_cli_end_to_end_workflow(self) -> None:
        cli = [sys.executable, "-B", str(REPO_ROOT / "gates/learn.py"), "--store", str(self.store), "--repo-root", str(self.root)]

        p1 = subprocess.run(
            cli + [
                "capture", "--title", "Ban print debugging",
                "--bad-code", "print('DEBUG:', payload)\n",
                "--desired", "Use structured logging instead of DEBUG prints.",
                "--valid-code", "logger.debug('payload=%s', payload)\n",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p1.returncode, 0, msg=p1.stderr)
        self.assertIn("L-001", p1.stdout)

        p2 = subprocess.run(
            cli + [
                "propose", "L-001", "--layer", "deterministic_check",
                "--severity", "error", "--pattern", r"print\(['\"]DEBUG:",
                "--remediation", "Replace print('DEBUG:...') with logger.debug.",
                "--retirement-trigger", "Retire once ruff T201 is enforced.",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p2.returncode, 0, msg=p2.stderr)

        p3 = subprocess.run(cli + ["verify", "L-001"], capture_output=True, text=True, check=False)
        self.assertEqual(p3.returncode, 0, msg=p3.stdout + p3.stderr)
        self.assertIn("Verification PASSED", p3.stdout)

        p4 = subprocess.run(
            cli + ["approve", "L-001", "--by", "maintainer"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p4.returncode, 0, msg=p4.stderr)

        bad_file = self.root / "src/noisy.py"
        bad_file.write_text("print('DEBUG:', 123)\n", encoding="utf-8")
        p5 = subprocess.run(
            cli + ["check", "--files", "src/noisy.py", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p5.returncode, 1)
        self.assertIn("LEARNED-L-001", _codes(json.loads(p5.stdout)["errors"]))

        p6 = subprocess.run(
            cli + ["retire", "L-001", "--reason", "Ruff T201 now enabled."],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p6.returncode, 0, msg=p6.stderr)

        p7 = subprocess.run(cli + ["list"], capture_output=True, text=True, check=False)
        self.assertEqual(p7.returncode, 0)
        self.assertIn("retired", p7.stdout)

    def test_unverified_forged_approval_glob_doublestar_and_comment_scoping(self) -> None:
        # 1. Forged approval (status='approved' + matching approved_proposal_sha256, but verification=None)
        #    MUST fail closed in both load_active_deterministic_rules and export_approved_prompt_rules!
        learn.capture_pattern(
            self.store,
            title="No eval",
            bad_example="x = eval(s)\n",
            desired_outcome="Use json.loads.",
            valid_neighbouring_case="x = json.loads(s)\n",
        )
        learn.propose_prevention(
            self.store, "L-001", layer="deterministic_check",
            pattern=r"\beval\s*\(", remediation="Use json.loads.", retirement_trigger="Always.",
        )
        raw = json.loads(self.store.read_text(encoding="utf-8"))
        prop_hash = raw["rules"][0]["proposal"]["proposal_sha256"]
        raw["rules"][0]["status"] = "approved"
        raw["rules"][0]["verification"] = None
        raw["rules"][0]["approval"] = {
            "approved_by": "forger",
            "approved_at": "2026-11-26T00:00:00Z",
            "note": "",
            "approved_proposal_sha256": prop_hash,
        }
        self.store.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        self.assertEqual(learn.load_active_deterministic_rules(self.store), [])

        # Also fail closed if approved_by is blank even when verification passed.
        raw["rules"][0]["verification"] = {"passed": True, "proposal_sha256": prop_hash}
        raw["rules"][0]["approval"]["approved_by"] = "   "
        self.store.write_text(json.dumps(raw, indent=2), encoding="utf-8")
        self.assertEqual(learn.load_active_deterministic_rules(self.store), [])

        # 2. Recursive ** globs match zero or more intermediate directories.
        self.assertTrue(learn._matches_file_glob("src/app.py", "src/**/*.py"))
        self.assertTrue(learn._matches_file_glob("src/a/b/app.py", "src/**/*.py"))
        self.assertFalse(learn._matches_file_glob("other/app.py", "src/**/*.py"))
        self.assertTrue(learn._matches_file_glob("app.py", "**/*.py"))

        # 3. Code-targeting rules ignore comments during verify & check, while comment-targeting rules still fire.
        (self.root / "src/commented.py").write_text(
            "# Never use float(cents) here; keep integer cents.\nvalue = 100\n",
            encoding="utf-8",
        )
        store2 = self.root / ".anti-slop/learned/rules2.json"
        learn.capture_pattern(
            store2,
            title="No float money",
            bad_example="x = float(cents) / 100.0\n",
            desired_outcome="Use integer cents.",
            valid_neighbouring_case="x = float(seconds)\n",
        )
        learn.propose_prevention(
            store2, "L-001", layer="deterministic_check", severity="error",
            pattern=r"\bfloat\s*\(\s*cents\s*\)",
            remediation="Use integer cents.", retirement_trigger="Static Cents type.",
        )
        ver_code = learn.verify_rule(store2, "L-001", repo_root=self.root)
        self.assertTrue(ver_code["verification"]["passed"], msg=ver_code["verification"])
        learn.approve_rule(store2, "L-001", approved_by="alice")
        comment_only_res = learn.check_learned_rules_in_files(
            ["src/commented.py"], store2, repo_root=self.root
        )
        self.assertTrue(comment_only_res["ok"], msg=comment_only_res)

        # Comment-targeting rule (`# HACK:`) still matches comments!
        learn.capture_pattern(
            store2,
            title="Ban HACK markers",
            bad_example="# HACK: temporary bypass\n",
            desired_outcome="Resolve hacks before merging.",
            valid_neighbouring_case="# Note: verified boundary\n",
        )
        learn.propose_prevention(
            store2, "L-002", layer="deterministic_check", severity="error",
            pattern=r"#\s*HACK:",
            remediation="Fix properly instead of HACK comment.", retirement_trigger="Never.",
        )
        ver_cmt = learn.verify_rule(store2, "L-002", repo_root=self.root)
        self.assertTrue(ver_cmt["verification"]["passed"], msg=ver_cmt["verification"])
        learn.approve_rule(store2, "L-002", approved_by="alice")
        (self.root / "src/hacky.py").write_text("# HACK: skip auth\n", encoding="utf-8")
        hack_res = learn.check_learned_rules_in_files(["src/hacky.py"], store2, repo_root=self.root)
        self.assertFalse(hack_res["ok"])
        self.assertIn("LEARNED-L-002", _codes(hack_res["errors"]))

        # 4. Negative max_repo_hits and missing --bad-file fail cleanly with LearnError / exit 2.
        with self.assertRaises(learn.LearnError):
            learn.verify_rule(store2, "L-001", repo_root=self.root, max_repo_hits=-1)
        bad_cli = subprocess.run(
            [
                sys.executable, "-B", str(REPO_ROOT / "gates/learn.py"),
                "--store", str(store2), "capture",
                "--title", "T", "--bad-file", str(self.root / "missing.py"),
                "--desired", "D", "--valid-code", "ok = 1",
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad_cli.returncode, 2)


if __name__ == "__main__":
    unittest.main()
