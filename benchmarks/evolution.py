#!/usr/bin/env python3
"""Multi-turn compounding software quality measurement & AST mutation testing.

Evaluates rules and controls against real software quality (not word caps):
  1. Test strength against injected mutated bugs (stdlib Python AST mutator).
  2. Duplicate code block growth across production modules.
  3. Dead / orphaned compatibility paths and unreferenced helpers.
  4. God-function / god-file growth and file sprawl.
  5. Silent failures, silent fallbacks, test skips, suppressions, and stubs.
  6. Empirical KEEP / DROP / INCONCLUSIVE decision helper comparing paired
     baseline vs. treatment multi-turn evolution runs.

Zero third-party dependencies (Python 3.11+ stdlib only).
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gates import diff_check as _dc  # noqa: E402
from gates import structural as _struct  # noqa: E402


COMPARE_SWAPS: Dict[type[ast.cmpop], Tuple[str, type[ast.cmpop]]] = {
    ast.LtE: ("<= -> <", ast.Lt),
    ast.Lt: ("< -> <=", ast.LtE),
    ast.GtE: (">= -> >", ast.Gt),
    ast.Gt: ("> -> >=", ast.GtE),
    ast.Eq: ("== -> !=", ast.NotEq),
    ast.NotEq: ("!= -> ==", ast.Eq),
}

BINOP_SWAPS: Dict[type[ast.operator], Tuple[str, type[ast.operator]]] = {
    ast.Add: ("+ -> -", ast.Sub),
    ast.Sub: ("- -> +", ast.Add),
    ast.Mult: ("* -> +", ast.Add),
    ast.FloorDiv: ("// -> +", ast.Add),
}

BOOLOP_SWAPS: Dict[type[ast.boolop], Tuple[str, type[ast.boolop]]] = {
    ast.And: ("and -> or", ast.Or),
    ast.Or: ("or -> and", ast.And),
}


def generate_python_mutants(
    rel_path: str,
    source: str,
    *,
    max_per_file: int = 12,
) -> List[Dict[str, Any]]:
    """Generate deterministic single-site Python AST bug mutants for rel_path."""
    try:
        base_tree = ast.parse(source)
    except SyntaxError:
        return []

    # Collect candidate mutation sites with exact AST path indices so we can
    # apply each mutation cleanly on a fresh deepcopy of base_tree.
    sites: List[Tuple[str, int, str, int]] = []  # (category, node_index, desc, lineno)
    all_nodes = list(ast.walk(base_tree))

    for idx, node in enumerate(all_nodes):
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            op_t = type(node.ops[0])
            if op_t in COMPARE_SWAPS:
                label, _ = COMPARE_SWAPS[op_t]
                sites.append(("boundary", idx, f"{rel_path}:{lineno} compare ({label})", lineno))
        elif isinstance(node, ast.BinOp):
            op_t = type(node.op)
            if op_t in BINOP_SWAPS:
                # Skip string concatenation `a + b` where an operand is a string constant.
                if isinstance(node.op, ast.Add) and (
                    (isinstance(node.left, ast.Constant) and isinstance(node.left.value, str))
                    or (isinstance(node.right, ast.Constant) and isinstance(node.right.value, str))
                ):
                    continue
                label, _ = BINOP_SWAPS[op_t]
                sites.append(("arithmetic", idx, f"{rel_path}:{lineno} arithmetic ({label})", lineno))
        elif isinstance(node, ast.BoolOp):
            op_t = type(node.op)
            if op_t in BOOLOP_SWAPS:
                label, _ = BOOLOP_SWAPS[op_t]
                sites.append(("logic", idx, f"{rel_path}:{lineno} boolean ({label})", lineno))
        elif isinstance(node, ast.Raise) and node.exc is not None:
            sites.append(("validation", idx, f"{rel_path}:{lineno} bypass raise -> pass", lineno))

    if not sites:
        return []

    # Round-robin across categories so boundary, arithmetic, logic, and validation
    # mutants are all represented cleanly within max_per_file.
    by_cat: Dict[str, List[Tuple[str, int, str, int]]] = {}
    for item in sites:
        by_cat.setdefault(item[0], []).append(item)

    selected: List[Tuple[str, int, str, int]] = []
    cat_order = ("validation", "boundary", "arithmetic", "logic")
    round_idx = 0
    while len(selected) < max_per_file:
        added_any = False
        for cat in cat_order:
            bucket = by_cat.get(cat) or []
            if round_idx < len(bucket):
                selected.append(bucket[round_idx])
                added_any = True
                if len(selected) >= max_per_file:
                    break
        if not added_any:
            break
        round_idx += 1

    mutants: List[Dict[str, Any]] = []
    for cat, target_idx, desc, lineno in selected:
        tree_copy = copy.deepcopy(base_tree)
        nodes_copy = list(ast.walk(tree_copy))
        target = nodes_copy[target_idx]

        if cat == "boundary" and isinstance(target, ast.Compare):
            _, new_op_cls = COMPARE_SWAPS[type(target.ops[0])]
            target.ops[0] = new_op_cls()
        elif cat == "arithmetic" and isinstance(target, ast.BinOp):
            _, new_op_cls = BINOP_SWAPS[type(target.op)]
            target.op = new_op_cls()
        elif cat == "logic" and isinstance(target, ast.BoolOp):
            _, new_op_cls = BOOLOP_SWAPS[type(target.op)]
            target.op = new_op_cls()
        elif cat == "validation" and isinstance(target, ast.Raise):
            _replace_stmt_in_tree(tree_copy, target, ast.Pass())
        else:
            continue

        ast.fix_missing_locations(tree_copy)
        try:
            mutated_source = ast.unparse(tree_copy) + "\n"
        except (AttributeError, ValueError, RecursionError):
            continue
        if mutated_source == source:
            continue
        mutants.append({
            "file": rel_path,
            "line": lineno,
            "category": cat,
            "description": desc,
            "mutated_source": mutated_source,
        })

    return mutants


def _replace_stmt_in_tree(tree: ast.AST, old_stmt: ast.stmt, new_stmt: ast.stmt) -> bool:
    for node in ast.walk(tree):
        for field_name in ("body", "orelse", "finalbody"):
            stmts = getattr(node, field_name, None)
            if isinstance(stmts, list):
                for i, s in enumerate(stmts):
                    if s is old_stmt:
                        stmts[i] = new_stmt
                        return True
    return False


def run_mutation_suite(
    workspace_dir: Path | str,
    target_rel_paths: Sequence[str],
    test_cmd: Sequence[str],
    *,
    max_mutants: int = 24,
    timeout_s: float = 5.0,
) -> Dict[str, Any]:
    """Run candidate's test suite against injected AST mutants in an isolated temp copy."""
    src_root = Path(workspace_dir).resolve()
    if not src_root.is_dir():
        return {
            "baseline_tests_passed": False,
            "error": f"Workspace directory not found: {src_root}",
            "total": 0,
            "killed": 0,
            "survived": 0,
            "timed_out": 0,
            "kill_rate": 0.0,
            "survived_mutants": [],
        }

    with tempfile.TemporaryDirectory(prefix="antislop_mut_") as tmp:
        copy_root = Path(tmp) / src_root.name
        shutil.copytree(
            src_root,
            copy_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )

        # Rewrite any test_cmd path pointing into src_root so tests always run against copy_root.
        effective_cmd: List[str] = []
        for arg in test_cmd:
            try:
                p = Path(arg)
                if p.is_absolute():
                    rel = p.resolve().relative_to(src_root)
                    effective_cmd.append(str(copy_root / rel))
                    continue
            except (OSError, ValueError):
                pass
            effective_cmd.append(arg)

        # 1. Confirm baseline tests actually pass before injecting mutations.
        try:
            base_proc = subprocess.run(
                effective_cmd,
                cwd=copy_root,
                capture_output=True,
                text=True,
                timeout=max(timeout_s * 2, 10.0),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "baseline_tests_passed": False,
                "error": "Baseline test command timed out before mutation testing.",
                "total": 0,
                "killed": 0,
                "survived": 0,
                "timed_out": 0,
                "kill_rate": 0.0,
                "survived_mutants": [],
            }

        if base_proc.returncode != 0:
            return {
                "baseline_tests_passed": False,
                "error": f"Baseline tests failed (exit {base_proc.returncode}); mutation testing skipped.",
                "baseline_stderr": (base_proc.stderr or base_proc.stdout)[-500:],
                "total": 0,
                "killed": 0,
                "survived": 0,
                "timed_out": 0,
                "kill_rate": 0.0,
                "survived_mutants": [],
            }

        # 2. Generate balanced mutants across target_rel_paths and interleave round-robin.
        valid_targets = [
            rel for rel in target_rel_paths
            if (copy_root / rel).is_file() and rel.endswith(".py")
        ]
        per_file_cap = max(4, (max_mutants + max(len(valid_targets), 1) - 1) // max(len(valid_targets), 1))
        per_file_buckets: List[List[Dict[str, Any]]] = []
        originals: Dict[str, str] = {}

        for rel in valid_targets:
            text = (copy_root / rel).read_text(encoding="utf-8")
            originals[rel] = text
            bucket = generate_python_mutants(rel, text, max_per_file=per_file_cap)
            if bucket:
                per_file_buckets.append(bucket)

        mutants: List[Dict[str, Any]] = []
        round_idx = 0
        while len(mutants) < max_mutants:
            added_any = False
            for bucket in per_file_buckets:
                if round_idx < len(bucket):
                    mutants.append(bucket[round_idx])
                    added_any = True
                    if len(mutants) >= max_mutants:
                        break
            if not added_any:
                break
            round_idx += 1
        killed = 0
        survived = 0
        timed_out = 0
        survived_mutants: List[str] = []

        for m in mutants:
            rel = m["file"]
            target_file = copy_root / rel
            try:
                target_file.write_text(m["mutated_source"], encoding="utf-8")
                try:
                    proc = subprocess.run(
                        effective_cmd,
                        cwd=copy_root,
                        capture_output=True,
                        text=True,
                        timeout=timeout_s,
                        check=False,
                    )
                    if proc.returncode != 0:
                        killed += 1
                    else:
                        survived += 1
                        survived_mutants.append(m["description"])
                except subprocess.TimeoutExpired:
                    killed += 1
                    timed_out += 1
            finally:
                target_file.write_text(originals[rel], encoding="utf-8")

        total = len(mutants)
        kill_rate = round(killed / total, 4) if total else 0.0
        return {
            "baseline_tests_passed": True,
            "total": total,
            "killed": killed,
            "survived": survived,
            "timed_out": timed_out,
            "kill_rate": kill_rate,
            "survived_mutants": survived_mutants,
        }


def measure_workspace_quality(
    workspace_dir: Path | str,
    *,
    test_cmd: Optional[Sequence[str]] = None,
    mutate_files: Optional[Sequence[str]] = None,
    max_mutants: int = 20,
    max_func_lines: int = _struct.DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = _struct.DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = _struct.DEFAULT_MAX_FILE_LINES,
) -> Dict[str, Any]:
    """Measure compounding software quality metrics across an entire workspace."""
    root = Path(workspace_dir).resolve()
    all_code_files: List[str] = []
    prod_files: List[str] = []
    test_files: List[str] = []

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in _struct.EXCLUDED_SCAN_DIRS for part in rel_parts):
            continue
        rel = "/".join(rel_parts)
        if not _dc._is_code_path(rel):
            continue
        all_code_files.append(rel)
        if _dc._is_test_file(rel):
            test_files.append(rel)
        else:
            prod_files.append(rel)

    surface = _dc.check_files(
        all_code_files,
        repo_root=root,
        allow_test_edit=True,
        allow_test_skip=False,
        no_budget=True,
    )
    structural = _struct.check_structural_files(
        all_code_files,
        repo_root=root,
        strict_structural=False,
        max_func_lines=max_func_lines,
        max_func_branches=max_func_branches,
        max_file_lines=max_file_lines,
    )

    all_findings = (
        list(surface["errors"])
        + list(surface["warnings"])
        + list(structural["errors"])
        + list(structural["warnings"])
    )

    def _by_code(*codes: str) -> List[Dict[str, Any]]:
        cset = set(codes)
        return [f for f in all_findings if f["code"] in cset]

    # Compute raw complexity/size stats across production Python files.
    prod_code_lines = 0
    max_fn_lines_seen = 0
    max_fn_branches_seen = 0
    for rel in prod_files:
        if not rel.endswith(".py"):
            continue
        src = (root / rel).read_text(encoding="utf-8")
        prod_code_lines += _struct._count_py_non_blank_code_lines(src, 1, len(src.splitlines()))
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
                doc_lines = _struct._docstring_line_range(node.body)
                fl = _struct._count_py_non_blank_code_lines(src, node.lineno, end_ln, docstring_lines=doc_lines)
                fb = _struct._py_branch_count(node)
                if fl > max_fn_lines_seen:
                    max_fn_lines_seen = fl
                if fb > max_fn_branches_seen:
                    max_fn_branches_seen = fb

    mutation_result: Optional[Dict[str, Any]] = None
    if test_cmd is not None:
        targets = list(mutate_files) if mutate_files is not None else [
            rel for rel in prod_files if rel.endswith(".py") and Path(rel).name not in ("__init__.py", "run_checks.py")
        ]
        mutation_result = run_mutation_suite(
            root,
            targets,
            test_cmd,
            max_mutants=max_mutants,
        )

    dups = _by_code("STRUCT-DUPLICATE-BLOCK")
    deads = _by_code("STRUCT-DEAD-COMPAT")
    god_fns = _by_code("STRUCT-GOD-FUNCTION")
    god_files = _by_code("STRUCT-GOD-FILE")
    theaters = _by_code("STRUCT-TEST-THEATER")
    silent_and_shortcuts = _by_code(
        "DIFF-SILENT-CATCH",
        "STRUCT-SILENT-FALLBACK",
        "DIFF-TEST-SKIP",
        "DIFF-SUPPRESSION",
        "DIFF-STUB-TODO",
        "DIFF-STUB-NOT-IMPLEMENTED",
        "DIFF-STUB-PASS",
        "DIFF-DEBUG-LEFTOVER",
        "DIFF-HOST-PATH",
    )

    return {
        "workspace": str(root.name),
        "prod_files_count": len(prod_files),
        "test_files_count": len(test_files),
        "prod_code_lines": prod_code_lines,
        "max_func_lines": max_fn_lines_seen,
        "max_func_branches": max_fn_branches_seen,
        "counts": {
            "duplicate_blocks": len(dups),
            "dead_compat": len(deads),
            "god_functions": len(god_fns),
            "god_files": len(god_files),
            "test_theater": len(theaters),
            "silent_failures_and_shortcuts": len(silent_and_shortcuts),
        },
        "mutation_testing": mutation_result,
        "findings": {
            "duplicate_blocks": dups,
            "dead_compat": deads,
            "god_functions": god_fns,
            "god_files": god_files,
            "test_theater": theaters,
            "silent_failures_and_shortcuts": silent_and_shortcuts,
        },
    }


def _avg(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compare_evolution_arms(
    baseline_runs: Sequence[Dict[str, Any]],
    treatment_runs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compare baseline vs. treatment multi-turn software quality snapshots -> KEEP / DROP / INCONCLUSIVE.

    Each run dict expects:
      - functional_passed: bool
      - mutation_kill_rate: float (0.0..1.0)
      - duplicate_blocks: int
      - dead_compat: int
      - god_functions: int
      - silent_failures_and_shortcuts: int
      - test_theater: int
    """
    if not baseline_runs or not treatment_runs:
        return {
            "decision": "INCONCLUSIVE",
            "reason": "Need at least one recorded run in both baseline and treatment arms.",
            "deltas": {},
        }

    def _unwrap(raw: Dict[str, Any]) -> Dict[str, Any]:
        # Accept either flat metrics dicts or full grade_ev1.py JSON reports (with nested "metrics").
        if isinstance(raw.get("metrics"), dict) and "functional_passed" in raw["metrics"]:
            return raw["metrics"]
        return raw

    def _agg(runs: Sequence[Dict[str, Any]]) -> Dict[str, float]:
        norm = [_unwrap(r) for r in runs]
        slop_totals = [
            int(r.get("duplicate_blocks", 0))
            + int(r.get("dead_compat", 0))
            + int(r.get("god_functions", 0))
            + int(r.get("god_files", 0))
            + int(r.get("silent_failures_and_shortcuts", 0))
            + int(r.get("test_theater", 0))
            for r in norm
        ]
        return {
            "functional_pass_rate": round(_avg([1.0 if r.get("functional_passed") else 0.0 for r in norm]), 4),
            "mutation_kill_rate": round(_avg([float(r.get("mutation_kill_rate", 0.0)) for r in norm]), 4),
            "avg_slop_defects": round(_avg([float(x) for x in slop_totals]), 4),
            "avg_duplicates": round(_avg([float(r.get("duplicate_blocks", 0)) for r in norm]), 4),
            "avg_dead_compat": round(_avg([float(r.get("dead_compat", 0)) for r in norm]), 4),
            "avg_silent_failures": round(_avg([float(r.get("silent_failures_and_shortcuts", 0)) for r in norm]), 4),
        }

    b = _agg(baseline_runs)
    t = _agg(treatment_runs)

    func_delta = round(t["functional_pass_rate"] - b["functional_pass_rate"], 4)
    mut_delta = round(t["mutation_kill_rate"] - b["mutation_kill_rate"], 4)
    slop_delta = round(t["avg_slop_defects"] - b["avg_slop_defects"], 4)

    # Empirical keep/drop rules:
    # - DROP if functional pass rate regresses, OR mutation strength drops meaningfully (> 5 pts),
    #   OR slop defects increase without functional gain, OR zero measurable gain across all dimensions.
    # - KEEP if functional pass rate does not regress AND at least one primary quality dimension
    #   improves meaningfully (functional > 0, mutation kill rate >= +0.05, or slop defects <= -1.0)
    #   without regressing other primary dimensions.
    if func_delta < 0:
        decision = "DROP"
        reason = f"Treatment regressed functional correctness ({b['functional_pass_rate']:.1%} -> {t['functional_pass_rate']:.1%})."
    elif mut_delta < -0.05:
        decision = "DROP"
        reason = f"Treatment weakened test mutation kill rate ({b['mutation_kill_rate']:.1%} -> {t['mutation_kill_rate']:.1%})."
    elif slop_delta > 0 and func_delta == 0:
        decision = "DROP"
        reason = f"Treatment increased structural slop defects ({b['avg_slop_defects']:.2f} -> {t['avg_slop_defects']:.2f}) with no functional gain."
    elif (func_delta > 0 or mut_delta >= 0.05 or slop_delta <= -1.0) and slop_delta <= 0:
        decision = "KEEP"
        reason = (
            f"Treatment improved real software quality without functional regression "
            f"(functional {func_delta:+.1%}, mutation kill rate {mut_delta:+.1%}, "
            f"slop defects {slop_delta:+.2f}/run)."
        )
    else:
        decision = "INCONCLUSIVE"
        reason = (
            f"No decisive quality gain detected across {len(treatment_runs)} run(s) "
            f"(functional {func_delta:+.1%}, mutation {mut_delta:+.1%}, slop {slop_delta:+.2f}/run); "
            "consider dropping the rule if it adds prompt or token cost."
        )

    return {
        "decision": decision,
        "reason": reason,
        "n_baseline": len(baseline_runs),
        "n_treatment": len(treatment_runs),
        "baseline": b,
        "treatment": t,
        "deltas": {
            "functional_pass_rate": func_delta,
            "mutation_kill_rate": mut_delta,
            "avg_slop_defects": slop_delta,
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure compounding software quality & mutation test strength, or compare evolution arms."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_m = sub.add_parser("measure", help="Measure compounding software quality for a workspace.")
    p_m.add_argument("workspace", help="Path to workspace directory.")
    p_m.add_argument("--test-cmd", nargs="+", default=None, help="Optional test command for AST mutation testing.")
    p_m.add_argument("--max-mutants", type=int, default=20, help="Max AST mutants to test (default: 20).")

    p_c = sub.add_parser("compare", help="Compare baseline vs. treatment evolution JSON summaries.")
    p_c.add_argument("--baseline", required=True, help="JSON file containing baseline run list.")
    p_c.add_argument("--treatment", required=True, help="JSON file containing treatment run list.")

    args = parser.parse_args(argv)
    if args.command == "measure":
        snap = measure_workspace_quality(
            args.workspace,
            test_cmd=args.test_cmd,
            max_mutants=args.max_mutants,
        )
        print(json.dumps(snap, indent=2))
        return 0

    b_runs = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    t_runs = json.loads(Path(args.treatment).read_text(encoding="utf-8"))
    report = compare_evolution_arms(b_runs, t_runs)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
