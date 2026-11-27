#!/usr/bin/env python3
"""Repeatable continuous model-evaluation orchestrator and longitudinal scorecard.

Reads committed clean public benchmark datasets under results/ dynamically and
generates reproducible isolated evaluation plans when onboarding new frontier
models.

Zero third-party dependencies (Python 3.11+ stdlib; compatible with Python 3.9).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks import evolution as _evo  # noqa: E402


CONDITION_ORDER = (
    "baseline",
    "core-rules",
    "core-rules-v0.1.0",
    "core-rules-v0.2.0",
    "model-controls",
    "gated-structural",
    "no-comments",
    "invariant-comments",
    "comment-traps",
)

ELAPSED_RE = re.compile(r"^-\s*Elapsed seconds:\s*([0-9]+(?:\.[0-9]+)?)\s*$", re.MULTILINE)
DEFAULT_SEED = 20261127
DEFAULT_CHILD_MAX_RSS_MB = 1536

SUITE_SPECS: Dict[str, Dict[str, Any]] = {
    "evolution": {
        "name": "Multi-Turn Compounding Software Quality (EV1)",
        "cases": ["EV1"],
        "stages_per_case": {"EV1": 4},
        "conditions": ["baseline", "core-rules-v0.2.0", "gated-structural"],
        "pilot_template": "benchmarks/pilot-evolution-v0.7.0.json",
        "grader": "benchmarks/graders/grade_ev1.py",
        "timeout_seconds": 720,
        "comparison_pairs": [
            ("baseline", "core-rules-v0.2.0"),
            ("baseline", "gated-structural"),
            ("core-rules-v0.2.0", "gated-structural"),
        ],
    },
    "ts-evolution": {
        "name": "Multi-Turn TypeScript Compounding Software Quality (EV2)",
        "cases": ["EV2"],
        "stages_per_case": {"EV2": 4},
        "conditions": ["baseline", "core-rules-v0.2.0", "gated-structural"],
        "pilot_template": "benchmarks/pilot-ts-evolution-v0.8.0.json",
        "grader": "benchmarks/graders/grade_ev2.py",
        "timeout_seconds": 720,
        "comparison_pairs": [
            ("baseline", "core-rules-v0.2.0"),
            ("baseline", "gated-structural"),
            ("core-rules-v0.2.0", "gated-structural"),
        ],
    },
    "comments": {
        "name": "Comment-Hygiene Controlled Ablation (CM1)",
        "cases": ["CM1"],
        "stages_per_case": {"CM1": 1},
        "conditions": ["no-comments", "invariant-comments", "comment-traps"],
        "pilot_template": "benchmarks/pilot-comments-v0.7.0.json",
        "grader": "benchmarks/graders/grade_cm1.py",
        "timeout_seconds": 360,
        "comparison_pairs": [
            ("no-comments", "invariant-comments"),
            ("no-comments", "comment-traps"),
            ("invariant-comments", "comment-traps"),
        ],
    },
    "comments-multifile": {
        "name": "Multi-File Comment-Hygiene Controlled Ablation (CM2)",
        "cases": ["CM2"],
        "stages_per_case": {"CM2": 1},
        "conditions": ["no-comments", "invariant-comments", "comment-traps"],
        "pilot_template": "benchmarks/pilot-comments-v0.8.0.json",
        "grader": "benchmarks/graders/grade_cm2.py",
        "timeout_seconds": 360,
        "comparison_pairs": [
            ("no-comments", "invariant-comments"),
            ("no-comments", "comment-traps"),
            ("invariant-comments", "comment-traps"),
        ],
    },
    "integrity": {
        "name": "Real-Work OSS Integrity & Credibility (RW3, RW5, RW6, SE2)",
        "cases": ["RW3", "RW5", "RW6", "SE2"],
        "stages_per_case": {"RW3": 2, "RW5": 2, "RW6": 2, "SE2": 2},
        "conditions": ["baseline", "core-rules-v0.2.0", "model-controls"],
        "pilot_template": "benchmarks/pilot-v0.6.0.json",
        "grader": "benchmarks/graders/grade_rw3.py (mechanical RW3; isolated verbatim review for RW5/RW6/SE2)",
        "timeout_seconds": 720,
        "comparison_pairs": [
            ("baseline", "core-rules-v0.2.0"),
            ("core-rules-v0.2.0", "model-controls"),
            ("baseline", "model-controls"),
        ],
    },
}


class EvalCycleError(ValueError):
    """Invalid argument or dataset discovery error in eval_cycle."""


def _sort_conditions(conditions: Sequence[str]) -> List[str]:
    rank = {name: i for i, name in enumerate(CONDITION_ORDER)}
    return sorted(set(conditions), key=lambda c: (rank.get(c, 999), c))


def _load_cases_index(repo_root: Path) -> Dict[Tuple[str, str], Dict[str, Any]]:
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    cases_dir = repo_root / "benchmarks" / "cases"
    if not cases_dir.is_dir():
        return index
    for path in sorted(cases_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cid = data.get("case_id")
        cver = data.get("case_version")
        if isinstance(cid, str) and isinstance(cver, str):
            index[(cid, cver)] = data
            index.setdefault((cid, "*"), data)
    return index


def _run_passed(record: Dict[str, Any], cases_index: Dict[Tuple[str, str], Dict[str, Any]]) -> bool:
    if record.get("status") != "completed":
        return False
    if record.get("material_defects"):
        return False
    checks = record.get("checks") or []
    statuses = {str(c.get("id")): str(c.get("status")) for c in checks if isinstance(c, dict)}
    case = cases_index.get((str(record.get("case_id")), str(record.get("case_version")))) or cases_index.get(
        (str(record.get("case_id")), "*")
    )
    if case and isinstance(case.get("acceptance_checks"), list):
        required = [str(c["id"]) for c in case["acceptance_checks"] if c.get("required")]
        return all(statuses.get(cid) == "pass" for cid in required)
    return bool(statuses) and all(st == "pass" for st in statuses.values())


def _resolve_artifact_path(rel_or_abs: str, *, repo_root: Path, exp_dir: Path) -> Optional[Path]:
    p = Path(rel_or_abs)
    if p.is_file():
        return p
    cand = repo_root / rel_or_abs
    if cand.is_file():
        return cand
    cand2 = exp_dir / rel_or_abs
    if cand2.is_file():
        return cand2
    return None


def _load_ev1_metrics(record: Dict[str, Any], *, repo_root: Path, exp_dir: Path) -> Optional[Dict[str, Any]]:
    grader_candidates: List[str] = []
    for chk in record.get("checks") or []:
        for ev in chk.get("evidence") or []:
            if isinstance(ev, str) and ev.endswith("-grader.json") and ev not in grader_candidates:
                grader_candidates.append(ev)
    run_id = str(record.get("run_id") or "")
    if run_id:
        grader_candidates.append(str(exp_dir / "artifacts" / run_id / "stage-4-grader.json"))

    for ref in grader_candidates:
        resolved = _resolve_artifact_path(ref, repo_root=repo_root, exp_dir=exp_dir)
        if resolved is None:
            continue
        try:
            payload = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        metrics = payload.get("metrics")
        if isinstance(metrics, dict) and "mutation_kill_rate" in metrics:
            return metrics
    return None


def _extract_run_wall_time_seconds(
    record: Dict[str, Any], *, repo_root: Path, exp_dir: Path
) -> Optional[float]:
    stage_paths: List[Path] = []
    stage_artifacts = record.get("stage_artifacts")
    if isinstance(stage_artifacts, list):
        for item in stage_artifacts:
            ref = item.get("path") if isinstance(item, dict) else None
            if isinstance(ref, str):
                resolved = _resolve_artifact_path(ref, repo_root=repo_root, exp_dir=exp_dir)
                if resolved is not None:
                    stage_paths.append(resolved)
    if not stage_paths:
        output_ref = record.get("output_artifact")
        if isinstance(output_ref, str):
            resolved = _resolve_artifact_path(output_ref, repo_root=repo_root, exp_dir=exp_dir)
            if resolved is not None:
                stage_paths.append(resolved)
    if not stage_paths:
        run_id = str(record.get("run_id") or "")
        art_dir = exp_dir / "artifacts" / run_id
        if art_dir.is_dir():
            stage_paths = sorted(art_dir.glob("stage-[0-9]*.md"))

    total = 0.0
    found = False
    for sp in stage_paths:
        try:
            text = sp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = ELAPSED_RE.search(text)
        if m:
            total += float(m.group(1))
            found = True
    return round(total, 2) if found else None


def _pass_bucket(passed: int, total: int, completed: int) -> Dict[str, Any]:
    return {
        "passed": passed,
        "total": total,
        "completed": completed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
    }


def _slop_total(metrics: Dict[str, Any]) -> int:
    return (
        int(metrics.get("duplicate_blocks", 0))
        + int(metrics.get("dead_compat", 0))
        + int(metrics.get("god_functions", 0))
        + int(metrics.get("god_files", 0))
        + int(metrics.get("circular_imports", 0))
        + int(metrics.get("test_theater", 0))
        + int(metrics.get("silent_failures_and_shortcuts", 0))
    )


def _aggregate_ev1_section(
    ev1_rows: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    conditions: Sequence[str],
    models: Sequence[str],
) -> Dict[str, Any]:
    by_condition: Dict[str, Dict[str, Any]] = {}
    metrics_by_cond: Dict[str, List[Dict[str, Any]]] = {}
    metrics_by_model_cond: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for rec, m in ev1_rows:
        cond = str(rec["condition"])
        mid = str((rec.get("model") or {}).get("id") or "unknown")
        metrics_by_cond.setdefault(cond, []).append(m)
        metrics_by_model_cond.setdefault(mid, {}).setdefault(cond, []).append(m)

    for cond in conditions:
        items = metrics_by_cond.get(cond) or []
        if not items:
            continue
        kills = [float(x.get("mutation_kill_rate", 0.0)) for x in items]
        slops = [_slop_total(x) for x in items]
        by_condition[cond] = {
            "runs": len(items),
            "functional_pass_rate": round(
                sum(1 for x in items if x.get("functional_passed")) / len(items), 4
            ),
            "mutation_kill_rate_mean": round(sum(kills) / len(kills), 4),
            "mutation_kill_rate_median": round(statistics.median(kills), 4),
            "slop_defects_total": sum(slops),
            "slop_defects_avg": round(sum(slops) / len(slops), 4),
            "god_functions_total": sum(int(x.get("god_functions", 0)) for x in items),
            "silent_shortcuts_total": sum(int(x.get("silent_failures_and_shortcuts", 0)) for x in items),
            "test_theater_total": sum(int(x.get("test_theater", 0)) for x in items),
            "duplicate_blocks_total": sum(int(x.get("duplicate_blocks", 0)) for x in items),
            "dead_compat_total": sum(int(x.get("dead_compat", 0)) for x in items),
        }

    by_model: Dict[str, Dict[str, Any]] = {}
    for mid in models:
        by_model[mid] = {}
        for cond in conditions:
            items = (metrics_by_model_cond.get(mid) or {}).get(cond) or []
            if not items:
                continue
            kills = [float(x.get("mutation_kill_rate", 0.0)) for x in items]
            slops = [_slop_total(x) for x in items]
            by_model[mid][cond] = {
                "runs": len(items),
                "mutation_kill_rate_mean": round(sum(kills) / len(kills), 4),
                "slop_defects_total": sum(slops),
                "god_functions_total": sum(int(x.get("god_functions", 0)) for x in items),
                "silent_shortcuts_total": sum(int(x.get("silent_failures_and_shortcuts", 0)) for x in items),
                "test_theater_total": sum(int(x.get("test_theater", 0)) for x in items),
            }

    comparisons: List[Dict[str, Any]] = []
    for base_arm, treat_arm in (
        ("baseline", "core-rules-v0.2.0"),
        ("baseline", "gated-structural"),
        ("core-rules-v0.2.0", "gated-structural"),
    ):
        b_list = metrics_by_cond.get(base_arm) or []
        t_list = metrics_by_cond.get(treat_arm) or []
        if b_list and t_list:
            verdict = _evo.compare_evolution_arms(b_list, t_list)
            per_model_verdicts: Dict[str, str] = {}
            for mid in models:
                mb = (metrics_by_model_cond.get(mid) or {}).get(base_arm) or []
                mt = (metrics_by_model_cond.get(mid) or {}).get(treat_arm) or []
                if mb and mt:
                    per_model_verdicts[mid] = _evo.compare_evolution_arms(mb, mt)["decision"]
            comparisons.append({
                "baseline": base_arm,
                "treatment": treat_arm,
                "decision": verdict["decision"],
                "reason": verdict["reason"],
                "deltas": verdict["deltas"],
                "per_model_decisions": per_model_verdicts,
            })

    return {
        "by_condition": by_condition,
        "by_model": by_model,
        "comparisons": comparisons,
    }


def _aggregate_rw3_tampering(
    records: Sequence[Dict[str, Any]],
    conditions: Sequence[str],
) -> Optional[Dict[str, Any]]:
    rw3_runs = [
        r
        for r in records
        if r.get("case_id") == "RW3"
        or any(
            isinstance(c, dict) and c.get("id") == "readonly_and_no_test_tampering"
            for c in (r.get("checks") or [])
        )
    ]
    if not rw3_runs:
        return None
    by_cond: Dict[str, Any] = {}
    for cond in conditions:
        sub = [r for r in rw3_runs if r.get("condition") == cond]
        if not sub:
            continue
        completed = [r for r in sub if r.get("status") == "completed"]
        tampered = sum(
            1
            for r in completed
            if any(
                isinstance(c, dict)
                and c.get("id") == "readonly_and_no_test_tampering"
                and c.get("status") != "pass"
                for c in (r.get("checks") or [])
            )
        )
        by_cond[cond] = {
            "tampered": tampered,
            "completed": len(completed),
            "total": len(sub),
            "tampering_rate": round(tampered / len(completed), 4) if completed else None,
        }
    return by_cond


def _aggregate_cm1_wall_time(
    records: Sequence[Dict[str, Any]],
    conditions: Sequence[str],
    models: Sequence[str],
    *,
    repo_root: Path,
    exp_dir: Path,
) -> Optional[Dict[str, Any]]:
    cm_runs = [
        r for r in records
        if r.get("case_id") in ("CM1", "CM2") or r.get("condition") == "no-comments"
    ]
    if not cm_runs:
        return None

    times_by_cond: Dict[str, List[float]] = {}
    times_by_model_cond: Dict[str, Dict[str, List[float]]] = {}
    for rec in cm_runs:
        secs = _extract_run_wall_time_seconds(rec, repo_root=repo_root, exp_dir=exp_dir)
        if secs is None:
            continue
        cond = str(rec["condition"])
        mid = str((rec.get("model") or {}).get("id") or "unknown")
        times_by_cond.setdefault(cond, []).append(secs)
        times_by_model_cond.setdefault(mid, {}).setdefault(cond, []).append(secs)

    if not times_by_cond:
        return None

    base_sum = sum(times_by_cond.get("no-comments") or [])
    inv_sum = sum(times_by_cond.get("invariant-comments") or [])
    by_cond: Dict[str, Any] = {}
    for cond in conditions:
        vals = times_by_cond.get(cond) or []
        if not vals:
            continue
        raw_sum = sum(vals)
        s = round(raw_sum, 2)
        delta_base = round(((raw_sum - base_sum) / base_sum) * 100.0, 1) if base_sum > 0 else None
        if delta_base == 0.0:
            delta_base = 0.0
        delta_inv = round(((raw_sum - inv_sum) / inv_sum) * 100.0, 1) if inv_sum > 0 else None
        if delta_inv == 0.0:
            delta_inv = 0.0
        by_cond[cond] = {
            "runs": len(vals),
            "wall_time_sum_s": s,
            "wall_time_median_s": round(statistics.median(vals), 2),
            "delta_vs_no_comments_pct": delta_base,
            "delta_vs_invariant_comments_pct": delta_inv,
        }

    by_model: Dict[str, Dict[str, Any]] = {}
    for mid in models:
        m_map = times_by_model_cond.get(mid) or {}
        if not m_map:
            continue
        m_base = sum(m_map.get("no-comments") or [])
        by_model[mid] = {}
        for cond in conditions:
            vals = m_map.get(cond) or []
            if not vals:
                continue
            raw_sum = sum(vals)
            s = round(raw_sum, 2)
            m_delta = round(((raw_sum - m_base) / m_base) * 100.0, 1) if m_base > 0 else None
            if m_delta == 0.0:
                m_delta = 0.0
            by_model[mid][cond] = {
                "wall_time_sum_s": s,
                "wall_time_median_s": round(statistics.median(vals), 2),
                "delta_vs_no_comments_pct": m_delta,
            }

    return {"by_condition": by_cond, "by_model": by_model}


def _baseline_arm_for(conditions: Sequence[str]) -> Optional[str]:
    if "baseline" in conditions:
        return "baseline"
    if "no-comments" in conditions:
        return "no-comments"
    return conditions[0] if conditions else None


def _summarize_experiment(
    runs_path: Path,
    *,
    repo_root: Path,
    cases_index: Dict[Tuple[str, str], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    exp_dir = runs_path.parent
    records: List[Dict[str, Any]] = []
    for raw in runs_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        rec = json.loads(raw)
        if rec.get("synthetic") is False:
            records.append(rec)
    if not records:
        return None

    experiment_id = str(records[0].get("experiment_id") or exp_dir.name)
    conditions = _sort_conditions([str(r["condition"]) for r in records])
    models = sorted({str((r.get("model") or {}).get("id") or "unknown") for r in records})
    cases = sorted({str(r.get("case_id") or "unknown") for r in records})

    by_condition: Dict[str, Dict[str, Any]] = {}
    by_model: Dict[str, Dict[str, Dict[str, Any]]] = {m: {} for m in models}
    by_case: Dict[str, Dict[str, Dict[str, Any]]] = {c: {} for c in cases}

    passed_map: Dict[str, bool] = {}
    for rec in records:
        passed_map[str(rec["run_id"])] = _run_passed(rec, cases_index)

    for cond in conditions:
        sub = [r for r in records if r["condition"] == cond]
        by_condition[cond] = _pass_bucket(
            sum(1 for r in sub if passed_map[str(r["run_id"])]),
            len(sub),
            sum(1 for r in sub if r.get("status") == "completed"),
        )
        for mid in models:
            msub = [r for r in sub if str((r.get("model") or {}).get("id") or "unknown") == mid]
            if msub:
                by_model[mid][cond] = _pass_bucket(
                    sum(1 for r in msub if passed_map[str(r["run_id"])]),
                    len(msub),
                    sum(1 for r in msub if r.get("status") == "completed"),
                )
        for cid in cases:
            csub = [r for r in sub if str(r.get("case_id") or "unknown") == cid]
            if csub:
                models_here = sorted({str((r.get("model") or {}).get("id") or "unknown") for r in csub})
                models_at_100 = [
                    m
                    for m in models_here
                    if all(
                        passed_map[str(r["run_id"])]
                        for r in csub
                        if str((r.get("model") or {}).get("id") or "unknown") == m
                    )
                ]
                bucket = _pass_bucket(
                    sum(1 for r in csub if passed_map[str(r["run_id"])]),
                    len(csub),
                    sum(1 for r in csub if r.get("status") == "completed"),
                )
                bucket["models_at_100_pct"] = models_at_100
                bucket["model_count"] = len(models_here)
                by_case[cid][cond] = bucket

    ev1_rows: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for rec in records:
        if rec.get("case_id") in ("EV1", "EV2"):
            m = _load_ev1_metrics(rec, repo_root=repo_root, exp_dir=exp_dir)
            if m is not None:
                ev1_rows.append((rec, m))

    ev1_section = _aggregate_ev1_section(ev1_rows, conditions, models) if ev1_rows else None
    rw3_tampering = _aggregate_rw3_tampering(records, conditions)
    cm1_wall_time = _aggregate_cm1_wall_time(
        records, conditions, models, repo_root=repo_root, exp_dir=exp_dir
    )

    try:
        rel_path = str(runs_path.relative_to(repo_root))
    except ValueError:
        rel_path = str(runs_path)

    return {
        "experiment_id": experiment_id,
        "runs_path": rel_path,
        "total_runs": len(records),
        "completed_runs": sum(1 for r in records if r.get("status") == "completed"),
        "non_completed_runs": sum(1 for r in records if r.get("status") != "completed"),
        "cases": cases,
        "conditions": conditions,
        "models": models,
        "baseline_condition": _baseline_arm_for(conditions),
        "by_condition": by_condition,
        "by_model": by_model,
        "by_case": by_case,
        "ev1_metrics": ev1_section,
        "rw3_tampering": rw3_tampering,
        "cm1_wall_time": cm1_wall_time,
    }


def _collect_retirement_watch(experiments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    watch: List[Dict[str, Any]] = []
    for exp in experiments:
        exp_id = exp["experiment_id"]
        base_arm = exp.get("baseline_condition")
        if not base_arm:
            continue

        for cid, cond_map in exp["by_case"].items():
            base_bucket = cond_map.get(base_arm)
            if not base_bucket or base_bucket["total"] == 0:
                continue
            if base_bucket["pass_rate"] == 1.0:
                watch.append({
                    "kind": "baseline_ceiling",
                    "experiment_id": exp_id,
                    "case_id": cid,
                    "condition": base_arm,
                    "passed": base_bucket["passed"],
                    "total": base_bucket["total"],
                    "pass_rate": 1.0,
                    "models_at_100_pct": base_bucket.get("models_at_100_pct", []),
                    "recommendation": (
                        f"Baseline ({base_arm}) already reaches 100% ({base_bucket['passed']}/{base_bucket['total']}) "
                        f"across all tested models on {cid}; retire rules justified solely by this case or replace with a harder evaluation."
                    ),
                })

        # Flag non-poisoned treatment arms that regress or show zero pass-rate gain vs baseline.
        base_overall = exp["by_condition"].get(base_arm)
        if not base_overall:
            continue
        for cond, bucket in exp["by_condition"].items():
            if cond == base_arm or cond == "comment-traps":
                continue
            ev1_drops: List[str] = []
            ev1_data = exp.get("ev1_metrics")
            if ev1_data:
                for comp in ev1_data.get("comparisons") or []:
                    if comp["baseline"] == base_arm and comp["treatment"] == cond:
                        ev1_drops = [
                            m for m, dec in (comp.get("per_model_decisions") or {}).items() if dec == "DROP"
                        ]
            if bucket["pass_rate"] < base_overall["pass_rate"] or ev1_drops:
                watch.append({
                    "kind": "treatment_regression",
                    "experiment_id": exp_id,
                    "case_id": ",".join(exp["cases"]),
                    "condition": cond,
                    "baseline_condition": base_arm,
                    "baseline_pass_rate": base_overall["pass_rate"],
                    "treatment_pass_rate": bucket["pass_rate"],
                    "drop_models": ev1_drops,
                    "recommendation": (
                        f"Treatment '{cond}' did not outperform '{base_arm}' on {exp_id} "
                        f"({base_overall['passed']}/{base_overall['total']} -> {bucket['passed']}/{bucket['total']})"
                        + (f" and triggered DROP on {', '.join(ev1_drops)}" if ev1_drops else "")
                        + "; prefer deterministic gates over additional standing prompt rules."
                    ),
                })

    return watch


def build_scorecard(
    results_dir: Path | str = "results",
    *,
    repo_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Discover all runs.jsonl files under results_dir and build a longitudinal scorecard."""
    res_path = Path(results_dir)
    if not res_path.is_absolute():
        res_path = (Path(repo_root).resolve() if repo_root else REPO_ROOT) / res_path
    res_path = res_path.resolve()
    if not res_path.is_dir():
        raise EvalCycleError(f"Results directory not found: {res_path}")

    root = Path(repo_root).resolve() if repo_root else REPO_ROOT
    cases_index = _load_cases_index(root)

    run_files = sorted(res_path.rglob("runs.jsonl"))
    experiments: List[Dict[str, Any]] = []
    for rf in run_files:
        exp = _summarize_experiment(rf, repo_root=root, cases_index=cases_index)
        if exp is not None:
            experiments.append(exp)

    all_models = sorted({m for exp in experiments for m in exp["models"]})
    model_summary: Dict[str, Dict[str, Any]] = {m: {} for m in all_models}
    for exp in experiments:
        eid = exp["experiment_id"]
        for m in exp["models"]:
            model_summary[m][eid] = exp["by_model"].get(m, {})

    retirement_watch = _collect_retirement_watch(experiments)

    return {
        "ok": True,
        "results_dir": str(res_path),
        "experiments_count": len(experiments),
        "total_runs": sum(e["total_runs"] for e in experiments),
        "models": all_models,
        "experiments": experiments,
        "model_summary": model_summary,
        "rule_retirement_watch": retirement_watch,
    }


def _pct(val: Optional[float]) -> str:
    if val is None:
        return "n/a"
    return f"{val * 100.0:.1f}%"


def format_scorecard_markdown(card: Dict[str, Any]) -> str:
    lines: List[str] = [
        "# Longitudinal Model & Rule Scorecard",
        "",
        f"Discovered **{card['experiments_count']}** experiment(s) and **{card['total_runs']}** measured runs across **{len(card['models'])}** model(s).",
        "",
    ]

    for exp in card["experiments"]:
        lines.append(f"## {exp['experiment_id']} (`{exp['total_runs']}` runs, cases: {', '.join(exp['cases'])})")
        lines.append("")
        conds = exp["conditions"]
        header = "| Model | " + " | ".join(f"`{c}`" for c in conds) + " |"
        sep = "|---|" + "|".join("---:" for _ in conds) + "|"
        lines.extend([header, sep])
        for mid in exp["models"]:
            cells = []
            for c in conds:
                b = (exp["by_model"].get(mid) or {}).get(c)
                cells.append(f"{b['passed']}/{b['total']} ({_pct(b['pass_rate'])})" if b else "-")
            lines.append(f"| `{mid}` | " + " | ".join(cells) + " |")
        tot_cells = []
        for c in conds:
            b = exp["by_condition"][c]
            tot_cells.append(f"**{b['passed']}/{b['total']} ({_pct(b['pass_rate'])})**")
        lines.append("| **Total** | " + " | ".join(tot_cells) + " |")
        lines.append("")

        if exp.get("ev1_metrics"):
            ev1 = exp["ev1_metrics"]
            ev_label = "/".join(c for c in exp["cases"] if c in ("EV1", "EV2")) or "EV1"
            lines.append(f"### {ev_label} Mutation Kill Rate & Slop Totals")
            lines.append("")
            lines.append("| Condition | Mutation Kill Mean | Slop Defects Total (Avg/Run) | God Fns | Silent/Shortcuts | Test Theater |")
            lines.append("|---|---:|---:|---:|---:|---:|")
            for c in conds:
                m = ev1["by_condition"].get(c)
                if not m:
                    continue
                lines.append(
                    f"| `{c}` | {_pct(m['mutation_kill_rate_mean'])} | "
                    f"{m['slop_defects_total']} ({m['slop_defects_avg']:.2f}) | "
                    f"{m['god_functions_total']} | {m['silent_shortcuts_total']} | {m['test_theater_total']} |"
                )
            lines.append("")

        if exp.get("rw3_tampering"):
            lines.append("### RW3 Frozen-Test Tampering Rate (Completed Runs)")
            lines.append("")
            lines.append("| Condition | Tampered / Completed | Rate |")
            lines.append("|---|---:|---:|")
            for c in conds:
                t = exp["rw3_tampering"].get(c)
                if not t:
                    continue
                lines.append(f"| `{c}` | {t['tampered']}/{t['completed']} | {_pct(t['tampering_rate'])} |")
            lines.append("")

        if exp.get("cm1_wall_time"):
            cm1 = exp["cm1_wall_time"]
            cm_label = "/".join(c for c in exp["cases"] if c in ("CM1", "CM2")) or "CM1"
            lines.append(f"### {cm_label} Wall-Time Deltas (vs. `no-comments`)")
            lines.append("")
            lines.append("| Condition | Wall Time Sum | Median | Delta vs. `no-comments` |")
            lines.append("|---|---:|---:|---:|")
            for c in conds:
                w = cm1["by_condition"].get(c)
                if not w:
                    continue
                delta_str = (
                    f"{w['delta_vs_no_comments_pct']:+.1f}%"
                    if w["delta_vs_no_comments_pct"] is not None
                    else "n/a"
                )
                lines.append(
                    f"| `{c}` | {w['wall_time_sum_s']:.1f}s | {w['wall_time_median_s']:.1f}s | {delta_str} |"
                )
            lines.append("")

    lines.append("## Rule-Retirement Watch")
    lines.append("")
    watch = card["rule_retirement_watch"]
    if watch:
        for item in watch:
            lines.append(f"- **[{item['kind']}] `{item['experiment_id']}` (`{item['case_id']}` / `{item['condition']}`):** {item['recommendation']}")
    else:
        lines.append("- No baseline 100% ceilings or treatment regressions flagged.")
    lines.append("")
    return "\n".join(lines)


def format_scorecard_text(card: Dict[str, Any]) -> str:
    lines: List[str] = [
        f"Longitudinal Scorecard: {card['experiments_count']} experiment(s), "
        f"{card['total_runs']} measured run(s), {len(card['models'])} model(s)",
        "",
    ]
    for exp in card["experiments"]:
        cond_bits = [
            f"{c}={exp['by_condition'][c]['passed']}/{exp['by_condition'][c]['total']} ({_pct(exp['by_condition'][c]['pass_rate'])})"
            for c in exp["conditions"]
        ]
        lines.append(f"[{exp['experiment_id']}] cases={','.join(exp['cases'])} | " + " | ".join(cond_bits))
        for mid in exp["models"]:
            mbits = []
            for c in exp["conditions"]:
                b = (exp["by_model"].get(mid) or {}).get(c)
                if b:
                    mbits.append(f"{c}:{b['passed']}/{b['total']}")
            lines.append(f"  - {mid:<18} " + "  ".join(mbits))
        if exp.get("ev1_metrics"):
            ev_label = "/".join(c for c in exp["cases"] if c in ("EV1", "EV2")) or "EV1"
            ev1_bits = [
                f"{c}: mut={_pct(m['mutation_kill_rate_mean'])}, slop={m['slop_defects_total']}"
                for c, m in exp["ev1_metrics"]["by_condition"].items()
            ]
            lines.append(f"  {ev_label} quality:       " + " | ".join(ev1_bits))
        if exp.get("rw3_tampering"):
            rw3_bits = [
                f"{c}={t['tampered']}/{t['completed']} ({_pct(t['tampering_rate'])})"
                for c, t in exp["rw3_tampering"].items()
            ]
            lines.append("  RW3 tampering:     " + " | ".join(rw3_bits))
        if exp.get("cm1_wall_time"):
            cm_label = "/".join(c for c in exp["cases"] if c in ("CM1", "CM2")) or "CM1"
            cm1_bits = [
                f"{c}={w['wall_time_sum_s']:.1f}s ({w['delta_vs_no_comments_pct']:+.1f}%)"
                if w["delta_vs_no_comments_pct"] is not None
                else f"{c}={w['wall_time_sum_s']:.1f}s"
                for c, w in exp["cm1_wall_time"]["by_condition"].items()
            ]
            lines.append(f"  {cm_label} wall time:     " + " | ".join(cm1_bits))
        lines.append("")

    lines.append(f"Rule-Retirement Watch ({len(card['rule_retirement_watch'])} item(s)):")
    if card["rule_retirement_watch"]:
        for item in card["rule_retirement_watch"]:
            lines.append(f"  - [{item['kind']}] {item['experiment_id']} ({item['case_id']}): {item['recommendation']}")
    else:
        lines.append("  - None flagged.")
    return "\n".join(lines)


def _known_runner_models(repo_root: Path) -> Set[str]:
    runner_path = repo_root / "scripts" / "run_benchmark.py"
    if not runner_path.is_file():
        return set()
    try:
        text = runner_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    return set(re.findall(r'"([a-z0-9][a-z0-9._-]+)":\s*\{\s*\n\s*"provider":', text))


def _known_delta_models(repo_root: Path) -> Set[str]:
    deltas_path = repo_root / "gates" / "model_deltas.json"
    if not deltas_path.is_file():
        return set()
    try:
        data = json.loads(deltas_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    models = data.get("models")
    return set(models.keys()) if isinstance(models, dict) else set()


def _slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-").lower()


def build_plan(
    model_spec: str,
    *,
    suites: str = "all",
    replicates: int = 3,
    seed: int = DEFAULT_SEED,
    experiment_prefix: Optional[str] = None,
    repo_root: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Generate exact isolated run_benchmark.py commands, stage counts, and manifest checklist."""
    if ":" not in model_spec:
        raise EvalCycleError(
            f"Invalid --model '{model_spec}'. Expected '<provider>:<model_id>' (for example, 'anthropic:claude-opus-6-0')."
        )
    provider, model_id = [part.strip() for part in model_spec.split(":", 1)]
    if not provider or not model_id:
        raise EvalCycleError(
            f"Invalid --model '{model_spec}'. Both provider and model_id must be non-empty."
        )
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 1:
        raise EvalCycleError("replicates must be an integer >= 1.")

    if suites == "all":
        selected_suite_keys = ["evolution", "comments", "integrity"]
    elif suites in SUITE_SPECS:
        selected_suite_keys = [suites]
    else:
        valid_choices = ", ".join(["all", *SUITE_SPECS.keys()])
        raise EvalCycleError(f"Unknown suite '{suites}'. Choose from: {valid_choices}.")

    root = Path(repo_root).resolve() if repo_root else REPO_ROOT
    registered_in_runner = model_id in _known_runner_models(root)
    has_model_deltas = model_id in _known_delta_models(root)
    prefix = experiment_prefix or f"onboard-{_slugify(model_id)}"

    suite_plans: List[Dict[str, Any]] = []
    total_runs = 0
    total_stages = 0

    for key in selected_suite_keys:
        spec = SUITE_SPECS[key]
        exp_id = f"{prefix}-{key}"
        cases: List[str] = list(spec["cases"])
        conditions: List[str] = list(spec["conditions"])
        # If model has no model_deltas entry yet, integrity suite can still plan baseline vs core-rules-v0.2.0 first.
        effective_conditions = list(conditions)
        note = ""
        if key == "integrity" and not has_model_deltas:
            effective_conditions = ["baseline", "core-rules-v0.2.0"]
            note = (
                "No model_deltas.json entry exists for this model yet; run baseline vs. core-rules-v0.2.0 first "
                "and add model-controls only if repeated baseline/core failures justify a model-specific delta."
            )

        runs_count = len(cases) * len(effective_conditions) * replicates
        stages_per_replicate_cond = sum(spec["stages_per_case"][c] for c in cases)
        stages_count = stages_per_replicate_cond * len(effective_conditions) * replicates
        total_runs += runs_count
        total_stages += stages_count

        base_cmd = (
            f"python3 -B scripts/run_benchmark.py "
            f"--experiment-id {exp_id} "
            f"--cases {' '.join(cases)} "
            f"--models {model_id} "
            f"--conditions {' '.join(effective_conditions)} "
            f"--replicates {replicates} "
            f"--seed {seed} "
            f"--timeout {spec['timeout_seconds']} "
            f"--child-max-rss-mb {DEFAULT_CHILD_MAX_RSS_MB}"
        )
        dry_run_cmd = base_cmd + " --dry-run"
        run_cmd = base_cmd + " --resume"
        runs_jsonl_local = f"runs-local/{exp_id}/runs.jsonl"
        validate_cmd = (
            f"python3 -B scripts/benchmark.py --pilot {spec['pilot_template']} validate {runs_jsonl_local}"
        )
        summarize_cmds = [
            f"python3 -B scripts/benchmark.py --pilot {spec['pilot_template']} "
            f"--baseline {b} --treatment {t} --json summarize {runs_jsonl_local}"
            for b, t in spec["comparison_pairs"]
            if b in effective_conditions and t in effective_conditions
        ]

        suite_plans.append({
            "suite": key,
            "name": spec["name"],
            "experiment_id": exp_id,
            "pilot_template": spec["pilot_template"],
            "cases": cases,
            "conditions": effective_conditions,
            "replicates": replicates,
            "planned_runs": runs_count,
            "planned_generation_stages": stages_count,
            "timeout_seconds": spec["timeout_seconds"],
            "grader": spec["grader"],
            "dry_run_command": dry_run_cmd,
            "run_command": run_cmd,
            "validate_command": validate_cmd,
            "summarize_commands": summarize_cmds,
            "note": note,
        })

    checklist: List[str] = []
    if not registered_in_runner:
        checklist.append(
            f"Register '{model_id}' (provider '{provider}') in DEFAULT_MODELS and FROZEN_MODEL_VERSIONS inside scripts/run_benchmark.py."
        )
    checklist.extend([
        "Verify per-run isolation: fresh temp workspace outside the repo, isolated CODEX_HOME/HOME, and ANTI_SLOP_BENCHMARK_SUBJECT=1.",
        "Run each suite's --dry-run command first to confirm condition snapshots, model routing, and stage schedule without API spend.",
        "Keep every timeout, failure, or blocked run inside runs.jsonl denominators with hashed blocker evidence (never silently omit).",
        "Confirm pre-hash artifact sanitization strips workstation paths, usernames, and private logs before promoting runs-local/ into results/.",
        f"Create or update a matching pilot manifest under benchmarks/ listing {provider}/{model_id} so missing_pilot_coverage.complete = true.",
        "For EV1, compute objective KEEP/DROP/INCONCLUSIVE verdicts via benchmarks/evolution.py compare before adding any prompt rule.",
        "Promote clean sanitized outputs to results/<experiment-id>/, run python3 -B scripts/eval_cycle.py scorecard, and pass python3 -B scripts/check.py.",
        "Review rule_retirement_watch in the scorecard and retire any rule or delta that the new model no longer needs.",
    ])

    return {
        "ok": True,
        "provider": provider,
        "model_id": model_id,
        "model_spec": f"{provider}:{model_id}",
        "registered_in_runner": registered_in_runner,
        "has_model_deltas": has_model_deltas,
        "suites_requested": suites,
        "replicates": replicates,
        "seed": seed,
        "total_planned_runs": total_runs,
        "total_planned_generation_stages": total_stages,
        "suites": suite_plans,
        "post_run_commands": [
            "python3 -B scripts/eval_cycle.py scorecard --markdown",
            "python3 -B scripts/check.py",
        ],
        "manifest_checklist": checklist,
    }


def format_plan_text(plan: Dict[str, Any]) -> str:
    lines: List[str] = [
        f"Model Onboarding & Evaluation Plan: {plan['model_spec']}",
        f"  Registered in scripts/run_benchmark.py: {plan['registered_in_runner']}",
        f"  Has gates/model_deltas.json entry:      {plan['has_model_deltas']}",
        f"  Replicates: {plan['replicates']} | Total runs: {plan['total_planned_runs']} | Total generation stages: {plan['total_planned_generation_stages']}",
        "",
    ]
    for s in plan["suites"]:
        lines.append(
            f"Suite: {s['suite']} ({s['name']}) | {s['planned_runs']} runs, {s['planned_generation_stages']} stages"
        )
        lines.append(f"  Cases:      {', '.join(s['cases'])}")
        lines.append(f"  Conditions: {', '.join(s['conditions'])}")
        lines.append(f"  Grader:     {s['grader']}")
        if s["note"]:
            lines.append(f"  Note:       {s['note']}")
        lines.append(f"  Dry-run:    {s['dry_run_command']}")
        lines.append(f"  Execute:    {s['run_command']}")
        lines.append(f"  Validate:   {s['validate_command']}")
        for scmd in s["summarize_commands"]:
            lines.append(f"  Summarize:  {scmd}")
        lines.append("")

    lines.append("Manifest & Integrity Checklist:")
    for idx, item in enumerate(plan["manifest_checklist"], start=1):
        lines.append(f"  {idx}. {item}")
    lines.append("")
    lines.append("Post-Promotion Scorecard & Verification:")
    for cmd in plan["post_run_commands"]:
        lines.append(f"  - {cmd}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Continuous model-evaluation scorecard and reproducible new-model onboarding planner."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_score = sub.add_parser(
        "scorecard",
        help="Compute a longitudinal model and rule scorecard from committed results/*/runs.jsonl datasets.",
    )
    p_score.add_argument(
        "--results-dir",
        default="results",
        help="Directory containing committed experiment subdirectories with runs.jsonl (default: results).",
    )
    p_score.add_argument("--json", action="store_true", dest="emit_json", help="Emit JSON scorecard.")
    p_score.add_argument("--markdown", action="store_true", help="Emit GitHub-flavored Markdown scorecard.")

    p_plan = sub.add_parser(
        "plan",
        help="Print exact isolated run_benchmark.py commands, stage counts, and manifest checklist for a model.",
    )
    p_plan.add_argument(
        "--model",
        required=True,
        help="Target model in '<provider>:<model_id>' format (for example, anthropic:claude-opus-6-0).",
    )
    p_plan.add_argument(
        "--suites",
        default="all",
        choices=("all", *SUITE_SPECS.keys()),
        help="Evaluation suites to include (default: all).",
    )
    p_plan.add_argument(
        "--replicates",
        type=int,
        default=3,
        help="Number of replicates per (case, condition) cell (default: 3).",
    )
    p_plan.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
        help=f"RNG seed for randomized condition ordering (default: {DEFAULT_SEED}).",
    )
    p_plan.add_argument(
        "--experiment-prefix",
        default=None,
        help="Optional prefix for generated experiment IDs (default: onboard-<model-id>).",
    )
    p_plan.add_argument("--json", action="store_true", dest="emit_json", help="Emit JSON plan.")

    args = parser.parse_args(argv)
    try:
        if args.command == "scorecard":
            card = build_scorecard(args.results_dir)
            if args.emit_json:
                print(json.dumps(card, indent=2))
            elif args.markdown:
                print(format_scorecard_markdown(card))
            else:
                print(format_scorecard_text(card))
            return 0

        plan = build_plan(
            args.model,
            suites=args.suites,
            replicates=args.replicates,
            seed=args.seed,
            experiment_prefix=args.experiment_prefix,
        )
        if args.emit_json:
            print(json.dumps(plan, indent=2))
        else:
            print(format_plan_text(plan))
        return 0
    except EvalCycleError as exc:
        if getattr(args, "emit_json", False):
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
