#!/usr/bin/env python3
"""Validate case/run evidence and compare matched manual or native-agent runs.

This tool does not call a model or decide whether an artifact is correct. Reviewers
record checks against a versioned case; this tool enforces the record contract and
derives complete acceptance without averaging away a material failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
import sys
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = 1
DEFAULT_BASELINE = "baseline"
DEFAULT_TREATMENT = "core-rules"
CONDITION_NAME_PATTERN = r"^[a-z0-9][a-z0-9._-]{1,63}$"
CONDITION_RE = re.compile(CONDITION_NAME_PATTERN)
PER_MODEL_CONDITION_PREFIXES = ("baseline", "model-controls")
RUN_STATUSES = {"completed", "failed", "blocked", "timeout"}
NON_COMPLETED_STATUSES = {"failed", "blocked", "timeout"}
PILOT_STATUSES = {"not_run", "planned", "in_progress", "completed"}
CHECK_STATUSES = {"pass", "fail", "not_run"}
MODEL_FIELDS = ("provider", "id", "version", "reasoning")
ENVIRONMENT_FIELDS = (
    "harness", "version", "tools_id", "source_snapshot_id", "budget_id", "baseline_id"
)
METRIC_FIELDS = ("cost_usd", "review_minutes", "repair_minutes", "total_tokens")


class ValidationError(ValueError):
    """A record cannot support the requested validation or comparison."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def string(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label}: expected nonempty string")
    return value


def obj(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, dict), f"{label}: expected object")
    return value


def array(value: Any, label: str) -> list[Any]:
    require(isinstance(value, list), f"{label}: expected array")
    return value


def boolean(value: Any, label: str) -> bool:
    require(isinstance(value, bool), f"{label}: expected boolean")
    return value


def positive_int(value: Any, label: str) -> int:
    require(type(value) is int and value >= 1, f"{label}: expected positive integer")
    return value


def schema(record: dict[str, Any], label: str) -> None:
    require(type(record.get("schema_version")) is int
            and record["schema_version"] == SCHEMA_VERSION,
            f"{label}: schema_version must be {SCHEMA_VERSION}")


def enum(value: Any, allowed: set[str], label: str) -> str:
    value = string(value, label)
    require(value in allowed, f"{label}: expected one of {', '.join(sorted(allowed))}")
    return value


def validate_condition_name(value: Any, label: str) -> str:
    value = string(value, label)
    require(CONDITION_RE.fullmatch(value) is not None,
            f"{label}: expected condition name matching {CONDITION_NAME_PATTERN}")
    return value


def is_per_model_condition(condition: str) -> bool:
    """Per-model conditions (baselines and model-specific overlays) are scoped per model."""
    return any(
        condition == prefix
        or condition.startswith(f"{prefix}-")
        or condition.startswith(f"{prefix}.")
        or condition.startswith(f"{prefix}_")
        for prefix in PER_MODEL_CONDITION_PREFIXES
    )


def sha256_hex(value: Any, label: str) -> str:
    digest = string(value, label)
    require(len(digest) == 64 and all(c in "0123456789abcdef" for c in digest),
            f"{label}: expected lowercase SHA-256")
    return digest


def local_file(root: Path, reference: Any, label: str) -> Path:
    """Evidence must be reproducibly available inside the project, not a claim."""
    reference = string(reference, label)
    relative = Path(reference)
    require(not relative.is_absolute(), f"{label}: use a project-relative file path")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), f"{label}: path escapes project root")
    require(path.is_file(), f"{label}: evidence file does not exist: {reference}")
    require(path.stat().st_size > 0, f"{label}: evidence file is empty: {reference}")
    return path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json_sha256(value: Any) -> str:
    """Digest JSON meaning independently of indentation or object-key order."""
    content = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def bad_constant(value: str) -> None:
    raise ValueError(f"non-finite number {value}")


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), parse_constant=bad_constant)
    except (OSError, ValueError) as exc:
        raise ValidationError(f"{path}: {exc}") from exc


def validate_case(record: Any, label: str = "case", root: Path | None = None) -> dict[str, Any]:
    record = obj(record, label)
    schema(record, label)
    for field in ("case_id", "version", "domain", "title", "prompt"):
        string(record.get(field), f"{label}.{field}")
    enum(record["domain"], {"writing", "research", "coding"}, f"{label}.domain")
    enum(record.get("origin"), {"constructed", "real_work"}, f"{label}.origin")
    require("synthetic" not in record,
            f"{label}: use origin for case inputs; synthetic belongs only on fabricated run records")
    checks = array(record.get("acceptance_checks"), f"{label}.acceptance_checks")
    require(bool(checks), f"{label}: at least one acceptance check is required")
    ids: set[str] = set()
    for index, check in enumerate(checks):
        prefix = f"{label}.acceptance_checks[{index}]"
        check = obj(check, prefix)
        check_id = string(check.get("id"), f"{prefix}.id")
        require(check_id not in ids, f"{prefix}: duplicate check id {check_id}")
        ids.add(check_id)
        string(check.get("description"), f"{prefix}.description")
        boolean(check.get("required"), f"{prefix}.required")
    require(any(check["required"] for check in checks), f"{label}: a required check is needed")
    source_ids: set[str] = set()
    for index, source in enumerate(array(record.get("evidence_sources"), f"{label}.evidence_sources")):
        prefix = f"{label}.evidence_sources[{index}]"
        source = obj(source, prefix)
        source_id = string(source.get("id"), f"{prefix}.id")
        require(source_id not in source_ids, f"{prefix}: duplicate source id {source_id}")
        source_ids.add(source_id)
        string(source.get("locator"), f"{prefix}.locator")
        if "sha256" in source:
            digest = sha256_hex(source["sha256"], f"{prefix}.sha256")
            if not urlparse(source["locator"]).scheme:
                require(root is not None, f"{prefix}: project root is needed to validate local source bytes")
                source_path = local_file(root, source["locator"], f"{prefix}.locator")
                require(sha256(source_path) == digest, f"{prefix}: local source SHA-256 mismatch")
    if "lineage_steps" in record:
        steps = array(record["lineage_steps"], f"{label}.lineage_steps")
        require(len(steps) >= 2, f"{label}.lineage_steps: use at least two stages")
        for index, step in enumerate(steps):
            string(step, f"{label}.lineage_steps[{index}]")
        require(steps[0] == record["prompt"],
                f"{label}.lineage_steps[0]: first lineage step must equal case prompt")
    return record


def load_cases(directory: Path, root: Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    require(directory.is_dir(), f"case directory does not exist: {directory}")
    cases: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        case = validate_case(read_json(path), str(path), root)
        key = (case["case_id"], case["version"])
        require(key not in cases, f"duplicate case/version: {key}")
        cases[key] = case
    require(bool(cases), f"no JSON cases found in {directory}")
    return cases


def validate_pilot(record: Any, cases: dict[tuple[str, str], dict[str, Any]],
                   label: str = "pilot") -> dict[str, Any]:
    record = obj(record, label)
    schema(record, label)
    for field in ("experiment_id", "standard_version", "suite"):
        string(record.get(field), f"{label}.{field}")
    enum(record.get("status"), PILOT_STATUSES, f"{label}.status")
    pilot_cases = array(record.get("cases"), f"{label}.cases")
    require(bool(pilot_cases), f"{label}.cases: at least one planned case is required")
    seen_case_ids: set[str] = set()
    for index, entry in enumerate(pilot_cases):
        prefix = f"{label}.cases[{index}]"
        entry = obj(entry, prefix)
        case_id = string(entry.get("case_id"), f"{prefix}.case_id")
        case_version = string(entry.get("case_version"), f"{prefix}.case_version")
        stages = positive_int(entry.get("stages"), f"{prefix}.stages")
        require(case_id not in seen_case_ids, f"{prefix}: duplicate case_id {case_id}")
        seen_case_ids.add(case_id)
        key = (case_id, case_version)
        require(key in cases, f"{prefix}: pilot case {key} not found in benchmarks/cases")
        case = cases[key]
        expected_stages = len(case["lineage_steps"]) if "lineage_steps" in case else 1
        require(stages == expected_stages,
                f"{prefix}.stages: expected {expected_stages} to match case {case_id}")
    pilot_models = array(record.get("models"), f"{label}.models")
    require(bool(pilot_models), f"{label}.models: at least one planned model is required")
    seen_models: set[tuple[str, str]] = set()
    for index, entry in enumerate(pilot_models):
        prefix = f"{label}.models[{index}]"
        entry = obj(entry, prefix)
        provider = string(entry.get("provider"), f"{prefix}.provider")
        model_id = string(entry.get("id"), f"{prefix}.id")
        model_key = (provider, model_id)
        require(model_key not in seen_models, f"{prefix}: duplicate model {model_key}")
        seen_models.add(model_key)
    pilot_conditions = array(record.get("conditions"), f"{label}.conditions")
    require(len(pilot_conditions) >= 2, f"{label}.conditions: at least two conditions are required")
    seen_conditions: set[str] = set()
    for index, condition in enumerate(pilot_conditions):
        name = validate_condition_name(condition, f"{label}.conditions[{index}]")
        require(name not in seen_conditions, f"{label}.conditions[{index}]: duplicate condition {name}")
        seen_conditions.add(name)
    positive_int(record.get("replicates"), f"{label}.replicates")
    for count_field in ("planned_matched_pairs", "planned_run_records", "planned_generation_stages"):
        if count_field in record:
            positive_int(record[count_field], f"{label}.{count_field}")
    if "planned_matched_pairs" in record and "planned_run_records" in record:
        require(record["planned_run_records"] >= record["planned_matched_pairs"],
                f"{label}.planned_run_records: must be >= planned_matched_pairs")
    if "planned_run_records" in record and "planned_generation_stages" in record:
        require(record["planned_generation_stages"] >= record["planned_run_records"],
                f"{label}.planned_generation_stages: must be >= planned_run_records")
    if "limits" in record:
        for index, item in enumerate(array(record["limits"], f"{label}.limits")):
            string(item, f"{label}.limits[{index}]")
    return record


def validate_run(record: Any, cases: dict[tuple[str, str], dict[str, Any]],
                 root: Path, label: str = "run") -> dict[str, Any]:
    record = obj(record, label)
    schema(record, label)
    for field in ("run_id", "experiment_id", "case_id", "case_version", "case_revision", "condition_revision"):
        string(record.get(field), f"{label}.{field}")
    validate_condition_name(record.get("condition"), f"{label}.condition")
    enum(record.get("status"), RUN_STATUSES, f"{label}.status")
    positive_int(record.get("replicate"), f"{label}.replicate")
    boolean(record.get("synthetic"), f"{label}.synthetic")
    case_key = (record["case_id"], record["case_version"])
    require(case_key in cases, f"{label}: unknown case/version {case_key}")
    case = cases[case_key]
    require(record["case_revision"] == canonical_json_sha256(case),
            f"{label}: case_revision does not match the canonical JSON SHA-256 of the case")
    for field, fields in (("model", MODEL_FIELDS), ("environment", ENVIRONMENT_FIELDS)):
        config = obj(record.get(field), f"{label}.{field}")
        for key in fields:
            string(config.get(key), f"{label}.{field}.{key}")
    # A local immutable snapshot makes a named condition auditable. Its revision
    # is a content digest, not a mutable label such as "latest".
    condition_path = local_file(root, record.get("condition_source"), f"{label}.condition_source")
    require(record["condition_revision"] == sha256(condition_path),
            f"{label}: condition_revision must match SHA-256 of condition_source")
    expected = {check["id"]: check for check in case["acceptance_checks"]}
    actual: set[str] = set()
    required_artifacts: set[str] = set()
    for index, check in enumerate(array(record.get("checks"), f"{label}.checks")):
        prefix = f"{label}.checks[{index}]"
        check = obj(check, prefix)
        check_id = string(check.get("id"), f"{prefix}.id")
        require(check_id in expected, f"{prefix}: check id is not in case: {check_id}")
        require(check_id not in actual, f"{prefix}: duplicate check id {check_id}")
        actual.add(check_id)
        enum(check.get("status"), CHECK_STATUSES, f"{prefix}.status")
        evidence = array(check.get("evidence"), f"{prefix}.evidence")
        if check["status"] in {"pass", "fail"}:
            require(bool(evidence), f"{prefix}: pass/fail needs evidence file(s)")
        for evidence_index, reference in enumerate(evidence):
            local_file(root, reference, f"{prefix}.evidence[{evidence_index}]")
            required_artifacts.add(reference)
    require(actual == set(expected),
            f"{label}: every case check must be recorded; use not_run for unchecked items")
    for index, defect in enumerate(array(record.get("material_defects"), f"{label}.material_defects")):
        string(defect, f"{label}.material_defects[{index}]")
    if record["status"] in NON_COMPLETED_STATUSES:
        string(record.get("notes"), f"{label}.notes")
        run_evidence = array(record.get("evidence"), f"{label}.evidence")
        require(bool(run_evidence),
                f"{label}.evidence: failed, blocked, and timeout runs require non-empty evidence")
    else:
        if "notes" in record and record["notes"] is not None:
            require(isinstance(record["notes"], str), f"{label}.notes: expected string or null")
        if "evidence" in record and record["evidence"] is not None:
            run_evidence = array(record["evidence"], f"{label}.evidence")
        else:
            run_evidence = []
    for evidence_index, reference in enumerate(run_evidence):
        local_file(root, reference, f"{label}.evidence[{evidence_index}]")
        required_artifacts.add(reference)
    output = record.get("output_artifact")
    if record["status"] == "completed":
        local_file(root, output, f"{label}.output_artifact")
        required_artifacts.add(output)
    elif output is not None:
        local_file(root, output, f"{label}.output_artifact")
        required_artifacts.add(output)
    has_lineage = "lineage_steps" in case
    expected_stages = len(case["lineage_steps"]) if has_lineage else 1
    stage_artifacts = record.get("stage_artifacts")
    if has_lineage and record["status"] == "completed":
        require(stage_artifacts is not None,
                f"{label}.stage_artifacts: required on completed runs for multi-stage lineage cases")
    validated_stages: list[tuple[int, str, str]] = []
    if stage_artifacts is not None:
        stage_entries = array(stage_artifacts, f"{label}.stage_artifacts")
        if has_lineage and record["status"] == "completed":
            require(len(stage_entries) == expected_stages,
                    f"{label}.stage_artifacts: expected {expected_stages} stage artifacts to match lineage_steps")
        else:
            require(len(stage_entries) <= expected_stages,
                    f"{label}.stage_artifacts: at most {expected_stages} stage artifacts allowed for this case")
        for index, entry in enumerate(stage_entries):
            prefix = f"{label}.stage_artifacts[{index}]"
            entry = obj(entry, prefix)
            stage_num = entry.get("stage")
            require(type(stage_num) is int and stage_num == index + 1,
                    f"{prefix}.stage: expected contiguous stage index {index + 1} (1..{len(stage_entries)})")
            stage_ref = string(entry.get("path"), f"{prefix}.path")
            stage_digest = sha256_hex(entry.get("sha256"), f"{prefix}.sha256")
            stage_path = local_file(root, stage_ref, f"{prefix}.path")
            require(sha256(stage_path) == stage_digest,
                    f"{prefix}: stage artifact SHA-256 mismatch: {stage_ref}")
            validated_stages.append((stage_num, stage_ref, stage_digest))
    hashes = obj(record.get("artifact_hashes"), f"{label}.artifact_hashes")
    require(required_artifacts <= set(hashes),
            f"{label}: artifact_hashes must cover output, run evidence, and all check evidence files")
    for reference, digest in hashes.items():
        artifact = local_file(root, reference, f"{label}.artifact_hashes path")
        require(sha256_hex(digest, f"{label}.artifact_hashes[{reference}]") == sha256(artifact),
                f"{label}: artifact SHA-256 mismatch: {reference}")
    for _, stage_ref, stage_digest in validated_stages:
        if stage_ref in hashes:
            require(hashes[stage_ref] == stage_digest,
                    f"{label}.stage_artifacts: sha256 mismatch with artifact_hashes[{stage_ref}]")
    if validated_stages and record["status"] == "completed" and (has_lineage or len(validated_stages) == 1):
        final_ref, final_digest = validated_stages[-1][1], validated_stages[-1][2]
        require(final_ref == output,
                f"{label}.stage_artifacts: final stage path {final_ref!r} must match output_artifact {output!r}")
        require(final_digest == hashes[output],
                f"{label}.stage_artifacts: final stage sha256 must match artifact_hashes[{output}]")
    metrics = obj(record.get("metrics"), f"{label}.metrics")
    for field in METRIC_FIELDS:
        require(field in metrics, f"{label}.metrics.{field}: use null when not measured")
        value = metrics[field]
        require(value is None or (type(value) is int and value >= 0)
                or (type(value) is float and math.isfinite(value) and value >= 0),
                f"{label}.metrics.{field}: expected nonnegative number or null")
        if field == "total_tokens" and value is not None:
            require(type(value) is int, f"{label}.metrics.total_tokens: expected integer or null")
    if "repair_capped" in metrics:
        boolean(metrics["repair_capped"], f"{label}.metrics.repair_capped")
        require(not metrics["repair_capped"] or metrics["repair_minutes"] is not None,
                f"{label}: capped repair time must have an observed/capped duration")
    return record


def load_runs(paths: list[Path], cases: dict[tuple[str, str], dict[str, Any]],
              root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in paths:
        require(path.is_file(), f"run file does not exist: {path}")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise ValidationError(f"{path}: {exc}") from exc
        for index, line in enumerate(lines, 1):
            if not line.strip():
                continue
            label = f"{path}:{index}"
            try:
                value = json.loads(line, parse_constant=bad_constant)
            except ValueError as exc:
                raise ValidationError(f"{label}: {exc}") from exc
            run = validate_run(value, cases, root, label)
            require(run["run_id"] not in ids, f"{label}: duplicate run_id {run['run_id']}")
            ids.add(run["run_id"])
            records.append(run)
    return records


def outcome(run: dict[str, Any], case: dict[str, Any]) -> str:
    required = {check["id"] for check in case["acceptance_checks"] if check["required"]}
    statuses = {check["id"]: check["status"] for check in run["checks"]}
    if run["material_defects"] or run["status"] == "failed" or any(statuses[key] == "fail" for key in required):
        return "fail"
    if run["status"] != "completed" or any(statuses[key] != "pass" for key in required):
        return "incomplete"
    return "pass"


def comparable_pairs(
    runs: list[dict[str, Any]],
    baseline_condition: str = DEFAULT_BASELINE,
    treatment_condition: str = DEFAULT_TREATMENT,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    validate_condition_name(baseline_condition, "baseline")
    validate_condition_name(treatment_condition, "treatment")
    require(baseline_condition != treatment_condition,
            f"baseline and treatment conditions must differ: {baseline_condition}")
    target_conditions = {baseline_condition, treatment_condition}
    filtered = [run for run in runs if run["condition"] in target_conditions]
    if runs and not filtered:
        found = ", ".join(sorted({run["condition"] for run in runs}))
        raise ValidationError(
            f"no runs match requested conditions {baseline_condition!r} and "
            f"{treatment_condition!r}; found conditions: {found}"
        )
    buckets: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    revisions: dict[tuple[Any, ...], str] = {}
    case_versions: dict[tuple[str, str], str] = {}
    source_snapshots: dict[tuple[str, str], str] = {}
    for run in filtered:
        key = (run["experiment_id"], run["case_id"], run["model"]["provider"],
               run["model"]["id"], run["replicate"])
        condition = run["condition"]
        require(condition not in buckets[key], f"duplicate {condition} in comparison pair {key}")
        buckets[key][condition] = run
        if is_per_model_condition(condition):
            revision_key: tuple[Any, ...] = (
                run["experiment_id"], condition, run["model"]["provider"], run["model"]["id"]
            )
        else:
            revision_key = (run["experiment_id"], condition)
        if revision_key in revisions:
            require(revisions[revision_key] == run["condition_revision"],
                    f"changed condition revision inside experiment {revision_key}")
        revisions[revision_key] = run["condition_revision"]
        case_key = (run["experiment_id"], run["case_id"])
        if case_key in case_versions:
            require(case_versions[case_key] == run["case_version"],
                    f"changed case version inside experiment {case_key}")
        case_versions[case_key] = run["case_version"]
        snapshot = run["environment"]["source_snapshot_id"]
        if case_key in source_snapshots:
            require(source_snapshots[case_key] == snapshot,
                    f"incompatible experiment/case {case_key}: source_snapshot_id differs across recorded runs")
        source_snapshots[case_key] = snapshot
    pairs = []
    for key, conditions in sorted(buckets.items()):
        require(set(conditions) == target_conditions,
                f"unpaired run {key}; need {baseline_condition} and {treatment_condition}")
        baseline, treatment = conditions[baseline_condition], conditions[treatment_condition]
        for field in ("case_version", "model", "environment"):
            require(baseline[field] == treatment[field],
                    f"incompatible pair {key}: {field} differs")
        pairs.append((baseline, treatment))
    return pairs


def condition_summary(runs: list[dict[str, Any]], cases: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    counts = {name: 0 for name in ("pass", "fail", "incomplete")}
    times = []
    cost = []
    tokens = []
    capped = 0
    capped_observed_times = 0
    material_defect_runs = 0
    for run in runs:
        counts[outcome(run, cases[(run["case_id"], run["case_version"])])] += 1
        material_defect_runs += bool(run["material_defects"])
        metrics = run["metrics"]
        if metrics["cost_usd"] is not None:
            cost.append(metrics["cost_usd"])
        if metrics["total_tokens"] is not None:
            tokens.append(metrics["total_tokens"])
        if metrics["review_minutes"] is not None and metrics["repair_minutes"] is not None:
            times.append(metrics["review_minutes"] + metrics["repair_minutes"])
            capped_observed_times += bool(metrics.get("repair_capped", False))
        capped += bool(metrics.get("repair_capped", False))
    return {
        "runs": len(runs), "outcomes": counts,
        "complete_acceptance_rate": counts["pass"] / len(runs) if runs else None,
        "material_defect_runs": material_defect_runs,
        "cost_usd_known_sum": sum(cost) if cost else None,
        "cost_observed_runs": len(cost),
        "tokens_known_sum": sum(tokens) if tokens else None,
        "tokens_observed_runs": len(tokens),
        "observed_review_plus_repair_minutes_median": median(times) if times else None,
        "observed_time_includes_capped_repair": bool(capped_observed_times),
        "time_observed_runs": len(times), "repair_capped_runs": capped,
    }


def pilot_coverage(
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    pilot: dict[str, Any],
) -> dict[str, Any]:
    planned_models = [(entry["provider"], entry["id"]) for entry in pilot["models"]]
    planned_cases = [(entry["case_id"], entry["case_version"]) for entry in pilot["cases"]]
    planned_replicates = pilot["replicates"]
    observed_models = {(baseline["model"]["provider"], baseline["model"]["id"]) for baseline, _ in pairs}
    observed_cases = {(baseline["case_id"], baseline["case_version"]) for baseline, _ in pairs}
    pair_counts: dict[tuple[tuple[str, str], tuple[str, str]], int] = defaultdict(int)
    for baseline, _ in pairs:
        model_key = (baseline["model"]["provider"], baseline["model"]["id"])
        case_key = (baseline["case_id"], baseline["case_version"])
        pair_counts[(model_key, case_key)] += 1
    missing_models = [
        {"provider": provider, "id": model_id}
        for provider, model_id in planned_models
        if (provider, model_id) not in observed_models
    ]
    missing_cases = [
        {"case_id": case_id, "case_version": case_version}
        for case_id, case_version in planned_cases
        if (case_id, case_version) not in observed_cases
    ]
    missing_pairs = []
    for provider, model_id in planned_models:
        for case_id, case_version in planned_cases:
            recorded = pair_counts[((provider, model_id), (case_id, case_version))]
            if recorded < planned_replicates:
                missing_pairs.append({
                    "provider": provider,
                    "model_id": model_id,
                    "case_id": case_id,
                    "case_version": case_version,
                    "recorded_replicates": recorded,
                    "planned_replicates": planned_replicates,
                })
    extra_models = [
        {"provider": provider, "id": model_id}
        for provider, model_id in sorted(observed_models - set(planned_models))
    ]
    extra_cases = [
        {"case_id": case_id, "case_version": case_version}
        for case_id, case_version in sorted(observed_cases - set(planned_cases))
    ]
    return {
        "pilot_experiment_id": pilot["experiment_id"],
        "complete": not (missing_models or missing_cases or missing_pairs),
        "planned_models_count": len(planned_models),
        "recorded_models_count": len(observed_models & set(planned_models)),
        "planned_cases_count": len(planned_cases),
        "recorded_cases_count": len(observed_cases & set(planned_cases)),
        "missing_models": missing_models,
        "missing_cases": missing_cases,
        "missing_pairs": missing_pairs,
        "extra_models": extra_models,
        "extra_cases": extra_cases,
    }


def summarize(
    runs: list[dict[str, Any]],
    cases: dict[tuple[str, str], dict[str, Any]],
    synthetic_only: bool = False,
    baseline_condition: str = DEFAULT_BASELINE,
    treatment_condition: str = DEFAULT_TREATMENT,
    pilot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validate_condition_name(baseline_condition, "baseline")
    validate_condition_name(treatment_condition, "treatment")
    require(baseline_condition != treatment_condition,
            f"baseline and treatment conditions must differ: {baseline_condition}")
    synthetic_matched = [run for run in runs if run["synthetic"] == synthetic_only]
    target_conditions = {baseline_condition, treatment_condition}
    selected = [run for run in synthetic_matched if run["condition"] in target_conditions]
    if synthetic_matched and not selected:
        found = ", ".join(sorted({run["condition"] for run in synthetic_matched}))
        raise ValidationError(
            f"no runs match requested conditions {baseline_condition!r} and "
            f"{treatment_condition!r}; found conditions: {found}"
        )
    pairs = comparable_pairs(selected, baseline_condition, treatment_condition)
    grouped: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for pair in pairs:
        # Keep model versions, settings, and experiments separate. A result on a
        # different task/harness is not a model leaderboard.
        execution = {key: value for key, value in pair[0]["environment"].items()
                     if key != "source_snapshot_id"}
        key = json.dumps({"experiment_id": pair[0]["experiment_id"],
                          "model": pair[0]["model"], "environment": execution}, sort_keys=True)
        grouped[key].append(pair)
    groups = []
    for key, group in sorted(grouped.items()):
        transitions = {"improved": 0, "regressed": 0, "both_pass": 0, "neither_pass": 0}
        for baseline, treatment in group:
            case = cases[(baseline["case_id"], baseline["case_version"])]
            before, after = outcome(baseline, case) == "pass", outcome(treatment, case) == "pass"
            label = "both_pass" if before and after else "regressed" if before else "improved" if after else "neither_pass"
            transitions[label] += 1
        baseline_summary = condition_summary([pair[0] for pair in group], cases)
        treatment_summary = condition_summary([pair[1] for pair in group], cases)
        group_entry: dict[str, Any] = {
            **json.loads(key),
            "pairs": len(group),
            "unique_task_scenarios": len({pair[0]["case_id"] for pair in group}),
            "case_origins": origin_counts([pair[0] for pair in group], cases),
            "baseline_condition": baseline_condition,
            "treatment_condition": treatment_condition,
            "baseline": baseline_summary,
            "treatment": treatment_summary,
            "paired_complete_acceptance": transitions,
        }
        if treatment_condition == DEFAULT_TREATMENT:
            group_entry["core_rules"] = treatment_summary
        groups.append(group_entry)
    coverage = pilot_coverage(pairs, pilot) if pilot is not None else None
    population = (
        "recorded matched runs reconciled against pilot manifest"
        if pilot is not None
        else "recorded matched runs only; planned roster not reconciled by this tool"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement_status": "synthetic_fixture" if synthetic_only else "measured_results" if selected else "not_run",
        "comparison": {"baseline": baseline_condition, "treatment": treatment_condition},
        "selected_records": len(selected), "excluded_records": len(runs) - len(selected),
        "population": population,
        "unique_task_scenarios": len({run["case_id"] for run in selected}),
        "case_origins": origin_counts(selected, cases),
        "missing_pilot_coverage": coverage,
        "groups": groups,
        "limitations": [
            "Evidence files and record structure are checked; artifact correctness still requires valid external checks and review.",
            "Repeated runs and lineage checkpoints are not independent task scenarios.",
            "No universal slop score or causal model ranking is computed.",
            "Missing metrics remain unknown; failed, blocked, and timed-out runs remain in acceptance denominators.",
            "Denominators cover recorded matched runs only. Reconcile the planned roster before making an experiment-level claim.",
            "Observed review plus repair time is not time-to-completion; capped repair observations are censored.",
            "Constructed cases can yield measured results, but do not establish effectiveness on representative real work.",
        ],
    }


def origin_counts(runs: list[dict[str, Any]], cases: dict[tuple[str, str], dict[str, Any]]) -> dict[str, int]:
    counts = {"constructed": 0, "real_work": 0}
    for key in {(run["case_id"], run["case_version"]) for run in runs}:
        counts[cases[key]["origin"]] += 1
    return counts


def print_summary(report: dict[str, Any]) -> None:
    if report["measurement_status"] == "not_run":
        print("No measured run records. The comparative benchmark has not been run.")
    elif report["measurement_status"] == "synthetic_fixture":
        print("SYNTHETIC FIXTURE SUMMARY — not measured model performance.")
    else:
        print("Recorded matched benchmark runs — local tested configurations, not a model leaderboard.")
    comparison = report.get("comparison", {"baseline": DEFAULT_BASELINE, "treatment": DEFAULT_TREATMENT})
    print(f"Comparison: {comparison['baseline']} -> {comparison['treatment']}")
    print(f"Selected records: {report['selected_records']}; excluded: {report['excluded_records']}")
    coverage = report.get("missing_pilot_coverage")
    if coverage is not None:
        if coverage["complete"]:
            print(
                f"Pilot coverage ({coverage['pilot_experiment_id']}): complete "
                f"({coverage['recorded_models_count']}/{coverage['planned_models_count']} models, "
                f"{coverage['recorded_cases_count']}/{coverage['planned_cases_count']} cases)."
            )
        else:
            missing_models = ", ".join(
                f"{m['provider']}/{m['id']}" for m in coverage["missing_models"]
            ) or "none"
            missing_cases = ", ".join(
                f"{c['case_id']}@{c['case_version']}" for c in coverage["missing_cases"]
            ) or "none"
            print(
                f"Missing pilot coverage ({coverage['pilot_experiment_id']}): "
                f"missing models=[{missing_models}]; missing cases=[{missing_cases}]; "
                f"incomplete model/case pairs={len(coverage['missing_pairs'])}"
            )
    for group in report["groups"]:
        model = group["model"]
        baseline_label = group.get("baseline_condition", comparison["baseline"])
        treatment_label = group.get("treatment_condition", comparison["treatment"])
        treatment_key = "treatment" if "treatment" in group else "core_rules"
        print(f"\n{group['experiment_id']} / {model['provider']}/{model['id']} / {model['version']} / {model['reasoning']}")
        print(f"Pairs: {group['pairs']}; distinct task scenarios: {group['unique_task_scenarios']}")
        print(f"Case origins: {group['case_origins']}")
        print(f"Execution configuration: {json.dumps(group['environment'], sort_keys=True)}")
        for label, key in ((baseline_label, "baseline"), (treatment_label, treatment_key)):
            result = group[key]
            counts = result["outcomes"]
            print(f"  {label}: {counts['pass']} pass, {counts['fail']} fail, {counts['incomplete']} incomplete / {result['runs']}")
            print(f"    Known cost USD: {result['cost_usd_known_sum']} ({result['cost_observed_runs']}/{result['runs']} recorded)")
            print(f"    Median observed review + repair minutes: {result['observed_review_plus_repair_minutes_median']} ({result['time_observed_runs']}/{result['runs']} recorded; {result['repair_capped_runs']} capped/censored; not time-to-completion)")
        print(f"  Paired complete acceptance: {group['paired_complete_acceptance']}")
    for note in report["limitations"]:
        print(f"Note: {note}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "summarize"))
    parser.add_argument("paths", nargs="*", type=Path, help="JSON case files or JSONL run records")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--cases", type=Path, default=Path("benchmarks/cases"))
    parser.add_argument("--pilot", type=Path, default=None,
                        help="pilot manifest JSON to validate or reconcile coverage against")
    parser.add_argument("--no-pilot", action="store_true",
                        help="skip auto-loading benchmarks/pilot.json during summarize")
    parser.add_argument("--run-record", dest="run_records", action="append", type=Path, default=[],
                        help="standalone JSON run record to validate via validate_run()")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                        help=f"baseline condition name for summarize (default: {DEFAULT_BASELINE})")
    parser.add_argument("--treatment", default=DEFAULT_TREATMENT,
                        help=f"treatment condition name for summarize (default: {DEFAULT_TREATMENT})")
    parser.add_argument("--json", action="store_true", help="emit machine-readable summary")
    parser.add_argument("--synthetic-only", action="store_true", help="inspect fixtures, explicitly not measured performance")
    args = parser.parse_intermixed_args(argv)
    root = args.root.resolve()
    case_directory = args.cases if args.cases.is_absolute() else root / args.cases
    try:
        cases = load_cases(case_directory, root)
        pilot: dict[str, Any] | None = None
        if args.pilot is not None:
            pilot_path = args.pilot if args.pilot.is_absolute() else root / args.pilot
            pilot = validate_pilot(read_json(pilot_path), cases, str(pilot_path))
        elif args.command == "summarize" and not args.no_pilot and args.cases == Path("benchmarks/cases"):
            default_pilot = root / "benchmarks/pilot.json"
            if default_pilot.is_file():
                pilot = validate_pilot(read_json(default_pilot), cases, str(default_pilot))
        if args.run_records and args.command != "validate":
            raise ValidationError("--run-record is only supported with the validate command")
        standalone_runs = 0
        for record_arg in args.run_records:
            record_path = record_arg if record_arg.is_absolute() else root / record_arg
            validate_run(read_json(record_path), cases, root, str(record_path))
            standalone_runs += 1
        paths = [path if path.is_absolute() else root / path for path in args.paths]
        run_paths = []
        for path in paths:
            if path.suffix == ".jsonl":
                run_paths.append(path)
            elif args.command == "validate" and path.suffix == ".json":
                validate_case(read_json(path), str(path), root)
            else:
                raise ValidationError(f"expected {'JSONL runs' if args.command == 'summarize' else 'JSON cases or JSONL runs'}: {path}")
        runs = load_runs(run_paths, cases, root)
        if args.command == "validate":
            parts = [f"{len(cases)} versioned cases"]
            if pilot is not None:
                parts.append(f"pilot manifest ({pilot['experiment_id']})")
            if standalone_runs:
                parts.append(f"{standalone_runs} standalone run record{'s' if standalone_runs != 1 else ''}")
            parts.append(f"{len(runs)} run records")
            print(f"Validated {', '.join(parts)}. Evidence adequacy is a review responsibility.")
        else:
            report = summarize(
                runs,
                cases,
                synthetic_only=args.synthetic_only,
                baseline_condition=args.baseline,
                treatment_condition=args.treatment,
                pilot=pilot,
            )
            if args.json:
                print(json.dumps(report, indent=2, allow_nan=False))
            else:
                print_summary(report)
        return 0
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
