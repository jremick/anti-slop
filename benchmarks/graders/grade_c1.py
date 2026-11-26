#!/usr/bin/env python3
"""Deterministic automated grader for benchmark case C1 (total_by_category)."""

from __future__ import annotations

import argparse
import copy
import inspect
from pathlib import Path
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_module,
    make_check,
    parse_candidate_ast,
    top_level_public_defs,
)


CASE_ID = "C1"


def grade(candidate_path: str | Path) -> dict[str, Any]:
    """Grade a candidate Python module for case C1."""
    path = Path(candidate_path)
    if not path.is_file():
        return build_report(
            CASE_ID,
            [make_check("load", False, f"candidate file does not exist: {path}")],
        )

    try:
        source, tree = parse_candidate_ast(path)
    except (OSError, SyntaxError) as exc:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"failed to parse candidate: {exc}")],
        )

    checks: list[dict[str, Any]] = []

    # 1. Static hygiene & scope check
    hygiene_errors: list[str] = []
    bad_imports = find_non_stdlib_imports(tree)
    if bad_imports:
        hygiene_errors.append(f"non-stdlib imports: {', '.join(bad_imports)}")
    hygiene_errors.extend(find_stub_or_placeholder_issues(source, tree))
    public_defs = top_level_public_defs(tree)
    extra_defs = sorted(public_defs - {"total_by_category"})
    if extra_defs:
        hygiene_errors.append(f"unexpected public definitions: {', '.join(extra_defs)}")
    if "total_by_category" not in public_defs:
        hygiene_errors.append("missing top-level function total_by_category")

    checks.append(
        make_check(
            "scope",
            not hygiene_errors,
            "stdlib-only, no stubs, public API limited to total_by_category"
            if not hygiene_errors
            else "; ".join(hygiene_errors),
        )
    )

    try:
        module = load_candidate_module(path, prefix="c1")
    except Exception as exc:
        checks.append(make_check("load", False, f"import error: {type(exc).__name__}: {exc}"))
        return build_report(CASE_ID, checks)

    fn = getattr(module, "total_by_category", None)
    if not callable(fn):
        checks.append(make_check("public_api", False, "total_by_category is missing or not callable"))
        return build_report(CASE_ID, checks)

    sig = inspect.signature(fn)
    required_params = [
        p for p in sig.parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
    ]
    if len(required_params) != 1:
        checks.append(
            make_check("public_api", False, f"expected 1 required parameter, found signature {sig}")
        )
        return build_report(CASE_ID, checks)

    # 2. Accumulation check
    acc_errors: list[str] = []
    try:
        res1 = fn([{"category": "A", "count": 3}, {"category": "a", "count": 2}])
        if not isinstance(res1, dict) or res1 != {"a": 5}:
            acc_errors.append(f"A=3, a=2 returned {res1!r}, expected {{'a': 5}}")

        multi_rows = [
            {"category": "  Alpha ", "count": 4},
            {"category": "Beta", "count": 2},
            {"category": "alpha", "count": 1},
            {"category": "BETA ", "count": 3},
            {"category": "Gamma", "count": 7},
        ]
        res2 = fn(multi_rows)
        expected2 = {"alpha": 5, "beta": 5, "gamma": 7}
        if not isinstance(res2, dict) or res2 != expected2:
            acc_errors.append(f"multi-category returned {res2!r}, expected {expected2!r}")

        gen_res = fn(row for row in ({"category": "x", "count": 2}, {"category": "X", "count": 4}))
        if not isinstance(gen_res, dict) or gen_res != {"x": 6}:
            acc_errors.append(f"generator input returned {gen_res!r}, expected {{'x': 6}}")
    except Exception as exc:
        acc_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "accumulate",
            not acc_errors,
            "repeated normalised categories and multi-category iterables accumulate correctly"
            if not acc_errors
            else "; ".join(acc_errors),
        )
    )

    # 3. Contract edge cases (empty, signed zeros, negatives, casefold, immutability)
    contract_errors: list[str] = []
    try:
        empty_res = fn([])
        if not isinstance(empty_res, dict) or empty_res != {}:
            contract_errors.append(f"empty input returned {empty_res!r}, expected {{}}")

        cancel_rows = [{"category": "Alpha", "count": -1}, {"category": "alpha", "count": 1}]
        cancel_res = fn(cancel_rows)
        if not isinstance(cancel_res, dict) or cancel_res != {"alpha": 0} or "alpha" not in cancel_res:
            contract_errors.append(f"-1 and +1 returned {cancel_res!r}, expected {{'alpha': 0}}")

        zero_res = fn([{"category": "Zero", "count": 0}])
        if not isinstance(zero_res, dict) or zero_res != {"zero": 0}:
            contract_errors.append(f"explicit zero returned {zero_res!r}, expected {{'zero': 0}}")

        neg_res = fn([{"category": "Err", "count": -3}, {"category": " err ", "count": -2}])
        if not isinstance(neg_res, dict) or neg_res != {"err": -5}:
            contract_errors.append(f"negative accumulation returned {neg_res!r}, expected {{'err': -5}}")

        fold_res = fn([{"category": "  Straße  ", "count": 1}, {"category": "STRASSE", "count": 2}])
        if not isinstance(fold_res, dict) or fold_res != {"strasse": 3}:
            contract_errors.append(f"Unicode casefold returned {fold_res!r}, expected {{'strasse': 3}}")

        immutable_rows = [
            {"category": "  KeepCase ", "count": 2, "extra": "untouched"},
            {"category": "keepcase", "count": 3, "extra": "also-untouched"},
        ]
        snapshot = copy.deepcopy(immutable_rows)
        fn(immutable_rows)
        if immutable_rows != snapshot:
            contract_errors.append("input rows were mutated")
    except Exception as exc:
        contract_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "contract",
            not contract_errors,
            "empty input, explicit zeros, signed counts, casefold/strip, and immutability preserved"
            if not contract_errors
            else "; ".join(contract_errors),
        )
    )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate Python module for case C1.")
    parser.add_argument("candidate", type=Path, help="Path to candidate Python file")
    args = parser.parse_args(argv)
    return emit_report(grade(args.candidate))


if __name__ == "__main__":
    raise SystemExit(main())
