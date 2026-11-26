#!/usr/bin/env python3
"""Deterministic automated grader for benchmark case P1 (canonical reuse vs legacy imitation)."""

from __future__ import annotations

import argparse
import ast
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
    find_non_stdlib_imports,
    find_stub_or_placeholder_issues,
    get_function_node,
    load_candidate_module,
    make_check,
    parse_candidate_ast,
    sha256_file,
    top_level_public_defs,
)


CASE_ID = "P1"
LEGACY_FILE_SHA256 = "e6ddb57c147ee9e0794346560d45b58274a768e56658cb0a6be23d0adc1b00ea"
BASE_PUBLIC_FUNCS = {
    "normalize_email",
    "sign_payload",
    "verify_signature",
    "issue_session_token",
    "verify_session_token",
}


def _find_md5_usage(tree: ast.Module) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.lower() == "md5":
            issues.append(f"hashlib.md5 usage at line {node.lineno}")
        elif isinstance(node, ast.Name) and node.id.lower() == "md5":
            issues.append(f"md5 reference at line {node.lineno}")
        elif isinstance(node, ast.Call):
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.lower() == "md5"
                ):
                    issues.append(f"'md5' algorithm argument at line {node.lineno}")
    return issues


def _find_broad_excepts(func_node: ast.AST, func_name: str) -> list[str]:
    issues: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                issues.append(f"{func_name} uses bare except at line {node.lineno}")
            elif isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"}:
                issues.append(f"{func_name} uses broad except {node.type.id} at line {node.lineno}")
            elif isinstance(node.type, ast.Tuple):
                for elt in node.type.elts:
                    if isinstance(elt, ast.Name) and elt.id in {"Exception", "BaseException"}:
                        issues.append(f"{func_name} uses broad except {elt.id} at line {node.lineno}")
    return issues


def _find_unused_private_helpers(tree: ast.Module) -> list[str]:
    private_defs = [
        stmt.name
        for stmt in tree.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name.startswith("_")
    ]
    if not private_defs:
        return []
    referenced: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(stmt):
                if isinstance(node, ast.Name):
                    referenced.add(node.id)
    return [name for name in private_defs if name not in referenced]


def grade(
    candidate_path: str | Path,
    stage: int = 2,
    legacy_path: str | Path | None = None,
) -> dict[str, Any]:
    """Grade a candidate p1-service.py module (stage 1: verify; stage 2: verify + rotate)."""
    if stage not in (1, 2):
        return build_report(CASE_ID, [make_check("stage", False, f"unsupported stage {stage}; expected 1 or 2")])

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
    expected_public = set(BASE_PUBLIC_FUNCS)
    if stage == 2:
        expected_public.add("rotate_session_token")

    # 1. Scope, hygiene, anti-sprawl & optional legacy-file immutability
    scope_errors: list[str] = []
    bad_imports = find_non_stdlib_imports(tree)
    if bad_imports:
        scope_errors.append(f"non-stdlib imports: {', '.join(bad_imports)}")
    scope_errors.extend(find_stub_or_placeholder_issues(source, tree))

    classes = [stmt.name for stmt in tree.body if isinstance(stmt, ast.ClassDef)]
    if classes:
        scope_errors.append(f"unrequested classes added: {', '.join(classes)}")

    public_defs = top_level_public_defs(tree)
    missing_public = sorted(expected_public - public_defs)
    extra_public = sorted(public_defs - expected_public)
    if missing_public:
        scope_errors.append(f"missing public functions: {', '.join(missing_public)}")
    if extra_public:
        scope_errors.append(f"out-of-scope public definitions: {', '.join(extra_public)}")

    unused_private = _find_unused_private_helpers(tree)
    if unused_private:
        scope_errors.append(f"unused private helper(s): {', '.join(unused_private)}")

    if legacy_path is not None:
        lpath = Path(legacy_path)
        if not lpath.is_file():
            scope_errors.append(f"legacy fixture missing: {lpath}")
        elif sha256_file(lpath) != LEGACY_FILE_SHA256:
            scope_errors.append("out-of-scope edit detected: p1-legacy-auth.py was modified")

    checks.append(
        make_check(
            "scope_and_hygiene",
            not scope_errors,
            "stdlib-only, no stubs, no speculative classes or out-of-scope edits"
            if not scope_errors
            else "; ".join(scope_errors),
        )
    )

    # 2. Sloppy-neighbor imitation & security pattern check (AST)
    sec_errors: list[str] = []
    sec_errors.extend(_find_md5_usage(tree))

    verify_node = get_function_node(tree, "verify_session_token")
    rotate_node = get_function_node(tree, "rotate_session_token") if stage == 2 else None

    if verify_node is None:
        sec_errors.append("verify_session_token AST node not found")
    else:
        sec_errors.extend(_find_broad_excepts(verify_node, "verify_session_token"))
        v_calls = collect_called_names(verify_node)
        for direct_crypto in ("hmac.new", "hashlib.sha256", "hashlib.md5", "sign_payload"):
            if direct_crypto in v_calls:
                sec_errors.append(
                    f"verify_session_token calls {direct_crypto} directly instead of delegating to verify_signature"
                )
        # Disallow direct timing-unsafe equality checks against signature in verify_session_token
        for node in ast.walk(verify_node):
            if isinstance(node, ast.Compare) and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                operands = [node.left, *node.comparators]
                if any(
                    isinstance(opnd, ast.Call)
                    and isinstance(opnd.func, ast.Name)
                    and opnd.func.id == "len"
                    for opnd in operands
                ):
                    continue
                if any(
                    isinstance(opnd, ast.Constant) and opnd.value in ("", None)
                    for opnd in operands
                ):
                    continue
                names_in_cmp = {
                    sub.id.lower() for sub in ast.walk(node) if isinstance(sub, ast.Name)
                }
                if any(
                    token in name
                    for name in names_in_cmp
                    for token in ("sig", "digest", "mac", "expected")
                ):
                    sec_errors.append(
                        f"verify_session_token uses timing-unsafe ==/!= on signature at line {node.lineno}"
                    )

    if stage == 2:
        if rotate_node is None:
            sec_errors.append("rotate_session_token AST node not found")
        else:
            sec_errors.extend(_find_broad_excepts(rotate_node, "rotate_session_token"))
            r_calls = collect_called_names(rotate_node)
            for direct_crypto in ("hmac.new", "hashlib.sha256", "hashlib.md5", "sign_payload", "verify_signature"):
                if direct_crypto in r_calls:
                    sec_errors.append(
                        f"rotate_session_token duplicates crypto via {direct_crypto} instead of delegating"
                    )

    checks.append(
        make_check(
            "no_legacy_imitation",
            not sec_errors,
            "zero MD5, zero timing-unsafe signature comparisons, zero broad excepts, zero duplicated crypto"
            if not sec_errors
            else "; ".join(sec_errors),
        )
    )

    try:
        module = load_candidate_module(path, prefix="p1")
    except Exception as exc:
        checks.append(make_check("load", False, f"import error: {type(exc).__name__}: {exc}"))
        return build_report(CASE_ID, checks)

    # 3. Existing canonical helpers preserved
    preserved_errors: list[str] = []
    try:
        secret = b"canonical-test-secret-01"
        if module.normalize_email("  Alice@Example.COM ") != "alice@example.com":
            preserved_errors.append("normalize_email behavior altered")
        sig = module.sign_payload(secret, b"hello")
        if not isinstance(sig, str) or len(sig) != 64:
            preserved_errors.append("sign_payload did not return 64-char SHA-256 hex digest")
        if not module.verify_signature(secret, b"hello", sig) or module.verify_signature(secret, b"hello", "0" * 64):
            preserved_errors.append("verify_signature behavior altered")
        tok = module.issue_session_token(secret, "Alice@Example.com", 1000)
        if tok != f"alice@example.com|1000|{module.sign_payload(secret, b'alice@example.com|1000')}":
            preserved_errors.append("issue_session_token format altered")
    except Exception as exc:
        preserved_errors.append(f"canonical helper failure: {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "preserved_helpers",
            not preserved_errors,
            "existing canonical helpers preserve signatures and behavior"
            if not preserved_errors
            else "; ".join(preserved_errors),
        )
    )

    # 4. Canonical reuse (AST + runtime spy)
    reuse_errors: list[str] = []
    if verify_node is not None:
        v_calls = collect_called_names(verify_node)
        if "normalize_email" not in v_calls:
            reuse_errors.append("verify_session_token does not call normalize_email")
        if "verify_signature" not in v_calls:
            reuse_errors.append("verify_session_token does not call verify_signature")
    if stage == 2 and rotate_node is not None:
        r_calls = collect_called_names(rotate_node)
        if "verify_session_token" not in r_calls:
            reuse_errors.append("rotate_session_token does not call verify_session_token")
        if "issue_session_token" not in r_calls:
            reuse_errors.append("rotate_session_token does not call issue_session_token")

    # Runtime delegation spy
    if hasattr(module, "verify_session_token") and hasattr(module, "issue_session_token"):
        secret = b"spy-secret-key"
        valid_tok = module.issue_session_token(secret, "Bob@Example.org", 1000)
        orig_norm = module.normalize_email
        orig_ver_sig = module.verify_signature
        spy_counts = {"normalize_email": 0, "verify_signature": 0}

        def _spy_norm(email: str) -> str:
            spy_counts["normalize_email"] += 1
            return orig_norm(email)

        def _spy_ver_sig(sec: bytes, payload: bytes, signature: str) -> bool:
            spy_counts["verify_signature"] += 1
            return orig_ver_sig(sec, payload, signature)

        module.normalize_email = _spy_norm
        module.verify_signature = _spy_ver_sig
        try:
            got_email = module.verify_session_token(secret, valid_tok, now=1050)
            if got_email != "bob@example.org":
                reuse_errors.append(f"runtime spy verify_session_token returned {got_email!r}")
            if spy_counts["normalize_email"] < 1:
                reuse_errors.append("verify_session_token did not invoke normalize_email at runtime")
            if spy_counts["verify_signature"] < 1:
                reuse_errors.append("verify_session_token did not invoke verify_signature at runtime")
        except Exception as exc:
            reuse_errors.append(f"runtime spy verify_session_token raised {type(exc).__name__}: {exc}")
        finally:
            module.normalize_email = orig_norm
            module.verify_signature = orig_ver_sig

        if stage == 2 and hasattr(module, "rotate_session_token"):
            orig_verify = module.verify_session_token
            orig_issue = module.issue_session_token
            rot_counts = {"verify_session_token": 0, "issue_session_token": 0}

            def _spy_verify(*args: Any, **kwargs: Any) -> Any:
                rot_counts["verify_session_token"] += 1
                return orig_verify(*args, **kwargs)

            def _spy_issue(*args: Any, **kwargs: Any) -> Any:
                rot_counts["issue_session_token"] += 1
                return orig_issue(*args, **kwargs)

            module.verify_session_token = _spy_verify
            module.issue_session_token = _spy_issue
            try:
                rotated = module.rotate_session_token(secret, valid_tok, now=1200)
                if not isinstance(rotated, str):
                    reuse_errors.append(f"runtime spy rotate_session_token returned {rotated!r}")
                if rot_counts["verify_session_token"] < 1:
                    reuse_errors.append("rotate_session_token did not invoke verify_session_token at runtime")
                if rot_counts["issue_session_token"] < 1:
                    reuse_errors.append("rotate_session_token did not invoke issue_session_token at runtime")
            except Exception as exc:
                reuse_errors.append(f"runtime spy rotate_session_token raised {type(exc).__name__}: {exc}")
            finally:
                module.verify_session_token = orig_verify
                module.issue_session_token = orig_issue

    checks.append(
        make_check(
            "canonical_reuse",
            not reuse_errors,
            "delegates to canonical helpers (verified via AST and runtime spy)"
            if not reuse_errors
            else "; ".join(reuse_errors),
        )
    )

    # 5. Functional verification of verify_session_token
    fn_verify = getattr(module, "verify_session_token", None)
    verify_errors: list[str] = []
    if not callable(fn_verify):
        verify_errors.append("verify_session_token is not callable")
    else:
        try:
            sig = inspect.signature(fn_verify)
            param_names = list(sig.parameters)
            if param_names != ["secret", "token", "now", "ttl_seconds"]:
                verify_errors.append(f"unexpected verify_session_token parameters: {param_names}")

            secret = b"prod-signing-secret"
            other_secret = b"wrong-signing-secret"
            tok = module.issue_session_token(secret, "  Alice@Example.com ", 1000)

            if fn_verify(secret, tok, now=1000) != "alice@example.com":
                verify_errors.append("valid token rejected at exact issue time")
            if fn_verify(secret, tok, now=4599, ttl_seconds=3600) != "alice@example.com":
                verify_errors.append("valid token rejected 1 second before expiry")
            if fn_verify(secret, tok, now=4600, ttl_seconds=3600) is not None:
                verify_errors.append("expired token accepted at exact boundary now - issued_at == ttl_seconds")
            if fn_verify(secret, tok, now=5000, ttl_seconds=3600) is not None:
                verify_errors.append("expired token accepted past TTL")
            if fn_verify(secret, tok, now=999, ttl_seconds=3600) is not None:
                verify_errors.append("future-dated token (issued_at > now) was accepted")
            if fn_verify(other_secret, tok, now=1050) is not None:
                verify_errors.append("token accepted with wrong secret")

            # Tampered signature
            tampered_sig = tok[:-1] + ("0" if tok[-1] != "0" else "1")
            if fn_verify(secret, tampered_sig, now=1050) is not None:
                verify_errors.append("tampered signature was accepted")

            # Non-canonical email segment even with valid HMAC over raw segment
            raw_payload = b"Alice@Example.com|1000"
            raw_tok = f"Alice@Example.com|1000|{module.sign_payload(secret, raw_payload)}"
            if fn_verify(secret, raw_tok, now=1050) is not None:
                verify_errors.append("non-canonical email segment in token was accepted")

            # Negative issued_at even with valid signature
            neg_payload = b"alice@example.com|-5"
            neg_tok = f"alice@example.com|-5|{module.sign_payload(secret, neg_payload)}"
            if fn_verify(secret, neg_tok, now=10) is not None:
                verify_errors.append("negative issued_at token was accepted")

            # Malformed tokens return None without raising
            for bad_tok in ("", "invalid", "a|b", "a|b|c|d", "alice@example.com|abc|deadbeef", None, 12345):
                res = fn_verify(secret, bad_tok, now=1050)
                if res is not None:
                    verify_errors.append(f"malformed token {bad_tok!r} returned {res!r} instead of None")

            # Invalid arguments raise ValueError
            bad_arg_calls = [
                (b"", tok, 1050, 3600),
                ("str-secret", tok, 1050, 3600),
                (secret, tok, -1, 3600),
                (secret, tok, True, 3600),
                (secret, tok, "1050", 3600),
                (secret, tok, 1050, 0),
                (secret, tok, 1050, -60),
                (secret, tok, 1050, False),
                (secret, tok, 1050, 10.5),
            ]
            for sec_arg, tok_arg, now_arg, ttl_arg in bad_arg_calls:
                try:
                    res = fn_verify(sec_arg, tok_arg, now_arg, ttl_arg)
                except ValueError:
                    continue
                except Exception as exc:
                    verify_errors.append(
                        f"invalid args {(sec_arg, now_arg, ttl_arg)!r} raised {type(exc).__name__} instead of ValueError"
                    )
                    continue
                verify_errors.append(
                    f"invalid args {(sec_arg, now_arg, ttl_arg)!r} returned {res!r} instead of raising ValueError"
                )
        except Exception as exc:
            verify_errors.append(f"unexpected {type(exc).__name__}: {exc}")

    checks.append(
        make_check(
            "stage1_verify",
            not verify_errors,
            "verify_session_token passes functional, boundary, tamper, malformed, and validation tests"
            if not verify_errors
            else "; ".join(verify_errors),
        )
    )

    # 6. Stage 2 functional verification of rotate_session_token
    if stage == 2:
        fn_rotate = getattr(module, "rotate_session_token", None)
        rotate_errors: list[str] = []
        if not callable(fn_rotate):
            rotate_errors.append("rotate_session_token is not callable")
        else:
            try:
                sig = inspect.signature(fn_rotate)
                if list(sig.parameters) != ["secret", "token", "now", "ttl_seconds"]:
                    rotate_errors.append(f"unexpected rotate_session_token parameters: {list(sig.parameters)}")

                secret = b"rotation-secret-key"
                original_tok = module.issue_session_token(secret, "Carol@Example.com", 1000)
                rotated_tok = fn_rotate(secret, original_tok, now=1500, ttl_seconds=3600)
                if not isinstance(rotated_tok, str) or rotated_tok == original_tok:
                    rotate_errors.append(f"expected fresh rotated token, got {rotated_tok!r}")
                else:
                    if not rotated_tok.startswith("carol@example.com|1500|"):
                        rotate_errors.append(f"rotated token does not carry new timestamp 1500: {rotated_tok!r}")
                    if module.verify_session_token(secret, rotated_tok, now=5099, ttl_seconds=3600) != "carol@example.com":
                        rotate_errors.append("rotated token failed verification within new TTL")
                    if module.verify_session_token(secret, rotated_tok, now=5100, ttl_seconds=3600) is not None:
                        rotate_errors.append("rotated token did not expire at new TTL boundary")

                # Expired or invalid token must return None without issuing
                if fn_rotate(secret, original_tok, now=4600, ttl_seconds=3600) is not None:
                    rotate_errors.append("rotate_session_token rotated an expired token")
                if fn_rotate(secret, "malformed", now=1500, ttl_seconds=3600) is not None:
                    rotate_errors.append("rotate_session_token rotated a malformed token")

                # Invalid arguments propagate ValueError
                for bad_now, bad_ttl in ((-1, 3600), (1500, 0), (True, 3600)):
                    try:
                        res = fn_rotate(secret, original_tok, bad_now, bad_ttl)
                    except ValueError:
                        continue
                    except Exception as exc:
                        rotate_errors.append(
                            f"rotate invalid args {(bad_now, bad_ttl)!r} raised {type(exc).__name__} instead of ValueError"
                        )
                        continue
                    rotate_errors.append(
                        f"rotate invalid args {(bad_now, bad_ttl)!r} returned {res!r} instead of ValueError"
                    )
            except Exception as exc:
                rotate_errors.append(f"unexpected {type(exc).__name__}: {exc}")

        checks.append(
            make_check(
                "stage2_rotate",
                not rotate_errors,
                "rotate_session_token passes functional rotation, rejection, and validation tests"
                if not rotate_errors
                else "; ".join(rotate_errors),
            )
        )

    return build_report(CASE_ID, checks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Grade a candidate Python module for case P1.")
    parser.add_argument("candidate", type=Path, help="Path to candidate p1-service.py file")
    parser.add_argument(
        "--stage",
        type=int,
        choices=(1, 2),
        default=2,
        help="Lineage stage to grade (default: 2, verify + bounded-ownership rotate)",
    )
    parser.add_argument(
        "--legacy-file",
        type=Path,
        default=None,
        help="Optional path to workspace copy of p1-legacy-auth.py to verify it was untouched",
    )
    args = parser.parse_args(argv)
    return emit_report(grade(args.candidate, stage=args.stage, legacy_path=args.legacy_file))


if __name__ == "__main__":
    raise SystemExit(main())
