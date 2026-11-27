"""Stdlib-only tests for continuous model-evaluation orchestrator (scripts/eval_cycle.py)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import eval_cycle  # noqa: E402


class EvalCycleTests(unittest.TestCase):
    def test_scorecard_live_results_json_and_markdown(self) -> None:
        card = eval_cycle.build_scorecard(REPO_ROOT / "results", repo_root=REPO_ROOT)
        self.assertTrue(card["ok"])
        self.assertEqual(card["experiments_count"], 5)
        self.assertEqual(card["total_runs"], 288)
        self.assertEqual(
            card["models"],
            ["claude-opus-5-5", "gemini-4-neon", "gpt-6.2-astra", "gpt-6.2-sol"],
        )

        by_exp = {exp["experiment_id"]: exp for exp in card["experiments"]}
        self.assertIn("pilot-3way-v0.6.0", by_exp)
        self.assertIn("pilot-comments-v0.7.0", by_exp)
        self.assertIn("pilot-evolution-v0.7.0", by_exp)
        self.assertIn("pilot-comments-v0.8.0", by_exp)
        self.assertIn("pilot-ts-evolution-v0.8.0", by_exp)

        # 1. pilot-3way-v0.6.0 pass rates & RW3 frozen-test tampering rates.
        p3 = by_exp["pilot-3way-v0.6.0"]
        self.assertEqual(p3["by_condition"]["baseline"]["passed"], 31)
        self.assertEqual(p3["by_condition"]["baseline"]["total"], 48)
        self.assertEqual(p3["by_condition"]["core-rules-v0.2.0"]["passed"], 40)
        self.assertEqual(p3["by_condition"]["model-controls"]["passed"], 43)
        self.assertEqual(p3["rw3_tampering"]["baseline"]["tampered"], 8)
        self.assertEqual(p3["rw3_tampering"]["baseline"]["completed"], 11)
        self.assertEqual(p3["rw3_tampering"]["core-rules-v0.2.0"]["tampered"], 0)
        self.assertEqual(p3["rw3_tampering"]["model-controls"]["tampered"], 0)

        # 2. pilot-comments-v0.7.0 pass ceiling & CM1 wall-time deltas.
        pcm = by_exp["pilot-comments-v0.7.0"]
        for cond in ("no-comments", "invariant-comments", "comment-traps"):
            self.assertEqual(pcm["by_condition"][cond]["passed"], 12)
            self.assertEqual(pcm["by_condition"][cond]["total"], 12)
        cm_wt = pcm["cm1_wall_time"]["by_condition"]
        self.assertLess(cm_wt["invariant-comments"]["delta_vs_no_comments_pct"], 0.0)
        self.assertGreater(cm_wt["comment-traps"]["delta_vs_no_comments_pct"], 20.0)

        # 3. pilot-evolution-v0.7.0 pass rates, EV1 mutation kill & slop totals.
        pev = by_exp["pilot-evolution-v0.7.0"]
        self.assertEqual(pev["by_condition"]["baseline"]["passed"], 6)
        self.assertEqual(pev["by_condition"]["core-rules-v0.2.0"]["passed"], 5)
        self.assertEqual(pev["by_condition"]["gated-structural"]["passed"], 11)
        ev1_cond = pev["ev1_metrics"]["by_condition"]
        self.assertEqual(ev1_cond["baseline"]["slop_defects_total"], 75)
        self.assertEqual(ev1_cond["core-rules-v0.2.0"]["slop_defects_total"], 45)
        self.assertEqual(ev1_cond["gated-structural"]["slop_defects_total"], 0)
        self.assertGreater(
            ev1_cond["gated-structural"]["mutation_kill_rate_mean"],
            ev1_cond["core-rules-v0.2.0"]["mutation_kill_rate_mean"],
        )

        # 3b. pilot-comments-v0.8.0 (CM2) and pilot-ts-evolution-v0.8.0 (EV2) live v0.8.0 datasets.
        pcm2 = by_exp["pilot-comments-v0.8.0"]
        for cond in ("no-comments", "invariant-comments", "comment-traps"):
            self.assertEqual(pcm2["by_condition"][cond]["passed"], 12)
            self.assertEqual(pcm2["by_condition"][cond]["total"], 12)
        self.assertLess(pcm2["cm1_wall_time"]["by_condition"]["invariant-comments"]["delta_vs_no_comments_pct"], 0.0)

        pev2 = by_exp["pilot-ts-evolution-v0.8.0"]
        self.assertEqual(pev2["by_condition"]["baseline"]["passed"], 7)
        self.assertEqual(pev2["by_condition"]["core-rules-v0.2.0"]["passed"], 8)
        self.assertEqual(pev2["by_condition"]["gated-structural"]["passed"], 12)
        ev2_cond = pev2["ev1_metrics"]["by_condition"]
        self.assertEqual(ev2_cond["baseline"]["slop_defects_total"], 10)
        self.assertEqual(ev2_cond["core-rules-v0.2.0"]["slop_defects_total"], 5)
        self.assertEqual(ev2_cond["gated-structural"]["slop_defects_total"], 0)

        # 4. Rule-retirement watch flags CM1 100% baseline ceiling & EV1 core-rules regression.
        watch = card["rule_retirement_watch"]
        self.assertTrue(
            any(
                w["kind"] == "baseline_ceiling"
                and w["experiment_id"] == "pilot-comments-v0.7.0"
                and w["case_id"] == "CM1"
                for w in watch
            )
        )
        self.assertTrue(
            any(
                w["kind"] == "treatment_regression"
                and w["experiment_id"] == "pilot-evolution-v0.7.0"
                and w["condition"] == "core-rules-v0.2.0"
                for w in watch
            )
        )

        # 5. CLI scorecard works in --json, --markdown, and plain text modes (zero em-dashes).
        cli_base = [sys.executable, "-B", str(REPO_ROOT / "scripts/eval_cycle.py"), "scorecard"]
        p_json = subprocess.run(cli_base + ["--json"], capture_output=True, text=True, check=False)
        self.assertEqual(p_json.returncode, 0, msg=p_json.stderr)
        self.assertEqual(json.loads(p_json.stdout)["total_runs"], 288)

        p_md = subprocess.run(cli_base + ["--markdown"], capture_output=True, text=True, check=False)
        self.assertEqual(p_md.returncode, 0, msg=p_md.stderr)
        self.assertIn("# Longitudinal Model & Rule Scorecard", p_md.stdout)
        self.assertIn("## Rule-Retirement Watch", p_md.stdout)
        self.assertNotIn("\u2014", p_md.stdout)

        p_txt = subprocess.run(cli_base, capture_output=True, text=True, check=False)
        self.assertEqual(p_txt.returncode, 0, msg=p_txt.stderr)
        self.assertIn("pilot-evolution-v0.7.0", p_txt.stdout)

    def test_plan_for_new_and_existing_models_and_error_handling(self) -> None:
        # 1. Unregistered new frontier model across all suites (replicates=3).
        plan_new = eval_cycle.build_plan(
            "anthropic:claude-opus-6-0",
            suites="all",
            replicates=3,
            repo_root=REPO_ROOT,
        )
        self.assertTrue(plan_new["ok"])
        self.assertEqual(plan_new["provider"], "anthropic")
        self.assertEqual(plan_new["model_id"], "claude-opus-6-0")
        self.assertFalse(plan_new["registered_in_runner"])
        self.assertFalse(plan_new["has_model_deltas"])
        self.assertEqual(len(plan_new["suites"]), 3)
        # evolution: 1*3*3=9 runs (36 stages); comments: 1*3*3=9 runs (9 stages);
        # integrity (baseline + core-rules-v0.2.0 without deltas yet): 4*2*3=24 runs (48 stages).
        self.assertEqual(plan_new["total_planned_runs"], 42)
        self.assertEqual(plan_new["total_planned_generation_stages"], 93)
        self.assertTrue(
            any("DEFAULT_MODELS" in item for item in plan_new["manifest_checklist"])
        )
        for suite in plan_new["suites"]:
            self.assertIn("scripts/run_benchmark.py", suite["run_command"])
            self.assertIn("--models claude-opus-6-0", suite["run_command"])
            self.assertIn("--dry-run", suite["dry_run_command"])
            self.assertIn("scripts/benchmark.py", suite["validate_command"])

        # 2. Existing registered model with model_deltas on a single suite.
        plan_existing = eval_cycle.build_plan(
            "openai:gpt-6.2-astra",
            suites="integrity",
            replicates=2,
            repo_root=REPO_ROOT,
        )
        self.assertTrue(plan_existing["registered_in_runner"])
        self.assertTrue(plan_existing["has_model_deltas"])
        self.assertEqual(len(plan_existing["suites"]), 1)
        self.assertEqual(plan_existing["suites"][0]["conditions"], ["baseline", "core-rules-v0.2.0", "model-controls"])
        self.assertEqual(plan_existing["total_planned_runs"], 24)
        self.assertEqual(plan_existing["total_planned_generation_stages"], 48)

        # 3. CLI plan output (--json and plain text) + invalid --model exit code 2.
        cli = [sys.executable, "-B", str(REPO_ROOT / "scripts/eval_cycle.py"), "plan"]
        p_json = subprocess.run(
            cli + ["--model", "google:gemini-5-pro", "--suites", "evolution", "--replicates", "3", "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_json.returncode, 0, msg=p_json.stderr)
        jdata = json.loads(p_json.stdout)
        self.assertEqual(jdata["total_planned_runs"], 9)
        self.assertEqual(jdata["total_planned_generation_stages"], 36)

        p_txt = subprocess.run(
            cli + ["--model", "google:gemini-5-pro", "--suites", "comments", "--replicates", "3"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_txt.returncode, 0, msg=p_txt.stderr)
        self.assertIn("scripts/run_benchmark.py", p_txt.stdout)
        self.assertIn("Manifest & Integrity Checklist:", p_txt.stdout)

        p_bad = subprocess.run(
            cli + ["--model", "missing-provider-colon"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(p_bad.returncode, 2)

        # 4. v0.8.0 TS evolution (EV2) and multi-file comment ablation (CM2) plan suites.
        plan_ev2 = eval_cycle.build_plan(
            "anthropic:claude-opus-5-5",
            suites="ts-evolution",
            replicates=3,
            repo_root=REPO_ROOT,
        )
        self.assertEqual(len(plan_ev2["suites"]), 1)
        self.assertEqual(plan_ev2["suites"][0]["cases"], ["EV2"])
        self.assertEqual(plan_ev2["suites"][0]["pilot_template"], "benchmarks/pilot-ts-evolution-v0.8.0.json")
        self.assertEqual(plan_ev2["total_planned_runs"], 9)
        self.assertEqual(plan_ev2["total_planned_generation_stages"], 36)

        plan_cm2 = eval_cycle.build_plan(
            "openai:gpt-6.2-astra",
            suites="comments-multifile",
            replicates=3,
            repo_root=REPO_ROOT,
        )
        self.assertEqual(len(plan_cm2["suites"]), 1)
        self.assertEqual(plan_cm2["suites"][0]["cases"], ["CM2"])
        self.assertEqual(plan_cm2["suites"][0]["pilot_template"], "benchmarks/pilot-comments-v0.8.0.json")
        self.assertEqual(plan_cm2["total_planned_runs"], 9)
        self.assertEqual(plan_cm2["total_planned_generation_stages"], 9)


if __name__ == "__main__":
    unittest.main()
