"""Risk-focused tests of evidence validation and honest paired reporting.

All inputs are artificial and created in temporary directories. These tests do
not run models and are not benchmark results.
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "benchmark.py"
SPEC = importlib.util.spec_from_file_location("benchmark", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name, content in {
            "baseline.txt": "Original instructions, retained verbatim.\n",
            "baseline-alt.txt": "Provider-native harness baseline for second model.\n",
            "core.txt": "Seven-rule candidate, frozen for this experiment.\n",
            "core-v0.1.0.txt": "Candidate standard v0.1.0 snapshot.\n",
            "core-v0.2.0.txt": "Candidate standard v0.2.0 snapshot.\n",
            "model-controls-a.txt": "Core rules plus model A delta.\n",
            "model-controls-b.txt": "Core rules plus model B delta.\n",
            "output.txt": "A fixture artifact, not a model result.\n",
            "stage1.txt": "Stage 1 fixture output.\n",
            "stage2.txt": "Stage 2 fixture output.\n",
            "stage3.txt": "Stage 3 final fixture output.\n",
            "review.txt": "A fixture review record, not an actual verification.\n",
            "blocker.log": "HTTP 503 provider timeout log fixture.\n",
        }.items():
            (self.root / name).write_text(content, encoding="utf-8")
        self.case = {
            "schema_version": 1, "case_id": "fixture", "version": "1.0.0",
            "domain": "writing", "title": "Temporary test case", "prompt": "Complete both requirements.",
            "origin": "constructed", "evidence_sources": [],
            "acceptance_checks": [
                {"id": "complete", "description": "Both requirements met", "required": True},
                {"id": "grounded", "description": "Material claims supported", "required": True},
            ],
        }
        self.lineage_case = {
            "schema_version": 1, "case_id": "fixture-chain", "version": "1.0.0",
            "domain": "writing", "title": "Temporary 3-stage lineage case",
            "prompt": "Stage 1 prompt.",
            "origin": "constructed", "evidence_sources": [],
            "acceptance_checks": [
                {"id": "stage1", "description": "Stage 1 check", "required": True},
                {"id": "stage3", "description": "Stage 3 check", "required": True},
            ],
            "lineage_steps": [
                "Stage 1 prompt.",
                "Stage 2 prompt.",
                "Stage 3 prompt.",
            ],
        }
        self.cases = {
            ("fixture", "1.0.0"): self.case,
            ("fixture-chain", "1.0.0"): self.lineage_case,
        }

    def run_record(
        self,
        condition: str = "baseline",
        replicate: int = 1,
        synthetic: bool = False,
        *,
        case: dict | None = None,
        source: str | None = None,
        provider: str = "test",
        model_id: str = "not-a-real-model",
        run_id: str | None = None,
    ) -> dict:
        target_case = case if case is not None else self.case
        if source is None:
            source = "baseline.txt" if condition == "baseline" else "core.txt"
        is_lineage = "lineage_steps" in target_case
        output_name = "stage3.txt" if is_lineage else "output.txt"
        record: dict = {
            "schema_version": 1,
            "run_id": run_id or f"{model_id}-{target_case['case_id']}-{condition}-{replicate}",
            "experiment_id": "test-only",
            "case_id": target_case["case_id"],
            "case_version": target_case["version"],
            "condition": condition,
            "case_revision": benchmark.canonical_json_sha256(target_case),
            "condition_source": source,
            "condition_revision": benchmark.sha256(self.root / source),
            "model": {"provider": provider, "id": model_id, "version": "fixture", "reasoning": "fixed"},
            "environment": {"harness": "manual", "version": "test", "tools_id": "tools-v1",
                            "source_snapshot_id": "source-v1", "budget_id": "budget-v1", "baseline_id": "baseline-v1"},
            "replicate": replicate,
            "synthetic": synthetic,
            "status": "completed",
            "checks": [{"id": check["id"], "status": "pass", "evidence": ["review.txt"]}
                       for check in target_case["acceptance_checks"]],
            "material_defects": [],
            "output_artifact": output_name,
            "artifact_hashes": {name: benchmark.sha256(self.root / name)
                                for name in (output_name, "review.txt")},
            "metrics": {"cost_usd": 2.0, "review_minutes": 2.0, "repair_minutes": 0.0, "total_tokens": 100},
        }
        if is_lineage:
            record["stage_artifacts"] = [
                {"stage": index, "path": f"stage{index}.txt",
                 "sha256": benchmark.sha256(self.root / f"stage{index}.txt")}
                for index in range(1, len(target_case["lineage_steps"]) + 1)
            ]
        return record

    def validate(self, run: dict) -> dict:
        return benchmark.validate_run(run, self.cases, self.root)

    # --- Original 18 risk-focused tests (preserved) ---

    def test_partial_credit_and_self_report_cannot_become_success(self) -> None:
        run = self.run_record()
        run["checks"][1]["status"] = "fail"
        run["claimed_success"] = True
        run["score"] = 0.99
        self.validate(run)
        self.assertEqual(benchmark.outcome(run, self.case), "fail")
        run["checks"][1] = {"id": "grounded", "status": "not_run", "evidence": []}
        self.assertEqual(benchmark.outcome(run, self.case), "incomplete")

    def test_material_defect_overrides_all_passing_checks(self) -> None:
        run = self.run_record()
        run["material_defects"] = ["Invented material source claim"]
        self.validate(run)
        self.assertEqual(benchmark.outcome(run, self.case), "fail")

    def test_missing_or_empty_evidence_does_not_validate(self) -> None:
        for evidence in ([], ["missing.txt"]):
            with self.subTest(evidence=evidence):
                run = self.run_record()
                run["checks"][0]["evidence"] = evidence
                with self.assertRaises(benchmark.ValidationError):
                    self.validate(run)
        (self.root / "empty.txt").write_text("", encoding="utf-8")
        run = self.run_record()
        run["output_artifact"] = "empty.txt"
        with self.assertRaisesRegex(benchmark.ValidationError, "empty"):
            self.validate(run)

    def test_mutated_condition_snapshot_invalidates_record(self) -> None:
        run = self.run_record()
        (self.root / "baseline.txt").write_text("Changed after evaluation", encoding="utf-8")
        with self.assertRaisesRegex(benchmark.ValidationError, "condition_revision"):
            self.validate(run)

    def test_mismatched_model_tools_sources_or_budget_refuses_pair(self) -> None:
        for field, key in (("model", "reasoning"), ("model", "version"),
                           ("environment", "tools_id"), ("environment", "source_snapshot_id"),
                           ("environment", "budget_id"), ("environment", "baseline_id")):
            with self.subTest(field=field, key=key):
                baseline, treatment = self.run_record(), self.run_record("core-rules")
                treatment[field][key] = "different"
                self.validate(baseline)
                self.validate(treatment)
                with self.assertRaisesRegex(benchmark.ValidationError, "incompatible"):
                    benchmark.summarize([baseline, treatment], self.cases)

    def test_unpaired_and_duplicate_runs_are_not_compared(self) -> None:
        baseline = self.run_record()
        with self.assertRaisesRegex(benchmark.ValidationError, "unpaired"):
            benchmark.summarize([baseline], self.cases)
        with self.assertRaisesRegex(benchmark.ValidationError, "duplicate"):
            benchmark.summarize([baseline, copy.deepcopy(baseline)], self.cases)

    def test_synthetic_fixtures_are_excluded_from_measured_results(self) -> None:
        runs = [self.run_record(synthetic=True), self.run_record("core-rules", synthetic=True)]
        for run in runs:
            self.validate(run)
        report = benchmark.summarize(runs, self.cases)
        self.assertEqual(report["measurement_status"], "not_run")
        self.assertEqual(report["groups"], [])
        self.assertEqual(report["excluded_records"], 2)
        fixtures = benchmark.summarize(runs, self.cases, synthetic_only=True)
        self.assertEqual(fixtures["measurement_status"], "synthetic_fixture")
        self.assertEqual(fixtures["selected_records"], 2)

    def test_constructed_inputs_can_have_measured_runs_without_becoming_real_work(self) -> None:
        runs = [self.run_record(), self.run_record("core-rules")]
        for run in runs:
            self.validate(run)
        report = benchmark.summarize(runs, self.cases)
        self.assertEqual(report["measurement_status"], "measured_results")
        self.assertEqual(report["case_origins"], {"constructed": 1, "real_work": 0})

    def test_failures_stay_in_denominator_cost_and_review_time(self) -> None:
        first = [self.run_record(), self.run_record("core-rules")]
        second = [self.run_record(replicate=2), self.run_record("core-rules", replicate=2)]
        second[0]["status"] = "timeout"
        second[0]["output_artifact"] = None
        second[0]["notes"] = "Request timed out after hitting budget ceiling."
        second[0]["evidence"] = ["blocker.log"]
        second[0]["artifact_hashes"] = {"blocker.log": benchmark.sha256(self.root / "blocker.log")}
        second[0]["checks"] = [{"id": check["id"], "status": "not_run", "evidence": []}
                               for check in self.case["acceptance_checks"]]
        second[0]["metrics"].update(cost_usd=8.0, review_minutes=3.0, repair_minutes=10.0, repair_capped=True)
        runs = first + second
        for run in runs:
            self.validate(run)
        report = benchmark.summarize(runs, self.cases)
        group = report["groups"][0]
        self.assertEqual(group["unique_task_scenarios"], 1)
        result = group["baseline"]
        self.assertEqual(result["runs"], 2)
        self.assertEqual(result["complete_acceptance_rate"], 0.5)
        self.assertEqual(result["outcomes"], {"pass": 1, "fail": 0, "incomplete": 1})
        self.assertEqual(result["cost_usd_known_sum"], 10.0)
        self.assertEqual(result["observed_review_plus_repair_minutes_median"], 7.5)
        self.assertTrue(result["observed_time_includes_capped_repair"])
        self.assertEqual(result["repair_capped_runs"], 1)
        self.assertEqual(group["paired_complete_acceptance"]["improved"], 1)

    def test_unknown_metrics_are_not_treated_as_zero(self) -> None:
        runs = [self.run_record(), self.run_record("core-rules")]
        for run in runs:
            run["metrics"] = {key: None for key in benchmark.METRIC_FIELDS}
            self.validate(run)
        result = benchmark.summarize(runs, self.cases)["groups"][0]["baseline"]
        self.assertIsNone(result["cost_usd_known_sum"])
        self.assertEqual(result["cost_observed_runs"], 0)
        self.assertIsNone(result["observed_review_plus_repair_minutes_median"])

    def test_negative_nonfinite_or_boolean_metrics_are_rejected(self) -> None:
        for value in (-1, float("nan"), float("inf"), True):
            with self.subTest(value=value):
                run = self.run_record()
                run["metrics"]["cost_usd"] = value
                with self.assertRaises(benchmark.ValidationError):
                    self.validate(run)

    def test_changed_condition_revision_cannot_be_pooled(self) -> None:
        runs = [self.run_record(), self.run_record("core-rules"),
                self.run_record(replicate=2), self.run_record("core-rules", replicate=2)]
        (self.root / "core-v2.txt").write_text("A different treatment", encoding="utf-8")
        runs[-1]["condition_source"] = "core-v2.txt"
        runs[-1]["condition_revision"] = benchmark.sha256(self.root / "core-v2.txt")
        for run in runs:
            self.validate(run)
        with self.assertRaisesRegex(benchmark.ValidationError, "changed condition revision"):
            benchmark.summarize(runs, self.cases)

    def test_evidence_cannot_escape_project_root(self) -> None:
        run = self.run_record()
        run["checks"][0]["evidence"] = ["../outside.txt"]
        with self.assertRaisesRegex(benchmark.ValidationError, "escapes"):
            self.validate(run)

    def test_case_and_jsonl_integration_detects_duplicate_run_id(self) -> None:
        case_dir = self.root / "cases"
        case_dir.mkdir()
        (case_dir / "fixture.json").write_text(json.dumps(self.case), encoding="utf-8")
        cases = benchmark.load_cases(case_dir)
        run = self.run_record()
        path = self.root / "runs.jsonl"
        path.write_text(json.dumps(run) + "\n" + json.dumps(run) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(benchmark.ValidationError, "duplicate run_id"):
            benchmark.load_runs([path], cases, self.root)

    def test_source_snapshot_changes_between_matched_replicates_are_rejected(self) -> None:
        runs = [self.run_record(), self.run_record("core-rules"),
                self.run_record(replicate=2), self.run_record("core-rules", replicate=2)]
        for run in runs[2:]:
            run["environment"]["source_snapshot_id"] = "different-source-v2"
        for run in runs:
            self.validate(run)
        with self.assertRaisesRegex(benchmark.ValidationError, "source_snapshot_id"):
            benchmark.summarize(runs, self.cases)

    def test_case_cannot_change_after_a_run_without_invalidating_its_digest(self) -> None:
        run = self.run_record()
        self.case["acceptance_checks"][1]["required"] = False
        with self.assertRaisesRegex(benchmark.ValidationError, "case_revision"):
            self.validate(run)

    def test_output_and_review_bytes_are_pinned_not_just_file_names(self) -> None:
        for name in ("output.txt", "review.txt"):
            with self.subTest(name=name):
                run = self.run_record()
                original = (self.root / name).read_bytes()
                (self.root / name).write_text("Changed after scoring", encoding="utf-8")
                with self.assertRaisesRegex(benchmark.ValidationError, "artifact SHA-256 mismatch"):
                    self.validate(run)
                (self.root / name).write_bytes(original)
        run = self.run_record()
        del run["artifact_hashes"]["review.txt"]
        with self.assertRaisesRegex(benchmark.ValidationError, "must cover"):
            self.validate(run)

    def test_case_local_source_hash_is_checked_against_file_bytes(self) -> None:
        self.case["evidence_sources"] = [{"id": "source", "locator": "review.txt",
                                          "sha256": benchmark.sha256(self.root / "review.txt")}]
        benchmark.validate_case(self.case, root=self.root)
        (self.root / "review.txt").write_text("Source edited without versioning", encoding="utf-8")
        with self.assertRaisesRegex(benchmark.ValidationError, "source SHA-256 mismatch"):
            benchmark.validate_case(self.case, root=self.root)

    # --- New v0.2.0 hardening tests ---

    def test_condition_name_validator_accepts_ablations_and_rejects_invalid(self) -> None:
        for name in ("baseline", "core-rules", "core-rules-v0.1.0", "core-rules-v0.2.0",
                     "model-controls", "gated", "a1", "v0_2.0-rc1"):
            with self.subTest(valid=name):
                self.assertEqual(benchmark.validate_condition_name(name, "condition"), name)
        for bad in ("", "   ", "a", "Core-Rules", "-leading", ".dot", "has space", "bad/slash", "a" * 65):
            with self.subTest(invalid=bad):
                with self.assertRaises(benchmark.ValidationError):
                    benchmark.validate_condition_name(bad, "condition")

    def test_arbitrary_condition_ablation_v0_1_0_vs_v0_2_0_and_cli(self) -> None:
        v1 = self.run_record("core-rules-v0.1.0", source="core-v0.1.0.txt")
        v1["checks"][1]["status"] = "fail"
        v2 = self.run_record("core-rules-v0.2.0", source="core-v0.2.0.txt")
        self.validate(v1)
        self.validate(v2)

        report = benchmark.summarize(
            [v1, v2], self.cases,
            baseline_condition="core-rules-v0.1.0",
            treatment_condition="core-rules-v0.2.0",
        )
        self.assertEqual(report["measurement_status"], "measured_results")
        self.assertEqual(report["comparison"], {
            "baseline": "core-rules-v0.1.0",
            "treatment": "core-rules-v0.2.0",
        })
        group = report["groups"][0]
        self.assertEqual(group["baseline_condition"], "core-rules-v0.1.0")
        self.assertEqual(group["treatment_condition"], "core-rules-v0.2.0")
        self.assertNotIn("core_rules", group)
        self.assertEqual(group["baseline"]["outcomes"], {"pass": 0, "fail": 1, "incomplete": 0})
        self.assertEqual(group["treatment"]["outcomes"], {"pass": 1, "fail": 0, "incomplete": 0})
        self.assertEqual(group["paired_complete_acceptance"]["improved"], 1)

        # Default baseline/core-rules against non-matching conditions must error, never silently say not_run.
        with self.assertRaisesRegex(benchmark.ValidationError, "no runs match requested conditions"):
            benchmark.summarize([v1, v2], self.cases)

        # Identical baseline and treatment must be rejected.
        with self.assertRaisesRegex(benchmark.ValidationError, "must differ"):
            benchmark.summarize([v1, v2], self.cases,
                                baseline_condition="core-rules-v0.1.0",
                                treatment_condition="core-rules-v0.1.0")

        # End-to-end CLI invocation with --baseline and --treatment.
        case_dir = self.root / "cases"
        case_dir.mkdir()
        (case_dir / "fixture.json").write_text(json.dumps(self.case), encoding="utf-8")
        runs_path = self.root / "ablation.jsonl"
        runs_path.write_text(json.dumps(v1) + "\n" + json.dumps(v2) + "\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = benchmark.main([
                "summarize", str(runs_path),
                "--root", str(self.root),
                "--cases", str(case_dir),
                "--baseline", "core-rules-v0.1.0",
                "--treatment", "core-rules-v0.2.0",
                "--json",
            ])
        self.assertEqual(code, 0)
        cli_report = json.loads(buf.getvalue())
        self.assertEqual(cli_report["comparison"]["treatment"], "core-rules-v0.2.0")
        self.assertEqual(cli_report["groups"][0]["paired_complete_acceptance"]["improved"], 1)

    def test_core_rules_vs_model_controls_with_per_model_revisions(self) -> None:
        runs = [
            # Model A: native baseline + shared core-rules + model-A delta overlay
            self.run_record("baseline", source="baseline.txt", provider="openai", model_id="gpt-6.2-astra"),
            self.run_record("core-rules", source="core.txt", provider="openai", model_id="gpt-6.2-astra"),
            self.run_record("model-controls", source="model-controls-a.txt", provider="openai", model_id="gpt-6.2-astra"),
            # Model B: distinct native baseline + SAME shared core-rules + model-B delta overlay
            self.run_record("baseline", source="baseline-alt.txt", provider="anthropic", model_id="claude-opus-5-5"),
            self.run_record("core-rules", source="core.txt", provider="anthropic", model_id="claude-opus-5-5"),
            self.run_record("model-controls", source="model-controls-b.txt", provider="anthropic", model_id="claude-opus-5-5"),
        ]
        for run in runs:
            self.validate(run)

        # 1) baseline vs core-rules succeeds across models with distinct provider-native baselines
        base_vs_core = benchmark.summarize(runs, self.cases)
        self.assertEqual(base_vs_core["selected_records"], 4)
        self.assertEqual(base_vs_core["excluded_records"], 2)
        self.assertEqual(len(base_vs_core["groups"]), 2)
        self.assertIn("core_rules", base_vs_core["groups"][0])

        # 2) core-rules vs model-controls succeeds across models with distinct per-model delta overlays
        core_vs_controls = benchmark.summarize(
            runs, self.cases,
            baseline_condition="core-rules",
            treatment_condition="model-controls",
        )
        self.assertEqual(core_vs_controls["selected_records"], 4)
        self.assertEqual(core_vs_controls["excluded_records"], 2)
        self.assertEqual(len(core_vs_controls["groups"]), 2)
        self.assertEqual(core_vs_controls["comparison"], {
            "baseline": "core-rules",
            "treatment": "model-controls",
        })

    def test_condition_revision_scoping_rejects_drift_within_model_or_across_shared_treatment(self) -> None:
        # Per-model condition still rejects drift across replicates for the SAME model.
        same_model_drift = [
            self.run_record("baseline", replicate=1, source="baseline.txt"),
            self.run_record("core-rules", replicate=1, source="core.txt"),
            self.run_record("baseline", replicate=2, source="baseline-alt.txt"),
            self.run_record("core-rules", replicate=2, source="core.txt"),
        ]
        with self.assertRaisesRegex(benchmark.ValidationError, "changed condition revision"):
            benchmark.summarize(same_model_drift, self.cases)

        # Shared treatment condition rejects differing revisions across DIFFERENT models.
        cross_model_shared_drift = [
            self.run_record("baseline", source="baseline.txt", provider="openai", model_id="gpt-6.2-astra"),
            self.run_record("core-rules", source="core-v0.1.0.txt", provider="openai", model_id="gpt-6.2-astra"),
            self.run_record("baseline", source="baseline-alt.txt", provider="anthropic", model_id="claude-opus-5-5"),
            self.run_record("core-rules", source="core-v0.2.0.txt", provider="anthropic", model_id="claude-opus-5-5"),
        ]
        with self.assertRaisesRegex(benchmark.ValidationError, "changed condition revision"):
            benchmark.summarize(cross_model_shared_drift, self.cases)

    def test_validate_case_requires_lineage_step_zero_to_equal_prompt(self) -> None:
        benchmark.validate_case(self.lineage_case)
        bad_case = copy.deepcopy(self.lineage_case)
        bad_case["lineage_steps"][0] = "Divergent stage 1 prompt."
        with self.assertRaisesRegex(benchmark.ValidationError, "lineage_steps\\[0\\]"):
            benchmark.validate_case(bad_case)

    def test_stage_artifacts_validation_on_lineage_and_non_lineage_cases(self) -> None:
        # Non-lineage case works cleanly without stage_artifacts.
        single = self.run_record()
        self.assertNotIn("stage_artifacts", single)
        self.validate(single)

        # Completed lineage run with valid contiguous 1..3 stage_artifacts passes.
        valid_chain = self.run_record(case=self.lineage_case)
        self.validate(valid_chain)

        # Missing stage_artifacts on completed lineage run is rejected.
        missing = copy.deepcopy(valid_chain)
        del missing["stage_artifacts"]
        with self.assertRaisesRegex(benchmark.ValidationError, "stage_artifacts: required"):
            self.validate(missing)

        # Wrong count (2 instead of 3) is rejected.
        short = copy.deepcopy(valid_chain)
        short["stage_artifacts"] = short["stage_artifacts"][:2]
        with self.assertRaisesRegex(benchmark.ValidationError, "expected 3 stage artifacts"):
            self.validate(short)

        # Non-contiguous stage indices (e.g., [1, 2, 4] or bool stage) are rejected.
        bad_stage = copy.deepcopy(valid_chain)
        bad_stage["stage_artifacts"][2]["stage"] = 4
        with self.assertRaisesRegex(benchmark.ValidationError, "contiguous stage index"):
            self.validate(bad_stage)

        bool_stage = copy.deepcopy(valid_chain)
        bool_stage["stage_artifacts"][0]["stage"] = True
        with self.assertRaisesRegex(benchmark.ValidationError, "contiguous stage index"):
            self.validate(bool_stage)

        # Bad hex digest is rejected.
        bad_hex = copy.deepcopy(valid_chain)
        bad_hex["stage_artifacts"][0]["sha256"] = "NOT-A-SHA256"
        with self.assertRaisesRegex(benchmark.ValidationError, "lowercase SHA-256"):
            self.validate(bad_hex)

        # Tampered intermediate stage bytes are rejected.
        original_stage2 = (self.root / "stage2.txt").read_bytes()
        (self.root / "stage2.txt").write_text("Tampered stage 2 bytes\n", encoding="utf-8")
        try:
            with self.assertRaisesRegex(benchmark.ValidationError, "stage artifact SHA-256 mismatch"):
                self.validate(valid_chain)
        finally:
            (self.root / "stage2.txt").write_bytes(original_stage2)

        # Final stage path mismatching output_artifact is rejected.
        mismatch_final = copy.deepcopy(valid_chain)
        mismatch_final["output_artifact"] = "output.txt"
        mismatch_final["artifact_hashes"]["output.txt"] = benchmark.sha256(self.root / "output.txt")
        with self.assertRaisesRegex(benchmark.ValidationError, "final stage path"):
            self.validate(mismatch_final)

        # Non-completed lineage run may omit stage_artifacts OR include partial prefix stages 1..2.
        partial = copy.deepcopy(valid_chain)
        partial["status"] = "timeout"
        partial["output_artifact"] = None
        partial["notes"] = "Timed out during stage 3."
        partial["evidence"] = ["blocker.log"]
        partial["artifact_hashes"] = {"blocker.log": benchmark.sha256(self.root / "blocker.log")}
        partial["checks"] = [{"id": check["id"], "status": "not_run", "evidence": []}
                             for check in self.lineage_case["acceptance_checks"]]
        partial["stage_artifacts"] = partial["stage_artifacts"][:2]
        self.validate(partial)
        del partial["stage_artifacts"]
        self.validate(partial)

    def test_failed_blocked_timeout_require_nonempty_evidence_and_notes(self) -> None:
        for status in ("failed", "blocked", "timeout"):
            with self.subTest(status=status):
                run = self.run_record()
                run["status"] = status
                run["output_artifact"] = None
                run["checks"] = [{"id": check["id"], "status": "not_run", "evidence": []}
                                 for check in self.case["acceptance_checks"]]
                run["notes"] = f"Run ended with {status} due to recorded blocker."
                run["evidence"] = ["blocker.log"]
                run["artifact_hashes"] = {"blocker.log": benchmark.sha256(self.root / "blocker.log")}
                self.validate(run)

                # Missing notes rejected
                no_notes = copy.deepcopy(run)
                del no_notes["notes"]
                with self.assertRaisesRegex(benchmark.ValidationError, "notes"):
                    self.validate(no_notes)

                # Whitespace-only notes rejected
                blank_notes = copy.deepcopy(run)
                blank_notes["notes"] = "   "
                with self.assertRaisesRegex(benchmark.ValidationError, "notes"):
                    self.validate(blank_notes)

                # Missing evidence rejected
                no_evidence = copy.deepcopy(run)
                del no_evidence["evidence"]
                with self.assertRaisesRegex(benchmark.ValidationError, "evidence"):
                    self.validate(no_evidence)

                # Empty evidence list rejected
                empty_evidence = copy.deepcopy(run)
                empty_evidence["evidence"] = []
                with self.assertRaisesRegex(benchmark.ValidationError, "require non-empty evidence"):
                    self.validate(empty_evidence)

                # Unhashed blocker evidence rejected
                unhashed = copy.deepcopy(run)
                unhashed["artifact_hashes"] = {}
                with self.assertRaisesRegex(benchmark.ValidationError, "must cover"):
                    self.validate(unhashed)

    def test_load_runs_rejects_nonfinite_json_constants_anywhere_in_jsonl(self) -> None:
        run = self.run_record()
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                raw = json.dumps(run)[:-1] + f', "extra_probe": {constant}}}'
                path = self.root / f"bad-{constant}.jsonl"
                path.write_text(raw + "\n", encoding="utf-8")
                with self.assertRaisesRegex(benchmark.ValidationError, "non-finite number"):
                    benchmark.load_runs([path], self.cases, self.root)

    def test_pilot_validation_and_missing_pilot_coverage_reporting(self) -> None:
        pilot = {
            "schema_version": 1,
            "experiment_id": "test-only",
            "status": "not_run",
            "standard_version": "0.2.0",
            "suite": "constructed-diagnostic-probes",
            "cases": [
                {"case_id": "fixture", "case_version": "1.0.0", "stages": 1},
                {"case_id": "fixture-chain", "case_version": "1.0.0", "stages": 3},
            ],
            "models": [
                {"provider": "openai", "id": "gpt-6.2-astra"},
                {"provider": "anthropic", "id": "claude-opus-5-5"},
            ],
            "conditions": ["baseline", "core-rules"],
            "replicates": 1,
            "planned_matched_pairs": 4,
            "planned_run_records": 8,
            "planned_generation_stages": 16,
        }
        benchmark.validate_pilot(pilot, self.cases)

        # Unknown case in pilot fails validation.
        bad_case = copy.deepcopy(pilot)
        bad_case["cases"][0]["case_id"] = "UNKNOWN"
        with self.assertRaisesRegex(benchmark.ValidationError, "not found"):
            benchmark.validate_pilot(bad_case, self.cases)

        # Wrong stage count in pilot fails validation.
        bad_stages = copy.deepcopy(pilot)
        bad_stages["cases"][1]["stages"] = 2
        with self.assertRaisesRegex(benchmark.ValidationError, "expected 3"):
            benchmark.validate_pilot(bad_stages, self.cases)

        # Partial run set reports explicit missing_pilot_coverage (never silently hides dropped models).
        partial_runs = [
            self.run_record("baseline", provider="openai", model_id="gpt-6.2-astra"),
            self.run_record("core-rules", provider="openai", model_id="gpt-6.2-astra"),
        ]
        report = benchmark.summarize(partial_runs, self.cases, pilot=pilot)
        cov = report["missing_pilot_coverage"]
        self.assertIsNotNone(cov)
        self.assertFalse(cov["complete"])
        self.assertEqual(cov["missing_models"], [{"provider": "anthropic", "id": "claude-opus-5-5"}])
        self.assertEqual(cov["missing_cases"], [{"case_id": "fixture-chain", "case_version": "1.0.0"}])
        self.assertEqual(len(cov["missing_pairs"]), 3)
        self.assertEqual(cov["recorded_models_count"], 1)
        self.assertEqual(cov["planned_models_count"], 2)

        # Complete run set reports complete=True and zero missing models/cases/pairs.
        full_runs = []
        for provider, model_id, base_src in (
            ("openai", "gpt-6.2-astra", "baseline.txt"),
            ("anthropic", "claude-opus-5-5", "baseline-alt.txt"),
        ):
            for target_case in (self.case, self.lineage_case):
                full_runs.append(self.run_record(
                    "baseline", case=target_case, source=base_src, provider=provider, model_id=model_id
                ))
                full_runs.append(self.run_record(
                    "core-rules", case=target_case, source="core.txt", provider=provider, model_id=model_id
                ))
        full_report = benchmark.summarize(full_runs, self.cases, pilot=pilot)
        full_cov = full_report["missing_pilot_coverage"]
        self.assertTrue(full_cov["complete"])
        self.assertEqual(full_cov["missing_models"], [])
        self.assertEqual(full_cov["missing_cases"], [])
        self.assertEqual(full_cov["missing_pairs"], [])

    def test_print_summary_and_extra_pilot_models(self) -> None:
        pilot = {
            "schema_version": 1,
            "experiment_id": "test-only",
            "status": "not_run",
            "standard_version": "0.2.0",
            "suite": "constructed-diagnostic-probes",
            "cases": [{"case_id": "fixture", "case_version": "1.0.0", "stages": 1}],
            "models": [{"provider": "openai", "id": "gpt-6.2-astra"}],
            "conditions": ["core-rules-v0.1.0", "core-rules-v0.2.0"],
            "replicates": 1,
        }
        runs = [
            self.run_record("core-rules-v0.1.0", source="core-v0.1.0.txt", provider="google", model_id="gemini-4-neon"),
            self.run_record("core-rules-v0.2.0", source="core-v0.2.0.txt", provider="google", model_id="gemini-4-neon"),
        ]
        report = benchmark.summarize(
            runs, self.cases,
            baseline_condition="core-rules-v0.1.0",
            treatment_condition="core-rules-v0.2.0",
            pilot=pilot,
        )
        cov = report["missing_pilot_coverage"]
        self.assertFalse(cov["complete"])
        self.assertEqual(cov["missing_models"], [{"provider": "openai", "id": "gpt-6.2-astra"}])
        self.assertEqual(cov["extra_models"], [{"provider": "google", "id": "gemini-4-neon"}])

        buf = io.StringIO()
        with redirect_stdout(buf):
            benchmark.print_summary(report)
        rendered = buf.getvalue()
        self.assertIn("Comparison: core-rules-v0.1.0 -> core-rules-v0.2.0", rendered)
        self.assertIn("Missing pilot coverage (test-only)", rendered)
        self.assertIn("core-rules-v0.1.0:", rendered)
        self.assertIn("core-rules-v0.2.0:", rendered)

    def test_cli_validate_pilot_and_run_record(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = benchmark.main([
                "validate",
                "--root", str(REPO_ROOT),
                "--pilot", "benchmarks/pilot.json",
                "--run-record", "benchmarks/run-record.example.json",
            ])
        self.assertEqual(code, 0)
        self.assertIn("pilot manifest", out.getvalue())
        self.assertIn("1 standalone run record", out.getvalue())

        # Invalid standalone run record exits with code 2.
        bad_record = self.root / "bad-run.json"
        bad = self.run_record()
        bad["status"] = "blocked"
        bad["output_artifact"] = None
        bad["checks"] = [{"id": check["id"], "status": "not_run", "evidence": []}
                         for check in self.case["acceptance_checks"]]
        bad_record.write_text(json.dumps(bad), encoding="utf-8")
        case_dir = self.root / "cli-cases"
        case_dir.mkdir()
        (case_dir / "fixture.json").write_text(json.dumps(self.case), encoding="utf-8")
        out2, err2 = io.StringIO(), io.StringIO()
        with redirect_stdout(out2), redirect_stderr(err2):
            code2 = benchmark.main([
                "validate",
                "--root", str(self.root),
                "--cases", str(case_dir),
                "--run-record", str(bad_record),
            ])
        self.assertEqual(code2, 2)
        self.assertIn("ERROR:", err2.getvalue())

    def test_repo_pilot_and_example_run_record_validate_cleanly(self) -> None:
        cases = benchmark.load_cases(REPO_ROOT / "benchmarks" / "cases", REPO_ROOT)
        pilot = benchmark.read_json(REPO_ROOT / "benchmarks" / "pilot.json")
        benchmark.validate_pilot(pilot, cases, "benchmarks/pilot.json")
        pilot_v03 = benchmark.read_json(REPO_ROOT / "benchmarks" / "pilot-v0.3.0.json")
        benchmark.validate_pilot(pilot_v03, cases, "benchmarks/pilot-v0.3.0.json")
        example = benchmark.read_json(REPO_ROOT / "benchmarks" / "run-record.example.json")
        validated = benchmark.validate_run(example, cases, REPO_ROOT, "benchmarks/run-record.example.json")
        self.assertTrue(validated["synthetic"])
        self.assertEqual(validated["status"], "blocked")
        self.assertEqual(validated["experiment_id"], pilot["experiment_id"])

    def test_check_discover_summary_pairs_supports_ablations_without_default_pair(self) -> None:
        check_spec = importlib.util.spec_from_file_location("check_script", REPO_ROOT / "scripts" / "check.py")
        assert check_spec is not None and check_spec.loader is not None
        check_mod = importlib.util.module_from_spec(check_spec)
        check_spec.loader.exec_module(check_mod)

        ablation_log = self.root / "ablation.jsonl"
        ablation_log.write_text(
            "\n".join(
                json.dumps({"condition": cond, "synthetic": False})
                for cond in ("baseline", "core-rules-v0.1.0", "core-rules-v0.2.0")
            ) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            check_mod.discover_summary_pairs(ablation_log),
            [
                ("baseline", "core-rules-v0.1.0"),
                ("baseline", "core-rules-v0.2.0"),
                ("core-rules-v0.1.0", "core-rules-v0.2.0"),
            ],
        )

        custom_log = self.root / "custom.jsonl"
        custom_log.write_text(
            "\n".join([
                json.dumps({"condition": "core-rules", "synthetic": False}),
                json.dumps({"condition": "model-controls", "synthetic": False}),
                json.dumps({"condition": "synthetic-noise", "synthetic": True}),
            ]) + "\n",
            encoding="utf-8",
        )
        self.assertEqual(
            check_mod.discover_summary_pairs(custom_log),
            [("core-rules", "model-controls")],
        )


if __name__ == "__main__":
    unittest.main()
