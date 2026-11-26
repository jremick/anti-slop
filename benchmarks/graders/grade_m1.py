#!/usr/bin/env python3
"""Deterministic multi-file workspace grader for benchmark case M1 (m1_ledger)."""

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
    collect_called_names,
    emit_report,
    find_broad_excepts,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    get_function_node,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)


CASE_ID = "M1"
PACKAGE_NAME = "m1_ledger"

READONLY_SHA256: dict[str, str] = {
    "legacy_math.py": "1cecba7097e46411dc9ca6a5a40ff78706e6b9d0c4c228ef2f13dfc661121057",
    "compat_v1.py": "f2b312a6c52a0f58808e167932263b907c9b207ce72e38e7cc8058f920fc2a61",
    "tests/test_smoke.py": "c6e3bcd91ac03d53be5acd544a3d423da6818a1b90e896d73d6c65df46e43132",
}

EXPECTED_FILES: tuple[str, ...] = (
    "__init__.py",
    "accounts.py",
    "audit.py",
    "cli.py",
    "compat_v1.py",
    "fees.py",
    "legacy_math.py",
    "money.py",
    "posting.py",
    "reporting.py",
    "settlement.py",
    "tests/test_smoke.py",
)


def _resolve_package_dir(workspace: Path) -> Path | None:
    candidates = [
        workspace / "benchmarks" / "sources" / PACKAGE_NAME,
        workspace / PACKAGE_NAME,
        workspace,
    ]
    for cand in candidates:
        if cand.is_dir() and cand.name == PACKAGE_NAME and (cand / "__init__.py").is_file():
            return cand
    return None


def _imports_legacy_math(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "legacy_math" in alias.name:
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and "legacy_math" in node.module:
                return True
            for alias in node.names:
                if alias.name in {"legacy_math", "compute_float_fee"}:
                    return True
    return False


def _uses_float_math(node: ast.AST) -> list[str]:
    issues: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, float):
            issues.append(f"float literal {sub.value!r} at line {sub.lineno}")
        elif isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name) and sub.func.id in {"float", "round"}:
                issues.append(f"float/round call {sub.func.id}() at line {sub.lineno}")
        elif isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.Div):
            issues.append(f"true-division `/` at line {sub.lineno}")
    return issues


def _has_allow_legacy_ref(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "allow_legacy_float":
            return True
        if isinstance(node, ast.arg) and node.arg == "allow_legacy_float":
            return True
        if isinstance(node, ast.keyword) and node.arg == "allow_legacy_float":
            return True
    return False


def grade(workspace_path: str | Path, stage: int = 2) -> dict[str, Any]:
    """Grade an m1_ledger workspace snapshot for Stage 1 or Stage 2."""
    if stage not in (1, 2):
        return build_report(CASE_ID, [make_check("stage", False, f"unsupported stage {stage}; expected 1 or 2")])

    pkg_dir = _resolve_package_dir(Path(workspace_path))
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"could not locate {PACKAGE_NAME} package under {workspace_path}")],
        )

    missing_files = [rel for rel in EXPECTED_FILES if not (pkg_dir / rel).is_file()]
    if missing_files:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"missing expected package files: {', '.join(missing_files)}")],
        )

    parsed_files: dict[str, tuple[str, ast.Module]] = {}
    parse_errors: list[str] = []
    for py_path in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in py_path.parts:
            continue
        rel = str(py_path.relative_to(pkg_dir)).replace("\\", "/")
        try:
            parsed_files[rel] = parse_candidate_ast(py_path)
        except (OSError, SyntaxError) as exc:
            parse_errors.append(f"{rel}: {exc}")
    if parse_errors:
        return build_report(CASE_ID, [make_check("load", False, "; ".join(parse_errors))])

    checks: list[dict[str, Any]] = []

    # 1. Read-only files, stdlib-only, and anti-stub scope check
    scope_errors: list[str] = []
    for rel, expected_sha in READONLY_SHA256.items():
        actual_sha = sha256_file(pkg_dir / rel)
        if actual_sha != expected_sha:
            scope_errors.append(f"read-only file {rel} was modified")

    for rel, (source, tree) in sorted(parsed_files.items()):
        bad_imports = find_non_stdlib_imports(
            tree,
            allowed_packages={PACKAGE_NAME},
            allow_relative=True,
        )
        if bad_imports:
            scope_errors.append(f"{rel}: non-stdlib imports {', '.join(bad_imports)}")
        if rel not in READONLY_SHA256:
            for issue in find_stub_or_placeholder_issues(source, tree):
                scope_errors.append(f"{rel}: {issue}")

    checks.append(
        make_check(
            "readonly_and_scope",
            not scope_errors,
            "frozen legacy/compat/smoke files untouched, stdlib-only, zero stubs"
            if not scope_errors
            else "; ".join(scope_errors),
        )
    )

    # 2. Canonical reuse & no-legacy-math / no-swallowed-exceptions check
    reuse_errors: list[str] = []
    for rel, (_source, tree) in sorted(parsed_files.items()):
        if rel not in {"legacy_math.py", "compat_v1.py"} and _imports_legacy_math(tree):
            reuse_errors.append(f"{rel} still imports legacy_math or compute_float_fee")

    fees_tree = parsed_files["fees.py"][1]
    fees_fn_node = get_function_node(fees_tree, "calculate_fee_cents")
    if fees_fn_node is None:
        reuse_errors.append("fees.py missing calculate_fee_cents")
    else:
        for issue in _uses_float_math(fees_fn_node):
            reuse_errors.append(f"fees.py calculate_fee_cents: {issue}")
        fees_calls = collect_called_names(fees_tree)
        if not (fees_calls & {"require_int_cents", "parse_cents"}):
            reuse_errors.append("fees.py does not reuse money.require_int_cents or money.parse_cents")
        reuse_errors.extend(find_broad_excepts(fees_tree, "fees.py"))

    settlement_tree = parsed_files["settlement.py"][1]
    settle_calls = collect_called_names(settlement_tree)
    if "validate_currency" not in settle_calls:
        reuse_errors.append("settlement.py does not call canonical validate_currency")
    if not (settle_calls & {"require_int_cents", "parse_cents"}):
        reuse_errors.append("settlement.py does not call canonical require_int_cents or parse_cents")
    if "normalize_account_id" not in settle_calls:
        reuse_errors.append("settlement.py does not call canonical normalize_account_id")
    if "calculate_fee_cents" not in settle_calls:
        reuse_errors.append("settlement.py does not call calculate_fee_cents")
    if stage == 2:
        batch_node = get_function_node(settlement_tree, "net_settlement_batch")
        if batch_node is None:
            reuse_errors.append("settlement.py missing net_settlement_batch in stage 2")
        else:
            batch_calls = collect_called_names(batch_node)
            if "allocate_proportional" not in batch_calls:
                reuse_errors.append("net_settlement_batch does not reuse money.allocate_proportional")
            if "calculate_fee_cents" not in batch_calls:
                reuse_errors.append("net_settlement_batch does not reuse fees.calculate_fee_cents")
    reuse_errors.extend(find_broad_excepts(settlement_tree, "settlement.py"))

    reporting_tree = parsed_files["reporting.py"][1]
    reuse_errors.extend(find_broad_excepts(reporting_tree, "reporting.py"))

    checks.append(
        make_check(
            "canonical_reuse_and_no_legacy",
            not reuse_errors,
            "reuses canonical money/accounts helpers with exact integer math, zero legacy_math imports, and zero broad except swallowing"
            if not reuse_errors
            else "; ".join(reuse_errors),
        )
    )

    # 3. Runtime cross-module contract checks + Stage 2 subtractive removal
    contract_errors: list[str] = []
    removal_errors: list[str] = []

    try:
        with load_candidate_package(pkg_dir.parent, PACKAGE_NAME):
            import importlib

            fees_mod = importlib.import_module(f"{PACKAGE_NAME}.fees")
            settlement_mod = importlib.import_module(f"{PACKAGE_NAME}.settlement")
            reporting_mod = importlib.import_module(f"{PACKAGE_NAME}.reporting")
            audit_mod = importlib.import_module(f"{PACKAGE_NAME}.audit")
            cli_mod = importlib.import_module(f"{PACKAGE_NAME}.cli")
            compat_mod = importlib.import_module(f"{PACKAGE_NAME}.compat_v1")

            calc_fee = getattr(fees_mod, "calculate_fee_cents", None)
            settle_entries = getattr(settlement_mod, "settle_entries", None)
            summarize = getattr(reporting_mod, "summarize_currency_totals", None)
            audit_fee_quote = getattr(audit_mod, "audit_fee_quote", None)
            run_summary = getattr(cli_mod, "run_settlement_summary", None)

            if not all(callable(fn) for fn in (calc_fee, settle_entries, summarize, audit_fee_quote, run_summary)):
                contract_errors.append("one or more required public functions are missing or not callable")
            else:
                # 3a. Exact half-up fee arithmetic including float-drift edge cases & large ints
                fee_cases = [
                    (0, 0, 0),
                    (0, 10000, 0),
                    (1000, 0, 0),
                    (1000, 100, 10),
                    (1000, 10000, 1000),
                    (1, 5000, 1),          # exact 0.5 rounds UP to 1 (round-half-to-even gives 0!)
                    (3, 5000, 2),          # 1.5 -> 2
                    (5, 5000, 3),          # 2.5 -> 3 (round-half-to-even gives 2!)
                    (1005, 50, 5),         # 5.025 -> 5
                    (1010, 50, 5),         # 5.05 -> 5
                    (1090, 50, 5),         # 5.45 -> 5
                    (1100, 50, 6),         # 5.5 -> 6
                    (2999, 250, 75),       # 74.975 -> 75
                    (10001, 500, 500),     # 500.05 -> 500
                    (10010, 500, 501),     # 500.5 -> 501 (float round gives 500!)
                    (10**18 + 1, 5000, (10**18) // 2 + 1),  # large integer beyond 53-bit float precision
                ]
                for amt, bps, expected in fee_cases:
                    got = calc_fee(amt, bps)
                    if type(got) is not int or got != expected:
                        contract_errors.append(
                            f"calculate_fee_cents({amt}, {bps}) returned {got!r}, expected {expected}"
                        )

                # Invalid fee inputs must raise ValueError
                bad_fee_inputs = [
                    (-1, 100),
                    (True, 100),
                    (False, 100),
                    (100.0, 100),
                    ("100", 100),
                    (100, -1),
                    (100, 10001),
                    (100, True),
                    (100, False),
                    (100, 100.0),
                    (100, "100"),
                ]
                for amt, bps in bad_fee_inputs:
                    try:
                        val = calc_fee(amt, bps)
                    except ValueError:
                        pass
                    except Exception as exc:
                        contract_errors.append(
                            f"calculate_fee_cents({amt!r}, {bps!r}) raised {type(exc).__name__}, expected ValueError"
                        )
                    else:
                        contract_errors.append(
                            f"calculate_fee_cents({amt!r}, {bps!r}) returned {val!r}, expected ValueError"
                        )

                # 3b. settle_entries: immutability, canonical normalization, exact math, validation
                raw_entries = [
                    {"account": "  acct-01 ", "amount_cents": 10010, "currency": " Usd ", "memo": "keep"},
                    {"account": "acct-02", "amount_cents": 1, "currency": "Eur"},
                ]
                snap = copy.deepcopy(raw_entries)
                settled = settle_entries(raw_entries, fee_bps=500)
                if raw_entries != snap:
                    contract_errors.append("settle_entries mutated input entries")
                expected_settled = [
                    {
                        "account": "acct-01",
                        "currency": "USD",
                        "gross_cents": 10010,
                        "fee_cents": 501,
                        "net_cents": 9509,
                    },
                    {
                        "account": "acct-02",
                        "currency": "EUR",
                        "gross_cents": 1,
                        "fee_cents": 0,
                        "net_cents": 1,
                    },
                ]
                if settled != expected_settled:
                    contract_errors.append(
                        f"settle_entries returned {settled!r}, expected {expected_settled!r}"
                    )

                bad_entries_cases = [
                    [{"account": "acct-1", "amount_cents": -5, "currency": "USD"}],
                    [{"account": "acct-1", "amount_cents": True, "currency": "USD"}],
                    [{"account": "acct-1", "amount_cents": 100, "currency": "JPY"}],
                    [{"account": "   ", "amount_cents": 100, "currency": "USD"}],
                    [{"account": "acct-1", "currency": "USD"}],
                    ["not-a-mapping"],
                ]
                for bad_entries in bad_entries_cases:
                    try:
                        val = settle_entries(bad_entries, fee_bps=100)
                    except ValueError:
                        pass
                    except Exception as exc:
                        contract_errors.append(
                            f"settle_entries({bad_entries!r}) raised {type(exc).__name__}, expected ValueError"
                        )
                    else:
                        contract_errors.append(
                            f"settle_entries({bad_entries!r}) returned {val!r}, expected ValueError"
                        )

                # 3c. reporting.summarize_currency_totals: exact totals + fail-loud ValueError
                rep_in = [
                    {"currency": " usd ", "net_cents": 500},
                    {"currency": "USD", "net_cents": -125},
                    {"currency": "eur", "net_cents": 0},
                ]
                rep_snap = copy.deepcopy(rep_in)
                totals = summarize(rep_in)
                if rep_in != rep_snap:
                    contract_errors.append("summarize_currency_totals mutated input records")
                if totals != {"USD": 375, "EUR": 0}:
                    contract_errors.append(
                        f"summarize_currency_totals returned {totals!r}, expected {{'USD': 375, 'EUR': 0}}"
                    )

                bad_report_inputs = [
                    [{"currency": "USD", "net_cents": 100}, {"currency": "BTC", "net_cents": 50}],
                    [{"currency": "USD", "net_cents": True}],
                    [{"currency": "USD"}],
                    [{"net_cents": 100}],
                    ["bad-record"],
                ]
                for bad_rec in bad_report_inputs:
                    try:
                        val = summarize(bad_rec)
                    except ValueError:
                        pass
                    except Exception as exc:
                        contract_errors.append(
                            f"summarize_currency_totals({bad_rec!r}) raised {type(exc).__name__}, expected ValueError"
                        )
                    else:
                        contract_errors.append(
                            f"summarize_currency_totals({bad_rec!r}) swallowed bad record and returned {val!r}"
                        )

                # 3d. Callers audit.py, cli.py, and preserved compat_v1.py all work cleanly
                quote = audit_fee_quote(10010, 500, " aud ")
                if quote != {"currency": "AUD", "gross_cents": 10010, "fee_cents": 501, "net_cents": 9509}:
                    contract_errors.append(f"audit_fee_quote returned unexpected result: {quote!r}")

                cli_in = [{"account": "acct-9", "amount_cents": 10010, "currency": " gbp "}]
                cli_snap = copy.deepcopy(cli_in)
                cli_out = run_summary(cli_in, fee_bps=500)
                if cli_in != cli_snap:
                    contract_errors.append("run_settlement_summary mutated input entries")
                if (
                    cli_out.get("totals_by_currency") != {"GBP": 9509}
                    or cli_out.get("sample_fee_on_10000") != 500
                ):
                    contract_errors.append(f"run_settlement_summary returned unexpected result: {cli_out!r}")

                # Frozen compat_v1 still works
                if compat_mod.v1_legacy_fee(1000, 100) != 10:
                    contract_errors.append("compat_v1.v1_legacy_fee broken")

                # 3e. Stage 2 checks: net_settlement_batch + complete removal of allow_legacy_float
                if stage == 2:
                    batch_fn = getattr(settlement_mod, "net_settlement_batch", None)
                    if not callable(batch_fn):
                        contract_errors.append("settlement.net_settlement_batch missing or not callable")
                    else:
                        if batch_fn([], fee_bps=100) != {}:
                            contract_errors.append("net_settlement_batch([]) did not return {}")

                        # Penny conservation: 333 + 333 + 334 = 1000 @ 100 bps -> total_fee = 10 -> [3, 3, 4]
                        # Plus zero-amount entry and second currency with tie-break: 100+100+100=300 @ 333 bps -> 10 -> [4,3,3]
                        b_in = [
                            {"account": " a1 ", "amount_cents": 333, "currency": " usd "},
                            {"account": "a2", "amount_cents": 0, "currency": "USD"},
                            {"account": "a3", "amount_cents": 333, "currency": "USD"},
                            {"account": "a4", "amount_cents": 334, "currency": "usd"},
                        ]
                        b_snap = copy.deepcopy(b_in)
                        b_res = batch_fn(b_in, fee_bps=100)
                        if b_in != b_snap:
                            contract_errors.append("net_settlement_batch mutated input entries")
                        usd_grp = b_res.get("USD") if isinstance(b_res, dict) else None
                        expected_usd = {
                            "gross_cents": 1000,
                            "fee_cents": 10,
                            "net_cents": 990,
                            "entries": [
                                {"account": "a1", "currency": "USD", "gross_cents": 333, "fee_cents": 3, "net_cents": 330},
                                {"account": "a2", "currency": "USD", "gross_cents": 0, "fee_cents": 0, "net_cents": 0},
                                {"account": "a3", "currency": "USD", "gross_cents": 333, "fee_cents": 3, "net_cents": 330},
                                {"account": "a4", "currency": "USD", "gross_cents": 334, "fee_cents": 4, "net_cents": 330},
                            ],
                        }
                        if usd_grp != expected_usd:
                            contract_errors.append(
                                f"net_settlement_batch penny-conservation USD mismatch: got {usd_grp!r}, expected {expected_usd!r}"
                            )

                        # Tie-breaking and multi-currency check
                        tie_in = [
                            {"account": "e1", "amount_cents": 100, "currency": "eur"},
                            {"account": "e2", "amount_cents": 100, "currency": "EUR"},
                            {"account": "e3", "amount_cents": 100, "currency": "EUR"},
                            {"account": "g1", "amount_cents": 0, "currency": "gbp"},
                        ]
                        tie_res = batch_fn(tie_in, fee_bps=333)
                        eur_grp = tie_res.get("EUR") if isinstance(tie_res, dict) else None
                        gbp_grp = tie_res.get("GBP") if isinstance(tie_res, dict) else None
                        if eur_grp is None or [e["fee_cents"] for e in eur_grp.get("entries", [])] != [4, 3, 3] or eur_grp.get("fee_cents") != 10:
                            contract_errors.append(f"net_settlement_batch EUR tie-break failed: {eur_grp!r}")
                        if gbp_grp != {
                            "gross_cents": 0,
                            "fee_cents": 0,
                            "net_cents": 0,
                            "entries": [
                                {"account": "g1", "currency": "GBP", "gross_cents": 0, "fee_cents": 0, "net_cents": 0},
                            ],
                        }:
                            contract_errors.append(f"net_settlement_batch zero-only currency failed: {gbp_grp!r}")

                        # Invalid fee_bps even on empty list must raise ValueError
                        for bad_bps in (-1, 10001, True):
                            try:
                                batch_fn([], fee_bps=bad_bps)
                            except ValueError:
                                pass
                            else:
                                contract_errors.append(f"net_settlement_batch([], fee_bps={bad_bps!r}) did not raise ValueError")

                    # Subtractive removal check across fees.py, audit.py, cli.py
                    sig = inspect.signature(calc_fee)
                    if "allow_legacy_float" in sig.parameters:
                        removal_errors.append("calculate_fee_cents still accepts allow_legacy_float parameter")
                    for param in sig.parameters.values():
                        if param.kind == inspect.Parameter.VAR_KEYWORD:
                            removal_errors.append("calculate_fee_cents retains **kwargs compatibility shim")
                    try:
                        calc_fee(1000, 100, allow_legacy_float=False)
                    except TypeError:
                        pass
                    else:
                        removal_errors.append("calculate_fee_cents(..., allow_legacy_float=False) did not raise TypeError")

                    for rel in ("fees.py", "audit.py", "cli.py", "settlement.py", "reporting.py"):
                        if _has_allow_legacy_ref(parsed_files[rel][1]):
                            removal_errors.append(f"{rel} still references allow_legacy_float")
    except Exception as exc:
        contract_errors.append(f"runtime load/execution failed: {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "cross_module_contract",
            not contract_errors,
            "fees, settlement, reporting, audit, cli, and batch penny-conservation contracts passed"
            if not contract_errors
            else "; ".join(contract_errors),
        )
    )

    if stage == 2:
        checks.append(
            make_check(
                "subtractive_removal",
                not removal_errors,
                "allow_legacy_float removed from fees.py without **kwargs shim and migrated across all callers"
                if not removal_errors
                else "; ".join(removal_errors),
            )
        )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate m1_ledger workspace for case M1.")
    parser.add_argument("workspace", type=Path, help="Path to workspace root or m1_ledger package directory")
    parser.add_argument("--stage", type=int, choices=(1, 2), default=2, help="Lineage stage to grade (default: 2)")
    args = parser.parse_args(argv)
    return emit_report(grade(args.workspace, stage=args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
