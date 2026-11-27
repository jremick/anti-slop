"""Stdlib-only tests for Pillar 2: verified human-gated self-learning loop (gates/learn.py)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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

        # 4. JS/TS private class field `#` in bad_example is NOT stripped as a Python comment.
        ts_store = self.root / ".anti-slop/learned/ts_rules.json"
        (self.root / "src/commented.ts").write_text("// avoid this.#secret here\nexport const ok = 1;\n", encoding="utf-8")
        ts_ent = learn.capture_pattern(
            ts_store,
            title="Ban private secret field",
            bad_example="this.#secret = 'dev'",
            desired_outcome="Read secret from KMS",
            valid_neighbouring_case="this.config = loadKms()",
            file_glob="*.ts",
        )
        learn.propose_prevention(
            ts_store, ts_ent["id"], layer="deterministic_check", severity="error",
            file_glob="*.ts", pattern=r"this\.#secret",
            remediation="Load from KMS.", retirement_trigger="KMS migration complete.",
        )
        ver_ts = learn.verify_rule(ts_store, ts_ent["id"], repo_root=self.root)
        self.assertTrue(ver_ts["verification"]["passed"], msg=ver_ts["verification"])

        # 5. Negative max_repo_hits and missing --bad-file fail cleanly with LearnError / exit 2.
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

    def test_library_list_show_enable_dry_run_dedup_and_verification_gate(self) -> None:
        cli = [
            sys.executable, "-B", str(REPO_ROOT / "gates/learn.py"),
            "--store", str(self.store), "--repo-root", str(self.root),
        ]

        # 1. library list & show (human + JSON)
        p_list = subprocess.run(cli + ["library", "list", "--json"], capture_output=True, text=True, check=False)
        self.assertEqual(p_list.returncode, 0, msg=p_list.stderr)
        list_data = json.loads(p_list.stdout)
        self.assertEqual(len(list_data["optional_packs"]), 6)
        self.assertEqual(list_data["excluded_count"], 6)

        p_show_pack = subprocess.run(cli + ["library", "show", "network-timeouts"], capture_output=True, text=True, check=False)
        self.assertEqual(p_show_pack.returncode, 0, msg=p_show_pack.stderr)
        self.assertIn("OPT-NET-01", p_show_pack.stdout)
        self.assertIn("OPT-NET-02", p_show_pack.stdout)
        self.assertIn("Valid neighbouring case:", p_show_pack.stdout)

        p_show_rule = subprocess.run(cli + ["library", "show", "OPT-SEC-01", "--json"], capture_output=True, text=True, check=False)
        self.assertEqual(p_show_rule.returncode, 0, msg=p_show_rule.stderr)
        self.assertEqual(json.loads(p_show_rule.stdout)["rule"]["id"], "OPT-SEC-01")

        # 2. --dry-run runs full 3-way verification without creating or modifying store.
        p_dry = subprocess.run(
            cli + ["library", "enable", "network-timeouts", "--by", "alice", "--dry-run", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_dry.returncode, 0, msg=p_dry.stderr + p_dry.stdout)
        dry_data = json.loads(p_dry.stdout)
        self.assertTrue(dry_data["ok"])
        self.assertTrue(dry_data["dry_run"])
        self.assertEqual(dry_data["enabled_count"], 2)
        self.assertFalse(self.store.exists())

        # 3. Real enable imports, verifies, approves, and enforces immediately!
        p_en = subprocess.run(
            cli + ["library", "enable", "network-timeouts", "--by", "alice", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_en.returncode, 0, msg=p_en.stderr + p_en.stdout)
        en_data = json.loads(p_en.stdout)
        self.assertTrue(en_data["ok"])
        self.assertEqual(en_data["enabled_count"], 2)
        self.assertTrue(self.store.is_file())

        bad_http_diff = (
            "diff --git a/src/client.py b/src/client.py\n"
            "--- /dev/null\n"
            "+++ b/src/client.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def ping():\n"
            "+    return requests.get('https://api.example.com/health')\n"
        )
        diff_res = diff_check.check_diff(
            bad_http_diff, repo_root=self.root, no_budget=True, learned_rules=self.store
        )
        self.assertIn("LEARNED-L-001", _codes(diff_res["warnings"]))

        # 4. Re-enabling skips already-active duplicates cleanly with 0 new entries!
        p_dup = subprocess.run(
            cli + ["library", "enable", "network-timeouts", "--by", "alice", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_dup.returncode, 0, msg=p_dup.stderr)
        dup_data = json.loads(p_dup.stdout)
        self.assertEqual(dup_data["enabled_count"], 0)
        self.assertEqual(dup_data["skipped_count"], 2)
        self.assertEqual(len(learn.load_store(self.store)["rules"]), 2)

        # 5. Enabling a prompt_rule pack exports cleanly via export-prompt.
        p_cmt = subprocess.run(
            cli + ["library", "enable", "comment-hygiene", "--by", "alice", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_cmt.returncode, 0, msg=p_cmt.stderr + p_cmt.stdout)
        exported = learn.export_approved_prompt_rules(self.store)
        self.assertIn("OPT-CMT-01", exported)

        # 6. Verification gate is NEVER bypassed: existing repo match blocks enable cleanly
        #    and reports exact file:line hits without mutating the store!
        (self.root / "src/deploy.py").write_text(
            "import subprocess\nsubprocess.run('ls -la', shell=True, check=True)\n",
            encoding="utf-8",
        )
        store_before = self.store.read_text(encoding="utf-8")
        p_fail = subprocess.run(
            cli + ["library", "enable", "security-boundaries", "--by", "alice"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_fail.returncode, 1, msg=p_fail.stdout + p_fail.stderr)
        self.assertIn("src/deploy.py:2", p_fail.stdout)
        self.assertIn("verification_failed", p_fail.stdout)
        self.assertEqual(self.store.read_text(encoding="utf-8"), store_before)

        # Explicit --max-repo-hits 1 allows enabling when user acknowledges the existing hit.
        p_allow = subprocess.run(
            cli + ["library", "enable", "OPT-SEC-01", "--by", "alice", "--max-repo-hits", "1", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_allow.returncode, 0, msg=p_allow.stdout + p_allow.stderr)
        self.assertEqual(json.loads(p_allow.stdout)["enabled_count"], 1)

        # 7. Retiring an enabled library rule allows re-enabling under a new ID without reusing old ID.
        learn.retire_rule(self.store, "L-001", reason="Temporary pause for migration.")
        p_reen = subprocess.run(
            cli + ["library", "enable", "OPT-NET-01", "--by", "alice", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_reen.returncode, 0, msg=p_reen.stdout + p_reen.stderr)
        reen_data = json.loads(p_reen.stdout)
        self.assertEqual(reen_data["enabled_count"], 1)
        self.assertNotEqual(reen_data["results"][0]["learned_id"], "L-001")

        # 8. Excluded IDs cannot be enabled (exit 2).
        p_excl = subprocess.run(
            cli + ["library", "enable", "EXCL-01", "--by", "alice"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_excl.returncode, 2)

    def _init_git_repo(self, repo_dir: Path) -> None:
        env_cmds = [
            ["git", "init"],
            ["git", "config", "user.email", "test@example.com"],
            ["git", "config", "user.name", "Test Author"],
        ]
        for cmd in env_cmds:
            proc = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

    def _git_commit(self, repo_dir: Path, message: str) -> str:
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        )
        sha = subprocess.run(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return sha

    def test_mine_telemetry_malformed_tolerance_retirement_and_read_only(self) -> None:
        # Prepare two approved rules: L-001 (stale, zero hits) and L-002 (active, recent hits).
        for title, bad, valid, pat in (
            ("No float money", "x = float(cents)\n", "x = float(sec)\n", r"\bfloat\s*\(\s*cents\s*\)"),
            ("No debug print", "print('DEBUG:', x)\n", "logger.debug('%s', x)\n", r"print\(['\"]DEBUG:"),
        ):
            ent = learn.capture_pattern(
                self.store,
                title=title,
                bad_example=bad,
                desired_outcome="Follow repo convention.",
                valid_neighbouring_case=valid,
            )
            learn.propose_prevention(
                self.store,
                ent["id"],
                layer="deterministic_check",
                severity="error",
                pattern=pat,
                remediation="Fix pattern.",
                retirement_trigger="Retire once static linter enforces this.",
            )
            learn.verify_rule(self.store, ent["id"], repo_root=self.root)
            learn.approve_rule(self.store, ent["id"], approved_by="alice")

        # Backdate L-001 approval to 90 days ago; keep L-002 recent.
        now_dt = datetime(2026, 11, 27, 12, 0, 0, tzinfo=timezone.utc)
        old_ts = (now_dt - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent_ts = (now_dt - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        raw_store = json.loads(self.store.read_text(encoding="utf-8"))
        raw_store["rules"][0]["approval"]["approved_at"] = old_ts
        raw_store["rules"][1]["approval"]["approved_at"] = old_ts
        self.store.write_text(json.dumps(raw_store, indent=2) + "\n", encoding="utf-8")
        store_snapshot_before = self.store.read_text(encoding="utf-8")

        # Write telemetry JSONL with valid records + malformed lines + non-dict JSON.
        telemetry_file = self.root / ".anti-slop/telemetry.jsonl"
        telemetry_lines = [
            json.dumps({
                "ts": recent_ts,
                "event": "stop_hook",
                "harness": "claude",
                "blocked": True,
                "codes": ["DIFF-TEST-SKIP", "LEARNED-L-002"],
                "file_exts": [".py"],
            }),
            "{this is broken json",
            "[1, 2, 3]",
            "",
            json.dumps({
                "ts": recent_ts,
                "event": "pretool_hook",
                "harness": "codex",
                "blocked": True,
                "codes": ["DIFF-TEST-SKIP"],
                "file_exts": [".py"],
            }),
            json.dumps({
                "ts": recent_ts,
                "event": "review",
                "harness": "antigravity",
                "blocked": False,
                "codes": ["STRUCT-GOD-FUNCTION"],
                "file_exts": [".py"],
            }),
        ]
        telemetry_file.write_text("\n".join(telemetry_lines) + "\n", encoding="utf-8")

        report = learn.mine_patterns(
            self.root,
            store_path=self.store,
            telemetry_path=telemetry_file,
            commits=10,
            stale_days=60,
            now=now_dt,
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["read_only"])

        tsum = report["telemetry_summary"]
        self.assertTrue(tsum["exists"])
        self.assertEqual(tsum["records_parsed"], 3)
        self.assertEqual(tsum["malformed_lines"], 2)
        self.assertEqual(tsum["blocked_events"], 2)
        self.assertEqual(tsum["allowed_events"], 1)
        self.assertEqual(tsum["code_counts"]["DIFF-TEST-SKIP"], 2)

        # Recurring patterns flags DIFF-TEST-SKIP (count=2), not single-hit STRUCT-GOD-FUNCTION.
        rec_codes = {item["code"]: item for item in report["recurring_patterns"]}
        self.assertIn("DIFF-TEST-SKIP", rec_codes)
        self.assertEqual(rec_codes["DIFF-TEST-SKIP"]["telemetry_count"], 2)
        self.assertNotIn("STRUCT-GOD-FUNCTION", rec_codes)

        # Retirement candidates flags L-001 (90d old, 0 hits), NOT L-002 (hit 2 days ago).
        ret_ids = [c["id"] for c in report["retirement_candidates"]]
        self.assertEqual(ret_ids, ["L-001"])
        self.assertEqual(report["retirement_candidates"][0]["telemetry_hits"], 0)
        self.assertGreaterEqual(report["retirement_candidates"][0]["age_days"], 89.0)

        # Strict read-only guarantee: rules.json is untouched byte-for-byte.
        self.assertEqual(self.store.read_text(encoding="utf-8"), store_snapshot_before)

    def test_mine_git_history_recommends_opt_pack_detects_churn_and_cli_works(self) -> None:
        self._init_git_repo(self.root)
        self._git_commit(self.root, "chore: initial commit")

        # Commit 1: adds Python requests.get without timeout + bare type: ignore suppression.
        (self.root / "src/http_client.py").write_text(
            "import requests\n\n"
            "def fetch_status():\n"
            "    return requests.get('https://api.example.com/status')  # type: ignore\n",
            encoding="utf-8",
        )
        sha1 = self._git_commit(self.root, "fix: fetch remote status")

        # Commit 2: second commit with requests.post without timeout + second bare type: ignore.
        (self.root / "src/http_client.py").write_text(
            "import requests\n\n"
            "def fetch_status():\n"
            "    return requests.get('https://api.example.com/status')  # type: ignore\n\n"
            "def push_event(body):\n"
            "    return requests.post('https://api.example.com/events')  # type: ignore\n",
            encoding="utf-8",
        )
        sha2 = self._git_commit(self.root, "fix: push event payload")

        # Store does not exist yet — mine must NEVER create it!
        self.assertFalse(self.store.exists())

        cli = [
            sys.executable, "-B", str(REPO_ROOT / "gates/learn.py"),
            "mine", "--repo-root", str(self.root), "--store", str(self.store),
            "--commits", "10", "--stale-days", "60",
        ]
        proc_json = subprocess.run(cli + ["--json"], capture_output=True, text=True, check=False)
        self.assertEqual(proc_json.returncode, 0, msg=proc_json.stderr)
        data = json.loads(proc_json.stdout)

        # Store still does not exist (strict read-only guarantee).
        self.assertFalse(self.store.exists())
        self.assertTrue(data["read_only"])

        # Recommends uninstalled `network-timeouts` pack with exact commit count & SHAs.
        packs = {p["pack_id"]: p for p in data["recommended_library_packs"]}
        self.assertIn("network-timeouts", packs)
        net_pack = packs["network-timeouts"]
        self.assertEqual(net_pack["matched_commits_count"], 2)
        self.assertIn(sha1, net_pack["sample_commits"])
        self.assertIn(sha2, net_pack["sample_commits"])
        self.assertEqual(net_pack["matched_rules"][0]["id"], "OPT-NET-01")

        # Detects recurring DIFF-SUPPRESSION across 2 commits + fix churn on src/http_client.py.
        rec_codes = {r["code"]: r for r in data["recurring_patterns"]}
        self.assertIn("DIFF-SUPPRESSION", rec_codes)
        self.assertEqual(rec_codes["DIFF-SUPPRESSION"]["git_commit_count"], 2)
        self.assertEqual(data["git_summary"]["fix_commit_count"], 2)
        self.assertTrue(
            any(f["file"] == "src/http_client.py" for f in data["git_summary"]["high_churn_files"])
        )
        self.assertTrue(data["suggested_next_steps"])

        # Human-readable CLI output also works cleanly.
        proc_txt = subprocess.run(cli, capture_output=True, text=True, check=False)
        self.assertEqual(proc_txt.returncode, 0, msg=proc_txt.stderr)
        self.assertIn("network-timeouts", proc_txt.stdout)
        self.assertIn("Read-only check:", proc_txt.stdout)

        # Once OPT-NET-01 is enabled in store, mine stops recommending network-timeouts.
        learn.enable_library_rules(
            self.store,
            "OPT-NET-01",
            approved_by="alice",
            repo_root=self.root,
            max_repo_hits=5,
        )
        after = learn.mine_patterns(self.root, store_path=self.store, commits=10)
        after_packs = {p["pack_id"] for p in after["recommended_library_packs"]}
        self.assertNotIn("network-timeouts", after_packs)

        # Negative --commits / --stale-days fail cleanly with exit 2.
        bad_cli = subprocess.run(
            [sys.executable, "-B", str(REPO_ROOT / "gates/learn.py"), "mine", "--commits", "-1"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(bad_cli.returncode, 2)


if __name__ == "__main__":
    unittest.main()
