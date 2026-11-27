#!/usr/bin/env python3
"""Render deterministic, publication-grade SVG visuals from live pilot data.

Zero external dependencies (stdlib Python 3.11+ only). Reads
`results/pilot-3way-v0.6.0/runs.jsonl`, `results/pilot-evolution-v0.7.0/runs.jsonl`,
`results/pilot-ts-evolution-v0.8.0/runs.jsonl`, and their referenced grader JSONs /
stage artifacts directly — never hardcodes benchmark counts, rates, or deltas.

Outputs written under `docs/assets/`:
  - pilot-v0.6.0-results-light.svg
  - pilot-v0.6.0-results-dark.svg
  - pilot-v0.7.0-evolution-light.svg
  - pilot-v0.7.0-evolution-dark.svg
  - pilot-v0.8.0-ts-evolution-light.svg
  - pilot-v0.8.0-ts-evolution-dark.svg
  - hook-loop-light.svg
  - hook-loop-dark.svg

Optional flag `--social-svg PATH` also writes a 1280x640 editorial light social
preview SVG (using live metrics across pilots) for PNG rasterization.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.evolution import compare_evolution_arms  # noqa: E402


FONT_SANS = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
)
FONT_SOCIAL_DISPLAY = (
    "'Avenir Next', -apple-system, BlinkMacSystemFont, 'Segoe UI', "
    "'Helvetica Neue', Helvetica, Arial, sans-serif"
)
FONT_MONO = (
    "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
)

CONDITIONS: tuple[str, ...] = ("baseline", "core-rules-v0.2.0", "model-controls")
EV_CONDITIONS: tuple[str, ...] = ("baseline", "core-rules-v0.2.0", "gated-structural")
MODEL_ORDER: tuple[tuple[str, str, str], ...] = (
    ("claude-opus-5-5", "Claude Opus 5.5", "Opus"),
    ("gpt-6.2-astra", "GPT-6.2 Astra", "Astra"),
    ("gpt-6.2-sol", "GPT-6.2 Sol", "Sol"),
    ("gemini-4-neon", "Gemini 4 Neon", "Neon"),
)

END_MARKER_RE = re.compile(
    r"^## (?:Workspace Grader & Diff|Deterministic Text Constraints)\b",
    re.MULTILINE,
)
ELAPSED_SECONDS_RE = re.compile(r"^- Elapsed seconds:\s*([0-9.]+)\s*$", re.MULTILINE)
MUT_THRESHOLD_RE = re.compile(r"\bmin\s+(\d+)%")


@dataclass(frozen=True)
class Theme:
    name: str
    canvas_bg: str
    canvas_border: str
    panel_bg: str
    panel_border: str
    code_bg: str
    code_header_bg: str
    code_border: str
    ink: str
    ink_secondary: str
    muted: str
    grid: str
    divider: str
    baseline: str
    core: str
    controls: str
    danger: str
    danger_bg: str
    danger_border: str
    danger_ink: str
    positive: str
    positive_bg: str
    positive_border: str
    positive_ink: str
    caution: str
    caution_bg: str
    caution_border: str
    caution_ink: str
    neutral_badge_bg: str
    neutral_badge_border: str
    neutral_badge_ink: str
    diff_del_bg: str
    diff_add_bg: str
    arrow: str


LIGHT_THEME = Theme(
    name="light",
    canvas_bg="#ffffff",
    canvas_border="#d0d7de",
    panel_bg="#ffffff",
    panel_border="#e2e8f0",
    code_bg="#f8fafc",
    code_header_bg="#f1f5f9",
    code_border="#e2e8f0",
    ink="#0f172a",
    ink_secondary="#334155",
    muted="#475569",
    grid="#e2e8f0",
    divider="#e2e8f0",
    baseline="#94a3b8",
    core="#2563eb",
    controls="#0f766e",
    danger="#dc2626",
    danger_bg="#fef2f2",
    danger_border="#fecaca",
    danger_ink="#b91c1c",
    positive="#0f766e",
    positive_bg="#f0fdfa",
    positive_border="#99f6e4",
    positive_ink="#0f766e",
    caution="#d97706",
    caution_bg="#fffbeb",
    caution_border="#fde68a",
    caution_ink="#b45309",
    neutral_badge_bg="#f1f5f9",
    neutral_badge_border="#cbd5e1",
    neutral_badge_ink="#334155",
    diff_del_bg="#fee2e2",
    diff_add_bg="#dcfce7",
    arrow="#64748b",
)

DARK_THEME = Theme(
    name="dark",
    canvas_bg="#0d1117",
    canvas_border="#30363d",
    panel_bg="#161b22",
    panel_border="#21262d",
    code_bg="#0d1117",
    code_header_bg="#1c2128",
    code_border="#30363d",
    ink="#e6edf3",
    ink_secondary="#c9d1d9",
    muted="#8b949e",
    grid="#21262d",
    divider="#21262d",
    baseline="#6e7681",
    core="#58a6ff",
    controls="#2fb6a4",
    danger="#f85149",
    danger_bg="#241416",
    danger_border="#5c2226",
    danger_ink="#ff7b72",
    positive="#2fb6a4",
    positive_bg="#0e2222",
    positive_border="#1f4d4b",
    positive_ink="#5eead4",
    caution="#d29922",
    caution_bg="#1f1a10",
    caution_border="#544018",
    caution_ink="#e3b341",
    neutral_badge_bg="#21262d",
    neutral_badge_border="#30363d",
    neutral_badge_ink="#c9d1d9",
    diff_del_bg="#31181c",
    diff_add_bg="#122b23",
    arrow="#8b949e",
)


@dataclass(frozen=True)
class ModelCondStats:
    passed: int
    completed: int
    total: int

    @property
    def timeouts(self) -> int:
        return self.total - self.completed


@dataclass(frozen=True)
class PilotStats:
    experiment_id: str
    total_runs: int
    completed_runs: int
    timeout_runs: int
    n_models: int
    n_cases: int
    n_conditions: int
    n_replicates: int
    cond_pass: dict[str, int]
    cond_total: dict[str, int]
    net_improved_bm: int
    net_regressed_bm: int
    rw3_tampered: dict[str, int]
    rw3_completed: dict[str, int]
    rw3_baseline_by_model: dict[str, tuple[int, int]]
    model_cond: dict[tuple[str, str], ModelCondStats]
    opus_oss_passed_m: int
    opus_oss_completed_m: int
    opus_oss_total_m: int
    opus_matched_triplets: int
    opus_words_baseline: int
    opus_words_controls: int
    opus_words_delta_pct: float
    opus_usd_baseline: float
    opus_usd_controls: float
    opus_usd_delta_pct: float
    opus_se2_failed: int
    opus_se2_total: int
    timeout_notes: tuple[str, ...]


def _is_accepted(run: dict[str, Any]) -> bool:
    if run.get("status") != "completed":
        return False
    if run.get("material_defects"):
        return False
    checks = run.get("checks") or []
    return bool(checks) and all(ch.get("status") == "pass" for ch in checks)


def _extract_raw_model_output(md_text: str) -> str:
    marker = "## Raw Model Output\n"
    idx = md_text.find(marker)
    if idx < 0:
        return ""
    body = md_text[idx + len(marker) :]
    match = END_MARKER_RE.search(body)
    if match:
        body = body[: match.start()]
    return body.strip()


def _count_lexical_words(text: str) -> int:
    return sum(1 for tok in text.split() if any(ch.isalnum() for ch in tok))


def compute_pilot_stats(repo_root: Path, runs_path: Path) -> PilotStats:
    """Parse runs.jsonl and stage artifacts to compute all empirical figures."""
    runs = [
        json.loads(line)
        for line in runs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not runs:
        raise ValueError(f"No run records found in {runs_path}")

    experiment_id = str(runs[0]["experiment_id"])
    models = {r["model"]["id"] for r in runs}
    cases = {r["case_id"] for r in runs}
    conditions = {r["condition"] for r in runs}
    replicates = {r["replicate"] for r in runs}

    completed_runs = sum(1 for r in runs if r["status"] == "completed")
    timeout_runs = sum(1 for r in runs if r["status"] != "completed")

    cond_pass: dict[str, int] = {c: 0 for c in CONDITIONS}
    cond_total: dict[str, int] = {c: 0 for c in CONDITIONS}
    rw3_tampered: dict[str, int] = {c: 0 for c in CONDITIONS}
    rw3_completed: dict[str, int] = {c: 0 for c in CONDITIONS}
    rw3_baseline_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    mc_raw: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    paired_cells: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    timeout_list: list[str] = []

    short_name = {mid: sname for mid, _, sname in MODEL_ORDER}
    short_cond = {
        "baseline": "baseline",
        "core-rules-v0.2.0": "core-rules",
        "model-controls": "model-controls",
    }

    for r in runs:
        mid = r["model"]["id"]
        cid = r["case_id"]
        cond = r["condition"]
        rep = int(r["replicate"])
        acc = _is_accepted(r)
        comp = r["status"] == "completed"

        cond_total[cond] += 1
        if acc:
            cond_pass[cond] += 1

        mc = mc_raw[(mid, cond)]
        mc[2] += 1
        if comp:
            mc[1] += 1
        if acc:
            mc[0] += 1

        paired_cells[(mid, cid, rep)][cond] = r

        if not comp:
            timeout_list.append(
                f"{short_name.get(mid, mid)} {short_cond.get(cond, cond)} ({cid} r{rep})"
            )

        if cid == "RW3" and comp:
            rw3_completed[cond] += 1
            tampered = any(
                ch.get("id") == "readonly_and_no_test_tampering"
                and ch.get("status") == "fail"
                for ch in (r.get("checks") or [])
            )
            if tampered:
                rw3_tampered[cond] += 1
            if cond == "baseline":
                rw3_baseline_counts[mid][1] += 1
                if tampered:
                    rw3_baseline_counts[mid][0] += 1

    net_improved_bm = 0
    net_regressed_bm = 0
    for cell_runs in paired_cells.values():
        b_pass = _is_accepted(cell_runs["baseline"])
        m_pass = _is_accepted(cell_runs["model-controls"])
        if not b_pass and m_pass:
            net_improved_bm += 1
        elif b_pass and not m_pass:
            net_regressed_bm += 1

    model_cond: dict[tuple[str, str], ModelCondStats] = {
        key: ModelCondStats(passed=vals[0], completed=vals[1], total=vals[2])
        for key, vals in mc_raw.items()
    }

    # Opus OSS (real_work = RW* cases) under model-controls
    opus_oss_m = [
        r
        for r in runs
        if r["model"]["id"] == "claude-opus-5-5"
        and r["case_id"].startswith("RW")
        and r["condition"] == "model-controls"
    ]
    opus_oss_passed_m = sum(1 for r in opus_oss_m if _is_accepted(r))
    opus_oss_completed_m = sum(1 for r in opus_oss_m if r["status"] == "completed")
    opus_oss_total_m = len(opus_oss_m)

    # Opus matched always-completed triplets: lexical words & USD (baseline vs model-controls)
    opus_matched_triplets = 0
    opus_words_b = 0
    opus_words_m = 0
    opus_usd_b = 0.0
    opus_usd_m = 0.0
    for (mid, _cid, _rep), cell_runs in sorted(paired_cells.items()):
        if mid != "claude-opus-5-5":
            continue
        if not all(cell_runs[c]["status"] == "completed" for c in CONDITIONS):
            continue
        opus_matched_triplets += 1
        rb = cell_runs["baseline"]
        rm = cell_runs["model-controls"]
        opus_usd_b += float(rb["metrics"]["cost_usd"])
        opus_usd_m += float(rm["metrics"]["cost_usd"])
        for sa in rb["stage_artifacts"]:
            raw_out = _extract_raw_model_output(
                (repo_root / sa["path"]).read_text(encoding="utf-8")
            )
            opus_words_b += _count_lexical_words(raw_out)
        for sa in rm["stage_artifacts"]:
            raw_out = _extract_raw_model_output(
                (repo_root / sa["path"]).read_text(encoding="utf-8")
            )
            opus_words_m += _count_lexical_words(raw_out)

    opus_words_delta_pct = (
        (opus_words_m - opus_words_b) / opus_words_b * 100.0
        if opus_words_b
        else 0.0
    )
    opus_usd_delta_pct = (
        (opus_usd_m - opus_usd_b) / opus_usd_b * 100.0
        if opus_usd_b
        else 0.0
    )

    # Opus SE2 failure rate across all conditions
    opus_se2 = [
        r
        for r in runs
        if r["model"]["id"] == "claude-opus-5-5" and r["case_id"] == "SE2"
    ]
    opus_se2_failed = sum(1 for r in opus_se2 if not _is_accepted(r))
    opus_se2_total = len(opus_se2)

    rw3_baseline_by_model = {
        mid: (vals[0], vals[1]) for mid, vals in rw3_baseline_counts.items()
    }

    return PilotStats(
        experiment_id=experiment_id,
        total_runs=len(runs),
        completed_runs=completed_runs,
        timeout_runs=timeout_runs,
        n_models=len(models),
        n_cases=len(cases),
        n_conditions=len(conditions),
        n_replicates=len(replicates),
        cond_pass=cond_pass,
        cond_total=cond_total,
        net_improved_bm=net_improved_bm,
        net_regressed_bm=net_regressed_bm,
        rw3_tampered=rw3_tampered,
        rw3_completed=rw3_completed,
        rw3_baseline_by_model=rw3_baseline_by_model,
        model_cond=model_cond,
        opus_oss_passed_m=opus_oss_passed_m,
        opus_oss_completed_m=opus_oss_completed_m,
        opus_oss_total_m=opus_oss_total_m,
        opus_matched_triplets=opus_matched_triplets,
        opus_words_baseline=opus_words_b,
        opus_words_controls=opus_words_m,
        opus_words_delta_pct=opus_words_delta_pct,
        opus_usd_baseline=opus_usd_b,
        opus_usd_controls=opus_usd_m,
        opus_usd_delta_pct=opus_usd_delta_pct,
        opus_se2_failed=opus_se2_failed,
        opus_se2_total=opus_se2_total,
        timeout_notes=tuple(sorted(timeout_list)),
    )


def _esc(text: str) -> str:
    return escape(text, quote=True)


def _fmt_pct_clean(val: float) -> str:
    if abs(val - round(val)) < 1e-9:
        return f"{val:.0f}%"
    return f"{val:.1f}%"


def _slop_defect_count(metrics: dict[str, Any]) -> int:
    return (
        int(metrics.get("duplicate_blocks", 0))
        + int(metrics.get("dead_compat", 0))
        + int(metrics.get("god_functions", 0))
        + int(metrics.get("god_files", 0))
        + int(metrics.get("silent_failures_and_shortcuts", 0))
        + int(metrics.get("test_theater", 0))
    )


@dataclass(frozen=True)
class EvolutionStats:
    experiment_id: str
    case_id: str
    total_runs: int
    total_stages: int
    n_turns: int
    n_models: int
    n_conditions: int
    n_replicates: int
    n_checks: int
    word_cap_checks: int
    functional_passed_runs: int
    mutation_threshold_pct: int
    mutants_per_run: int
    cond_pass: dict[str, int]
    cond_total: dict[str, int]
    cond_slop: dict[str, int]
    cond_duplicate_blocks: dict[str, int]
    cond_god_functions: dict[str, int]
    cond_silent_shortcuts: dict[str, int]
    cond_mut_mean_pct: dict[str, float]
    cond_repair_turns: dict[str, int]
    cond_tokens: dict[str, int]
    cond_usd: dict[str, float]
    cond_wall_s: dict[str, float]
    wall_delta_pct: float
    wall_delta_gated_vs_core_pct: float
    mut_delta_gated_vs_core_pp: float
    net_improved_bg: int
    net_regressed_bg: int
    model_cond: dict[tuple[str, str], ModelCondStats]
    model_mut_mean_pct: dict[tuple[str, str], float]
    model_god_fns: dict[tuple[str, str], int]
    model_slop: dict[tuple[str, str], int]
    model_mut_fails: dict[tuple[str, str], int]
    model_repair_turns: dict[tuple[str, str], int]
    gated_vs_baseline_verdict: str
    core_verdict_by_model: dict[str, str]
    core_drop_short_names: tuple[str, ...]
    tok_delta_min_pct: float
    tok_delta_max_pct: float
    tok_delta_gated_vs_base_pct: float
    tok_delta_gated_vs_core_pct: float
    opus_usd_delta_pct: float
    opus_usd_delta_gated_vs_core_pct: float
    gated_fail_summary: str


def compute_evolution_stats(repo_root: Path, runs_path: Path) -> EvolutionStats:
    """Parse EV1/EV2 runs.jsonl, stage grader JSONs, and stage artifacts."""
    runs = [
        json.loads(line)
        for line in runs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not runs:
        raise ValueError(f"No run records found in {runs_path}")

    experiment_id = str(runs[0]["experiment_id"])
    case_id = str(runs[0]["case_id"])
    models = {r["model"]["id"] for r in runs}
    conditions = {r["condition"] for r in runs}
    replicates = {r["replicate"] for r in runs}
    n_turns = len(runs[0].get("stage_artifacts") or [])
    n_checks = len(runs[0].get("checks") or [])
    word_cap_checks = sum(
        1
        for ch in (runs[0].get("checks") or [])
        if "word" in str(ch.get("id", "")).lower()
    )

    cond_pass: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_total: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_slop: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_duplicate_blocks: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_god_functions: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_silent_shortcuts: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_mut_rates: dict[str, list[float]] = {c: [] for c in EV_CONDITIONS}
    cond_repair_turns: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_tokens: dict[str, int] = {c: 0 for c in EV_CONDITIONS}
    cond_usd: dict[str, float] = {c: 0.0 for c in EV_CONDITIONS}
    cond_wall_s: dict[str, float] = {c: 0.0 for c in EV_CONDITIONS}

    mc_raw: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])
    mc_mut_rates: dict[tuple[str, str], list[float]] = defaultdict(list)
    mc_god_fns: dict[tuple[str, str], int] = defaultdict(int)
    mc_slop: dict[tuple[str, str], int] = defaultdict(int)
    mc_mut_fails: dict[tuple[str, str], int] = defaultdict(int)
    mc_repair_turns: dict[tuple[str, str], int] = defaultdict(int)
    mc_tokens: dict[tuple[str, str], int] = defaultdict(int)
    mc_usd: dict[tuple[str, str], float] = defaultdict(float)

    grader_by_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grader_by_mc: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    paired_cells: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)

    total_stages = 0
    functional_passed_runs = 0
    mutation_threshold_pct: int | None = None
    mutants_per_run = 0
    gated_failures: list[tuple[str, list[str]]] = []

    short_name = {mid: sname for mid, _, sname in MODEL_ORDER}

    for r in runs:
        mid = r["model"]["id"]
        cond = r["condition"]
        rep = int(r["replicate"])
        acc = _is_accepted(r)
        comp = r["status"] == "completed"
        stages = r.get("stage_artifacts") or []
        total_stages += len(stages)

        # Load the final stage grader JSON referenced in check evidence.
        evidence_json_rel: str | None = None
        for ch in r.get("checks") or []:
            for ev in ch.get("evidence") or []:
                if isinstance(ev, str) and ev.endswith(".json"):
                    evidence_json_rel = ev
                    break
            if evidence_json_rel is not None:
                break
        if evidence_json_rel is None:
            raise ValueError(f"Missing grader JSON evidence for run {r['run_id']}")

        grader = json.loads((repo_root / evidence_json_rel).read_text(encoding="utf-8"))
        metrics = grader["metrics"]
        if metrics.get("functional_passed"):
            functional_passed_runs += 1
        if not mutants_per_run and metrics.get("mutation_total"):
            mutants_per_run = int(metrics["mutation_total"])
        if mutation_threshold_pct is None:
            for gch in grader.get("checks") or []:
                if gch.get("id") == "mutation_test_strength":
                    m_thresh = MUT_THRESHOLD_RE.search(str(gch.get("detail", "")))
                    if m_thresh:
                        mutation_threshold_pct = int(m_thresh.group(1))
                        break

        slop = _slop_defect_count(metrics)
        mut_rate = float(metrics.get("mutation_kill_rate", 0.0))
        dup_blocks = int(metrics.get("duplicate_blocks", 0))
        god_fns = int(metrics.get("god_functions", 0))
        silent_shortcuts = int(metrics.get("silent_failures_and_shortcuts", 0))

        cond_total[cond] += 1
        if acc:
            cond_pass[cond] += 1
        cond_slop[cond] += slop
        cond_duplicate_blocks[cond] += dup_blocks
        cond_god_functions[cond] += god_fns
        cond_silent_shortcuts[cond] += silent_shortcuts
        cond_mut_rates[cond].append(mut_rate)

        repairs = sum(
            1
            for k in (r.get("artifact_hashes") or {})
            if k.endswith("-gate-repair-trace.log")
        )
        cond_repair_turns[cond] += repairs
        mc_repair_turns[(mid, cond)] += repairs

        for sa in stages:
            stage_text = (repo_root / sa["path"]).read_text(encoding="utf-8")
            m_el = ELAPSED_SECONDS_RE.search(stage_text)
            if m_el:
                cond_wall_s[cond] += float(m_el.group(1))

        mc = mc_raw[(mid, cond)]
        mc[2] += 1
        if comp:
            mc[1] += 1
        if acc:
            mc[0] += 1

        mc_mut_rates[(mid, cond)].append(mut_rate)
        mc_god_fns[(mid, cond)] += god_fns
        mc_slop[(mid, cond)] += slop
        failed_ids = [
            str(ch.get("id"))
            for ch in (r.get("checks") or [])
            if ch.get("status") != "pass"
        ]
        if "mutation_test_strength" in failed_ids:
            mc_mut_fails[(mid, cond)] += 1
        if cond == "gated-structural" and not acc:
            gated_failures.append((mid, failed_ids))

        run_metrics = r.get("metrics") or {}
        if run_metrics.get("total_tokens") is not None:
            tok_val = int(run_metrics["total_tokens"])
            mc_tokens[(mid, cond)] += tok_val
            cond_tokens[cond] += tok_val
        if run_metrics.get("cost_usd") is not None:
            usd_val = float(run_metrics["cost_usd"])
            mc_usd[(mid, cond)] += usd_val
            cond_usd[cond] += usd_val

        grader_by_cond[cond].append(grader)
        grader_by_mc[(mid, cond)].append(grader)
        paired_cells[(mid, rep)][cond] = r

    if mutation_threshold_pct is None:
        raise ValueError(f"Could not parse mutation kill threshold from {case_id} grader JSONs")

    net_improved_bg = 0
    net_regressed_bg = 0
    for cell_runs in paired_cells.values():
        b_pass = _is_accepted(cell_runs["baseline"])
        g_pass = _is_accepted(cell_runs["gated-structural"])
        if not b_pass and g_pass:
            net_improved_bg += 1
        elif b_pass and not g_pass:
            net_regressed_bg += 1

    cond_mut_mean_pct = {
        c: (sum(vals) / len(vals) * 100.0 if vals else 0.0)
        for c, vals in cond_mut_rates.items()
    }
    model_cond = {
        key: ModelCondStats(passed=vals[0], completed=vals[1], total=vals[2])
        for key, vals in mc_raw.items()
    }
    model_mut_mean_pct = {
        key: (sum(vals) / len(vals) * 100.0 if vals else 0.0)
        for key, vals in mc_mut_rates.items()
    }

    wall_b = cond_wall_s["baseline"]
    wall_c = cond_wall_s["core-rules-v0.2.0"]
    wall_g = cond_wall_s["gated-structural"]
    wall_delta_pct = ((wall_g - wall_b) / wall_b * 100.0) if wall_b else 0.0
    wall_delta_gated_vs_core_pct = ((wall_g - wall_c) / wall_c * 100.0) if wall_c else 0.0
    mut_delta_gated_vs_core_pp = (
        cond_mut_mean_pct["gated-structural"] - cond_mut_mean_pct["core-rules-v0.2.0"]
    )

    tok_deltas = [
        (mc_tokens[(mid, "gated-structural")] - mc_tokens[(mid, "baseline")])
        / mc_tokens[(mid, "baseline")]
        * 100.0
        for mid, _, _ in MODEL_ORDER
        if mc_tokens[(mid, "baseline")]
    ]
    tok_delta_min_pct = min(tok_deltas) if tok_deltas else 0.0
    tok_delta_max_pct = max(tok_deltas) if tok_deltas else 0.0

    tok_b = cond_tokens["baseline"]
    tok_c = cond_tokens["core-rules-v0.2.0"]
    tok_g = cond_tokens["gated-structural"]
    tok_delta_gated_vs_base_pct = ((tok_g - tok_b) / tok_b * 100.0) if tok_b else 0.0
    tok_delta_gated_vs_core_pct = ((tok_g - tok_c) / tok_c * 100.0) if tok_c else 0.0

    opus_usd_b = mc_usd[("claude-opus-5-5", "baseline")]
    opus_usd_c = mc_usd[("claude-opus-5-5", "core-rules-v0.2.0")]
    opus_usd_g = mc_usd[("claude-opus-5-5", "gated-structural")]
    opus_usd_delta_pct = (
        ((opus_usd_g - opus_usd_b) / opus_usd_b * 100.0) if opus_usd_b else 0.0
    )
    opus_usd_delta_gated_vs_core_pct = (
        ((opus_usd_g - opus_usd_c) / opus_usd_c * 100.0) if opus_usd_c else 0.0
    )

    gated_vs_baseline_verdict = str(
        compare_evolution_arms(
            grader_by_cond["baseline"], grader_by_cond["gated-structural"]
        )["decision"]
    )
    core_verdict_by_model: dict[str, str] = {}
    core_drop_names: list[str] = []
    for mid, _, sname in MODEL_ORDER:
        dec = str(
            compare_evolution_arms(
                grader_by_mc[(mid, "baseline")],
                grader_by_mc[(mid, "core-rules-v0.2.0")],
            )["decision"]
        )
        core_verdict_by_model[mid] = dec
        if dec == "DROP":
            core_drop_names.append(sname)

    if not gated_failures:
        gated_fail_summary = "0 failing gated runs"
    else:
        fail_counts: dict[str, int] = defaultdict(int)
        all_mut_only = True
        for mid, fids in gated_failures:
            fail_counts[short_name.get(mid, mid)] += 1
            if fids != ["mutation_test_strength"]:
                all_mut_only = False
        parts = [
            f"{cnt} {sname} run" + ("s" if cnt != 1 else "")
            for sname, cnt in fail_counts.items()
        ]
        if all_mut_only:
            gated_fail_summary = (
                f"{', '.join(parts)} missed {mutation_threshold_pct}% mut"
            )
        else:
            gated_fail_summary = f"{', '.join(parts)} failed checks"

    return EvolutionStats(
        experiment_id=experiment_id,
        case_id=case_id,
        total_runs=len(runs),
        total_stages=total_stages,
        n_turns=n_turns,
        n_models=len(models),
        n_conditions=len(conditions),
        n_replicates=len(replicates),
        n_checks=n_checks,
        word_cap_checks=word_cap_checks,
        functional_passed_runs=functional_passed_runs,
        mutation_threshold_pct=mutation_threshold_pct,
        mutants_per_run=mutants_per_run,
        cond_pass=cond_pass,
        cond_total=cond_total,
        cond_slop=cond_slop,
        cond_duplicate_blocks=cond_duplicate_blocks,
        cond_god_functions=cond_god_functions,
        cond_silent_shortcuts=cond_silent_shortcuts,
        cond_mut_mean_pct=cond_mut_mean_pct,
        cond_repair_turns=cond_repair_turns,
        cond_tokens=cond_tokens,
        cond_usd=cond_usd,
        cond_wall_s=cond_wall_s,
        wall_delta_pct=wall_delta_pct,
        wall_delta_gated_vs_core_pct=wall_delta_gated_vs_core_pct,
        mut_delta_gated_vs_core_pp=mut_delta_gated_vs_core_pp,
        net_improved_bg=net_improved_bg,
        net_regressed_bg=net_regressed_bg,
        model_cond=model_cond,
        model_mut_mean_pct=model_mut_mean_pct,
        model_god_fns=dict(mc_god_fns),
        model_slop=dict(mc_slop),
        model_mut_fails=dict(mc_mut_fails),
        model_repair_turns=dict(mc_repair_turns),
        gated_vs_baseline_verdict=gated_vs_baseline_verdict,
        core_verdict_by_model=core_verdict_by_model,
        core_drop_short_names=tuple(core_drop_names),
        tok_delta_min_pct=tok_delta_min_pct,
        tok_delta_max_pct=tok_delta_max_pct,
        tok_delta_gated_vs_base_pct=tok_delta_gated_vs_base_pct,
        tok_delta_gated_vs_core_pct=tok_delta_gated_vs_core_pct,
        opus_usd_delta_pct=opus_usd_delta_pct,
        opus_usd_delta_gated_vs_core_pct=opus_usd_delta_gated_vs_core_pct,
        gated_fail_summary=gated_fail_summary,
    )


def render_pilot_results_svg(stats: PilotStats, theme: Theme) -> str:
    """Render the two-panel empirical results SVG for light or dark theme."""
    width, height = 960, 476
    t = theme

    subtitle = (
        f"{stats.experiment_id} · {stats.total_runs} runs · "
        f"{stats.n_models} models × {stats.n_cases} cases × "
        f"{stats.n_conditions} conditions × n = {stats.n_replicates}"
    )

    # Left panel: RW3 tampering metrics
    rw3_items: list[tuple[str, str, int, int, str]] = [
        (
            "baseline",
            "unruled",
            stats.rw3_tampered["baseline"],
            stats.rw3_completed["baseline"],
            t.danger,
        ),
        (
            "core-rules",
            "v0.2.0",
            stats.rw3_tampered["core-rules-v0.2.0"],
            stats.rw3_completed["core-rules-v0.2.0"],
            t.core,
        ),
        (
            "model-controls",
            "+ deltas",
            stats.rw3_tampered["model-controls"],
            stats.rw3_completed["model-controls"],
            t.controls,
        ),
    ]

    footnote_order = (
        ("gpt-6.2-astra", "Astra"),
        ("gpt-6.2-sol", "Sol"),
        ("claude-opus-5-5", "Opus"),
        ("gemini-4-neon", "Neon"),
    )
    rw3_breakdown = ", ".join(
        f"{label} {stats.rw3_baseline_by_model[mid][0]}/{stats.rw3_baseline_by_model[mid][1]}"
        for mid, label in footnote_order
    )
    ruled_tampered = (
        stats.rw3_tampered["core-rules-v0.2.0"] + stats.rw3_tampered["model-controls"]
    )
    ruled_completed = (
        stats.rw3_completed["core-rules-v0.2.0"] + stats.rw3_completed["model-controls"]
    )

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">Empirical Benchmark Results ({_esc(stats.experiment_id)})</title>',
        f'  <desc id="desc">{_esc(subtitle)}. Frozen-test tampering in RW3 drops from '
        f'{stats.rw3_tampered["baseline"]}/{stats.rw3_completed["baseline"]} baseline to '
        f'{ruled_tampered}/{ruled_completed} ruled; overall acceptance rises '
        f'{stats.cond_pass["baseline"]}/{stats.cond_total["baseline"]} to '
        f'{stats.cond_pass["core-rules-v0.2.0"]}/{stats.cond_total["core-rules-v0.2.0"]} to '
        f'{stats.cond_pass["model-controls"]}/{stats.cond_total["model-controls"]}.</desc>',
        "  <style>",
        f"    .sans {{ font-family: {FONT_SANS}; }}",
        f"    .mono {{ font-family: {FONT_MONO}; }}",
        "  </style>",
        "",
        f'  <!-- Outer frame -->',
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t.canvas_bg}" stroke="{t.canvas_border}"/>',
        "",
        "  <!-- Header -->",
        f'  <text x="28" y="38" class="sans" font-size="16.5" font-weight="700" fill="{t.ink}">Empirical Results: {_esc(stats.experiment_id)}</text>',
        f'  <text x="28" y="58" class="sans" font-size="11.5" fill="{t.muted}">{_esc(subtitle)}</text>',
        "",
        "  <!-- Condition legend (top right) -->",
        f'  <g transform="translate(598, 26)">',
        f'    <rect x="0" y="3" width="10" height="10" rx="2" fill="{t.baseline}"/>',
        f'    <text x="16" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">baseline</text>',
        f'    <rect x="82" y="3" width="10" height="10" rx="2" fill="{t.core}"/>',
        f'    <text x="98" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">core-rules (v0.2.0)</text>',
        f'    <rect x="226" y="3" width="10" height="10" rx="2" fill="{t.controls}"/>',
        f'    <text x="242" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">model-controls</text>',
        "  </g>",
        f'  <line x1="28" y1="72" x2="{width - 28}" y2="72" stroke="{t.divider}" stroke-width="1"/>',
        "",
        "  <!-- Left Panel: RW3 Frozen-Test Tampering -->",
        f'  <rect x="24" y="84" width="400" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="40" y="108" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Frozen-Test Tampering Under Release Pressure</text>',
        f'  <text x="40" y="125" class="sans" font-size="10.5" fill="{t.muted}">RW3 (urllib3) · % of completed runs modifying frozen tests</text>',
    ]

    # Left panel chart area: y_top=152 (100%) to y_bottom=288 (0%), height=136
    lp_y_top = 152.0
    lp_y_bottom = 288.0
    lp_h = lp_y_bottom - lp_y_top
    lp_x_left = 74.0
    lp_x_right = 406.0

    for pct in (0, 50, 100):
        y = lp_y_bottom - (pct / 100.0) * lp_h
        stroke_color = t.muted if pct == 0 else t.grid
        stroke_op = "0.45" if pct == 0 else "1"
        dash = "" if pct == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{lp_x_left:.0f}" y1="{y:.1f}" x2="{lp_x_right:.0f}" y2="{y:.1f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        lines.append(
            f'  <text x="{lp_x_left - 8:.0f}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="mono" font-size="10" fill="{t.muted}">{pct}%</text>'
        )

    bar_centers = (130.0, 240.0, 350.0)
    bar_w = 64.0
    for (label, sublabel, tamp, comp, color), cx in zip(rw3_items, bar_centers):
        pct = (tamp / comp * 100.0) if comp else 0.0
        bh = (pct / 100.0) * lp_h
        bx = cx - bar_w / 2.0
        if bh > 0:
            by = lp_y_bottom - bh
            lines.append(
                f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="4" fill="{color}"/>'
            )
            val_y = by - 22.0
            sub_y = by - 8.0
            val_color = t.danger_ink
        else:
            # Crisp 3px zero-indicator bar right above baseline
            lines.append(
                f'  <rect x="{bx:.1f}" y="{lp_y_bottom - 3.5:.1f}" width="{bar_w:.1f}" height="3.5" '
                f'rx="1.5" fill="{color}"/>'
            )
            val_y = lp_y_bottom - 26.0
            sub_y = lp_y_bottom - 12.0
            val_color = t.positive_ink

        lines.append(
            f'  <text x="{cx:.1f}" y="{val_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="13" font-weight="700" fill="{val_color}">{pct:.1f}%</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="{sub_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">({tamp}/{comp})</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="307" text-anchor="middle" '
            f'class="sans" font-size="11" font-weight="600" fill="{t.ink}">{_esc(label)}</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="321" text-anchor="middle" '
            f'class="sans" font-size="9.5" fill="{t.muted}">{_esc(sublabel)}</text>'
        )

    lines.extend([
        f'  <line x1="40" y1="334" x2="408" y2="334" stroke="{t.divider}" stroke-width="1"/>',
        f'  <text x="40" y="350" class="sans" font-size="10" fill="{t.muted}">Baseline tampering: {_esc(rw3_breakdown)}</text>',
        f'  <text x="40" y="364" class="sans" font-size="9.5" fill="{t.muted}">Core rules alone cut tampering to 0% ({ruled_tampered}/{ruled_completed} ruled; deltas unchanged)</text>',
        "",
        "  <!-- Right Panel: Overall Acceptance by Model -->",
        f'  <rect x="438" y="84" width="498" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="454" y="108" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Acceptance by Model &amp; Condition</text>',
        f'  <text x="454" y="125" class="sans" font-size="10.5" fill="{t.muted}">'
        f'All {stats.n_cases} cases (n = {stats.n_replicates}) · Total: '
        f'{stats.cond_pass["baseline"]}/{stats.cond_total["baseline"]} → '
        f'{stats.cond_pass["core-rules-v0.2.0"]}/{stats.cond_total["core-rules-v0.2.0"]} → '
        f'{stats.cond_pass["model-controls"]}/{stats.cond_total["model-controls"]} '
        f'(+{stats.net_improved_bm}/-{stats.net_regressed_bm} vs. baseline)</text>',
    ])

    # Right panel grouped horizontal bars
    rp_x0 = 584.0
    rp_x1 = 860.0  # 276px track -> 23px per run for 12 runs
    rp_track_w = rp_x1 - rp_x0
    max_runs = 12
    rp_y_top = 140.0
    rp_y_bot = 330.0

    for tick in (0, 4, 8, 12):
        tx = rp_x0 + (tick / max_runs) * rp_track_w
        stroke_color = t.muted if tick == 0 else t.grid
        stroke_op = "0.45" if tick == 0 else "1"
        dash = "" if tick == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{tx:.1f}" y1="{rp_y_top:.0f}" x2="{tx:.1f}" y2="{rp_y_bot:.0f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        tick_label = f"{tick}/12" if tick == 12 else str(tick)
        lines.append(
            f'  <text x="{tx:.1f}" y="346" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">{tick_label}</text>'
        )

    cond_colors = {
        "baseline": t.baseline,
        "core-rules-v0.2.0": t.core,
        "model-controls": t.controls,
    }
    group_ys = (146.0, 194.0, 242.0, 290.0)
    bar_h = 10.0
    bar_step = 12.5

    for idx, ((mid, display_name, _short), gy) in enumerate(zip(MODEL_ORDER, group_ys)):
        if idx > 0:
            sep_y = gy - 6.0
            lines.append(
                f'  <line x1="454" y1="{sep_y:.1f}" x2="920" y2="{sep_y:.1f}" '
                f'stroke="{t.divider}" stroke-opacity="0.65" stroke-width="1"/>'
            )

        # Model label on the left
        label_y = gy + 17.0
        lines.append(
            f'  <text x="454" y="{label_y:.1f}" class="sans" font-size="11.5" font-weight="600" fill="{t.ink}">{_esc(display_name)}</text>'
        )
        if mid == "claude-opus-5-5":
            lines.append(
                f'  <text x="454" y="{label_y + 13.5:.1f}" class="sans" font-size="9.5" font-weight="600" fill="{t.danger_ink}">'
                f'SE2: {stats.opus_se2_failed}/{stats.opus_se2_total} fail</text>'
            )
        else:
            mc_c = stats.model_cond[(mid, "core-rules-v0.2.0")]
            mc_m = stats.model_cond[(mid, "model-controls")]
            if mc_c.passed == mc_m.passed:
                sub_txt = f"core = controls ({mc_m.passed}/{mc_m.total})"
            else:
                sub_txt = f"core {mc_c.passed} → controls {mc_m.passed}"
            lines.append(
                f'  <text x="454" y="{label_y + 13.5:.1f}" class="sans" font-size="9.5" fill="{t.muted}">{_esc(sub_txt)}</text>'
            )

        for c_idx, cond in enumerate(CONDITIONS):
            mc = stats.model_cond[(mid, cond)]
            by = gy + c_idx * bar_step
            bw = (mc.passed / mc.total) * rp_track_w if mc.total else 0.0
            lines.append(
                f'  <rect x="{rp_x0:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" '
                f'rx="2.5" fill="{cond_colors[cond]}"/>'
            )
            lbl = f"{mc.passed}/{mc.total}" + ("†" if mc.timeouts > 0 else "")
            lbl_weight = "700" if cond == "model-controls" else "500"
            lbl_fill = t.ink if cond == "model-controls" else t.muted
            lines.append(
                f'  <text x="{rp_x0 + bw + 6:.1f}" y="{by + 8.5:.1f}" '
                f'class="mono" font-size="10" font-weight="{lbl_weight}" fill="{lbl_fill}">{_esc(lbl)}</text>'
            )

    timeout_footer = "† 1 × 720s timeout kept in denominator: " + "; ".join(
        stats.timeout_notes
    )
    lines.append(
        f'  <text x="454" y="364" class="sans" font-size="9.5" fill="{t.muted}">{_esc(timeout_footer)}</text>'
    )

    # Bottom two crisp callout boxes
    words_sign = "+" if stats.opus_words_delta_pct > 0 else ""
    usd_sign = "+" if stats.opus_usd_delta_pct > 0 else ""
    pos_headline = (
        f"Opus + D-OPU-4: {stats.opus_oss_passed_m}/{stats.opus_oss_completed_m} completed OSS · "
        f"{words_sign}{stats.opus_words_delta_pct:.1f}% words · "
        f"{usd_sign}{stats.opus_usd_delta_pct:.1f}% USD"
    )
    pos_detail = (
        f"Matched {stats.opus_matched_triplets} triplets: "
        f"{stats.opus_words_baseline:,} → {stats.opus_words_controls:,} lexical words · "
        f"${stats.opus_usd_baseline:.2f} → ${stats.opus_usd_controls:.2f}"
    )

    tied_models = sum(
        1
        for mid, _, _ in MODEL_ORDER
        if stats.model_cond[(mid, "core-rules-v0.2.0")].passed
        == stats.model_cond[(mid, "model-controls")].passed
    )
    neg_headline = (
        f"Opus failed SE2 ({stats.opus_se2_failed}/{stats.opus_se2_total}); "
        f"core = controls on {tied_models}/{stats.n_models} models"
    )
    neg_detail = (
        "Deltas only moved Opus verbosity/cost; EV1 shifts evals to multi-turn code quality"
    )

    lines.extend([
        "",
        "  <!-- Positive Callout: Opus + D-OPU-4 -->",
        f'  <defs>',
        f'    <clipPath id="clip-pos-{t.name}"><rect x="24" y="388" width="448" height="68" rx="6"/></clipPath>',
        f'    <clipPath id="clip-neg-{t.name}"><rect x="488" y="388" width="448" height="68" rx="6"/></clipPath>',
        f'  </defs>',
        f'  <rect x="24" y="388" width="448" height="68" rx="6" fill="{t.positive_bg}" stroke="{t.positive_border}"/>',
        f'  <rect x="24" y="388" width="4.5" height="68" fill="{t.positive}" clip-path="url(#clip-pos-{t.name})"/>',
        f'  <text x="42" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.positive_ink}">COMPLIANCE &amp; COST WIN</text>',
        f'  <text x="42" y="426" class="sans" font-size="11.5" font-weight="700" fill="{t.ink}">{_esc(pos_headline)}</text>',
        f'  <text x="42" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(pos_detail)}</text>',
        "",
        "  <!-- Negative Callout: Unresolved SE2 Failure & Ceiling -->",
        f'  <rect x="488" y="388" width="448" height="68" rx="6" fill="{t.danger_bg}" stroke="{t.danger_border}"/>',
        f'  <rect x="488" y="388" width="4.5" height="68" fill="{t.danger}" clip-path="url(#clip-neg-{t.name})"/>',
        f'  <text x="506" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.danger_ink}">LIMITS · PROMPT CEILING &amp; SE2 GAP</text>',
        f'  <text x="506" y="426" class="sans" font-size="11.5" font-weight="700" fill="{t.ink}">{_esc(neg_headline)}</text>',
        f'  <text x="506" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(neg_detail)}</text>',
        "</svg>",
        "",
    ])
    return "\n".join(lines)


def render_hook_loop_svg(theme: Theme) -> str:
    """Render the 3-step blocking agent Stop-hook turn-loop SVG."""
    width, height = 960, 336
    t = theme

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        '  <title id="title">Blocking Agent Stop-Hook Turn Loop</title>',
        '  <desc id="desc">Three-step blocking hook workflow: Step 1 Agent turn adds @pytest.mark.skip to tests/test_sync.py; Step 2 Stop hook exits 2 with DIFF-TEST-SKIP remediation on stderr; Step 3 Agent removes skip, fixes src/billing/sync.py, re-runs tests, and Stop hook exits 0 silently.</desc>',
        "  <defs>",
        f'    <marker id="arrow-{t.name}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">',
        f'      <path d="M 1 1.5 L 8.5 5 L 1 8.5 z" fill="{t.arrow}"/>',
        "    </marker>",
        "  </defs>",
        "  <style>",
        f"    .sans {{ font-family: {FONT_SANS}; }}",
        f"    .mono {{ font-family: {FONT_MONO}; }}",
        "  </style>",
        "",
        f'  <!-- Outer canvas -->',
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t.canvas_bg}" stroke="{t.canvas_border}"/>',
        "",
        "  <!-- Header -->",
        f'  <text x="28" y="36" class="sans" font-size="15.5" font-weight="700" fill="{t.ink}">Blocking Agent Turn Loop (Stop Hook)</text>',
        f'  <text x="28" y="55" class="sans" font-size="11" fill="{t.muted}">Enforces diff and approved learned-rule gates before turn completion · zero prompt tokens, zero CI round-trip</text>',
        f'  <rect x="698" y="23" width="234" height="24" rx="12" fill="{t.neutral_badge_bg}" stroke="{t.neutral_badge_border}"/>',
        f'  <text x="815" y="38.5" text-anchor="middle" class="mono" font-size="10" fill="{t.neutral_badge_ink}">Claude Code · Codex · Antigravity</text>',
        f'  <line x1="28" y1="68" x2="{width - 28}" y2="68" stroke="{t.divider}" stroke-width="1"/>',
        "",
        "  <!-- Step 1: Agent turn (x=28..284, w=256) -->",
        f'  <rect x="28" y="82" width="256" height="202" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <rect x="40" y="94" width="20" height="20" rx="10" fill="{t.neutral_badge_bg}" stroke="{t.neutral_badge_border}"/>',
        f'  <text x="50" y="108" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{t.ink}">1</text>',
        f'  <text x="68" y="108.5" class="sans" font-size="12.5" font-weight="700" fill="{t.ink}">Agent turn</text>',
        f'  <rect x="196" y="95" width="76" height="19" rx="9.5" fill="{t.neutral_badge_bg}" stroke="{t.neutral_badge_border}"/>',
        f'  <text x="234" y="108" text-anchor="middle" class="mono" font-size="9.5" fill="{t.neutral_badge_ink}">edits test</text>',
        f'  <text x="40" y="133" class="sans" font-size="11" fill="{t.ink_secondary}">Adds <tspan class="mono" font-size="10" fill="{t.ink}">@pytest.mark.skip</tspan> to</text>',
        f'  <text x="40" y="148" class="sans" font-size="11" fill="{t.ink_secondary}">dodge a failing test in <tspan class="mono" font-size="10" fill="{t.ink}">tests/</tspan>.</text>',
        "",
        f'  <rect x="40" y="162" width="232" height="110" rx="6" fill="{t.code_bg}" stroke="{t.code_border}"/>',
        f'  <path d="M 46 162 H 266 Q 272 162 272 168 V 184 H 40 V 168 Q 40 162 46 162 Z" fill="{t.code_header_bg}"/>',
        f'  <line x1="40" y1="184" x2="272" y2="184" stroke="{t.code_border}" stroke-width="1"/>',
        f'  <text x="50" y="176.5" class="mono" font-size="9.5" fill="{t.muted}">tests/test_sync.py</text>',
        f'  <rect x="41" y="206" width="230" height="19" fill="{t.diff_del_bg}"/>',
        f'  <text x="49" y="201" class="mono" font-size="9.8" fill="{t.muted}">7</text>',
        f'  <text x="72" y="201" class="mono" font-size="9.8" fill="{t.muted}"># frozen release gate</text>',
        f'  <text x="49" y="219" class="mono" font-size="9.8" font-weight="600" fill="{t.danger_ink}">+8</text>',
        f'  <text x="72" y="219" class="mono" font-size="9.8" font-weight="600" fill="{t.danger_ink}">@pytest.mark.skip</text>',
        f'  <text x="49" y="238" class="mono" font-size="9.8" fill="{t.muted}">9</text>',
        f'  <text x="72" y="238" class="mono" font-size="9.8" fill="{t.ink_secondary}">def test_sync_order():</text>',
        f'  <text x="49" y="256" class="mono" font-size="9.8" fill="{t.muted}">10</text>',
        f'  <text x="86" y="256" class="mono" font-size="9.8" fill="{t.muted}">assert sync() == OK</text>',
        "",
        "  <!-- Arrow 1 -> 2 -->",
        f'  <line x1="286" y1="183" x2="309" y2="183" stroke="{t.arrow}" stroke-width="1.6" marker-end="url(#arrow-{t.name})"/>',
        "",
        "  <!-- Step 2: Stop hook -> exit 2 (x=314..646, w=332) -->",
        f'  <rect x="314" y="82" width="332" height="202" rx="8" fill="{t.panel_bg}" stroke="{t.danger_border}" stroke-width="1.4"/>',
        f'  <rect x="326" y="94" width="20" height="20" rx="10" fill="{t.danger_bg}" stroke="{t.danger_border}"/>',
        f'  <text x="336" y="108" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{t.danger_ink}">2</text>',
        f'  <text x="354" y="108.5" class="sans" font-size="12.5" font-weight="700" fill="{t.ink}">Stop hook</text>',
        f'  <rect x="524" y="95" width="110" height="19" rx="9.5" fill="{t.danger_bg}" stroke="{t.danger_border}"/>',
        f'  <text x="579" y="108" text-anchor="middle" class="mono" font-size="9.5" font-weight="700" fill="{t.danger_ink}">exit 2 · BLOCKED</text>',
        f'  <text x="326" y="133" class="sans" font-size="11" fill="{t.ink_secondary}"><tspan class="mono" font-size="10" fill="{t.ink}">anti-slop hook</tspan> blocks completion and</text>',
        f'  <text x="326" y="148" class="sans" font-size="11" fill="{t.ink_secondary}">returns actionable stderr to the agent.</text>',
        "",
        f'  <rect x="326" y="162" width="308" height="110" rx="6" fill="{t.code_bg}" stroke="{t.danger_border}"/>',
        f'  <path d="M 332 162 H 628 Q 634 162 634 168 V 184 H 326 V 168 Q 326 162 332 162 Z" fill="{t.danger_bg}"/>',
        f'  <line x1="326" y1="184" x2="634" y2="184" stroke="{t.danger_border}" stroke-width="1"/>',
        f'  <text x="336" y="176.5" class="mono" font-size="9.5" font-weight="600" fill="{t.danger_ink}">stderr → returned to agent</text>',
        f'  <text x="336" y="201" class="mono" font-size="10" font-weight="700" fill="{t.danger_ink}">DIFF-TEST-SKIP: tests/test_sync.py:8</text>',
        f'  <text x="348" y="218" class="mono" font-size="10" fill="{t.ink}">adds &apos;@pytest.mark.skip&apos;</text>',
        f'  <text x="336" y="238" class="mono" font-size="9.8" fill="{t.muted}">→ remediation: Fix the underlying</text>',
        f'  <text x="348" y="254" class="mono" font-size="9.8" fill="{t.muted}">failure instead of skipping tests.</text>',
        "",
        "  <!-- Arrow 2 -> 3 -->",
        f'  <line x1="648" y1="183" x2="671" y2="183" stroke="{t.arrow}" stroke-width="1.6" marker-end="url(#arrow-{t.name})"/>',
        "",
        "  <!-- Step 3: Agent retry -> exit 0 (x=676..932, w=256) -->",
        f'  <rect x="676" y="82" width="256" height="202" rx="8" fill="{t.panel_bg}" stroke="{t.positive_border}" stroke-width="1.4"/>',
        f'  <rect x="688" y="94" width="20" height="20" rx="10" fill="{t.positive_bg}" stroke="{t.positive_border}"/>',
        f'  <text x="698" y="108" text-anchor="middle" class="mono" font-size="10.5" font-weight="700" fill="{t.positive_ink}">3</text>',
        f'  <text x="716" y="108.5" class="sans" font-size="12.5" font-weight="700" fill="{t.ink}">Agent retry</text>',
        f'  <rect x="832" y="95" width="88" height="19" rx="9.5" fill="{t.positive_bg}" stroke="{t.positive_border}"/>',
        f'  <text x="876" y="108" text-anchor="middle" class="mono" font-size="9.5" font-weight="700" fill="{t.positive_ink}">exit 0 · PASS</text>',
        f'  <text x="688" y="133" class="sans" font-size="11" fill="{t.ink_secondary}">Removes skip, fixes <tspan class="mono" font-size="10" fill="{t.ink}">sync.py</tspan>,</text>',
        f'  <text x="688" y="148" class="sans" font-size="11" fill="{t.ink_secondary}">re-runs tests; hook exits <tspan class="mono" font-size="10" fill="{t.ink}">0</tspan> silently.</text>',
        "",
        f'  <rect x="688" y="162" width="232" height="110" rx="6" fill="{t.code_bg}" stroke="{t.positive_border}"/>',
        f'  <path d="M 694 162 H 914 Q 920 162 920 168 V 184 H 688 V 168 Q 688 162 694 162 Z" fill="{t.positive_bg}"/>',
        f'  <line x1="688" y1="184" x2="920" y2="184" stroke="{t.positive_border}" stroke-width="1"/>',
        f'  <text x="698" y="176.5" class="mono" font-size="9.5" font-weight="600" fill="{t.positive_ink}">verified diff &amp; test run</text>',
        f'  <rect x="689" y="189" width="230" height="18" fill="{t.diff_del_bg}"/>',
        f'  <text x="698" y="201" class="mono" font-size="10" fill="{t.danger_ink}">- @pytest.mark.skip</text>',
        f'  <rect x="689" y="208" width="230" height="18" fill="{t.diff_add_bg}"/>',
        f'  <text x="698" y="220" class="mono" font-size="10" fill="{t.positive_ink}">+ src/billing/sync.py fixed</text>',
        f'  <text x="698" y="240" class="mono" font-size="10" fill="{t.muted}">$ pytest tests/test_sync.py</text>',
        f'  <text x="698" y="257" class="mono" font-size="10" font-weight="700" fill="{t.positive_ink}">4 passed · Stop hook exit 0</text>',
        "",
        "  <!-- Bottom summary bar -->",
        f'  <rect x="28" y="296" width="904" height="26" rx="5" fill="{t.code_bg}" stroke="{t.divider}"/>',
        f'  <text x="480" y="313" text-anchor="middle" class="sans" font-size="10.5" fill="{t.muted}">'
        'Catches test skips, silent catches, bare suppressions, and approved learned rules mid-turn before commit or review · Anti-loop guard prevents infinite retries</text>',
        "</svg>",
        "",
    ]
    return "\n".join(lines)


def render_evolution_results_svg(stats: EvolutionStats, theme: Theme) -> str:
    """Render the two-panel EV1 multi-turn code quality SVG for light or dark theme."""
    width, height = 960, 476
    t = theme

    subtitle = (
        f"{stats.experiment_id} · {stats.total_runs} runs · {stats.total_stages} stages · "
        f"{stats.n_models} models × {stats.n_conditions} conditions × n = {stats.n_replicates} · "
        f"{stats.word_cap_checks} word caps"
    )

    b_pass = stats.cond_pass["baseline"]
    b_tot = stats.cond_total["baseline"]
    c_pass = stats.cond_pass["core-rules-v0.2.0"]
    c_tot = stats.cond_total["core-rules-v0.2.0"]
    g_pass = stats.cond_pass["gated-structural"]
    g_tot = stats.cond_total["gated-structural"]

    b_pct = (b_pass / b_tot * 100.0) if b_tot else 0.0
    c_pct = (c_pass / c_tot * 100.0) if c_tot else 0.0
    g_pct = (g_pass / g_tot * 100.0) if g_tot else 0.0

    arm_items: list[tuple[str, str, int, int, int, float, str, str]] = [
        (
            "baseline",
            "baseline",
            b_pass,
            b_tot,
            stats.cond_slop["baseline"],
            stats.cond_mut_mean_pct["baseline"],
            t.baseline,
            t.ink_secondary,
        ),
        (
            "core-rules-v0.2.0",
            "core-rules",
            c_pass,
            c_tot,
            stats.cond_slop["core-rules-v0.2.0"],
            stats.cond_mut_mean_pct["core-rules-v0.2.0"],
            t.core,
            t.core,
        ),
        (
            "gated-structural",
            "gated-structural",
            g_pass,
            g_tot,
            stats.cond_slop["gated-structural"],
            stats.cond_mut_mean_pct["gated-structural"],
            t.controls,
            t.positive_ink,
        ),
    ]

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">Multi-Turn Code Quality: {_esc(stats.case_id)} ({stats.n_turns}-Turn Evolution)</title>',
        f'  <desc id="desc">{_esc(subtitle)}. Overall acceptance moves from '
        f'{b_pct:.1f}% ({b_pass}/{b_tot}, {stats.cond_slop["baseline"]} slop) baseline to '
        f'{c_pct:.1f}% ({c_pass}/{c_tot}, {stats.cond_slop["core-rules-v0.2.0"]} slop) core-rules to '
        f'{g_pct:.1f}% ({g_pass}/{g_tot}, {stats.cond_slop["gated-structural"]} slop) gated-structural; '
        f'mean AST mutation kill rate rises to {stats.cond_mut_mean_pct["gated-structural"]:.1f}%.</desc>',
        "  <style>",
        f"    .sans {{ font-family: {FONT_SANS}; }}",
        f"    .mono {{ font-family: {FONT_MONO}; }}",
        "  </style>",
        "",
        "  <!-- Outer frame -->",
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t.canvas_bg}" stroke="{t.canvas_border}"/>',
        "",
        "  <!-- Header -->",
        f'  <text x="28" y="38" class="sans" font-size="16.5" font-weight="700" fill="{t.ink}">Multi-Turn Code Quality: {_esc(stats.case_id)} ({stats.n_turns}-Turn Evolution)</text>',
        f'  <text x="28" y="58" class="sans" font-size="11.5" fill="{t.muted}">{_esc(subtitle)}</text>',
        "",
        "  <!-- Condition legend (top right) -->",
        '  <g transform="translate(588, 26)">',
        f'    <rect x="0" y="3" width="10" height="10" rx="2" fill="{t.baseline}"/>',
        f'    <text x="16" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">baseline</text>',
        f'    <rect x="80" y="3" width="10" height="10" rx="2" fill="{t.core}"/>',
        f'    <text x="96" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">core-rules (v0.2.0)</text>',
        f'    <rect x="224" y="3" width="10" height="10" rx="2" fill="{t.controls}"/>',
        f'    <text x="240" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">gated-structural</text>',
        "  </g>",
        f'  <line x1="28" y1="72" x2="{width - 28}" y2="72" stroke="{t.divider}" stroke-width="1"/>',
        "",
        "  <!-- Left Panel: Overall Pass Rate & Slop Findings -->",
        f'  <rect x="24" y="84" width="400" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="40" y="106" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Overall Pass Rate &amp; Slop Findings</text>',
        f'  <text x="40" y="122" class="sans" font-size="10.5" fill="{t.muted}">All {stats.n_models} models ({b_tot} runs/arm) · {stats.n_checks} mechanical {_esc(stats.case_id)} checks</text>',
    ]

    # Left panel chart area: y_top=160 (100%) to y_bottom=268 (0%), height=108
    lp_y_top = 160.0
    lp_y_bottom = 268.0
    lp_h = lp_y_bottom - lp_y_top
    lp_x_left = 74.0
    lp_x_right = 406.0

    for pct in (0, 50, 100):
        y = lp_y_bottom - (pct / 100.0) * lp_h
        stroke_color = t.muted if pct == 0 else t.grid
        stroke_op = "0.45" if pct == 0 else "1"
        dash = "" if pct == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{lp_x_left:.0f}" y1="{y:.1f}" x2="{lp_x_right:.0f}" y2="{y:.1f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        lines.append(
            f'  <text x="{lp_x_left - 8:.0f}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="mono" font-size="10" fill="{t.muted}">{pct}%</text>'
        )

    bar_centers = (130.0, 240.0, 350.0)
    bar_w = 64.0
    best_mut = max(stats.cond_mut_mean_pct.values())
    for (_cond, label, passed, total, slop, mut_pct, color, val_color), cx in zip(
        arm_items, bar_centers
    ):
        pct = (passed / total * 100.0) if total else 0.0
        bh = (pct / 100.0) * lp_h
        bx = cx - bar_w / 2.0
        if bh > 0:
            by = lp_y_bottom - bh
            lines.append(
                f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="4" fill="{color}"/>'
            )
            val_y = by - 19.5
            sub_y = by - 6.5
        else:
            lines.append(
                f'  <rect x="{bx:.1f}" y="{lp_y_bottom - 3.5:.1f}" width="{bar_w:.1f}" height="3.5" '
                f'rx="1.5" fill="{color}"/>'
            )
            val_y = lp_y_bottom - 24.5
            sub_y = lp_y_bottom - 11.5

        # Clean backdrop masks dashed gridlines behind bar value stacks
        lines.append(
            f'  <rect x="{cx - 28:.1f}" y="{val_y - 12.0:.1f}" width="56" height="27.5" '
            f'rx="3" fill="{t.panel_bg}"/>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="{val_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="13" font-weight="700" fill="{val_color}">{pct:.1f}%</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="{sub_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">({passed}/{total})</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="285" text-anchor="middle" '
            f'class="sans" font-size="11" font-weight="600" fill="{t.ink}">{_esc(label)}</text>'
        )
        slop_fill = t.positive_ink if slop == 0 else t.danger_ink
        lines.append(
            f'  <text x="{cx:.1f}" y="300" text-anchor="middle" '
            f'class="mono" font-size="10" font-weight="700" fill="{slop_fill}">{slop} slop</text>'
        )
        mut_fill = t.positive_ink if abs(mut_pct - best_mut) < 1e-9 else t.muted
        mut_weight = "600" if abs(mut_pct - best_mut) < 1e-9 else "400"
        lines.append(
            f'  <text x="{cx:.1f}" y="314" text-anchor="middle" '
            f'class="mono" font-size="9.5" font-weight="{mut_weight}" fill="{mut_fill}">{mut_pct:.1f}% mut</text>'
        )

    lines.extend([
        f'  <line x1="40" y1="327" x2="408" y2="327" stroke="{t.divider}" stroke-width="1"/>',
        f'  <text x="40" y="343" class="sans" font-size="9.5" fill="{t.muted}">All {stats.functional_passed_runs}/{stats.total_runs} runs passed functional tests across all {stats.n_turns} turns;</text>',
        f'  <text x="40" y="358" class="sans" font-size="9.5" fill="{t.muted}">failures were structural/suppression slop or &lt;{stats.mutation_threshold_pct}% mutation score.</text>',
        "",
        "  <!-- Right Panel: Acceptance & Mutation Kill Rate by Model -->",
        f'  <rect x="438" y="84" width="498" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="454" y="106" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Acceptance &amp; Mutation Kill Rate by Model</text>',
        f'  <text x="454" y="122" class="sans" font-size="10.5" fill="{t.muted}">'
        f'n = {stats.n_replicates} per arm · Total: {b_pass}/{b_tot} → {c_pass}/{c_tot} → {g_pass}/{g_tot} '
        f'(+{stats.net_improved_bg}/-{stats.net_regressed_bg} vs. baseline)</text>',
        f'  <text x="920" y="138" text-anchor="end" class="mono" font-size="9.5" fill="{t.muted}">mut kill</text>',
    ])

    # Right panel grouped horizontal bars (0..3 runs) + right-aligned mut kill column
    rp_x0 = 604.0
    rp_x1 = 784.0  # 180px track -> 60px per run for n=3
    rp_track_w = rp_x1 - rp_x0
    max_runs = stats.n_replicates
    rp_y_top = 142.0
    rp_y_bot = 330.0

    for tick in range(max_runs + 1):
        tx = rp_x0 + (tick / max_runs) * rp_track_w
        stroke_color = t.muted if tick == 0 else t.grid
        stroke_op = "0.45" if tick == 0 else "1"
        dash = "" if tick == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{tx:.1f}" y1="{rp_y_top:.0f}" x2="{tx:.1f}" y2="{rp_y_bot:.0f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        tick_label = f"{tick}/{max_runs}" if tick == max_runs else str(tick)
        lines.append(
            f'  <text x="{tx:.1f}" y="346" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">{tick_label}</text>'
        )

    ev_cond_colors = {
        "baseline": t.baseline,
        "core-rules-v0.2.0": t.core,
        "gated-structural": t.controls,
    }
    group_ys = (146.0, 194.0, 242.0, 290.0)
    bar_h = 10.0
    bar_step = 12.5

    for idx, ((mid, display_name, _short), gy) in enumerate(zip(MODEL_ORDER, group_ys)):
        if idx > 0:
            sep_y = gy - 6.0
            lines.append(
                f'  <line x1="454" y1="{sep_y:.1f}" x2="920" y2="{sep_y:.1f}" '
                f'stroke="{t.divider}" stroke-opacity="0.65" stroke-width="1"/>'
            )

        label_y = gy + 17.0
        lines.append(
            f'  <text x="454" y="{label_y:.1f}" class="sans" font-size="11.5" font-weight="600" fill="{t.ink}">{_esc(display_name)}</text>'
        )

        gods_b = stats.model_god_fns.get((mid, "baseline"), 0)
        gods_g = stats.model_god_fns.get((mid, "gated-structural"), 0)
        slop_b = stats.model_slop.get((mid, "baseline"), 0)
        slop_g = stats.model_slop.get((mid, "gated-structural"), 0)
        mut_delta_bg = (
            stats.model_mut_mean_pct[(mid, "gated-structural")]
            - stats.model_mut_mean_pct[(mid, "baseline")]
        )
        core_verdict = stats.core_verdict_by_model[mid]
        gated_mut_fails = stats.model_mut_fails.get((mid, "gated-structural"), 0)

        if gods_b > 0 and gods_g == 0:
            sub_txt = f"{gods_b} → {gods_g} god fns · {mut_delta_bg:+.1f}pp"
            sub_fill = t.positive_ink
            sub_weight = "600"
        elif core_verdict == "DROP" and slop_b > 0:
            sub_txt = f"core: {core_verdict} · slop {slop_b} → {slop_g}"
            sub_fill = t.muted
            sub_weight = "400"
        elif core_verdict == "DROP" and gated_mut_fails > 0:
            sub_txt = f"core: {core_verdict} · {gated_mut_fails} mut <{stats.mutation_threshold_pct}%"
            sub_fill = t.muted
            sub_weight = "400"
        else:
            sub_txt = f"{slop_g} slop · mut {mut_delta_bg:+.1f}pp"
            sub_fill = t.muted
            sub_weight = "400"

        lines.append(
            f'  <text x="454" y="{label_y + 13.5:.1f}" class="sans" font-size="9.5" font-weight="{sub_weight}" fill="{sub_fill}">{_esc(sub_txt)}</text>'
        )

        for c_idx, cond in enumerate(EV_CONDITIONS):
            mc = stats.model_cond[(mid, cond)]
            mut_val = stats.model_mut_mean_pct[(mid, cond)]
            by = gy + c_idx * bar_step
            bw = (mc.passed / mc.total) * rp_track_w if mc.total else 0.0
            if bw > 0:
                lines.append(
                    f'  <rect x="{rp_x0:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" '
                    f'rx="2.5" fill="{ev_cond_colors[cond]}"/>'
                )
                lbl_x = rp_x0 + bw + 7.0
            else:
                lines.append(
                    f'  <rect x="{rp_x0:.1f}" y="{by:.1f}" width="3.5" height="{bar_h:.1f}" '
                    f'rx="1.5" fill="{ev_cond_colors[cond]}"/>'
                )
                lbl_x = rp_x0 + 3.5 + 6.5

            lbl = f"{mc.passed}/{mc.total}"
            is_gated = cond == "gated-structural"
            lbl_weight = "700" if is_gated else "500"
            lbl_fill = t.ink if is_gated else t.muted
            lines.append(
                f'  <text x="{lbl_x:.1f}" y="{by + 8.5:.1f}" '
                f'class="mono" font-size="10" font-weight="{lbl_weight}" fill="{lbl_fill}">{_esc(lbl)}</text>'
            )

            mut_fill = t.positive_ink if is_gated and mut_val >= stats.mutation_threshold_pct else t.muted
            mut_weight = "700" if is_gated else "500"
            lines.append(
                f'  <text x="920" y="{by + 8.5:.1f}" text-anchor="end" '
                f'class="mono" font-size="10" font-weight="{mut_weight}" fill="{mut_fill}">{mut_val:.1f}%</text>'
            )

    lines.append(
        f'  <text x="454" y="363" class="sans" font-size="9.5" fill="{t.muted}">'
        f'Right column: mean AST mutation kill rate per arm (min {stats.mutation_threshold_pct}% to pass, {stats.mutants_per_run} mutants/run).</text>'
    )

    # Bottom two crisp callout cards
    wall_sign = "+" if stats.wall_delta_pct >= 0 else ""
    mut_vs_core_sign = "+" if stats.mut_delta_gated_vs_core_pp >= 0 else ""
    pos_headline = (
        f"Mechanical gates: {_fmt_pct_clean(b_pct)} → {_fmt_pct_clean(g_pct)} pass · "
        f"{stats.cond_slop['gated-structural']} slop · "
        f"{mut_vs_core_sign}{stats.mut_delta_gated_vs_core_pp:.1f}pp mut vs prompts"
    )
    pos_detail = (
        f"{stats.cond_repair_turns['gated-structural']} repair turns across "
        f"{g_tot} runs · {wall_sign}{stats.wall_delta_pct:.1f}% wall time "
        f"({round(stats.cond_wall_s['baseline']):,}s → {round(stats.cond_wall_s['gated-structural']):,}s)"
    )

    drop_label = " & ".join(stats.core_drop_short_names)
    neg_headline = (
        f"Prompts alone dropped pass ({_fmt_pct_clean(b_pct)} → {_fmt_pct_clean(c_pct)}; "
        f"DROP on {drop_label})"
    )
    tok_min_sign = "+" if stats.tok_delta_min_pct >= 0 else ""
    tok_max_sign = "+" if stats.tok_delta_max_pct >= 0 else ""
    usd_sign = "+" if stats.opus_usd_delta_pct >= 0 else ""
    neg_detail = (
        f"Repair turns cost {tok_min_sign}{round(stats.tok_delta_min_pct)}% to "
        f"{tok_max_sign}{round(stats.tok_delta_max_pct)}% tokens "
        f"({usd_sign}{stats.opus_usd_delta_pct:.1f}% Opus USD); {stats.gated_fail_summary}"
    )

    lines.extend([
        "",
        "  <!-- Positive Callout: Mechanical Gating Verdict -->",
        "  <defs>",
        f'    <clipPath id="clip-ev-pos-{t.name}"><rect x="24" y="388" width="448" height="68" rx="6"/></clipPath>',
        f'    <clipPath id="clip-ev-neg-{t.name}"><rect x="488" y="388" width="448" height="68" rx="6"/></clipPath>',
        "  </defs>",
        f'  <rect x="24" y="388" width="448" height="68" rx="6" fill="{t.positive_bg}" stroke="{t.positive_border}"/>',
        f'  <rect x="24" y="388" width="4.5" height="68" fill="{t.positive}" clip-path="url(#clip-ev-pos-{t.name})"/>',
        f'  <text x="42" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.positive_ink}">GATED VERDICT: {_esc(stats.gated_vs_baseline_verdict)}</text>',
        f'  <text x="42" y="426" class="sans" font-size="11" font-weight="700" fill="{t.ink}">{_esc(pos_headline)}</text>',
        f'  <text x="42" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(pos_detail)}</text>',
        "",
        "  <!-- Tradeoff Callout: Prompt Limit & Cost Overhead -->",
        f'  <rect x="488" y="388" width="448" height="68" rx="6" fill="{t.danger_bg}" stroke="{t.danger_border}"/>',
        f'  <rect x="488" y="388" width="4.5" height="68" fill="{t.danger}" clip-path="url(#clip-ev-neg-{t.name})"/>',
        f'  <text x="506" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.danger_ink}">PROMPT LIMIT &amp; COST TRADEOFF</text>',
        f'  <text x="506" y="426" class="sans" font-size="11" font-weight="700" fill="{t.ink}">{_esc(neg_headline)}</text>',
        f'  <text x="506" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(neg_detail)}</text>',
        "</svg>",
        "",
    ])
    return "\n".join(lines)


def render_ts_evolution_results_svg(stats: EvolutionStats, theme: Theme) -> str:
    """Render the two-panel EV2 TypeScript multi-turn quality SVG (light or dark)."""
    width, height = 960, 476
    t = theme

    subtitle = (
        f"{stats.experiment_id} · {stats.total_runs} runs · {stats.total_stages} stages · "
        f"{stats.n_models} models × {stats.n_conditions} conditions × n = {stats.n_replicates} · "
        f"{stats.word_cap_checks} word caps"
    )

    b_pass = stats.cond_pass["baseline"]
    b_tot = stats.cond_total["baseline"]
    c_pass = stats.cond_pass["core-rules-v0.2.0"]
    c_tot = stats.cond_total["core-rules-v0.2.0"]
    g_pass = stats.cond_pass["gated-structural"]
    g_tot = stats.cond_total["gated-structural"]

    b_pct = (b_pass / b_tot * 100.0) if b_tot else 0.0
    c_pct = (c_pass / c_tot * 100.0) if c_tot else 0.0
    g_pct = (g_pass / g_tot * 100.0) if g_tot else 0.0

    arm_items: list[tuple[str, str, int, int, int, float, str, str]] = [
        (
            "baseline",
            "baseline",
            b_pass,
            b_tot,
            stats.cond_slop["baseline"],
            stats.cond_mut_mean_pct["baseline"],
            t.baseline,
            t.ink_secondary,
        ),
        (
            "core-rules-v0.2.0",
            "core-rules",
            c_pass,
            c_tot,
            stats.cond_slop["core-rules-v0.2.0"],
            stats.cond_mut_mean_pct["core-rules-v0.2.0"],
            t.core,
            t.core,
        ),
        (
            "gated-structural",
            "gated-structural",
            g_pass,
            g_tot,
            stats.cond_slop["gated-structural"],
            stats.cond_mut_mean_pct["gated-structural"],
            t.controls,
            t.positive_ink,
        ),
    ]

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        f'  <title id="title">TypeScript Multi-Turn Quality: {_esc(stats.case_id)} ({stats.n_turns}-Turn Evolution)</title>',
        f'  <desc id="desc">{_esc(subtitle)}. Overall acceptance moves from '
        f'{b_pct:.1f}% ({b_pass}/{b_tot}, {stats.cond_slop["baseline"]} slop) baseline to '
        f'{c_pct:.1f}% ({c_pass}/{c_tot}, {stats.cond_slop["core-rules-v0.2.0"]} slop) core-rules to '
        f'{g_pct:.1f}% ({g_pass}/{g_tot}, {stats.cond_slop["gated-structural"]} slop) gated-structural; '
        f'mean TS mutation kill rate rises to {stats.cond_mut_mean_pct["gated-structural"]:.1f}%.</desc>',
        "  <style>",
        f"    .sans {{ font-family: {FONT_SANS}; }}",
        f"    .mono {{ font-family: {FONT_MONO}; }}",
        "  </style>",
        "",
        "  <!-- Outer frame -->",
        f'  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t.canvas_bg}" stroke="{t.canvas_border}"/>',
        "",
        "  <!-- Header -->",
        f'  <text x="28" y="38" class="sans" font-size="16.5" font-weight="700" fill="{t.ink}">TypeScript Multi-Turn Quality: {_esc(stats.case_id)} ({stats.n_turns}-Turn Evolution)</text>',
        f'  <text x="28" y="58" class="sans" font-size="11.5" fill="{t.muted}">{_esc(subtitle)}</text>',
        "",
        "  <!-- Condition legend (top right) -->",
        '  <g transform="translate(588, 26)">',
        f'    <rect x="0" y="3" width="10" height="10" rx="2" fill="{t.baseline}"/>',
        f'    <text x="16" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">baseline</text>',
        f'    <rect x="80" y="3" width="10" height="10" rx="2" fill="{t.core}"/>',
        f'    <text x="96" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">core-rules (v0.2.0)</text>',
        f'    <rect x="224" y="3" width="10" height="10" rx="2" fill="{t.controls}"/>',
        f'    <text x="240" y="12" class="sans" font-size="11" fill="{t.ink_secondary}">gated-structural</text>',
        "  </g>",
        f'  <line x1="28" y1="72" x2="{width - 28}" y2="72" stroke="{t.divider}" stroke-width="1"/>',
        "",
        "  <!-- Left Panel: Overall Pass Rate & Slop Findings -->",
        f'  <rect x="24" y="84" width="400" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="40" y="106" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Overall Pass Rate &amp; Slop Findings</text>',
        f'  <text x="40" y="122" class="sans" font-size="10.5" fill="{t.muted}">All {stats.n_models} models ({b_tot} runs/arm) · {stats.n_checks} mechanical {_esc(stats.case_id)} checks</text>',
    ]

    # Left panel chart area: y_top=168 (100%) to y_bottom=268 (0%), height=100
    lp_y_top = 168.0
    lp_y_bottom = 268.0
    lp_h = lp_y_bottom - lp_y_top
    lp_x_left = 74.0
    lp_x_right = 406.0

    for pct in (0, 50, 100):
        y = lp_y_bottom - (pct / 100.0) * lp_h
        stroke_color = t.muted if pct == 0 else t.grid
        stroke_op = "0.45" if pct == 0 else "1"
        dash = "" if pct == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{lp_x_left:.0f}" y1="{y:.1f}" x2="{lp_x_right:.0f}" y2="{y:.1f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        lines.append(
            f'  <text x="{lp_x_left - 8:.0f}" y="{y + 3.5:.1f}" text-anchor="end" '
            f'class="mono" font-size="10" fill="{t.muted}">{pct}%</text>'
        )

    bar_centers = (130.0, 240.0, 350.0)
    bar_w = 64.0
    best_mut = max(stats.cond_mut_mean_pct.values())
    for (_cond, label, passed, total, slop, mut_pct, color, val_color), cx in zip(
        arm_items, bar_centers
    ):
        pct = (passed / total * 100.0) if total else 0.0
        bh = (pct / 100.0) * lp_h
        bx = cx - bar_w / 2.0
        if bh > 0:
            by = lp_y_bottom - bh
            lines.append(
                f'  <rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="4" fill="{color}"/>'
            )
            val_y = by - 19.5
            sub_y = by - 6.5
        else:
            lines.append(
                f'  <rect x="{bx:.1f}" y="{lp_y_bottom - 3.5:.1f}" width="{bar_w:.1f}" height="3.5" '
                f'rx="1.5" fill="{color}"/>'
            )
            val_y = lp_y_bottom - 24.5
            sub_y = lp_y_bottom - 11.5

        lines.append(
            f'  <rect x="{cx - 32:.1f}" y="{val_y - 12.0:.1f}" width="64" height="27.5" '
            f'rx="3" fill="{t.panel_bg}"/>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="{val_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="13" font-weight="700" fill="{val_color}">{pct:.1f}%</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="{sub_y:.1f}" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">({passed}/{total})</text>'
        )
        lines.append(
            f'  <text x="{cx:.1f}" y="285" text-anchor="middle" '
            f'class="sans" font-size="11" font-weight="600" fill="{t.ink}">{_esc(label)}</text>'
        )
        slop_fill = t.positive_ink if slop == 0 else t.danger_ink
        lines.append(
            f'  <text x="{cx:.1f}" y="300" text-anchor="middle" '
            f'class="mono" font-size="10" font-weight="700" fill="{slop_fill}">{slop} slop</text>'
        )
        mut_fill = t.positive_ink if abs(mut_pct - best_mut) < 1e-9 else t.muted
        mut_weight = "600" if abs(mut_pct - best_mut) < 1e-9 else "400"
        lines.append(
            f'  <text x="{cx:.1f}" y="314" text-anchor="middle" '
            f'class="mono" font-size="9.5" font-weight="{mut_weight}" fill="{mut_fill}">{mut_pct:.1f}% mut</text>'
        )

    non_gated_slop = stats.cond_slop["baseline"] + stats.cond_slop["core-rules-v0.2.0"]
    non_gated_dups = (
        stats.cond_duplicate_blocks["baseline"]
        + stats.cond_duplicate_blocks["core-rules-v0.2.0"]
    )
    non_gated_gods = (
        stats.cond_god_functions["baseline"]
        + stats.cond_god_functions["core-rules-v0.2.0"]
    )
    total_silent = sum(stats.cond_silent_shortcuts.values())

    lines.extend([
        f'  <line x1="40" y1="327" x2="408" y2="327" stroke="{t.divider}" stroke-width="1"/>',
        f'  <text x="40" y="343" class="sans" font-size="9.5" fill="{t.muted}">All {non_gated_slop} baseline/core defects were duplicate blocks ({non_gated_dups})</text>',
        f'  <text x="40" y="358" class="sans" font-size="9.5" fill="{t.muted}">or god functions ({non_gated_gods}); {total_silent} suppression noise.</text>',
        "",
        "  <!-- Right Panel: Acceptance & TS Mutation Kill Rate by Model -->",
        f'  <rect x="438" y="84" width="498" height="290" rx="8" fill="{t.panel_bg}" stroke="{t.panel_border}"/>',
        f'  <text x="454" y="106" class="sans" font-size="13" font-weight="700" fill="{t.ink}">Acceptance &amp; TS Mutation Kill Rate by Model</text>',
        f'  <text x="454" y="122" class="sans" font-size="10.5" fill="{t.muted}">'
        f'n = {stats.n_replicates} per arm · Total: {b_pass}/{b_tot} → {c_pass}/{c_tot} → {g_pass}/{g_tot} '
        f'(+{stats.net_improved_bg}/-{stats.net_regressed_bg} vs. baseline)</text>',
        f'  <text x="920" y="138" text-anchor="end" class="mono" font-size="9.5" fill="{t.muted}">mut kill</text>',
    ])

    # Right panel grouped horizontal bars (0..3 runs) + right-aligned mut kill column
    rp_x0 = 604.0
    rp_x1 = 784.0
    rp_track_w = rp_x1 - rp_x0
    max_runs = stats.n_replicates
    rp_y_top = 142.0
    rp_y_bot = 330.0

    for tick in range(max_runs + 1):
        tx = rp_x0 + (tick / max_runs) * rp_track_w
        stroke_color = t.muted if tick == 0 else t.grid
        stroke_op = "0.45" if tick == 0 else "1"
        dash = "" if tick == 0 else ' stroke-dasharray="3 3"'
        lines.append(
            f'  <line x1="{tx:.1f}" y1="{rp_y_top:.0f}" x2="{tx:.1f}" y2="{rp_y_bot:.0f}" '
            f'stroke="{stroke_color}" stroke-opacity="{stroke_op}" stroke-width="1"{dash}/>'
        )
        tick_label = f"{tick}/{max_runs}" if tick == max_runs else str(tick)
        lines.append(
            f'  <text x="{tx:.1f}" y="346" text-anchor="middle" '
            f'class="mono" font-size="10" fill="{t.muted}">{tick_label}</text>'
        )

    ev_cond_colors = {
        "baseline": t.baseline,
        "core-rules-v0.2.0": t.core,
        "gated-structural": t.controls,
    }
    group_ys = (146.0, 194.0, 242.0, 290.0)
    bar_h = 10.0
    bar_step = 12.5

    for idx, ((mid, display_name, _short), gy) in enumerate(zip(MODEL_ORDER, group_ys)):
        if idx > 0:
            sep_y = gy - 6.0
            lines.append(
                f'  <line x1="454" y1="{sep_y:.1f}" x2="920" y2="{sep_y:.1f}" '
                f'stroke="{t.divider}" stroke-opacity="0.65" stroke-width="1"/>'
            )

        label_y = gy + 17.0
        lines.append(
            f'  <text x="454" y="{label_y:.1f}" class="sans" font-size="11.5" font-weight="600" fill="{t.ink}">{_esc(display_name)}</text>'
        )

        slop_b = stats.model_slop.get((mid, "baseline"), 0)
        slop_g = stats.model_slop.get((mid, "gated-structural"), 0)
        repairs_g = stats.model_repair_turns.get((mid, "gated-structural"), 0)
        mut_delta_bg = (
            stats.model_mut_mean_pct[(mid, "gated-structural")]
            - stats.model_mut_mean_pct[(mid, "baseline")]
        )

        if repairs_g > 0 and slop_b > 0 and slop_g == 0:
            sub_txt = f"{mut_delta_bg:+.1f}pp mut · {slop_g} slop"
            sub_fill = t.positive_ink
            sub_weight = "600"
        elif slop_b > 0 and slop_g == 0:
            sub_txt = f"slop {slop_b} → {slop_g} · {repairs_g} repairs"
            sub_fill = t.muted
            sub_weight = "400"
        else:
            sub_txt = f"{slop_g} slop · mut {mut_delta_bg:+.1f}pp"
            sub_fill = t.muted
            sub_weight = "400"

        lines.append(
            f'  <text x="454" y="{label_y + 13.5:.1f}" class="sans" font-size="9.5" font-weight="{sub_weight}" fill="{sub_fill}">{_esc(sub_txt)}</text>'
        )

        for c_idx, cond in enumerate(EV_CONDITIONS):
            mc = stats.model_cond[(mid, cond)]
            mut_val = stats.model_mut_mean_pct[(mid, cond)]
            by = gy + c_idx * bar_step
            bw = (mc.passed / mc.total) * rp_track_w if mc.total else 0.0
            if bw > 0:
                lines.append(
                    f'  <rect x="{rp_x0:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" '
                    f'rx="2.5" fill="{ev_cond_colors[cond]}"/>'
                )
                lbl_x = rp_x0 + bw + 7.0
            else:
                lines.append(
                    f'  <rect x="{rp_x0:.1f}" y="{by:.1f}" width="3.5" height="{bar_h:.1f}" '
                    f'rx="1.5" fill="{ev_cond_colors[cond]}"/>'
                )
                lbl_x = rp_x0 + 3.5 + 6.5

            lbl = f"{mc.passed}/{mc.total}"
            is_gated = cond == "gated-structural"
            lbl_weight = "700" if is_gated else "500"
            lbl_fill = t.ink if is_gated else t.muted
            lines.append(
                f'  <text x="{lbl_x:.1f}" y="{by + 8.5:.1f}" '
                f'class="mono" font-size="10" font-weight="{lbl_weight}" fill="{lbl_fill}">{_esc(lbl)}</text>'
            )

            mut_fill = (
                t.positive_ink
                if is_gated and mut_val >= stats.mutation_threshold_pct
                else t.muted
            )
            mut_weight = "700" if is_gated else "500"
            lines.append(
                f'  <text x="920" y="{by + 8.5:.1f}" text-anchor="end" '
                f'class="mono" font-size="10" font-weight="{mut_weight}" fill="{mut_fill}">{mut_val:.1f}%</text>'
            )

    lines.append(
        f'  <text x="454" y="363" class="sans" font-size="9.5" fill="{t.muted}">'
        f'Right column: mean JS/TS mutation kill rate per arm (min {stats.mutation_threshold_pct}% to pass, {stats.mutants_per_run} mutants/run).</text>'
    )

    # Bottom two crisp callout cards
    pos_headline = (
        f"Gated: {_fmt_pct_clean(b_pct)} → {_fmt_pct_clean(g_pct)} pass · "
        f"{stats.cond_slop['gated-structural']} slop "
        f"({stats.cond_duplicate_blocks['baseline']} dup + "
        f"{stats.cond_god_functions['baseline']} god fn → "
        f"{stats.cond_slop['gated-structural']})"
    )
    pos_detail = (
        f"Cheaper & faster than prompts: "
        f"{stats.tok_delta_gated_vs_core_pct:+.1f}% tokens · "
        f"{stats.opus_usd_delta_gated_vs_core_pct:+.1f}% Opus USD · "
        f"{stats.wall_delta_gated_vs_core_pct:+.1f}% wall"
    )

    base_perfect_names = [
        sname
        for mid, _, sname in MODEL_ORDER
        if stats.model_cond[(mid, "baseline")].passed == stats.n_replicates
    ]
    total_repairs = stats.cond_repair_turns["gated-structural"]
    top_rep_mid, _, top_rep_name = max(
        MODEL_ORDER,
        key=lambda item: stats.model_repair_turns.get((item[0], "gated-structural"), 0),
    )
    top_rep_count = stats.model_repair_turns.get((top_rep_mid, "gated-structural"), 0)
    top_rep_mut_delta = (
        stats.model_mut_mean_pct[(top_rep_mid, "gated-structural")]
        - stats.model_mut_mean_pct[(top_rep_mid, "baseline")]
    )
    perfect_label = " & ".join(base_perfect_names)
    split_headline = (
        f"{perfect_label} hit {stats.n_replicates}/{stats.n_replicates} in baseline; "
        f"{top_rep_name} drove {top_rep_count}/{total_repairs} repair turns "
        f"({top_rep_mut_delta:+.1f}pp mut)"
    )
    split_detail = (
        f"Total overhead vs baseline: "
        f"{stats.tok_delta_gated_vs_base_pct:+.1f}% tokens · "
        f"{stats.opus_usd_delta_pct:+.1f}% Opus USD · "
        f"{stats.wall_delta_pct:+.1f}% wall"
    )

    lines.extend([
        "",
        "  <!-- Positive Callout: TypeScript EV2 Verdict -->",
        "  <defs>",
        f'    <clipPath id="clip-ts-pos-{t.name}"><rect x="24" y="388" width="448" height="68" rx="6"/></clipPath>',
        f'    <clipPath id="clip-ts-split-{t.name}"><rect x="488" y="388" width="448" height="68" rx="6"/></clipPath>',
        "  </defs>",
        f'  <rect x="24" y="388" width="448" height="68" rx="6" fill="{t.positive_bg}" stroke="{t.positive_border}"/>',
        f'  <rect x="24" y="388" width="4.5" height="68" fill="{t.positive}" clip-path="url(#clip-ts-pos-{t.name})"/>',
        f'  <text x="42" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.positive_ink}">TYPESCRIPT {_esc(stats.case_id)} VERDICT: {_esc(stats.gated_vs_baseline_verdict)}</text>',
        f'  <text x="42" y="426" class="sans" font-size="11" font-weight="700" fill="{t.ink}">{_esc(pos_headline)}</text>',
        f'  <text x="42" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(pos_detail)}</text>',
        "",
        "  <!-- Model Split & Repair Profile Callout -->",
        f'  <rect x="488" y="388" width="448" height="68" rx="6" fill="{t.caution_bg}" stroke="{t.caution_border}"/>',
        f'  <rect x="488" y="388" width="4.5" height="68" fill="{t.caution}" clip-path="url(#clip-ts-split-{t.name})"/>',
        f'  <text x="506" y="407" class="mono" font-size="10" font-weight="700" letter-spacing="0.4" fill="{t.caution_ink}">MODEL SPLIT &amp; REPAIR PROFILE</text>',
        f'  <text x="506" y="426" class="sans" font-size="11" font-weight="700" fill="{t.ink}">{_esc(split_headline)}</text>',
        f'  <text x="506" y="443" class="sans" font-size="10" fill="{t.muted}">{_esc(split_detail)}</text>',
        "</svg>",
        "",
    ])
    return "\n".join(lines)


def render_social_preview_svg(
    stats: PilotStats,
    ev_stats: EvolutionStats | None = None,
    ts_ev_stats: EvolutionStats | None = None,
) -> str:
    """Render the 1280x640 editorial light agent-first GitHub social preview SVG."""
    width, height = 1280, 640

    b_tamp = stats.rw3_tampered["baseline"]
    b_comp = stats.rw3_completed["baseline"]
    b_pct = (b_tamp / b_comp * 100.0) if b_comp else 0.0
    ruled_tamp = (
        stats.rw3_tampered["core-rules-v0.2.0"] + stats.rw3_tampered["model-controls"]
    )
    ruled_comp = (
        stats.rw3_completed["core-rules-v0.2.0"] + stats.rw3_completed["model-controls"]
    )
    ruled_pct = (ruled_tamp / ruled_comp * 100.0) if ruled_comp else 0.0
    rw3_arrow = f"{round(b_pct)}% → {round(ruled_pct)}%"

    if ev_stats is not None:
        ev1_b_pct = (
            ev_stats.cond_pass["baseline"] / ev_stats.cond_total["baseline"] * 100.0
            if ev_stats.cond_total["baseline"]
            else 0.0
        )
        ev1_g_pct = (
            ev_stats.cond_pass["gated-structural"]
            / ev_stats.cond_total["gated-structural"]
            * 100.0
            if ev_stats.cond_total["gated-structural"]
            else 0.0
        )
        left_stat_val = f"{round(ev1_b_pct)}% → {round(ev1_g_pct)}%"
        left_stat_label = "Python 4-step builds"
        slop_count = ev_stats.cond_slop["gated-structural"]
    else:
        left_stat_val = rw3_arrow
        left_stat_label = "Skipped tests blocked"
        slop_count = 0

    if ts_ev_stats is not None:
        ev2_b_pct = (
            ts_ev_stats.cond_pass["baseline"]
            / ts_ev_stats.cond_total["baseline"]
            * 100.0
            if ts_ev_stats.cond_total["baseline"]
            else 0.0
        )
        ev2_g_pct = (
            ts_ev_stats.cond_pass["gated-structural"]
            / ts_ev_stats.cond_total["gated-structural"]
            * 100.0
            if ts_ev_stats.cond_total["gated-structural"]
            else 0.0
        )
        right_stat_val = f"{round(ev2_b_pct)}% → {round(ev2_g_pct)}%"
        right_stat_label = "TypeScript 4-step builds"
        slop_count = max(slop_count, ts_ev_stats.cond_slop["gated-structural"])
    else:
        right_stat_val = rw3_arrow
        right_stat_label = "Skipped tests under pressure"

    slop_chip = f"✓ {slop_count} slop issues"

    lines: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        "  <defs>",
        '    <linearGradient id="bg-editorial" x1="0" y1="0" x2="1" y2="1">',
        '      <stop offset="0%" stop-color="#fcfcfa"/>',
        '      <stop offset="100%" stop-color="#f3f5f2"/>',
        "    </linearGradient>",
        '    <pattern id="grid-editorial" width="40" height="40" patternUnits="userSpaceOnUse">',
        '      <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e2e8f0" stroke-width="0.7" stroke-opacity="0.5"/>',
        "    </pattern>",
        "  </defs>",
        "  <style>",
        f"    .sans {{ font-family: {FONT_SOCIAL_DISPLAY}; }}",
        f"    .mono {{ font-family: {FONT_MONO}; }}",
        "  </style>",
        "",
        "  <!-- Canvas -->",
        f'  <rect width="{width}" height="{height}" fill="url(#bg-editorial)"/>',
        f'  <rect width="{width}" height="{height}" fill="url(#grid-editorial)"/>',
        f'  <rect x="24" y="24" width="{width - 48}" height="{height - 48}" rx="24" fill="none" stroke="#d6dde6" stroke-width="1.5"/>',
        "",
        "  <!-- Left Column: Brand + Headline + Proof -->",
        '  <g transform="translate(72, 74)">',
        '    <rect x="0" y="0" width="40" height="40" rx="11" fill="#0f766e"/>',
        '    <path d="M 20 9 L 29 13 V 20.5 C 29 26 25 29.8 20 31.6 C 15 29.8 11 26 11 20.5 V 13 Z" fill="none" stroke="#ffffff" stroke-width="2" stroke-linejoin="round"/>',
        '    <path d="M 16 20.4 L 19 23.4 L 24.6 17.6" fill="none" stroke="#ffffff" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"/>',
        '    <text x="52" y="28.5" class="sans" font-size="28" font-weight="700" fill="#0f172a" letter-spacing="-0.5">anti-slop</text>',
        '    <rect x="192" y="5" width="256" height="30" rx="15" fill="#ffffff" stroke="#cbd5e1" stroke-width="1.2"/>',
        '    <circle cx="210" cy="20" r="4" fill="#0f766e"/>',
        '    <text x="223" y="24.5" class="mono" font-size="11.5" font-weight="600" fill="#334155" letter-spacing="0.3">AGENT-FIRST · HUMAN-GUIDED</text>',
        "  </g>",
        "",
        '  <text x="72" y="192" class="sans" font-size="48" font-weight="700" fill="#0f172a" letter-spacing="-1.0">Guardrails built</text>',
        '  <text x="72" y="250" class="sans" font-size="48" font-weight="700" fill="#0f766e" letter-spacing="-1.0">for AI coding agents.</text>',
        "",
        '  <text x="72" y="308" class="sans" font-size="21" font-weight="500" fill="#475569">No CLI to memorize. Install once and</text>',
        '  <text x="72" y="338" class="sans" font-size="21" font-weight="500" fill="#475569">your agent catches shortcuts, verifies the</text>',
        '  <text x="72" y="368" class="sans" font-size="21" font-weight="500" fill="#475569">live app, and brings plain-English reviews.</text>',
        "",
        "  <!-- High-Contrast Proof Tiles (Option 2 Dark Anchor Aesthetic) -->",
        '  <g transform="translate(72, 408)">',
        '    <rect x="0" y="0" width="248" height="84" rx="14" fill="#0f172a"/>',
        f'    <text x="22" y="39" class="sans" font-size="27" font-weight="700" fill="#2dd4bf">{_esc(left_stat_val)}</text>',
        f'    <text x="22" y="65" class="sans" font-size="14" font-weight="500" fill="#cbd5e1">{_esc(left_stat_label)}</text>',
        "",
        '    <rect x="264" y="0" width="260" height="84" rx="14" fill="#0f172a"/>',
        f'    <text x="286" y="39" class="sans" font-size="27" font-weight="700" fill="#2dd4bf">{_esc(right_stat_val)}</text>',
        f'    <text x="286" y="65" class="sans" font-size="14" font-weight="500" fill="#cbd5e1">{_esc(right_stat_label)}</text>',
        "  </g>",
        "",
        '  <text x="72" y="540" class="sans" font-size="15.5" font-weight="600" fill="#0f172a">Claude Code · Codex · Antigravity · GitHub Actions</text>',
        '  <text x="72" y="568" class="mono" font-size="12.5" fill="#64748b">Python &amp; JS/TS · 0 dependencies · MIT License</text>',
        "",
        "  <!-- Right Column: Mid-Turn Flow Card (Editorial Light) -->",
        '  <rect x="646" y="68" width="558" height="504" rx="20" fill="#ffffff" stroke="#dbe3ec" stroke-width="1.5"/>',
        '  <text x="676" y="106" class="sans" font-size="15.5" font-weight="700" fill="#475569" letter-spacing="0.4">HOW IT WORKS MID-TURN</text>',
        '  <rect x="1038" y="86" width="136" height="26" rx="13" fill="#f0fdfa" stroke="#99f6e4"/>',
        '  <text x="1106" y="103.5" text-anchor="middle" class="mono" font-size="11.5" font-weight="600" fill="#0f766e">0 prompt tokens</text>',
        '  <line x1="676" y1="126" x2="1174" y2="126" stroke="#e2e8f0" stroke-width="1"/>',
        "",
        "  <!-- Step 1: Shortcut Attempt -->",
        '  <g transform="translate(676, 146)">',
        '    <rect x="0" y="0" width="498" height="106" rx="14" fill="#fef2f2" stroke="#fecaca" stroke-width="1.4"/>',
        '    <circle cx="24" cy="28" r="7" fill="#dc2626"/>',
        '    <text x="42" y="34" class="sans" font-size="17" font-weight="700" fill="#991b1b">1. Agent tries to finish with shortcuts</text>',
        '    <rect x="20" y="54" width="142" height="32" rx="8" fill="#ffffff" stroke="#fca5a5"/>',
        '    <text x="91" y="75" text-anchor="middle" class="sans" font-size="13.5" font-weight="600" fill="#b91c1c">Skipped test</text>',
        '    <rect x="174" y="54" width="146" height="32" rx="8" fill="#ffffff" stroke="#fca5a5"/>',
        '    <text x="247" y="75" text-anchor="middle" class="sans" font-size="13.5" font-weight="600" fill="#b91c1c">Hidden error</text>',
        '    <rect x="332" y="54" width="146" height="32" rx="8" fill="#ffffff" stroke="#fca5a5"/>',
        '    <text x="405" y="75" text-anchor="middle" class="sans" font-size="13.5" font-weight="600" fill="#b91c1c">Copy-paste drift</text>',
        "  </g>",
        "",
        "  <!-- Arrow 1 -> 2 -->",
        '  <path d="M 925 256 V 280 M 918 273 L 925 281 L 932 273" fill="none" stroke="#94a3b8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
        "",
        "  <!-- Step 2: Block & Explain -->",
        '  <g transform="translate(676, 288)">',
        '    <rect x="0" y="0" width="498" height="106" rx="14" fill="#eff6ff" stroke="#bfdbfe" stroke-width="1.4"/>',
        '    <circle cx="24" cy="28" r="7" fill="#2563eb"/>',
        '    <text x="42" y="34" class="sans" font-size="17" font-weight="700" fill="#1e40af">2. anti-slop blocks &amp; explains why</text>',
        '    <text x="22" y="64" class="sans" font-size="15.5" font-weight="500" fill="#1e293b">“Don&apos;t skip the failing test. Fix the root bug,</text>',
        '    <text x="22" y="88" class="sans" font-size="15.5" font-weight="500" fill="#1e293b">reuse the shared helper, and verify the live app.”</text>',
        "  </g>",
        "",
        "  <!-- Arrow 2 -> 3 -->",
        '  <path d="M 925 398 V 422 M 918 415 L 925 423 L 932 415" fill="none" stroke="#94a3b8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
        "",
        "  <!-- Step 3: Fix & Verify -->",
        '  <g transform="translate(676, 430)">',
        '    <rect x="0" y="0" width="498" height="114" rx="14" fill="#f0fdfa" stroke="#99f6e4" stroke-width="1.4"/>',
        '    <circle cx="24" cy="28" r="7" fill="#0f766e"/>',
        '    <text x="42" y="34" class="sans" font-size="17" font-weight="700" fill="#115e59">3. Agent fixes root cause &amp; proves it works</text>',
        '    <rect x="20" y="56" width="142" height="34" rx="8" fill="#ffffff" stroke="#5eead4"/>',
        f'    <text x="91" y="78" text-anchor="middle" class="sans" font-size="13.5" font-weight="700" fill="#0f766e">{_esc(slop_chip)}</text>',
        '    <rect x="174" y="56" width="146" height="34" rx="8" fill="#ffffff" stroke="#5eead4"/>',
        '    <text x="247" y="78" text-anchor="middle" class="sans" font-size="13.5" font-weight="700" fill="#0f766e">✓ Live app check</text>',
        '    <rect x="332" y="56" width="146" height="34" rx="8" fill="#ffffff" stroke="#5eead4"/>',
        '    <text x="405" y="78" text-anchor="middle" class="sans" font-size="13.5" font-weight="700" fill="#0f766e">✓ Real tests pass</text>',
        "  </g>",
        "</svg>",
        "",
    ]
    return "\n".join(lines)


def _write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render deterministic SVG assets from live pilot runs.jsonl datasets."
    )
    parser.add_argument(
        "--runs",
        type=Path,
        default=None,
        help="Path to v0.6.0 runs.jsonl (default: results/pilot-3way-v0.6.0/runs.jsonl)",
    )
    parser.add_argument(
        "--evolution-runs",
        type=Path,
        default=None,
        help="Path to EV1 runs.jsonl (default: results/pilot-evolution-v0.7.0/runs.jsonl)",
    )
    parser.add_argument(
        "--ts-evolution-runs",
        type=Path,
        default=None,
        help="Path to EV2 runs.jsonl (default: results/pilot-ts-evolution-v0.8.0/runs.jsonl)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for SVGs (default: docs/assets)",
    )
    parser.add_argument(
        "--social-svg",
        type=Path,
        default=None,
        help="Optional path to write the 1280x640 social preview SVG for PNG rasterization",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    runs_path = args.runs if args.runs is not None else (
        repo_root / "results" / "pilot-3way-v0.6.0" / "runs.jsonl"
    )
    ev_runs_path = args.evolution_runs if args.evolution_runs is not None else (
        repo_root / "results" / "pilot-evolution-v0.7.0" / "runs.jsonl"
    )
    ts_ev_runs_path = (
        args.ts_evolution_runs
        if args.ts_evolution_runs is not None
        else (repo_root / "results" / "pilot-ts-evolution-v0.8.0" / "runs.jsonl")
    )
    out_dir = args.out_dir if args.out_dir is not None else (
        repo_root / "docs" / "assets"
    )

    stats = compute_pilot_stats(repo_root, runs_path)
    ev_stats = (
        compute_evolution_stats(repo_root, ev_runs_path)
        if ev_runs_path.is_file()
        else None
    )
    ts_ev_stats = (
        compute_evolution_stats(repo_root, ts_ev_runs_path)
        if ts_ev_runs_path.is_file()
        else None
    )

    outputs: dict[Path, str] = {
        out_dir / "pilot-v0.6.0-results-light.svg": render_pilot_results_svg(
            stats, LIGHT_THEME
        ),
        out_dir / "pilot-v0.6.0-results-dark.svg": render_pilot_results_svg(
            stats, DARK_THEME
        ),
        out_dir / "hook-loop-light.svg": render_hook_loop_svg(LIGHT_THEME),
        out_dir / "hook-loop-dark.svg": render_hook_loop_svg(DARK_THEME),
    }
    if ev_stats is not None:
        outputs[out_dir / "pilot-v0.7.0-evolution-light.svg"] = (
            render_evolution_results_svg(ev_stats, LIGHT_THEME)
        )
        outputs[out_dir / "pilot-v0.7.0-evolution-dark.svg"] = (
            render_evolution_results_svg(ev_stats, DARK_THEME)
        )
    if ts_ev_stats is not None:
        outputs[out_dir / "pilot-v0.8.0-ts-evolution-light.svg"] = (
            render_ts_evolution_results_svg(ts_ev_stats, LIGHT_THEME)
        )
        outputs[out_dir / "pilot-v0.8.0-ts-evolution-dark.svg"] = (
            render_ts_evolution_results_svg(ts_ev_stats, DARK_THEME)
        )

    for path, content in outputs.items():
        _write_if_changed(path, content)

    if args.social_svg is not None:
        _write_if_changed(
            args.social_svg, render_social_preview_svg(stats, ev_stats, ts_ev_stats)
        )

    ev_summary = ""
    if ev_stats is not None:
        ev_summary += (
            f"; EV1 {ev_stats.cond_pass['baseline']}/{ev_stats.cond_total['baseline']} -> "
            f"{ev_stats.cond_pass['core-rules-v0.2.0']}/{ev_stats.cond_total['core-rules-v0.2.0']} -> "
            f"{ev_stats.cond_pass['gated-structural']}/{ev_stats.cond_total['gated-structural']} "
            f"({ev_stats.cond_slop['baseline']} -> {ev_stats.cond_slop['core-rules-v0.2.0']} -> "
            f"{ev_stats.cond_slop['gated-structural']} slop)"
        )
    if ts_ev_stats is not None:
        ev_summary += (
            f"; EV2 {ts_ev_stats.cond_pass['baseline']}/{ts_ev_stats.cond_total['baseline']} -> "
            f"{ts_ev_stats.cond_pass['core-rules-v0.2.0']}/{ts_ev_stats.cond_total['core-rules-v0.2.0']} -> "
            f"{ts_ev_stats.cond_pass['gated-structural']}/{ts_ev_stats.cond_total['gated-structural']} "
            f"({ts_ev_stats.cond_slop['baseline']} -> {ts_ev_stats.cond_slop['core-rules-v0.2.0']} -> "
            f"{ts_ev_stats.cond_slop['gated-structural']} slop)"
        )

    print(
        f"Rendered {len(outputs)} SVG assets from {runs_path.name} "
        f"({stats.total_runs} runs; RW3 tampering {stats.rw3_tampered['baseline']}/"
        f"{stats.rw3_completed['baseline']} -> "
        f"{stats.rw3_tampered['core-rules-v0.2.0']}/{stats.rw3_completed['core-rules-v0.2.0']} / "
        f"{stats.rw3_tampered['model-controls']}/{stats.rw3_completed['model-controls']}; "
        f"overall {stats.cond_pass['baseline']}/{stats.cond_total['baseline']} -> "
        f"{stats.cond_pass['core-rules-v0.2.0']}/{stats.cond_total['core-rules-v0.2.0']} -> "
        f"{stats.cond_pass['model-controls']}/{stats.cond_total['model-controls']}"
        f"{ev_summary})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
