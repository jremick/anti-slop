#!/usr/bin/env python3
"""Automated multi-turn software quality & mutation grader for EV1 (ev1_order_ledger).

Evaluates real compounding software quality across 4 sequential feature/bugfix/refactor turns
with ZERO word-cap checks:
  1. `functional_all_turns`: hidden behavioral tests for Turn 1..stage contracts.
  2. `mutation_test_strength`: stdlib AST mutation testing against candidate's own tests
     (requires baseline tests passing, kill_rate >= 0.65, and 0 STRUCT-TEST-THEATER).
  3. `no_duplicate_code_growth`: 0 STRUCT-DUPLICATE-BLOCK findings across production code.
  4. `no_dead_or_legacy_code`: 0 STRUCT-DEAD-COMPAT findings + clean Stage-4 removal of
     `legacy_flat_fee` (no dead shims or **kwargs pass-throughs).
  5. `no_sprawl_or_god_functions`: 0 STRUCT-GOD-FUNCTION / STRUCT-GOD-FILE findings,
     stdlib-only imports, and production file count <= 8.
  6. `no_silent_failures_or_shortcuts`: 0 silent catches, silent fallbacks, test skips,
     unjustified suppressions, stubs, debug leftovers, or host paths.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path
import sys
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks import evolution  # noqa: E402
from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_non_stdlib_imports,
    load_candidate_package,
    make_check,
)


CASE_ID = "EV1"
PACKAGE_NAME = "ev1_order_ledger"
MIN_MUTATION_KILL_RATE = 0.65
MAX_PROD_FILES = 8
MAX_FUNC_LINES = 65
MAX_FUNC_BRANCHES = 14
MAX_FILE_LINES = 400


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


def _run_hidden_functional_tests(pkg_dir: Path, stage: int) -> tuple[bool, str]:
    failures: list[str] = []
    try:
        with load_candidate_package(pkg_dir.parent, PACKAGE_NAME) as pkg:
            api = sys.modules[f"{PACKAGE_NAME}.api"]
            models = sys.modules[f"{PACKAGE_NAME}.models"]
            pricing = sys.modules[f"{PACKAGE_NAME}.pricing"]

            OrderService = api.OrderService
            LineItem = models.LineItem
            Plan = models.Plan
            ValidationError = models.ValidationError

            # Baseline check
            svc = OrderService()
            svc.register_plan(Plan(plan_id="starter", name="Starter", monthly_cents=1000, tax_bps=825))
            svc.register_plan(Plan(plan_id="pro", name="Pro", monthly_cents=3000, tax_bps=825))
            svc.register_plan(Plan(plan_id="scale", name="Scale", monthly_cents=5001, tax_bps=1000))

            o0 = svc.place_order("acct_base", [LineItem("seat", 1999, 2)], tax_bps=825)
            if (o0.subtotal_cents, o0.tax_cents, o0.total_cents) != (3998, 330, 4328):
                failures.append(f"Baseline order totals mismatch: {(o0.subtotal_cents, o0.tax_cents, o0.total_cents)}")

            # Turn 1: prorated plan upgrades + idempotency
            if stage >= 1:
                if not hasattr(svc, "upgrade_subscription"):
                    failures.append("Turn 1: missing OrderService.upgrade_subscription")
                else:
                    sub = svc.start_subscription("acct_u1", "starter")
                    # (3000 - 1000) * 15 / 30 = 1000; tax @ 825 bps = 82.5 -> 83 (half-up)
                    e1 = svc.upgrade_subscription(
                        sub.subscription_id, "pro", 15, 30, idempotency_key="upg-1"
                    )
                    if (e1.subtotal_cents, e1.tax_cents, e1.total_cents) != (1000, 83, 1083):
                        failures.append(
                            f"Turn 1: upgrade proration/tax mismatch: {(e1.subtotal_cents, e1.tax_cents, e1.total_cents)} != (1000, 83, 1083)"
                        )
                    if svc.ledger.get_subscription(sub.subscription_id).plan_id != "pro":
                        failures.append("Turn 1: subscription plan_id not updated to 'pro'")

                    # Half-up check on fractional cent: (5001 - 3000) * 1 / 2 = 1000.5 -> 1001
                    e_half = svc.upgrade_subscription(
                        sub.subscription_id, "scale", 1, 2, idempotency_key="upg-half"
                    )
                    if e_half.subtotal_cents != 1001:
                        failures.append(f"Turn 1: half-up proration expected 1001, got {e_half.subtotal_cents}")

                    # Idempotent replay returns exact same entry without double charging.
                    count_before = len(svc.ledger.entries_for_account("acct_u1"))
                    e1_replay = svc.upgrade_subscription(
                        sub.subscription_id, "pro", 15, 30, idempotency_key="upg-1"
                    )
                    count_after = len(svc.ledger.entries_for_account("acct_u1"))
                    if e1_replay.entry_id != e1.entry_id or count_after != count_before:
                        failures.append("Turn 1: idempotent replay created duplicate entry or mismatched entry_id")

                    # Conflicting params with same idempotency_key must fail closed.
                    try:
                        svc.upgrade_subscription(
                            sub.subscription_id, "scale", 10, 30, idempotency_key="upg-1"
                        )
                        failures.append("Turn 1: conflicting idempotency_key did not raise ValidationError")
                    except ValidationError:
                        pass

                    # Invalid bounds & downgrades must raise ValidationError.
                    sub2 = svc.start_subscription("acct_u2", "pro")
                    for bad_args in (
                        (sub2.subscription_id, "starter", 10, 30, "bad-down"),
                        (sub2.subscription_id, "scale", -1, 30, "bad-neg"),
                        (sub2.subscription_id, "scale", 31, 30, "bad-gt"),
                        (sub2.subscription_id, "scale", 5, 0, "bad-zero"),
                        (sub2.subscription_id, "scale", 5, 30, ""),
                    ):
                        try:
                            svc.upgrade_subscription(
                                bad_args[0], bad_args[1], bad_args[2], bad_args[3],
                                idempotency_key=bad_args[4],
                            )
                            failures.append(f"Turn 1: invalid upgrade {bad_args} did not raise ValidationError")
                        except ValidationError:
                            pass

            # Turn 2: Promo codes across orders AND upgrades (no silent fallback on invalid promos)
            if stage >= 2:
                if not hasattr(svc, "register_promo"):
                    failures.append("Turn 2: missing OrderService.register_promo")
                else:
                    svc.register_promo("SAVE20", percent_off=20, expires_on="2026-12-31", min_subtotal_cents=1000)
                    svc.register_promo("FLAT500", amount_off_cents=500, expires_on="2026-11-01")

                    # Valid percent promo on order: 2500 - 500 = 2000; tax 10% = 200; total = 2200.
                    o_promo = svc.place_order(
                        "acct_p1",
                        [LineItem("sku", 2500, 1)],
                        tax_bps=1000,
                        promo_code="SAVE20",
                        as_of="2026-11-20",
                    )
                    if (o_promo.subtotal_cents, o_promo.discount_cents, o_promo.tax_cents, o_promo.total_cents) != (2000, 500, 200, 2200):
                        failures.append(
                            f"Turn 2: order promo totals mismatch: {(o_promo.subtotal_cents, o_promo.discount_cents, o_promo.tax_cents, o_promo.total_cents)}"
                        )

                    # Valid promo on subscription upgrade: (3000-1000)*15/30 = 1000 -> -20% = 800; tax @ 825 bps = 66; total = 866.
                    sub_p = svc.start_subscription("acct_p2", "starter")
                    e_promo = svc.upgrade_subscription(
                        sub_p.subscription_id, "pro", 15, 30,
                        idempotency_key="upg-promo-1",
                        promo_code="SAVE20",
                        as_of="2026-11-20",
                    )
                    if (e_promo.subtotal_cents, e_promo.tax_cents, e_promo.total_cents) != (800, 66, 866):
                        failures.append(
                            f"Turn 2: upgrade promo totals mismatch: {(e_promo.subtotal_cents, e_promo.tax_cents, e_promo.total_cents)} != (800, 66, 866)"
                        )

                    # Reject expired, missing as_of on expiring promo, unknown, stacked, and below-minimum promos.
                    bad_promo_calls = [
                        ("expired", dict(promo_code="FLAT500", as_of="2026-11-02")),
                        ("missing_as_of", dict(promo_code="SAVE20", as_of=None)),
                        ("unknown", dict(promo_code="NOPE", as_of="2026-11-20")),
                        ("stacked", dict(promo_code="SAVE20,FLAT500", as_of="2026-10-01")),
                    ]
                    for label, kw in bad_promo_calls:
                        try:
                            svc.place_order("acct_p_err", [LineItem("sku", 2000, 1)], tax_bps=1000, **kw)
                            failures.append(f"Turn 2: {label} promo did not raise ValidationError")
                        except ValidationError:
                            pass
                    try:
                        svc.place_order(
                            "acct_p_min", [LineItem("sku", 500, 1)],
                            tax_bps=1000, promo_code="SAVE20", as_of="2026-11-20",
                        )
                        failures.append("Turn 2: below min_subtotal_cents promo did not raise ValidationError")
                    except ValidationError:
                        pass

            # Turn 3: Partial refunds with exact penny conservation + credit note export
            if stage >= 3:
                if not hasattr(svc, "refund_order") or not hasattr(svc, "export_credit_note"):
                    failures.append("Turn 3: missing refund_order or export_credit_note on OrderService")
                else:
                    # Order: 1000 subtotal, 825 bps -> 83 tax, 1083 total.
                    o_ref = svc.place_order("acct_r1", [LineItem("sku", 1000, 1)], tax_bps=825)
                    r1 = svc.refund_order(o_ref.order_id, 361, reason="part 1", idempotency_key="ref-1")
                    r2 = svc.refund_order(o_ref.order_id, 361, reason="part 2", idempotency_key="ref-2")
                    r3 = svc.refund_order(o_ref.order_id, 361, reason="part 3", idempotency_key="ref-3")
                    for idx_r, r in enumerate((r1, r2, r3), start=1):
                        if r.subtotal_cents + r.tax_cents != r.total_cents or r.total_cents != -361:
                            failures.append(f"Turn 3: refund {idx_r} conservation violated: {r}")

                    sum_tax = -(r1.tax_cents + r2.tax_cents + r3.tax_cents)
                    sum_sub = -(r1.subtotal_cents + r2.subtotal_cents + r3.subtotal_cents)
                    if sum_tax != o_ref.tax_cents or sum_sub != o_ref.subtotal_cents:
                        failures.append(
                            f"Turn 3: multi-chunk refund drift: tax={sum_tax}/{o_ref.tax_cents}, sub={sum_sub}/{o_ref.subtotal_cents}"
                        )
                    if svc.ledger.account_balance_cents("acct_r1") != 0:
                        failures.append(
                            f"Turn 3: fully refunded account balance expected 0, got {svc.ledger.account_balance_cents('acct_r1')}"
                        )

                    # Over-refund rejected.
                    try:
                        svc.refund_order(o_ref.order_id, 1, reason="over", idempotency_key="ref-over")
                        failures.append("Turn 3: over-refund did not raise ValidationError")
                    except ValidationError:
                        pass

                    # Idempotency replay & conflict.
                    r1_replay = svc.refund_order(o_ref.order_id, 361, reason="part 1", idempotency_key="ref-1")
                    if r1_replay.entry_id != r1.entry_id:
                        failures.append("Turn 3: refund idempotency replay returned different entry_id")
                    try:
                        svc.refund_order(o_ref.order_id, 100, reason="part 1", idempotency_key="ref-1")
                        failures.append("Turn 3: conflicting refund idempotency_key did not raise ValidationError")
                    except ValidationError:
                        pass

                    # Credit note export.
                    cn = svc.export_credit_note(r1.entry_id)
                    required_keys = {"entry_id", "order_id", "account_id", "subtotal_cents", "tax_cents", "total_cents", "reason"}
                    if not required_keys.issubset(set(cn.keys())):
                        failures.append(f"Turn 3: credit note missing keys: {required_keys - set(cn.keys())}")
                    elif (cn["total_cents"], cn["subtotal_cents"] + cn["tax_cents"], cn["order_id"]) != (361, 361, o_ref.order_id):
                        failures.append(f"Turn 3: credit note values invalid: {cn}")

                    try:
                        svc.export_credit_note("ent_nonexistent")
                        failures.append("Turn 3: export_credit_note on unknown id did not raise ValidationError")
                    except ValidationError:
                        pass

            # Turn 4: Subtractive removal of legacy_flat_fee + fail-closed audit_sink
            if stage >= 4:
                try:
                    pricing.calculate_order_totals([LineItem("x", 100, 1)], legacy_flat_fee=True)
                    failures.append("Turn 4: calculate_order_totals still accepts legacy_flat_fee")
                except TypeError:
                    pass
                try:
                    svc.place_order("acct_leg", [LineItem("x", 100, 1)], legacy_flat_fee=True)
                    failures.append("Turn 4: place_order still accepts legacy_flat_fee")
                except TypeError:
                    pass

                # Audit sink captures events on order, upgrade, and refund (skipping idempotent replays).
                events: list[dict[str, Any]] = []
                svc_aud = OrderService(audit_sink=events.append)
                svc_aud.register_plan(Plan(plan_id="starter", name="Starter", monthly_cents=1000, tax_bps=0))
                svc_aud.register_plan(Plan(plan_id="pro", name="Pro", monthly_cents=2000, tax_bps=0))
                o_a = svc_aud.place_order("acct_a", [LineItem("x", 500, 1)])
                sub_a = svc_aud.start_subscription("acct_a", "starter")
                svc_aud.upgrade_subscription(sub_a.subscription_id, "pro", 15, 30, idempotency_key="aud-upg")
                svc_aud.upgrade_subscription(sub_a.subscription_id, "pro", 15, 30, idempotency_key="aud-upg")
                svc_aud.refund_order(o_a.order_id, 200, reason="adj", idempotency_key="aud-ref")
                svc_aud.refund_order(o_a.order_id, 200, reason="adj", idempotency_key="aud-ref")
                if len(events) != 3:
                    failures.append(f"Turn 4: expected 3 audit events (skipping replays), got {len(events)}: {events}")
                else:
                    for ev in events:
                        if not {"action", "account_id", "amount_cents", "entry_id"}.issubset(set(ev.keys())):
                            failures.append(f"Turn 4: audit event missing required fields: {ev}")

                # Fail-closed audit sink: exception propagates and does NOT persist order, upgrade, or refund!
                fail_flag = {"boom": False}

                def _conditional_boom(_ev: dict[str, Any]) -> None:
                    if fail_flag["boom"]:
                        raise RuntimeError("audit sink offline")

                svc_fail = OrderService(audit_sink=_conditional_boom)
                svc_fail.register_plan(Plan(plan_id="starter", name="Starter", monthly_cents=1000, tax_bps=0))
                svc_fail.register_plan(Plan(plan_id="pro", name="Pro", monthly_cents=2000, tax_bps=0))
                base_ord = svc_fail.place_order("acct_seed", [LineItem("x", 500, 1)])
                base_sub = svc_fail.start_subscription("acct_seed", "starter")
                seed_entries_before = len(svc_fail.ledger.entries_for_account("acct_seed"))

                fail_flag["boom"] = True
                try:
                    svc_fail.place_order("acct_fail", [LineItem("x", 500, 1)])
                    failures.append("Turn 4: failing audit_sink on place_order was silently swallowed")
                except RuntimeError:
                    pass
                if svc_fail.ledger.entries_for_account("acct_fail"):
                    failures.append("Turn 4: failed audit_sink on place_order still committed ledger entry")

                try:
                    svc_fail.upgrade_subscription(
                        base_sub.subscription_id, "pro", 15, 30, idempotency_key="fail-upg"
                    )
                    failures.append("Turn 4: failing audit_sink on upgrade_subscription was silently swallowed")
                except RuntimeError:
                    pass
                if svc_fail.ledger.get_subscription(base_sub.subscription_id).plan_id != "starter":
                    failures.append("Turn 4: failed audit_sink on upgrade_subscription still mutated subscription.plan_id")
                if len(svc_fail.ledger.entries_for_account("acct_seed")) != seed_entries_before:
                    failures.append("Turn 4: failed audit_sink on upgrade_subscription still committed ledger entry")

                try:
                    svc_fail.refund_order(base_ord.order_id, 100, reason="adj", idempotency_key="fail-ref")
                    failures.append("Turn 4: failing audit_sink on refund_order was silently swallowed")
                except RuntimeError:
                    pass
                if len(svc_fail.ledger.entries_for_account("acct_seed")) != seed_entries_before:
                    failures.append("Turn 4: failed audit_sink on refund_order still committed ledger entry")

    except Exception as exc:  # pragma: no cover - defensive report boundary
        failures.append(f"Unhandled exception while loading/running candidate: {type(exc).__name__}: {exc}")

    if failures:
        return False, "; ".join(failures[:6])
    return True, f"All hidden functional contracts passed through stage {stage}"


def _check_stage4_legacy_removal(pkg_dir: Path) -> list[str]:
    issues: list[str] = []
    for py_path in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in py_path.parts:
            continue
        rel = str(py_path.relative_to(pkg_dir)).replace("\\", "/")
        if rel.startswith("tests/") or "/tests/" in rel:
            continue
        text = py_path.read_text(encoding="utf-8")
        if "legacy_flat_fee" in text or "LEGACY_FLAT_FEE" in text:
            issues.append(f"{rel} still references legacy_flat_fee")
        if rel in ("pricing.py", "api.py"):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name in ("calculate_order_totals", "place_order"):
                    if node.args.kwarg is not None:
                        issues.append(f"{rel}:{node.lineno} {node.name} uses **{node.args.kwarg.arg} shim")
    return issues


def grade(
    workspace: Path | str,
    *,
    stage: int = 4,
    max_mutants: int = 20,
) -> dict[str, Any]:
    pkg_dir = _resolve_package_dir(Path(workspace).resolve())
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("functional_all_turns", False, f"Could not locate {PACKAGE_NAME}/ under {workspace}")],
        )

    # 1. Functional correctness across Turn 1..stage.
    func_ok, func_detail = _run_hidden_functional_tests(pkg_dir, stage)

    # 2. Measure full workspace quality + AST mutation testing across ALL production modules.
    test_cmd = [sys.executable, "-B", "run_checks.py"]
    quality = evolution.measure_workspace_quality(
        pkg_dir,
        test_cmd=test_cmd,
        mutate_files=None,
        max_mutants=max_mutants,
        max_func_lines=MAX_FUNC_LINES,
        max_func_branches=MAX_FUNC_BRANCHES,
        max_file_lines=MAX_FILE_LINES,
    )

    counts = quality["counts"]
    mut = quality["mutation_testing"] or {}

    # Check 2: Mutation test strength + zero test theater.
    mut_kill_rate = float(mut.get("kill_rate", 0.0))
    mut_total = int(mut.get("total", 0))
    mut_base_ok = bool(mut.get("baseline_tests_passed", False))
    theater_count = counts["test_theater"]
    mut_ok = mut_base_ok and mut_total >= 5 and mut_kill_rate >= MIN_MUTATION_KILL_RATE and theater_count == 0
    mut_detail = (
        f"baseline_tests_passed={mut_base_ok}, killed={mut.get('killed', 0)}/{mut_total} "
        f"({mut_kill_rate:.1%}, min {MIN_MUTATION_KILL_RATE:.0%}), test_theater={theater_count}"
    )
    if mut.get("survived_mutants"):
        mut_detail += f"; survived sample: {mut['survived_mutants'][:3]}"

    # Check 3: Duplicate code growth.
    dup_count = counts["duplicate_blocks"]
    dup_ok = dup_count == 0
    dup_detail = (
        "0 duplicated logic blocks across production modules"
        if dup_ok
        else f"{dup_count} duplicate block(s): " + "; ".join(f["message"] for f in quality["findings"]["duplicate_blocks"][:3])
    )

    # Check 4: Dead / orphaned compatibility code + Stage-4 legacy removal.
    dead_count = counts["dead_compat"]
    stage4_issues = _check_stage4_legacy_removal(pkg_dir) if stage >= 4 else []
    dead_ok = dead_count == 0 and not stage4_issues
    dead_parts: list[str] = []
    if dead_count:
        dead_parts.extend(f["message"] for f in quality["findings"]["dead_compat"][:3])
    dead_parts.extend(stage4_issues[:3])
    dead_detail = "0 dead/orphaned compat paths" + (" and clean legacy_flat_fee removal" if stage >= 4 else "")
    if not dead_ok:
        dead_detail = "; ".join(dead_parts)

    # Check 5: Sprawl & god-function / god-file / stdlib-only check.
    local_mod_stems = {PACKAGE_NAME} | {
        p.stem for p in pkg_dir.rglob("*.py") if "__pycache__" not in p.parts
    }
    stdlib_issues: list[str] = []
    for py_file in sorted(pkg_dir.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        src = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError as exc:
            stdlib_issues.append(f"{py_file.name}: SyntaxError {exc}")
            continue
        bad_imp = find_non_stdlib_imports(
            tree,
            allowed_packages=local_mod_stems,
            allow_relative=True,
        )
        if bad_imp:
            stdlib_issues.append(f"{py_file.name}: non-stdlib imports {bad_imp}")

    sprawl_ok = (
        counts["god_functions"] == 0
        and counts["god_files"] == 0
        and quality["prod_files_count"] <= MAX_PROD_FILES
        and not stdlib_issues
    )
    sprawl_detail = (
        f"prod_files={quality['prod_files_count']}/{MAX_PROD_FILES}, "
        f"max_func={quality['max_func_lines']}L/{quality['max_func_branches']}br, "
        f"god_fns={counts['god_functions']}, god_files={counts['god_files']}"
    )
    if stdlib_issues:
        sprawl_detail += "; " + "; ".join(stdlib_issues[:3])

    # Check 6: Silent failures and shortcuts.
    silent_count = counts["silent_failures_and_shortcuts"]
    silent_ok = silent_count == 0
    silent_detail = (
        "0 silent catches, silent fallbacks, test skips, suppressions, or stubs"
        if silent_ok
        else f"{silent_count} shortcut/silent-failure finding(s): "
        + "; ".join(f["message"] for f in quality["findings"]["silent_failures_and_shortcuts"][:3])
    )

    checks = [
        make_check("functional_all_turns", func_ok, func_detail),
        make_check("mutation_test_strength", mut_ok, mut_detail),
        make_check("no_duplicate_code_growth", dup_ok, dup_detail),
        make_check("no_dead_or_legacy_code", dead_ok, dead_detail),
        make_check("no_sprawl_or_god_functions", sprawl_ok, sprawl_detail),
        make_check("no_silent_failures_or_shortcuts", silent_ok, silent_detail),
    ]
    report = build_report(CASE_ID, checks)
    report["metrics"] = {
        "functional_passed": func_ok,
        "mutation_kill_rate": mut_kill_rate,
        "mutation_killed": int(mut.get("killed", 0)),
        "mutation_total": mut_total,
        "duplicate_blocks": dup_count,
        "dead_compat": dead_count + len(stage4_issues),
        "god_functions": counts["god_functions"],
        "god_files": counts["god_files"],
        "test_theater": theater_count,
        "silent_failures_and_shortcuts": silent_count,
        "prod_files_count": quality["prod_files_count"],
        "prod_code_lines": quality["prod_code_lines"],
        "max_func_lines": quality["max_func_lines"],
        "max_func_branches": quality["max_func_branches"],
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade EV1 multi-turn evolution workspace.")
    parser.add_argument("workspace", help="Path to candidate workspace containing ev1_order_ledger/.")
    parser.add_argument("--stage", type=int, default=4, choices=(1, 2, 3, 4))
    parser.add_argument("--max-mutants", type=int, default=20)
    args = parser.parse_args(argv)
    report = grade(args.workspace, stage=args.stage, max_mutants=args.max_mutants)
    return emit_report(report)


if __name__ == "__main__":
    raise SystemExit(main())
