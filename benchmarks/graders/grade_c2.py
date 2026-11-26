#!/usr/bin/env python3
"""Deterministic automated grader for benchmark case C2 (invoice_total)."""

from __future__ import annotations

import argparse
import ast
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


CASE_ID = "C2"


def _find_discount_ast_symbols(tree: ast.Module) -> list[str]:
    """Find leftover `discount` identifiers in code AST (ignoring docstrings/comments)."""
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if "discount" in node.name.lower():
                hits.add(node.name)
        elif isinstance(node, ast.arg):
            if "discount" in node.arg.lower():
                hits.add(node.arg)
        elif isinstance(node, ast.Name):
            if "discount" in node.id.lower():
                hits.add(node.id)
        elif isinstance(node, ast.Attribute):
            if "discount" in node.attr.lower():
                hits.add(node.attr)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            if "discount" in node.arg.lower():
                hits.add(node.arg)
    return sorted(hits)


def _check_invalid_line_inputs(fn: Any, errors: list[str]) -> None:
    bad_lines = [
        [{"quantity": -1, "unit_price_cents": 100}],
        [{"quantity": 1, "unit_price_cents": -100}],
        [{"quantity": True, "unit_price_cents": 100}],
        [{"quantity": False, "unit_price_cents": 100}],
        [{"quantity": 1, "unit_price_cents": True}],
        [{"quantity": 1, "unit_price_cents": False}],
        [{"quantity": 1.5, "unit_price_cents": 100}],
        [{"quantity": 1.0, "unit_price_cents": 100}],
        [{"quantity": "2", "unit_price_cents": 100}],
        [{"quantity": 1, "unit_price_cents": "100"}],
        [{"quantity": None, "unit_price_cents": 100}],
        [{"quantity": 1, "unit_price_cents": None}],
    ]
    for sample in bad_lines:
        try:
            res = fn(sample)
        except ValueError:
            continue
        except Exception as exc:
            errors.append(f"invalid line {sample!r} raised {type(exc).__name__} instead of ValueError")
            continue
        errors.append(f"invalid line {sample!r} returned {res!r} instead of raising ValueError")


def _check_invalid_scalar_arg(fn: Any, kwarg: str, errors: list[str]) -> None:
    for bad in (-1, True, False, 1.0, 2.5, "100", None):
        try:
            res = fn([{"quantity": 1, "unit_price_cents": 500}], **{kwarg: bad})
        except ValueError:
            continue
        except Exception as exc:
            errors.append(f"{kwarg}={bad!r} raised {type(exc).__name__} instead of ValueError")
            continue
        errors.append(f"{kwarg}={bad!r} returned {res!r} instead of raising ValueError")


def grade(candidate_path: str | Path, stage: int = 3) -> dict[str, Any]:
    """Grade a candidate Python module for case C2 (stage 1, 2, or final 3)."""
    if stage not in (1, 2, 3):
        return build_report(CASE_ID, [make_check("stage", False, f"unsupported stage {stage}; expected 1, 2, or 3")])

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

    # 1. Static hygiene & scope
    hygiene_errors: list[str] = []
    bad_imports = find_non_stdlib_imports(tree)
    if bad_imports:
        hygiene_errors.append(f"non-stdlib imports: {', '.join(bad_imports)}")
    hygiene_errors.extend(find_stub_or_placeholder_issues(source, tree))
    public_defs = top_level_public_defs(tree)
    extra_defs = sorted(public_defs - {"invoice_total"})
    if extra_defs:
        hygiene_errors.append(f"unexpected public definitions: {', '.join(extra_defs)}")
    if "invoice_total" not in public_defs:
        hygiene_errors.append("missing top-level function invoice_total")

    checks.append(
        make_check(
            "scope",
            not hygiene_errors,
            "stdlib-only, no stubs, public API limited to invoice_total"
            if not hygiene_errors
            else "; ".join(hygiene_errors),
        )
    )

    try:
        module = load_candidate_module(path, prefix="c2")
    except Exception as exc:
        checks.append(make_check("load", False, f"import error: {type(exc).__name__}: {exc}"))
        return build_report(CASE_ID, checks)

    fn = getattr(module, "invoice_total", None)
    if not callable(fn):
        checks.append(make_check("public_api", False, "invoice_total is missing or not callable"))
        return build_report(CASE_ID, checks)

    # 2. Core calculation & immutability
    calc_errors: list[str] = []
    try:
        empty_val = fn([])
        if type(empty_val) is not int or empty_val != 0:
            calc_errors.append(f"empty input returned {empty_val!r}, expected int 0")

        sample_lines = [
            {"quantity": 2, "unit_price_cents": 350},
            {"quantity": 3, "unit_price_cents": 100},
        ]
        snapshot = copy.deepcopy(sample_lines)
        total = fn(sample_lines)
        if type(total) is not int or total != 1000:
            calc_errors.append(f"sample lines returned {total!r}, expected 1000")
        if sample_lines != snapshot:
            calc_errors.append("input lines were mutated")

        zero_lines = [
            {"quantity": 0, "unit_price_cents": 999},
            {"quantity": 5, "unit_price_cents": 0},
        ]
        z_total = fn(zero_lines)
        if type(z_total) is not int or z_total != 0:
            calc_errors.append(f"zero-valued lines returned {z_total!r}, expected 0")

        gen_total = fn(item for item in ({"quantity": 2, "unit_price_cents": 50},))
        if type(gen_total) is not int or gen_total != 100:
            calc_errors.append(f"generator input returned {gen_total!r}, expected 100")

        if stage == 2:
            disc_res = fn(sample_lines, discount_cents=250)
            if type(disc_res) is not int or disc_res != 750:
                calc_errors.append(f"discount_cents=250 returned {disc_res!r}, expected 750")
            clamped = fn(sample_lines, discount_cents=2000)
            if type(clamped) is not int or clamped != 0:
                calc_errors.append(f"clamped discount returned {clamped!r}, expected 0")
            empty_disc = fn([], discount_cents=50)
            if type(empty_disc) is not int or empty_disc != 0:
                calc_errors.append(f"empty lines with discount returned {empty_disc!r}, expected 0")

        if stage == 3:
            ship_res = fn(sample_lines, shipping_cents=250)
            if type(ship_res) is not int or ship_res != 1250:
                calc_errors.append(f"shipping_cents=250 returned {ship_res!r}, expected 1250")
            empty_ship = fn([], shipping_cents=500)
            if type(empty_ship) is not int or empty_ship != 500:
                calc_errors.append(f"empty lines with shipping_cents=500 returned {empty_ship!r}, expected 500")
            zero_ship = fn(sample_lines, shipping_cents=0)
            if type(zero_ship) is not int or zero_ship != 1000:
                calc_errors.append(f"shipping_cents=0 returned {zero_ship!r}, expected 1000")
    except Exception as exc:
        calc_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            f"stage{stage}_calculation",
            not calc_errors,
            f"stage {stage} calculation, edge cases, and non-mutation verified"
            if not calc_errors
            else "; ".join(calc_errors),
        )
    )

    # 3. Input validation (negative, non-int, bool)
    val_errors: list[str] = []
    _check_invalid_line_inputs(fn, val_errors)
    if stage == 2:
        _check_invalid_scalar_arg(fn, "discount_cents", val_errors)
    elif stage == 3:
        _check_invalid_scalar_arg(fn, "shipping_cents", val_errors)

    checks.append(
        make_check(
            "validation",
            not val_errors,
            "rejects negative, non-integer, and bool values with ValueError"
            if not val_errors
            else "; ".join(val_errors),
        )
    )

    # 4. Stage-3 subtractive removal check
    if stage == 3:
        removal_errors: list[str] = []
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        if any(p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD) for p in params):
            removal_errors.append(f"variadic compatibility shim not allowed in signature {sig}")
        param_names = [p.name for p in params]
        if param_names != ["lines", "shipping_cents"]:
            removal_errors.append(f"expected parameters ['lines', 'shipping_cents'], got {param_names}")
        elif params[1].default != 0 or type(params[1].default) is not int:
            removal_errors.append(f"shipping_cents default must be int 0, got {params[1].default!r}")

        for call_lines, disc_val in (([], 0), ([{"quantity": 1, "unit_price_cents": 500}], 50)):
            try:
                res = fn(call_lines, discount_cents=disc_val)
            except TypeError:
                pass
            except Exception as exc:
                removal_errors.append(
                    f"discount_cents={disc_val} raised {type(exc).__name__} instead of TypeError"
                )
            else:
                removal_errors.append(
                    f"discount_cents={disc_val} was accepted (returned {res!r}) instead of raising TypeError"
                )

        leftover = _find_discount_ast_symbols(tree)
        if leftover:
            removal_errors.append(f"obsolete discount symbols remain in code AST: {', '.join(leftover)}")

        checks.append(
            make_check(
                "removal",
                not removal_errors,
                "obsolete discount_cents parameter and logic fully removed; calls raise TypeError"
                if not removal_errors
                else "; ".join(removal_errors),
            )
        )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate Python module for case C2.")
    parser.add_argument("candidate", type=Path, help="Path to candidate Python file")
    parser.add_argument(
        "--stage",
        type=int,
        choices=(1, 2, 3),
        default=3,
        help="Lineage stage to grade (default: 3, final subtractive-removal contract)",
    )
    args = parser.parse_args(argv)
    return emit_report(grade(args.candidate, stage=args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
