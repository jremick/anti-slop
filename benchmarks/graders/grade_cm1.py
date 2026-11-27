#!/usr/bin/env python3
"""100% deterministic automated grader for CM1 (controlled comment-hygiene ablation).

Grades any of the three identical-AST sibling variants (`no_comments`,
`invariant_comments`, `comment_traps`) on four mechanical checks:
  1. `feature_and_idempotency_verified`: `invoice.payment_failed` works and retries
     of both `invoice.paid` and `invoice.payment_failed` are idempotent.
  2. `out_of_order_invariant_preserved`: stale events (`created_at < last_event_at`)
     are ignored without rolling back newer subscription state, while equal timestamps
     apply normally.
  3. `integer_cent_precision_preserved`: exact integer half-up cent arithmetic is
     preserved across half-cent boundaries and >2^53 integers (catches float traps).
  4. `commented_code_cleaned_and_readonly_intact`: read-only tests/runner remain
     byte-identical, stdlib-only imports, zero stubs/silent catches, and zero
     multi-line commented-out code blocks remain (single-line invariant comments OK).
"""

from __future__ import annotations

import argparse
import ast
import io
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tokenize
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from benchmarks.graders import (  # noqa: E402
    build_report,
    emit_report,
    find_broad_excepts,
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    load_candidate_package,
    make_check,
    parse_candidate_ast,
    sha256_file,
)


CASE_ID = "CM1"
FIXTURE_ROOT_NAME = "cm1_comment_ablation"
VALID_VARIANTS: tuple[str, ...] = ("no_comments", "invariant_comments", "comment_traps")
DEFAULT_VARIANT = "comment_traps"

READONLY_SHA256: dict[str, str] = {
    "run_checks.py": "d1edc6bceecd4c351699de6d53659875fd6d4c595a156196777f7f971a9ae873",
    "tests/__init__.py": "02c7b83b5161ccde3ec5fc59e6a0828556d76b167dff9d98dfe048bb0be10aed",
    "tests/test_webhooks.py": "06670b233475143c660b60ab8a5ffad9cf07d538a8e771d5fe9f68d7ba89020b",
}

EXPECTED_FILES: tuple[str, ...] = (
    "__init__.py",
    "models.py",
    "webhooks.py",
    "run_checks.py",
    "tests/__init__.py",
    "tests/test_webhooks.py",
)

_PY_CODE_LINE_RE = re.compile(
    r"^(?:"
    r"(?:async\s+)?def\s+[A-Za-z_]\w*\s*\(|"
    r"class\s+[A-Za-z_]\w*\b|"
    r"(?:if|elif|while)\s+.+:\s*$|"
    r"(?:else|try|finally)\s*:\s*$|"
    r"except\b.*:\s*$|"
    r"(?:async\s+)?for\s+.+\bin\b.+:\s*$|"
    r"(?:async\s+)?with\s+.+:\s*$|"
    r"return(?:\s+.+)?$|"
    r"raise\s+[A-Za-z_]\w*|"
    r"(?:from\s+[\w.]+\s+)?import\s+[A-Za-z_]\w*|"
    r"@[A-Za-z_][\w.]*(?:\(|$)|"
    r"[A-Za-z_][\w.]*\s*(?:\+=|-=|\*=|//=|/=|=)\s*[^=]|"
    r"[A-Za-z_][\w.]*\s*\([^)]*\)\s*$"
    r")"
)
_PROSE_PREFIX_RE = re.compile(r"^(?:INVARIANT|NOTE|WHY|WARNING|CAUTION|FIXME|TODO)\s*:", re.IGNORECASE)


def find_commented_out_code_blocks(source: str, *, min_lines: int = 3) -> list[dict[str, Any]]:
    """Detect contiguous runs of >= min_lines comment-only lines containing Python code."""
    lines = source.splitlines()
    comment_only_lines: list[tuple[int, str]] = []
    try:
        for tok_type, tok_str, (lineno, col), _, _ in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok_type != tokenize.COMMENT:
                continue
            if 1 <= lineno <= len(lines) and lines[lineno - 1][:col].strip() == "":
                body = tok_str.lstrip("#").strip()
                comment_only_lines.append((lineno, body))
    except (tokenize.TokenError, IndentationError):
        return []

    blocks: list[dict[str, Any]] = []
    run: list[tuple[int, str]] = []

    def _flush(seq: list[tuple[int, str]]) -> None:
        if len(seq) >= min_lines:
            blocks.append({
                "start_line": seq[0][0],
                "end_line": seq[-1][0],
                "line_count": len(seq),
                "preview": seq[0][1][:80],
            })

    for lineno, body in comment_only_lines:
        is_code = bool(body) and not _PROSE_PREFIX_RE.match(body) and bool(_PY_CODE_LINE_RE.match(body))
        if is_code and (not run or lineno == run[-1][0] + 1):
            run.append((lineno, body))
        else:
            _flush(run)
            run = [(lineno, body)] if is_code else []
    _flush(run)
    return blocks


def count_comments(source: str) -> list[tuple[int, str]]:
    """Return all Python `# ...` comments as (lineno, text) tuples."""
    out: list[tuple[int, str]] = []
    for tok_type, tok_str, (lineno, _), _, _ in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok_type == tokenize.COMMENT:
            out.append((lineno, tok_str))
    return out


def _resolve_variant_dir(workspace: Path, variant: str) -> Path | None:
    candidates = [
        workspace / "benchmarks" / "sources" / FIXTURE_ROOT_NAME / variant,
        workspace / FIXTURE_ROOT_NAME / variant,
        workspace / variant,
        workspace,
    ]
    for cand in candidates:
        if cand.is_dir() and (cand / "webhooks.py").is_file() and (cand / "models.py").is_file():
            return cand
    return None


def prepare_variant_workspace(
    variant: str,
    dest_dir: str | Path,
    *,
    repo_root: str | Path = _REPO_ROOT,
) -> Path:
    """Copy one CM1 ablation variant into an isolated workspace directory."""
    if variant not in VALID_VARIANTS:
        raise ValueError(f"Unsupported CM1 variant {variant!r}; expected one of {', '.join(VALID_VARIANTS)}.")
    src_dir = Path(repo_root).resolve() / "benchmarks" / "sources" / FIXTURE_ROOT_NAME / variant
    if not src_dir.is_dir():
        raise FileNotFoundError(f"CM1 variant directory not found: {src_dir}")
    target = Path(dest_dir).resolve() / variant
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        src_dir,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return target


def verify_ablation_fixtures(repo_root: str | Path = _REPO_ROOT) -> dict[str, Any]:
    """Verify all 3 CM1 variants have 100% identical executable ASTs and expected comment profiles."""
    base = Path(repo_root).resolve() / "benchmarks" / "sources" / FIXTURE_ROOT_NAME
    errors: list[str] = []
    ast_dumps: dict[str, str] = {}
    comment_counts: dict[str, int] = {}
    code_block_counts: dict[str, int] = {}

    for variant in VALID_VARIANTS:
        vdir = base / variant
        if not vdir.is_dir():
            errors.append(f"Missing variant directory: {variant}")
            continue
        for rel in EXPECTED_FILES:
            if not (vdir / rel).is_file():
                errors.append(f"{variant}: missing expected file {rel}")
        for rel, expected_sha in READONLY_SHA256.items():
            p = vdir / rel
            if p.is_file() and sha256_file(p) != expected_sha:
                errors.append(f"{variant}/{rel}: SHA-256 mismatch with shared read-only fixture")

        wh_path = vdir / "webhooks.py"
        if wh_path.is_file():
            src, tree = parse_candidate_ast(wh_path)
            ast_dumps[variant] = ast.dump(tree, include_attributes=False)
            comments = count_comments(src)
            blocks = find_commented_out_code_blocks(src)
            comment_counts[variant] = len(comments)
            code_block_counts[variant] = len(blocks)
            if variant == "no_comments" and comments:
                errors.append(f"no_comments/webhooks.py must have 0 comments, found {len(comments)}")
            elif variant == "invariant_comments":
                inv_lines = [txt for _, txt in comments if "# INVARIANT:" in txt]
                if len(inv_lines) != 3 or len(comments) != 3:
                    errors.append(
                        f"invariant_comments/webhooks.py expected exactly 3 '# INVARIANT:' comments, "
                        f"found {len(inv_lines)} invariant / {len(comments)} total"
                    )
                if blocks:
                    errors.append(f"invariant_comments/webhooks.py must have 0 commented-out code blocks, found {len(blocks)}")
            elif variant == "comment_traps":
                if len(blocks) < 2:
                    errors.append(
                        f"comment_traps/webhooks.py expected >= 2 commented-out code blocks, found {len(blocks)}"
                    )

    if len(ast_dumps) == len(VALID_VARIANTS):
        ref_ast = ast_dumps["no_comments"]
        for variant in VALID_VARIANTS[1:]:
            if ast_dumps[variant] != ref_ast:
                errors.append(f"{variant}/webhooks.py executable AST differs from no_comments/webhooks.py")

    # Also verify shared models.py and __init__.py are byte-identical across all 3 variants.
    for shared_rel in ("__init__.py", "models.py"):
        shas = {
            v: sha256_file(base / v / shared_rel)
            for v in VALID_VARIANTS
            if (base / v / shared_rel).is_file()
        }
        if len(set(shas.values())) > 1:
            errors.append(f"{shared_rel} differs across variants: {shas}")

    return {
        "ok": not errors,
        "variants": list(VALID_VARIANTS),
        "identical_executable_ast": len(ast_dumps) == len(VALID_VARIANTS) and len(set(ast_dumps.values())) == 1,
        "comment_counts": comment_counts,
        "commented_code_blocks": code_block_counts,
        "errors": errors,
    }


def grade(
    workspace_path: str | Path,
    *,
    variant: str = DEFAULT_VARIANT,
) -> dict[str, Any]:
    """Mechanically grade a CM1 candidate workspace for the requested variant."""
    if variant not in VALID_VARIANTS:
        return build_report(
            CASE_ID,
            [make_check("variant", False, f"unsupported variant {variant!r}; expected {', '.join(VALID_VARIANTS)}")],
        )

    ws_path = Path(workspace_path)
    pkg_dir = _resolve_variant_dir(ws_path, variant)
    if pkg_dir is None:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"could not locate CM1 variant '{variant}' under {workspace_path}")],
        )

    missing_files = [rel for rel in EXPECTED_FILES if not (pkg_dir / rel).is_file()]
    if missing_files:
        return build_report(
            CASE_ID,
            [make_check("load", False, f"missing expected files: {', '.join(missing_files)}")],
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

    # Check 4 (static & read-only hygiene) can be gathered before executing candidate code,
    # then appended in canonical acceptance_checks order.
    hygiene_errors: list[str] = []
    for rel, expected_sha in READONLY_SHA256.items():
        if sha256_file(pkg_dir / rel) != expected_sha:
            hygiene_errors.append(f"read-only file {rel} was modified")

    allowed_local = {"models", "webhooks", pkg_dir.name, "cm1_candidate_pkg"}
    for rel, (source, tree) in sorted(parsed_files.items()):
        bad_imports = find_non_stdlib_imports(tree, allowed_packages=allowed_local, allow_relative=True)
        if bad_imports:
            hygiene_errors.append(f"{rel}: non-stdlib imports {', '.join(bad_imports)}")
        if rel not in READONLY_SHA256:
            for issue in find_stub_or_placeholder_issues(source, tree):
                hygiene_errors.append(f"{rel}: {issue}")
            for issue in find_broad_excepts(tree, rel):
                hygiene_errors.append(issue)

    webhooks_source, _ = parsed_files["webhooks.py"]
    commented_blocks = find_commented_out_code_blocks(webhooks_source)
    for blk in commented_blocks:
        hygiene_errors.append(
            f"webhooks.py:{blk['start_line']}-{blk['end_line']} still contains commented-out code block "
            f"({blk['line_count']} lines: '{blk['preview']}')"
        )

    feature_errors: list[str] = []
    ordering_errors: list[str] = []
    precision_errors: list[str] = []

    try:
        with tempfile.TemporaryDirectory(prefix="cm1_eval_") as tmp_dir:
            eval_pkg = Path(tmp_dir) / "cm1_candidate_pkg"
            shutil.copytree(
                pkg_dir,
                eval_pkg,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            with load_candidate_package(Path(tmp_dir), "cm1_candidate_pkg") as pkg:
                Subscription = pkg.Subscription
                WebhookError = pkg.WebhookError
                WebhookEvent = pkg.WebhookEvent
                WebhookProcessor = pkg.WebhookProcessor
                compute_fee_cents = pkg.compute_fee_cents

                # --- Check 1: invoice.payment_failed feature + idempotent retries ---
                proc = WebhookProcessor()
                proc.register_subscription(
                    Subscription("sub_f1", "acct_1", status="past_due", balance_due_cents=5000, failed_attempts=2)
                )
                paid_ev = WebhookEvent(
                    event_id="evt_p_1",
                    event_type="invoice.paid",
                    subscription_id="sub_f1",
                    created_at=100,
                    amount_cents=2000,
                    fee_bps=300,
                )
                r_paid = proc.handle_event(paid_ev)
                if not (
                    r_paid.get("applied") is True
                    and r_paid.get("fee_cents") == 60
                    and r_paid.get("balance_due_cents") == 3000
                    and r_paid.get("subscription_status") == "active"
                    and r_paid.get("failed_attempts") == 0
                ):
                    feature_errors.append(f"invoice.paid unexpected result: {r_paid!r}")

                r_paid_retry = proc.handle_event(paid_ev)
                if not (
                    r_paid_retry.get("applied") is False
                    and r_paid_retry.get("reason") == "duplicate"
                    and r_paid_retry.get("balance_due_cents") == 3000
                ):
                    feature_errors.append(f"invoice.paid duplicate retry failed: {r_paid_retry!r}")

                fail_ev1 = WebhookEvent(
                    event_id="evt_f_1",
                    event_type="invoice.payment_failed",
                    subscription_id="sub_f1",
                    created_at=200,
                    amount_cents=1000,
                    fee_bps=300,
                )
                r_fail1 = proc.handle_event(fail_ev1)
                if not (
                    r_fail1.get("applied") is True
                    and r_fail1.get("reason") == "applied"
                    and r_fail1.get("fee_cents") == 30
                    and r_fail1.get("subscription_status") == "past_due"
                    and r_fail1.get("balance_due_cents") == 4030
                    and r_fail1.get("failed_attempts") == 1
                ):
                    feature_errors.append(f"invoice.payment_failed first event unexpected: {r_fail1!r}")

                r_fail1_retry = proc.handle_event(fail_ev1)
                if not (
                    r_fail1_retry.get("applied") is False
                    and r_fail1_retry.get("reason") == "duplicate"
                    and r_fail1_retry.get("balance_due_cents") == 4030
                    and r_fail1_retry.get("failed_attempts") == 1
                ):
                    feature_errors.append(f"invoice.payment_failed duplicate retry failed: {r_fail1_retry!r}")

                # Second distinct failure increments failed_attempts to 2.
                fail_ev2 = WebhookEvent(
                    event_id="evt_f_2",
                    event_type="invoice.payment_failed",
                    subscription_id="sub_f1",
                    created_at=250,
                    amount_cents=500,
                    fee_bps=0,
                )
                r_fail2 = proc.handle_event(fail_ev2)
                if not (
                    r_fail2.get("applied") is True
                    and r_fail2.get("balance_due_cents") == 4530
                    and r_fail2.get("failed_attempts") == 2
                ):
                    feature_errors.append(f"second invoice.payment_failed unexpected: {r_fail2!r}")

                # Invalid inputs still fail closed with WebhookError / ValueError.
                for label, bad_ev in (
                    ("unknown_type", WebhookEvent("evt_bad1", "invoice.voided", "sub_f1", created_at=300)),
                    ("empty_id", WebhookEvent("", "invoice.payment_failed", "sub_f1", created_at=300)),
                    ("unknown_sub", WebhookEvent("evt_bad2", "invoice.payment_failed", "sub_missing", created_at=300)),
                    ("negative_amt", WebhookEvent("evt_bad3", "invoice.payment_failed", "sub_f1", created_at=300, amount_cents=-5)),
                ):
                    try:
                        proc.handle_event(bad_ev)
                    except (WebhookError, ValueError):
                        pass
                    else:
                        feature_errors.append(f"invalid event ({label}) did not raise WebhookError/ValueError")

                # --- Check 2: Out-of-order webhook timestamp invariant ---
                proc_ord = WebhookProcessor()
                proc_ord.register_subscription(
                    Subscription("sub_o1", "acct_o", status="past_due", balance_due_cents=1000, failed_attempts=1)
                )
                proc_ord.handle_event(
                    WebhookEvent("evt_o_paid", "invoice.paid", "sub_o1", created_at=500, amount_cents=1000, fee_bps=0)
                )
                # Stale payment_failed arriving late (created_at=400 < 500) must be ignored!
                stale_fail = proc_ord.handle_event(
                    WebhookEvent("evt_o_stale_fail", "invoice.payment_failed", "sub_o1", created_at=400, amount_cents=1000, fee_bps=300)
                )
                sub_o1 = proc_ord.get_subscription("sub_o1")
                if not (
                    stale_fail.get("applied") is False
                    and stale_fail.get("reason") == "stale_event"
                    and sub_o1.status == "active"
                    and sub_o1.balance_due_cents == 0
                    and sub_o1.failed_attempts == 0
                    and sub_o1.last_event_at == 500
                ):
                    ordering_errors.append(
                        f"stale invoice.payment_failed (400 < 500) corrupted subscription state: "
                        f"res={stale_fail!r}, sub={sub_o1!r}"
                    )

                # Equal timestamp (created_at == 500) with new event_id MUST apply (`>=` invariant).
                eq_fail = proc_ord.handle_event(
                    WebhookEvent("evt_o_eq_fail", "invoice.payment_failed", "sub_o1", created_at=500, amount_cents=200, fee_bps=0)
                )
                if not (
                    eq_fail.get("applied") is True
                    and sub_o1.status == "past_due"
                    and sub_o1.balance_due_cents == 200
                    and sub_o1.failed_attempts == 1
                ):
                    ordering_errors.append(f"equal-timestamp event (500 == 500) failed to apply: {eq_fail!r}")

                # Stale invoice.paid arriving after newer subscription.canceled must NOT resurrect subscription.
                proc_ord.handle_event(
                    WebhookEvent("evt_o_cancel", "subscription.canceled", "sub_o1", created_at=800)
                )
                stale_paid = proc_ord.handle_event(
                    WebhookEvent("evt_o_stale_paid", "invoice.paid", "sub_o1", created_at=700, amount_cents=200)
                )
                if not (
                    stale_paid.get("applied") is False
                    and stale_paid.get("reason") == "stale_event"
                    and proc_ord.get_subscription("sub_o1").status == "canceled"
                ):
                    ordering_errors.append(
                        f"stale invoice.paid (700 < 800) resurrected canceled subscription: {stale_paid!r}"
                    )

                # --- Check 3: Exact integer-cent half-up rounding precision ---
                fee_cases = [
                    (1005, 1000, 101),               # 100.5 -> half-up 101 (catches float truncation & banker's rounding)
                    (1000, 825, 83),                 # 82.5 -> half-up 83 (catches banker's rounding)
                    (100, 290, 3),                   # 100 * (290/10000.0) = 2.8999999999999999 -> catches int() float trap
                    (1, 5000, 1),                    # 0.5 -> 1
                    (333, 150, 5),                   # 4.995 -> 5
                    (0, 290, 0),
                    (10**16 + 1, 10000, 10**16 + 1), # Exceeds IEEE-754 float64 53-bit mantissa!
                ]
                for amt, bps, expected_fee in fee_cases:
                    got_fee = compute_fee_cents(amt, bps)
                    if type(got_fee) is not int or got_fee != expected_fee:
                        precision_errors.append(
                            f"compute_fee_cents({amt}, {bps}) returned {got_fee!r}, expected {expected_fee}"
                        )

                # End-to-end half-cent precision inside invoice.payment_failed (catches inline float trap!)
                proc_prec = WebhookProcessor()
                proc_prec.register_subscription(Subscription("sub_p1", "acct_p", status="active", balance_due_cents=0))
                r_p1 = proc_prec.handle_event(
                    WebhookEvent("evt_prec_1", "invoice.payment_failed", "sub_p1", created_at=10, amount_cents=1005, fee_bps=1000)
                )
                if type(r_p1.get("fee_cents")) is not int or r_p1.get("fee_cents") != 101 or r_p1.get("balance_due_cents") != 1106:
                    precision_errors.append(
                        f"invoice.payment_failed(1005, 1000bps) lost precision: fee={r_p1.get('fee_cents')!r}, "
                        f"balance={r_p1.get('balance_due_cents')!r} (expected fee=101, balance=1106)"
                    )

                r_p2 = proc_prec.handle_event(
                    WebhookEvent("evt_prec_2", "invoice.payment_failed", "sub_p1", created_at=20, amount_cents=100, fee_bps=290)
                )
                if type(r_p2.get("fee_cents")) is not int or r_p2.get("fee_cents") != 3 or r_p2.get("balance_due_cents") != 1209:
                    precision_errors.append(
                        f"invoice.payment_failed(100, 290bps) lost float precision: fee={r_p2.get('fee_cents')!r}, "
                        f"balance={r_p2.get('balance_due_cents')!r} (expected fee=3, balance=1209)"
                    )
    except Exception as exc:
        msg = f"runtime error loading/executing candidate package: {type(exc).__name__}: {exc}"
        feature_errors.append(msg)
        ordering_errors.append(msg)
        precision_errors.append(msg)

    checks.append(
        make_check(
            "feature_and_idempotency_verified",
            not feature_errors,
            "invoice.payment_failed and idempotent retries verified across valid and invalid inputs"
            if not feature_errors
            else "; ".join(feature_errors),
        )
    )
    checks.append(
        make_check(
            "out_of_order_invariant_preserved",
            not ordering_errors,
            "stale out-of-order webhooks ignored and equal-timestamp webhooks applied cleanly"
            if not ordering_errors
            else "; ".join(ordering_errors),
        )
    )
    checks.append(
        make_check(
            "integer_cent_precision_preserved",
            not precision_errors,
            "exact integer half-up cent math verified across half-cent boundaries and >2^53 integers"
            if not precision_errors
            else "; ".join(precision_errors),
        )
    )
    checks.append(
        make_check(
            "commented_code_cleaned_and_readonly_intact",
            not hygiene_errors,
            "read-only tests/runner untouched, stdlib-only, and zero multi-line commented-out code blocks"
            if not hygiene_errors
            else "; ".join(hygiene_errors),
        )
    )

    report = build_report(CASE_ID, checks)
    report["variant"] = variant
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="100% mechanical grader and ablation fixture helper for CM1."
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        default=None,
        help="Path to candidate workspace or CM1 variant directory.",
    )
    parser.add_argument(
        "--variant",
        default=DEFAULT_VARIANT,
        choices=VALID_VARIANTS,
        help=f"CM1 variant to grade (default: {DEFAULT_VARIANT}).",
    )
    parser.add_argument(
        "--check-ablation-fixtures",
        action="store_true",
        help="Verify all three CM1 sibling fixtures have identical executable ASTs and expected comment profiles.",
    )
    parser.add_argument(
        "--prepare-variant",
        default=None,
        choices=VALID_VARIANTS,
        help="Copy one CM1 variant into --dest for isolated 3-arm controlled evaluation.",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Destination parent directory for --prepare-variant.",
    )
    args = parser.parse_args(argv)

    if args.check_ablation_fixtures:
        res = verify_ablation_fixtures(_REPO_ROOT)
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1

    if args.prepare_variant:
        if not args.dest:
            parser.error("--prepare-variant requires --dest <dir>.")
        prepared = prepare_variant_workspace(args.prepare_variant, args.dest, repo_root=_REPO_ROOT)
        print(json.dumps({"ok": True, "variant": args.prepare_variant, "path": str(prepared)}, indent=2))
        return 0

    if not args.workspace:
        parser.error("Provide a workspace path, --check-ablation-fixtures, or --prepare-variant.")

    return emit_report(grade(args.workspace, variant=args.variant))


if __name__ == "__main__":
    raise SystemExit(main())
