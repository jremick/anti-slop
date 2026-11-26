#!/usr/bin/env python3
"""AI-era structural slop detectors for diffs and source files.

Catches convincing-looking software patterns that pass a quick smoke test but
compound across future AI coding sessions:
  1. STRUCT-TEST-THEATER: assertion-free, tautological, or over-mocked tests
     that stay green even when production logic breaks.
  2. STRUCT-SILENT-FALLBACK: broad catches returning fabricated default values
     without logging/re-raising, or hardcoded secret/auth environment defaults.
  3. STRUCT-DUPLICATE-BLOCK: copy-pasted logic blocks duplicated across
     production files or functions (including variable-renamed clones).
  4. STRUCT-DEAD-COMPAT: unreachable branches (`if False:`), unreferenced
     legacy/compatibility shims or flags, and orphaned private helpers.
  5. STRUCT-GOD-FUNCTION / STRUCT-GOD-FILE: oversized or high-branch functions
     and growing monolithic files.
  6. STRUCT-SCOPE-SPRAWL: single-diff scatter across too many unrelated
     production module directories.

Zero third-party dependencies (Python 3.11+ stdlib only).
"""

from __future__ import annotations

import ast
import hashlib
import io
from pathlib import Path
import re
import sys
import tokenize
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402


# [Heuristic] Starting structural thresholds; calibrate locally if needed.
DEFAULT_MAX_FUNC_LINES = 60
DEFAULT_MAX_FUNC_BRANCHES = 12
DEFAULT_MAX_FILE_LINES = 400
DEFAULT_MAX_MODULE_SPREAD = 3
DEFAULT_DUPLICATE_MIN_STMTS = 6
DEFAULT_DUPLICATE_MIN_TOKENS = 35
DEFAULT_DUPLICATE_MIN_C_LINES = 6

EXCLUDED_SCAN_DIRS = frozenset({
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "runs-local",
    "results",
})

LEGACY_NAME_RE = re.compile(
    r"(?:^|_)(?:legacy|compat|deprecated|old|v\d+_compat|fallback_old)(?:$|_)",
    re.IGNORECASE,
)
LEGACY_FLAG_PARAM_RE = re.compile(
    r"^(?:allow_legacy|use_legacy|legacy_mode|compat_mode|enable_legacy)|(?:_legacy_mode|_compat_mode)$",
    re.IGNORECASE,
)
LEGACY_PREFIX_PARAM_RE = re.compile(r"^legacy_", re.IGNORECASE)
SENSITIVE_ENV_KEY_RE = re.compile(
    r"(?:SECRET|API_KEY|ACCESS_KEY|PRIVATE_KEY|SIGNING_KEY|AUTH_TOKEN|ACCESS_TOKEN|TOKEN|PASSWORD|PASSWD)",
    re.IGNORECASE,
)

LOGGING_CALL_NAMES = frozenset({
    "debug",
    "info",
    "warning",
    "warn",
    "error",
    "exception",
    "critical",
    "fatal",
    "log",
    "capture_exception",
    "capture_message",
    "record_error",
})
LOGGING_MODULE_TOKENS = frozenset({
    "log",
    "logger",
    "logging",
    "warn",
    "warnings",
    "stderr",
    "sentry",
    "sentry_sdk",
})

MOCK_TARGETS = frozenset({
    "patch",
    "mock.patch",
    "unittest.mock.patch",
    "patch.object",
    "mock.patch.object",
    "unittest.mock.patch.object",
    "patch.dict",
    "mock.patch.dict",
    "unittest.mock.patch.dict",
    "Mock",
    "MagicMock",
    "AsyncMock",
    "mock.Mock",
    "mock.MagicMock",
    "mock.AsyncMock",
    "unittest.mock.Mock",
    "unittest.mock.MagicMock",
    "unittest.mock.AsyncMock",
})

MOCK_ASSERT_METHODS = frozenset({
    "assert_called",
    "assert_called_once",
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
    "assert_not_called",
    "assert_awaited",
    "assert_awaited_once",
    "assert_awaited_with",
    "assert_awaited_once_with",
    "assert_any_await",
    "assert_has_awaits",
    "assert_not_awaited",
})

PYTEST_ASSERT_CALLS = frozenset({
    "pytest.raises",
    "pytest.warns",
    "pytest.fail",
    "pytest.approx",
    "raises",
    "warns",
    "fail",
})

JS_TEST_START_RE = re.compile(r"\b(?:it|test)\s*\([^,]+,\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{|\b(?:it|test)\s*\([^,]+,\s*(?:async\s*)?function\b[^{]*\{")
JS_ASSERT_RE = re.compile(
    r"\b(?:expect(?:\.\w+)?\s*\(|expectTypeOf\s*(?:<|\()|assertType\s*(?:<|\()|assert(?:\.\w+)?\s*\()"
)
JS_TAUTOLOGY_RE = re.compile(
    r"\bexpect\s*\(\s*(true|false|\d+|'[^']*'|\"[^\"]*\"|[A-Za-z_$][\w$]*)\s*\)\s*\.\s*(?:toBe|toEqual|toStrictEqual)\s*\(\s*\1\s*\)"
    r"|\bexpect\s*\(\s*true\s*\)\s*\.\s*toBeTruthy\s*\(\s*\)"
    r"|\bexpect\s*\(\s*false\s*\)\s*\.\s*toBeFalsy\s*\(\s*\)"
)
JS_LITERAL_RETURN_RE = re.compile(
    r"\breturn\s+(?:null|undefined|false|true|-?\d+(?:\.\d+)?|''|\"\"|\[\]|\{\})\s*;?"
)
JS_CATCH_FALLBACK_RE = re.compile(
    r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*return\s+(?:null|undefined|false|true|-?\d+(?:\.\d+)?|''|\"\"|\[\]|\{\})\s*;?\s*\}"
)
JS_ENV_FALLBACK_RE = re.compile(
    r"\bprocess\.env(?:\.([A-Za-z_][A-Za-z0-9_]*)|\[\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]\s*\])\s*(?:\|\||\?\?)\s*(['\"])([^'\"]+)\3"
)
JS_LOG_OR_THROW_RE = re.compile(r"\b(?:throw|console\.(?:error|warn|log)|logger\.|log\.)\b")
JS_FUNC_START_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?(?:function\s+([A-Za-z_$][\w$]*)\s*\(|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{)"
)
GO_FUNC_START_RE = re.compile(
    r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("
)


def _finding(
    code: str,
    severity: str,
    message: str,
    remediation: str,
    *,
    file: Optional[str] = None,
    line: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    item = _dc._finding(
        code=code,
        severity=severity,
        message=message,
        remediation=remediation,
        file=file,
        line=line,
    )
    if meta:
        item["meta"] = meta
    return item


def _sev(strict_structural: bool) -> str:
    return "error" if strict_structural else "warning"


def _iter_repo_code_files(
    repo_root: Path,
    *,
    include_tests: bool = False,
    skip_benchmark_sources: bool = True,
) -> Iterable[Path]:
    """Yield repo code files while skipping build/venv/archived/fixture dirs."""
    root = repo_root.resolve()
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in EXCLUDED_SCAN_DIRS for part in rel_parts):
            continue
        if skip_benchmark_sources and len(rel_parts) >= 2 and rel_parts[:2] == ("benchmarks", "sources"):
            continue
        rel_str = "/".join(rel_parts)
        if not _dc._is_code_path(rel_str):
            continue
        if not include_tests and _dc._is_test_file(rel_str):
            continue
        yield path


def _function_overlaps_added(
    node: ast.AST,
    added_lines: Optional[Set[int]],
) -> bool:
    if added_lines is None:
        return True
    start = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", start) or start
    return any(start <= ln <= end for ln in added_lines)


def _is_tautological_assert(stmt: ast.Assert) -> bool:
    test = stmt.test
    if isinstance(test, ast.Constant) and bool(test.value):
        return True
    if (
        isinstance(test, ast.UnaryOp)
        and isinstance(test.op, ast.Not)
        and isinstance(test.operand, ast.Constant)
        and not bool(test.operand.value)
    ):
        return True
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        op = test.ops[0]
        left = test.left
        right = test.comparators[0]
        if isinstance(op, (ast.Eq, ast.Is)) and ast.dump(left) == ast.dump(right):
            return True
    return False


def _is_tautological_unittest_call(call: ast.Call) -> bool:
    if not isinstance(call.func, ast.Attribute):
        return False
    attr = call.func.attr
    if attr == "assertTrue" and call.args:
        arg0 = call.args[0]
        if isinstance(arg0, ast.Constant) and bool(arg0.value):
            return True
    if attr == "assertFalse" and call.args:
        arg0 = call.args[0]
        if isinstance(arg0, ast.Constant) and not bool(arg0.value):
            return True
    if attr in ("assertEqual", "assertIs") and len(call.args) >= 2:
        if ast.dump(call.args[0]) == ast.dump(call.args[1]):
            return True
    return False


def _is_warnings_error_call(call: ast.Call, aliases: Dict[str, str]) -> bool:
    """Return True for warnings.simplefilter('error', ...) or warnings.filterwarnings('error', ...)."""
    resolved = _dc._resolve_dotted(_dc._dotted_name(call.func), aliases)
    if resolved not in ("warnings.simplefilter", "warnings.filterwarnings"):
        return False
    action_node: Optional[ast.expr] = call.args[0] if call.args else None
    if action_node is None:
        for kw in call.keywords:
            if kw.arg == "action":
                action_node = kw.value
                break
    return isinstance(action_node, ast.Constant) and action_node.value == "error"


def _call_is_real_assertion(
    call: ast.Call,
    aliases: Dict[str, str],
    verified_fn_helpers: Set[str],
    verified_method_helpers: Set[str],
) -> Tuple[bool, bool]:
    """Return (is_real_assertion, is_tautological_assertion) for a Python ast.Call."""
    dotted = _dc._dotted_name(call.func)
    resolved = _dc._resolve_dotted(dotted, aliases)
    attr = (
        call.func.attr
        if isinstance(call.func, ast.Attribute)
        else (call.func.id if isinstance(call.func, ast.Name) else "")
    )
    if attr in MOCK_ASSERT_METHODS:
        return False, False
    if isinstance(call.func, ast.Attribute) and (attr.startswith("assert") or attr == "fail"):
        if _is_tautological_unittest_call(call):
            return False, True
        return True, False
    if resolved in PYTEST_ASSERT_CALLS or _is_warnings_error_call(call, aliases):
        return True, False
    if isinstance(call.func, ast.Name):
        if attr in verified_fn_helpers or attr.startswith(
            ("assert_", "_assert_", "check_", "_check_", "verify_", "_verify_")
        ):
            return True, False
    elif (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id in ("self", "cls")
        and (
            attr in verified_method_helpers
            or attr.startswith(("check_", "_check_", "verify_", "_verify_", "_assert_"))
        )
    ):
        return True, False
    elif isinstance(call.func, ast.Attribute) and attr.startswith(("assert_", "_assert_")):
        return True, False
    return False, False


def _body_has_real_assertion(
    body: Sequence[ast.stmt],
    aliases: Dict[str, str],
    verified_fn_helpers: Set[str],
    verified_method_helpers: Set[str],
) -> bool:
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Assert) and not _is_tautological_assert(sub):
                return True
            if isinstance(sub, ast.Call):
                is_real, _ = _call_is_real_assertion(
                    sub, aliases, verified_fn_helpers, verified_method_helpers
                )
                if is_real:
                    return True
    return False


def _collect_verified_assertion_helpers(
    tree: ast.Module,
    aliases: Dict[str, str],
    seed_fn_helpers: Optional[Set[str]] = None,
) -> Tuple[Set[str], Set[str]]:
    """Find same-module helper functions and class methods proven by AST to execute real assertions."""
    mod_funcs: Dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    cls_methods: Dict[str, List[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("test_"):
            mod_funcs[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and not member.name.startswith("test_"):
                    cls_methods.setdefault(member.name, []).append(member)

    verified_fns: Set[str] = set(seed_fn_helpers or ())
    verified_methods: Set[str] = set()
    for _ in range(4):
        changed = False
        for name, fn in mod_funcs.items():
            if name not in verified_fns and _body_has_real_assertion(
                fn.body, aliases, verified_fns, verified_methods
            ):
                verified_fns.add(name)
                changed = True
        for name, methods in cls_methods.items():
            if name not in verified_methods and any(
                _body_has_real_assertion(m.body, aliases, verified_fns, verified_methods)
                for m in methods
            ):
                verified_methods.add(name)
                changed = True
        if not changed:
            break
    return verified_fns, verified_methods


_TEST_HELPER_CACHE: Dict[Tuple[str, int, int], Set[str]] = {}


def _resolve_imported_test_assertion_helpers(
    rel_path: str,
    tree: ast.Module,
    repo_root: Optional[Path],
) -> Set[str]:
    """Resolve functions imported from local test-helper modules and verify via AST that they assert."""
    if repo_root is None:
        return set()
    root = repo_root.resolve()
    rel_dir = (root / rel_path).parent
    verified_imported: Set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        mod = node.module or ""
        candidate_paths: List[Path] = []
        if node.level > 0:
            base = rel_dir
            for _ in range(node.level - 1):
                base = base.parent
            if mod:
                parts = mod.split(".")
                candidate_paths.append(base.joinpath(*parts).with_suffix(".py"))
                candidate_paths.append(base.joinpath(*parts) / "__init__.py")
            else:
                candidate_paths.append(base / "__init__.py")
        elif mod:
            parts = mod.split(".")
            first = parts[0].lower()
            if first in ("tests", "test") or any(p.lower() in ("tests", "test") for p in parts):
                candidate_paths.append(root.joinpath(*parts).with_suffix(".py"))
                candidate_paths.append(root.joinpath(*parts) / "__init__.py")
            else:
                candidate_paths.append(rel_dir.joinpath(*parts).with_suffix(".py"))
        else:
            continue

        resolved_file: Optional[Path] = None
        for cand in candidate_paths:
            try:
                rcand = cand.resolve()
                rcand.relative_to(root)
            except (OSError, ValueError):
                continue
            if rcand.is_file():
                resolved_file = rcand
                break
        if resolved_file is None:
            continue

        try:
            st = resolved_file.stat()
        except OSError:
            continue
        cache_key = (str(resolved_file), st.st_mtime_ns, st.st_size)
        helper_names = _TEST_HELPER_CACHE.get(cache_key)
        if helper_names is None:
            try:
                helper_src = resolved_file.read_text(encoding="utf-8")
                helper_tree = ast.parse(helper_src)
            except (OSError, UnicodeDecodeError, SyntaxError):
                helper_names = set()
            else:
                helper_aliases = _dc._python_import_aliases(helper_tree)
                helper_names, _ = _collect_verified_assertion_helpers(
                    helper_tree, helper_aliases
                )
            if len(_TEST_HELPER_CACHE) > 256:
                _TEST_HELPER_CACHE.clear()
            _TEST_HELPER_CACHE[cache_key] = helper_names

        for alias in node.names:
            if alias.name == "*":
                verified_imported.update(helper_names)
            elif alias.name in helper_names:
                verified_imported.add(alias.asname or alias.name)

    return verified_imported


def check_test_theater_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
    repo_root: Optional[Path] = None,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect assertion-free, tautological, or over-mocked tests."""
    if not _dc._is_test_file(rel_path):
        return []
    findings: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        aliases = _dc._python_import_aliases(tree)
        imported_helpers = _resolve_imported_test_assertion_helpers(
            rel_path, tree, repo_root
        )
        verified_fn_helpers, verified_method_helpers = _collect_verified_assertion_helpers(
            tree, aliases, seed_fn_helpers=imported_helpers
        )

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if not _function_overlaps_added(node, added_lines):
                continue

            real_assertions = 0
            tautological_assertions = 0
            mock_assertions = 0
            mock_count = 0

            # Count decorator mocks (`@patch(...)`, `@mock.patch(...)`).
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                resolved = _dc._resolve_dotted(_dc._dotted_name(target), aliases)
                if resolved in MOCK_TARGETS or resolved.endswith(".patch") or resolved.endswith(".patch.object"):
                    mock_count += 1

            # Walk function body only (decorators already counted above) to avoid double-counting @patch.
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Assert):
                        if _is_tautological_assert(sub):
                            tautological_assertions += 1
                        else:
                            real_assertions += 1
                    elif isinstance(sub, ast.Call):
                        dotted = _dc._dotted_name(sub.func)
                        resolved = _dc._resolve_dotted(dotted, aliases)
                        attr = sub.func.attr if isinstance(sub.func, ast.Attribute) else (
                            sub.func.id if isinstance(sub.func, ast.Name) else ""
                        )

                        if resolved in MOCK_TARGETS or attr in ("Mock", "MagicMock", "AsyncMock"):
                            mock_count += 1
                        elif isinstance(sub.func, ast.Attribute) and sub.func.attr in ("setattr", "setitem") and "monkeypatch" in dotted:
                            mock_count += 1

                        if attr in MOCK_ASSERT_METHODS:
                            mock_assertions += 1
                        else:
                            is_real, is_taut = _call_is_real_assertion(
                                sub,
                                aliases,
                                verified_fn_helpers,
                                verified_method_helpers,
                            )
                            if is_taut:
                                tautological_assertions += 1
                            elif is_real:
                                real_assertions += 1

            if real_assertions == 0 and tautological_assertions > 0:
                findings.append(
                    _finding(
                        code="STRUCT-TEST-THEATER",
                        severity=severity,
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"{rel_path}:{node.lineno} test '{node.name}' only runs tautological "
                            f"assertion(s) that always pass."
                        ),
                        remediation="Replace tautological assertions with checks against real return values, state transitions, or raised errors.",
                        meta={"kind": "tautological", "function": node.name},
                    )
                )
            elif real_assertions == 0 and mock_count >= 3:
                findings.append(
                    _finding(
                        code="STRUCT-TEST-THEATER",
                        severity=severity,
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"{rel_path}:{node.lineno} test '{node.name}' mocks {mock_count} targets "
                            f"with 0 real value/state assertions (mock-only test theater)."
                        ),
                        remediation="Test real collaborator behavior where practical and assert concrete outputs or state changes, not only mock calls.",
                        meta={"kind": "over_mocked", "function": node.name, "mocks": mock_count},
                    )
                )
            elif real_assertions == 0 and mock_assertions == 0:
                findings.append(
                    _finding(
                        code="STRUCT-TEST-THEATER",
                        severity=severity,
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"{rel_path}:{node.lineno} test '{node.name}' contains zero assertions "
                            f"(only checks that code does not crash)."
                        ),
                        remediation="Add explicit assertions verifying the required output, state change, or error condition.",
                        meta={"kind": "assertion_free", "function": node.name},
                    )
                )
        return findings

    if _dc._is_js_ts_path(rel_path):
        code_lines, _ = _dc._scan_c_like_lines(source.splitlines())
        n = len(code_lines)
        i = 0
        while i < n:
            line = code_lines[i]
            if JS_TEST_START_RE.search(line):
                start_lineno = i + 1
                depth = line.count("{") - line.count("}")
                j = i + 1
                while j < n and depth > 0:
                    depth += code_lines[j].count("{") - code_lines[j].count("}")
                    j += 1
                end_lineno = j
                body_text = "\n".join(code_lines[i:j])
                overlaps = added_lines is None or any(
                    start_lineno <= ln <= end_lineno for ln in added_lines
                )
                if overlaps:
                    assert_count = len(JS_ASSERT_RE.findall(body_text))
                    taut_count = len(JS_TAUTOLOGY_RE.findall(body_text))
                    if taut_count > 0 and taut_count >= assert_count:
                        findings.append(
                            _finding(
                                code="STRUCT-TEST-THEATER",
                                severity=severity,
                                file=rel_path,
                                line=start_lineno,
                                message=f"{rel_path}:{start_lineno} JS/TS test only executes tautological assertion(s).",
                                remediation="Assert real return values or state changes instead of constant tautologies.",
                                meta={"kind": "tautological"},
                            )
                        )
                    elif assert_count == 0:
                        findings.append(
                            _finding(
                                code="STRUCT-TEST-THEATER",
                                severity=severity,
                                file=rel_path,
                                line=start_lineno,
                                message=f"{rel_path}:{start_lineno} JS/TS test block has zero expect/assert checks.",
                                remediation="Add explicit expect(...) or assert(...) checks for the expected behavior.",
                                meta={"kind": "assertion_free"},
                            )
                        )
                i = max(j, i + 1)
                continue
            i += 1
    return findings


def _is_literal_fallback_expr(expr: Optional[ast.expr]) -> bool:
    if expr is None:
        return True
    if isinstance(expr, ast.Constant):
        return True
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.USub) and isinstance(expr.operand, ast.Constant):
        return True
    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)) and not expr.elts:
        return True
    if isinstance(expr, ast.Dict) and not expr.keys:
        return True
    return False


def _handler_logs_or_reraises(body: List[ast.stmt]) -> bool:
    for node in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(node, ast.Raise):
            return True
        if isinstance(node, ast.Call):
            dotted = _dc._dotted_name(node.func)
            segments = [seg.lower() for seg in dotted.split(".") if seg]
            leaf = segments[-1] if segments else ""
            if leaf in LOGGING_CALL_NAMES or leaf in ("print", "write"):
                return True
            if any(
                seg in LOGGING_MODULE_TOKENS or seg.endswith(("_log", "_logger"))
                for seg in segments
            ):
                return True
    return False


def _assigned_simple_names(stmt: ast.stmt) -> Set[str]:
    names: Set[str] = set()
    if isinstance(stmt, ast.Assign):
        for target in stmt.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        names.add(stmt.target.id)
    return names


def _is_literal_assign_stmt(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.Assign):
        return _is_literal_fallback_expr(stmt.value)
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        return _is_literal_fallback_expr(stmt.value)
    return False


def _extract_env_call_info(
    node: ast.Call,
    aliases: Dict[str, str],
) -> Optional[Tuple[str, Optional[ast.expr]]]:
    resolved = _dc._resolve_dotted(_dc._dotted_name(node.func), aliases)
    if resolved not in ("os.getenv", "os.environ.get", "environ.get"):
        return None
    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        return None
    env_key = node.args[0].value
    default_arg: Optional[ast.expr] = node.args[1] if len(node.args) >= 2 else None
    if default_arg is None:
        for kw in node.keywords:
            if kw.arg == "default":
                default_arg = kw.value
                break
    return env_key, default_arg


def _strip_js_line_comment(raw_line: str) -> str:
    """Strip trailing // comments while preserving string literal contents."""
    in_single = False
    in_double = False
    in_backtick = False
    i = 0
    n = len(raw_line)
    while i < n:
        ch = raw_line[i]
        if in_single or in_double or in_backtick:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if (in_single and ch == "'") or (in_double and ch == '"') or (in_backtick and ch == "`"):
                in_single = in_double = in_backtick = False
            i += 1
            continue
        if raw_line[i : i + 2] == "//":
            return raw_line[:i]
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "`":
            in_backtick = True
        i += 1
    return raw_line


def check_silent_fallbacks_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect silent fallback defaults in broad catches and hardcoded sensitive env defaults."""
    if not _dc._is_code_path(rel_path):
        return []
    findings: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []
        aliases = _dc._python_import_aliases(tree)
        reported_env_sites: Set[Tuple[int, str]] = set()

        def _emit_env_fallback(lineno: int, env_key: str) -> None:
            site = (lineno, env_key)
            if site in reported_env_sites:
                return
            if added_lines is not None and lineno not in added_lines:
                return
            reported_env_sites.add(site)
            findings.append(
                _finding(
                    code="STRUCT-SILENT-FALLBACK",
                    severity=severity,
                    file=rel_path,
                    line=lineno,
                    message=f"{rel_path}:{lineno} supplies a hardcoded fallback string for sensitive env var '{env_key}'.",
                    remediation="Fail closed with a clear startup error when required secrets or auth credentials are missing.",
                    meta={"kind": "sensitive_env_default", "env_key": env_key},
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                broad = _dc._broad_except_label(node.type, aliases)
                if broad is None:
                    continue
                # Skip handlers already reported by DIFF-SILENT-CATCH (pass/.../None/False/[]/{}).
                if _dc._silent_handler_body(node.body) is not None:
                    continue
                if _handler_logs_or_reraises(node.body):
                    continue
                effective = _dc._strip_docstring(node.body)
                if not effective:
                    continue
                is_fallback = False
                detail = ""
                if len(effective) == 1:
                    stmt = effective[0]
                    if isinstance(stmt, ast.Return) and _is_literal_fallback_expr(stmt.value):
                        is_fallback = True
                        detail = f"{broad} silent literal return fallback"
                    elif _is_literal_assign_stmt(stmt):
                        is_fallback = True
                        detail = f"{broad} silent literal assignment fallback"
                elif len(effective) == 2:
                    s0, s1 = effective
                    if _is_literal_assign_stmt(s0) and isinstance(s1, ast.Return):
                        assigned = _assigned_simple_names(s0)
                        if _is_literal_fallback_expr(s1.value) or (
                            isinstance(s1.value, ast.Name) and s1.value.id in assigned
                        ):
                            is_fallback = True
                            detail = f"{broad} silent default fallback"
                    elif _is_literal_assign_stmt(s0) and _is_literal_assign_stmt(s1):
                        is_fallback = True
                        detail = f"{broad} silent default fallback"

                if is_fallback:
                    end_ln = getattr(effective[-1], "end_lineno", node.lineno) or node.lineno
                    if added_lines is None or any(node.lineno <= ln <= end_ln for ln in added_lines):
                        findings.append(
                            _finding(
                                code="STRUCT-SILENT-FALLBACK",
                                severity=severity,
                                file=rel_path,
                                line=node.lineno,
                                message=f"{rel_path}:{node.lineno} hides unexpected failures behind a {detail} without logging or re-raising.",
                                remediation="Catch the specific expected exception, or log/surface the failure instead of silently substituting a fabricated default.",
                                meta={"kind": "broad_except_fallback"},
                            )
                        )

            elif isinstance(node, ast.Call) and not _dc._is_test_file(rel_path):
                env_info = _extract_env_call_info(node, aliases)
                if env_info is not None:
                    env_key, default_arg = env_info
                    if (
                        SENSITIVE_ENV_KEY_RE.search(env_key)
                        and isinstance(default_arg, ast.Constant)
                        and isinstance(default_arg.value, str)
                        and default_arg.value.strip() != ""
                    ):
                        _emit_env_fallback(node.lineno, env_key)

            elif (
                isinstance(node, ast.BoolOp)
                and isinstance(node.op, ast.Or)
                and not _dc._is_test_file(rel_path)
            ):
                env_key_found: Optional[str] = None
                for val in node.values:
                    if env_key_found is None and isinstance(val, ast.Call):
                        env_info = _extract_env_call_info(val, aliases)
                        if env_info is not None and SENSITIVE_ENV_KEY_RE.search(env_info[0]):
                            env_key_found = env_info[0]
                    elif (
                        env_key_found is not None
                        and isinstance(val, ast.Constant)
                        and isinstance(val.value, str)
                        and val.value.strip() != ""
                    ):
                        _emit_env_fallback(node.lineno, env_key_found)
                        break
        return findings

    if _dc._is_js_ts_path(rel_path):
        raw_lines = source.splitlines()
        code_lines, _ = _dc._scan_c_like_lines(raw_lines)
        n = len(code_lines)
        is_test = _dc._is_test_file(rel_path)
        for idx, line in enumerate(code_lines):
            lineno = idx + 1
            if not is_test and "process.env" in line:
                raw_no_comment = _strip_js_line_comment(raw_lines[idx])
                for em in JS_ENV_FALLBACK_RE.finditer(raw_no_comment):
                    env_key = em.group(1) or em.group(2) or ""
                    fallback_val = em.group(4) or ""
                    if SENSITIVE_ENV_KEY_RE.search(env_key) and fallback_val.strip():
                        if added_lines is None or lineno in added_lines:
                            findings.append(
                                _finding(
                                    code="STRUCT-SILENT-FALLBACK",
                                    severity=severity,
                                    file=rel_path,
                                    line=lineno,
                                    message=f"{rel_path}:{lineno} supplies a hardcoded fallback string for sensitive env var '{env_key}'.",
                                    remediation="Fail closed with a clear startup error when required secrets or auth credentials are missing.",
                                    meta={"kind": "sensitive_env_default", "env_key": env_key},
                                )
                            )
            if JS_CATCH_FALLBACK_RE.search(line):
                if added_lines is None or lineno in added_lines:
                    findings.append(
                        _finding(
                            code="STRUCT-SILENT-FALLBACK",
                            severity=severity,
                            file=rel_path,
                            line=lineno,
                            message=f"{rel_path}:{lineno} JS/TS catch block silently returns a fallback default without logging or rethrowing.",
                            remediation="Log the error or propagate failure instead of silently returning a fabricated default.",
                            meta={"kind": "js_catch_fallback"},
                        )
                    )
                continue
            if _dc.JS_CATCH_OPEN_RE.search(line):
                depth = line.count("{") - line.count("}")
                j = idx + 1
                body_lines: List[str] = []
                while j < n and depth > 0:
                    cur = code_lines[j]
                    depth += cur.count("{") - cur.count("}")
                    if depth > 0 and cur.strip():
                        body_lines.append(cur.strip())
                    j += 1
                if body_lines and len(body_lines) <= 2:
                    joined = " ".join(body_lines)
                    if not JS_LOG_OR_THROW_RE.search(joined) and JS_LITERAL_RETURN_RE.search(joined):
                        end_ln = j
                        if added_lines is None or any(lineno <= ln <= end_ln for ln in added_lines):
                            findings.append(
                                _finding(
                                    code="STRUCT-SILENT-FALLBACK",
                                    severity=severity,
                                    file=rel_path,
                                    line=lineno,
                                    message=f"{rel_path}:{lineno} JS/TS catch block silently returns a fallback default without logging or rethrowing.",
                                    remediation="Log the error or propagate failure instead of silently returning a fabricated default.",
                                    meta={"kind": "js_catch_fallback"},
                                )
                            )
    return findings


def _normalize_py_stmt_sequence(stmts: Sequence[ast.stmt]) -> Tuple[str, int]:
    """Alpha-normalize local variable names in a Python AST statement sequence."""
    var_map: Dict[str, str] = {}
    tokens: List[str] = []

    def _norm_name(name: str) -> str:
        if name in ("None", "True", "False", "self", "cls"):
            return name
        if name[0:1].isupper():
            return name
        mapped = var_map.get(name)
        if mapped is None:
            mapped = f"$v{len(var_map)}"
            var_map[name] = mapped
        return mapped

    def _walk(node: ast.AST, is_call_func: bool = False) -> None:
        cls_name = type(node).__name__
        if isinstance(node, ast.Name):
            tokens.append(node.id if is_call_func else _norm_name(node.id))
            return
        if isinstance(node, ast.Attribute):
            tokens.append("Attr")
            _walk(node.value, is_call_func=False)
            tokens.append(f".{node.attr}")
            return
        if isinstance(node, ast.Constant):
            tokens.append(f"Const:{type(node.value).__name__}")
            return
        if isinstance(node, ast.JoinedStr):
            tokens.append("Const:str")
            return
        if isinstance(node, ast.Call):
            tokens.append("Call(")
            _walk(node.func, is_call_func=True)
            for arg in node.args:
                _walk(arg)
            for kw in node.keywords:
                tokens.append(f"kw:{kw.arg}")
                _walk(kw.value)
            tokens.append(")")
            return
        tokens.append(cls_name)
        for field_name, val in ast.iter_fields(node):
            if field_name in ("ctx", "type_comment", "lineno", "col_offset", "end_lineno", "end_col_offset"):
                continue
            if isinstance(val, ast.AST):
                _walk(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, ast.AST):
                        _walk(item)

    for s in stmts:
        _walk(s)
    return " ".join(tokens), len(tokens)


def _window_has_nontrivial_logic(stmts: Sequence[ast.stmt]) -> bool:
    """Require at least one control-flow node or >= 3 calls/operators so flat config assigns don't collide."""
    ops_and_calls = 0
    for s in stmts:
        for sub in ast.walk(s):
            if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)):
                return True
            if isinstance(sub, (ast.Call, ast.BinOp, ast.Compare, ast.Subscript)):
                ops_and_calls += 1
                if ops_and_calls >= 3:
                    return True
    return False


def _count_recursive_stmts(stmts: Sequence[ast.stmt]) -> int:
    total = 0
    for s in stmts:
        for sub in ast.walk(s):
            if isinstance(sub, ast.stmt):
                total += 1
    return total


def _iter_qualified_py_functions(
    node: ast.AST,
    prefix: Tuple[str, ...] = (),
) -> Iterable[Tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            yield from _iter_qualified_py_functions(child, prefix + (child.name,))
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qual = ".".join(prefix + (child.name,))
            yield qual, child
            yield from _iter_qualified_py_functions(child, prefix + (child.name,))
        else:
            yield from _iter_qualified_py_functions(child, prefix)


def _extract_py_blocks(
    rel_path: str,
    source: str,
    *,
    min_stmts: int = DEFAULT_DUPLICATE_MIN_STMTS,
    min_tokens: int = DEFAULT_DUPLICATE_MIN_TOKENS,
) -> List[Dict[str, Any]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    blocks: List[Dict[str, Any]] = []
    for qual_name, node in _iter_qualified_py_functions(tree):
        body = _dc._strip_docstring(node.body)
        if not body or _count_recursive_stmts(body) < min_stmts:
            continue
        # Fingerprint the whole function body and sliding windows of top-level statements
        # that contain at least min_stmts recursive statements.
        windows: List[List[ast.stmt]] = [body]
        win_size = min(len(body), max(4, min_stmts - 1))
        if len(body) > win_size:
            for i in range(0, len(body) - win_size + 1):
                win = body[i : i + win_size]
                if _count_recursive_stmts(win) >= min_stmts:
                    windows.append(win)
        seen_hashes: Set[str] = set()
        for win in windows:
            if not _window_has_nontrivial_logic(win):
                continue
            norm, tok_count = _normalize_py_stmt_sequence(win)
            if tok_count < min_tokens:
                continue
            digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)
            start_ln = win[0].lineno
            end_ln = getattr(win[-1], "end_lineno", start_ln) or start_ln
            blocks.append({
                "hash": digest,
                "file": rel_path,
                "function": qual_name,
                "start_line": start_ln,
                "end_line": end_ln,
                "stmts": _count_recursive_stmts(win),
                "is_whole_fn": len(win) == len(body),
            })
    return blocks


def _extract_c_like_blocks(
    rel_path: str,
    source: str,
    *,
    min_lines: int = DEFAULT_DUPLICATE_MIN_C_LINES,
) -> List[Dict[str, Any]]:
    code_lines, _ = _dc._scan_c_like_lines(source.splitlines())
    meaningful: List[Tuple[int, str]] = []
    for idx, line in enumerate(code_lines, start=1):
        norm = re.sub(r"\s+", " ", line).strip()
        if not norm or norm in ("{", "}", "};", ");", "else {", "} else {"):
            continue
        if norm.startswith(("import ", "export type ", "package ", "from ")):
            continue
        meaningful.append((idx, norm))
    if len(meaningful) < min_lines:
        return []
    blocks: List[Dict[str, Any]] = []
    for i in range(0, len(meaningful) - min_lines + 1):
        win = meaningful[i : i + min_lines]
        joined = "\n".join(text for _, text in win)
        if len(re.sub(r"\s+", "", joined)) < 120:
            continue
        digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
        blocks.append({
            "hash": digest,
            "file": rel_path,
            "function": "<block>",
            "start_line": win[0][0],
            "end_line": win[-1][0],
            "stmts": min_lines,
            "is_whole_fn": False,
        })
    return blocks


def check_duplicate_blocks(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    *,
    repo_root: Optional[Path] = None,
    severity: str = "warning",
    min_stmts: int = DEFAULT_DUPLICATE_MIN_STMTS,
) -> List[Dict[str, Any]]:
    """Detect duplicated code blocks across target files and existing repo files."""
    target_blocks: List[Dict[str, Any]] = []
    target_paths: Set[str] = set()

    for rel_path, (source, added_lines) in sorted(target_sources.items()):
        if not _dc._is_code_path(rel_path) or _dc._is_test_file(rel_path):
            continue
        target_paths.add(rel_path)
        suffix = Path(rel_path).suffix.lower()
        if suffix == ".py":
            extracted = _extract_py_blocks(rel_path, source, min_stmts=min_stmts)
        elif _dc._is_js_ts_path(rel_path) or _dc._is_go_path(rel_path):
            extracted = _extract_c_like_blocks(rel_path, source, min_lines=min_stmts)
        else:
            extracted = []

        for blk in extracted:
            if added_lines is not None and not any(
                blk["start_line"] <= ln <= blk["end_line"] for ln in added_lines
            ):
                continue
            target_blocks.append(blk)

    if not target_blocks:
        return []

    # Index existing repo code blocks (excluding target files themselves) + all blocks in target files.
    index: Dict[str, List[Dict[str, Any]]] = {}
    for rel_path, (source, _) in sorted(target_sources.items()):
        if not _dc._is_code_path(rel_path) or _dc._is_test_file(rel_path):
            continue
        suffix = Path(rel_path).suffix.lower()
        blocks = (
            _extract_py_blocks(rel_path, source, min_stmts=min_stmts)
            if suffix == ".py"
            else (
                _extract_c_like_blocks(rel_path, source, min_lines=min_stmts)
                if (_dc._is_js_ts_path(rel_path) or _dc._is_go_path(rel_path))
                else []
            )
        )
        for blk in blocks:
            index.setdefault(blk["hash"], []).append(blk)

    if repo_root is not None:
        root = repo_root.resolve()
        skip_bench = not any(p.startswith("benchmarks/sources/") for p in target_paths)
        for disk_path in _iter_repo_code_files(
            root, include_tests=False, skip_benchmark_sources=skip_bench
        ):
            rel = str(disk_path.relative_to(root)).replace("\\", "/")
            if rel in target_paths:
                continue
            try:
                text = disk_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            suffix = disk_path.suffix.lower()
            blocks = (
                _extract_py_blocks(rel, text, min_stmts=min_stmts)
                if suffix == ".py"
                else (
                    _extract_c_like_blocks(rel, text, min_lines=min_stmts)
                    if (_dc._is_js_ts_path(rel) or _dc._is_go_path(rel))
                    else []
                )
            )
            for blk in blocks:
                index.setdefault(blk["hash"], []).append(blk)

    findings: List[Dict[str, Any]] = []
    reported_pairs: Set[Tuple[str, str, str, str]] = set()
    # Prefer whole-function matches over sliding sub-window matches.
    ordered_targets = sorted(
        target_blocks,
        key=lambda b: (not b["is_whole_fn"], b["file"], b["start_line"]),
    )
    reported_fn_sites: Set[Tuple[str, str]] = set()

    for blk in ordered_targets:
        matches = index.get(blk["hash"], [])
        for other in matches:
            if other["file"] == blk["file"]:
                if blk["function"] != "<block>" and other["function"] == blk["function"]:
                    continue
                if (
                    abs(other["start_line"] - blk["start_line"]) < min_stmts
                    or (
                        blk["start_line"] <= other["end_line"]
                        and other["start_line"] <= blk["end_line"]
                    )
                ):
                    continue
            site_key = (blk["file"], blk["function"])
            if blk["function"] != "<block>" and site_key in reported_fn_sites:
                continue
            pair_key = tuple(sorted([
                (blk["file"], str(blk["function"]), str(blk["start_line"])),
                (other["file"], str(other["function"]), str(other["start_line"])),
            ]))
            flat_key = (
                pair_key[0][0],
                pair_key[0][1],
                pair_key[1][0],
                pair_key[1][1],
            )
            if flat_key in reported_pairs:
                continue
            reported_pairs.add(flat_key)
            if blk["function"] != "<block>":
                reported_fn_sites.add(site_key)
            loc_other = (
                f"{other['file']}:{other['start_line']} ({other['function']})"
                if other["function"] != "<block>"
                else f"{other['file']}:{other['start_line']}"
            )
            fn_label = f" in '{blk['function']}'" if blk["function"] != "<block>" else ""
            findings.append(
                _finding(
                    code="STRUCT-DUPLICATE-BLOCK",
                    severity=severity,
                    file=blk["file"],
                    line=blk["start_line"],
                    message=(
                        f"{blk['file']}:{blk['start_line']}{fn_label} duplicates a {blk['stmts']}-statement "
                        f"logic block already present at {loc_other}."
                    ),
                    remediation="Extract or reuse one shared canonical helper instead of maintaining copy-pasted logic in multiple places.",
                    meta={
                        "duplicate_of": other["file"],
                        "duplicate_line": other["start_line"],
                        "duplicate_function": other["function"],
                    },
                )
            )
            break
    return findings


def _repo_mentions_symbol(
    symbol: str,
    *,
    exclude_rel: str,
    repo_root: Optional[Path],
    extra_sources: Optional[Dict[str, str]] = None,
) -> bool:
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    override_paths: Set[str] = set()
    if extra_sources:
        for rel, text in extra_sources.items():
            override_paths.add(rel)
            if rel == exclude_rel:
                continue
            if pattern.search(text):
                return True
    if repo_root is not None:
        root = repo_root.resolve()
        skip_bench = not exclude_rel.startswith("benchmarks/sources/")
        for disk_path in _iter_repo_code_files(
            root, include_tests=True, skip_benchmark_sources=skip_bench
        ):
            rel = str(disk_path.relative_to(root)).replace("\\", "/")
            if rel == exclude_rel or rel in override_paths:
                continue
            try:
                if pattern.search(disk_path.read_text(encoding="utf-8")):
                    return True
            except (OSError, UnicodeDecodeError):
                continue
    return False


def _extract_dunder_all(tree: ast.Module) -> Set[str]:
    exported: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported.add(elt.value)
    return exported


def _iter_func_arg_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterable[Tuple[ast.arg, Optional[ast.expr]]]:
    pos_args = list(node.args.posonlyargs) + list(node.args.args)
    pos_defaults: List[Optional[ast.expr]] = [None] * (
        len(pos_args) - len(node.args.defaults)
    ) + list(node.args.defaults)
    for arg, default_node in zip(pos_args, pos_defaults):
        yield arg, default_node
    for arg, default_node in zip(node.args.kwonlyargs, node.args.kw_defaults):
        yield arg, default_node


def _is_legacy_compat_param(arg: ast.arg, default_node: Optional[ast.expr]) -> bool:
    if LEGACY_FLAG_PARAM_RE.search(arg.arg):
        return True
    if not LEGACY_PREFIX_PARAM_RE.match(arg.arg):
        return False
    if isinstance(default_node, ast.Constant) and isinstance(default_node.value, bool):
        return True
    ann = arg.annotation
    if isinstance(ann, ast.Name) and ann.id == "bool":
        return True
    if isinstance(ann, ast.Constant) and ann.value == "bool":
        return True
    return False


def check_dead_compat_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
    repo_root: Optional[Path] = None,
    extra_sources: Optional[Dict[str, str]] = None,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect unreachable dead branches, unreferenced legacy/compat shims, and orphaned private helpers."""
    if not _dc._is_code_path(rel_path) or _dc._is_test_file(rel_path):
        return []
    if Path(rel_path).suffix.lower() != ".py":
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    findings: List[Dict[str, Any]] = []
    exported = _extract_dunder_all(tree)

    # Collect all name/attribute references across the module for orphan detection.
    name_loads: Dict[str, List[int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            name_loads.setdefault(node.id, []).append(node.lineno)
        elif isinstance(node, ast.Attribute):
            name_loads.setdefault(node.attr, []).append(node.lineno)

    # 1. Unreachable constant-False branches (`if False:`, `if 0:`, `if None:`).
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_dead = (
                isinstance(test, ast.Constant)
                and test.value in (False, 0, None, "")
            )
            if is_dead and (added_lines is None or node.lineno in added_lines):
                findings.append(
                    _finding(
                        code="STRUCT-DEAD-COMPAT",
                        severity=severity,
                        file=rel_path,
                        line=node.lineno,
                        message=f"{rel_path}:{node.lineno} contains an unreachable dead branch ('if {test.value!r}:').",
                        remediation="Delete dead code paths instead of disabling them behind constant-False branches.",
                        meta={"kind": "unreachable_branch"},
                    )
                )

    def _inspect_def(
        node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
        *,
        qual_name: str,
        check_orphan_private: bool,
    ) -> None:
        name = node.name
        if not _function_overlaps_added(node, added_lines):
            return
        start_ln = node.lineno
        end_ln = getattr(node, "end_lineno", start_ln) or start_ln
        external_in_module = [
            ln for ln in name_loads.get(name, [])
            if not (start_ln <= ln <= end_ln)
        ]

        # Legacy/compat named symbol with zero callers in module or repo.
        if LEGACY_NAME_RE.search(name):
            if not external_in_module and not _repo_mentions_symbol(
                name,
                exclude_rel=rel_path,
                repo_root=repo_root,
                extra_sources=extra_sources,
            ):
                findings.append(
                    _finding(
                        code="STRUCT-DEAD-COMPAT",
                        severity=severity,
                        file=rel_path,
                        line=start_ln,
                        message=(
                            f"{rel_path}:{start_ln} defines legacy/compat symbol '{qual_name}' "
                            f"with zero callers found in this file or repository."
                        ),
                        remediation="Remove obsolete compatibility shims cleanly instead of leaving unreferenced legacy paths behind.",
                        meta={"kind": "dead_legacy_symbol", "symbol": qual_name},
                    )
                )
                return

        # Legacy/compat parameter flag on a function or method.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg, default_node in _iter_func_arg_defaults(node):
                if _is_legacy_compat_param(arg, default_node):
                    if added_lines is None or arg.lineno in added_lines or start_ln in added_lines:
                        findings.append(
                            _finding(
                                code="STRUCT-DEAD-COMPAT",
                                severity=severity,
                                file=rel_path,
                                line=arg.lineno,
                                message=(
                                    f"{rel_path}:{arg.lineno} keeps or adds legacy compatibility flag "
                                    f"'{arg.arg}' on '{qual_name}'."
                                ),
                                remediation="Migrate callers to the canonical path and remove legacy compatibility flags unless explicitly required by a public contract.",
                                meta={"kind": "legacy_param", "symbol": qual_name, "param": arg.arg},
                            )
                        )

        # Orphaned private top-level helper (only when undecorated and unexported).
        if (
            check_orphan_private
            and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and name.startswith("_")
            and not name.startswith("__")
            and not node.decorator_list
            and name not in exported
            and not external_in_module
            and not _repo_mentions_symbol(
                name,
                exclude_rel=rel_path,
                repo_root=repo_root,
                extra_sources=extra_sources,
            )
        ):
            findings.append(
                _finding(
                    code="STRUCT-DEAD-COMPAT",
                    severity=severity,
                    file=rel_path,
                    line=start_ln,
                    message=f"{rel_path}:{start_ln} defines private helper '{name}' that is never called.",
                    remediation="Remove unused private helpers left behind after edits or wire them into the active code path.",
                    meta={"kind": "orphaned_private_helper", "symbol": name},
                )
            )

    # 2. Top-level functions, classes, and class methods.
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _inspect_def(node, qual_name=node.name, check_orphan_private=True)
        elif isinstance(node, ast.ClassDef):
            _inspect_def(node, qual_name=node.name, check_orphan_private=False)
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _inspect_def(
                        member,
                        qual_name=f"{node.name}.{member.name}",
                        check_orphan_private=False,
                    )

    return findings


def _count_py_non_blank_code_lines(
    source: str,
    start_line: int,
    end_line: int,
    *,
    docstring_lines: Optional[Set[int]] = None,
) -> int:
    comment_only_lines: Set[int] = set()
    code_lines: Set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            ln = tok.start[0]
            if ln < start_line or ln > end_line:
                continue
            if tok.type in (
                tokenize.NL,
                tokenize.NEWLINE,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.ENDMARKER,
                tokenize.ENCODING,
            ):
                continue
            if tok.type == tokenize.COMMENT:
                comment_only_lines.add(ln)
            else:
                code_lines.add(ln)
    except (tokenize.TokenError, IndentationError):
        lines = source.splitlines()[start_line - 1 : end_line]
        return sum(1 for ln in lines if ln.strip() and not ln.strip().startswith("#"))

    if docstring_lines:
        code_lines -= docstring_lines
    _ = comment_only_lines
    return len(code_lines)


def _py_branch_count(node: ast.AST) -> int:
    branches = 0
    for sub in ast.walk(node):
        if isinstance(
            sub,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
                ast.IfExp,
            ),
        ):
            branches += 1
        elif isinstance(sub, ast.BoolOp):
            branches += max(0, len(sub.values) - 1)
        elif isinstance(sub, ast.comprehension):
            branches += len(sub.ifs)
        elif hasattr(ast, "match_case") and isinstance(sub, ast.match_case):
            branches += 1
    return branches


def _docstring_line_range(body: List[ast.stmt]) -> Set[int]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        start = body[0].lineno
        end = getattr(body[0], "end_lineno", start) or start
        return set(range(start, end + 1))
    return set()


def check_god_growth_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
    net_loc_delta: Optional[int] = None,
    max_func_lines: int = DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = DEFAULT_MAX_FILE_LINES,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect god-function complexity/size growth and growing god-files."""
    if not _dc._is_code_path(rel_path) or _dc._is_test_file(rel_path):
        return []

    findings: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        total_code_lines = _count_py_non_blank_code_lines(source, 1, len(source.splitlines()))
        # In diff mode, only flag god-file when the diff actually grew the file (net_loc_delta > 0).
        if max_file_lines > 0 and total_code_lines > max_file_lines and (
            net_loc_delta is None or net_loc_delta > 0
        ):
            delta_note = f" (grew +{net_loc_delta} net LOC)" if net_loc_delta is not None else ""
            findings.append(
                _finding(
                    code="STRUCT-GOD-FILE",
                    severity=severity,
                    file=rel_path,
                    line=1,
                    message=(
                        f"{rel_path} has {total_code_lines} non-blank code lines{delta_note}, "
                        f"exceeding the {max_file_lines}-line modularity threshold [Heuristic]."
                    ),
                    remediation="Split distinct responsibilities into cohesive modules before adding more features to this file.",
                    meta={"code_lines": total_code_lines, "threshold": max_file_lines},
                )
            )

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _function_overlaps_added(node, added_lines):
                continue
            end_ln = getattr(node, "end_lineno", node.lineno) or node.lineno
            doc_lines = _docstring_line_range(node.body)
            fn_lines = _count_py_non_blank_code_lines(
                source,
                node.lineno,
                end_ln,
                docstring_lines=doc_lines,
            )
            branches = _py_branch_count(node)
            exceeds_lines = max_func_lines > 0 and fn_lines > max_func_lines
            exceeds_branches = max_func_branches > 0 and branches > max_func_branches
            if exceeds_lines or exceeds_branches:
                reasons: List[str] = []
                if exceeds_lines:
                    reasons.append(f"{fn_lines} code lines > {max_func_lines}")
                if exceeds_branches:
                    reasons.append(f"{branches} branches > {max_func_branches}")
                findings.append(
                    _finding(
                        code="STRUCT-GOD-FUNCTION",
                        severity=severity,
                        file=rel_path,
                        line=node.lineno,
                        message=(
                            f"{rel_path}:{node.lineno} function '{node.name}' is growing too complex "
                            f"({', '.join(reasons)}) [Heuristic]."
                        ),
                        remediation="Break the function into smaller single-responsibility helpers with clear inputs and return types.",
                        meta={
                            "function": node.name,
                            "code_lines": fn_lines,
                            "branches": branches,
                        },
                    )
                )
        return findings

    if _dc._is_js_ts_path(rel_path) or _dc._is_go_path(rel_path):
        code_lines, _ = _dc._scan_c_like_lines(source.splitlines())
        non_blank = sum(1 for ln in code_lines if ln.strip())
        if max_file_lines > 0 and non_blank > max_file_lines and (
            net_loc_delta is None or net_loc_delta > 0
        ):
            delta_note = f" (grew +{net_loc_delta} net LOC)" if net_loc_delta is not None else ""
            findings.append(
                _finding(
                    code="STRUCT-GOD-FILE",
                    severity=severity,
                    file=rel_path,
                    line=1,
                    message=(
                        f"{rel_path} has {non_blank} non-blank code lines{delta_note}, exceeding the "
                        f"{max_file_lines}-line modularity threshold [Heuristic]."
                    ),
                    remediation="Split distinct responsibilities into cohesive modules before growing this file further.",
                    meta={"code_lines": non_blank, "threshold": max_file_lines},
                )
            )

        is_go = _dc._is_go_path(rel_path)
        n = len(code_lines)
        i = 0
        while i < n:
            if is_go:
                m = GO_FUNC_START_RE.match(code_lines[i])
                fn_name = m.group(1) if m else ""
            else:
                m = JS_FUNC_START_RE.match(code_lines[i])
                fn_name = (m.group(1) or m.group(2) or "<anonymous>") if m else ""
            if m:
                start_ln = i + 1
                depth = code_lines[i].count("{") - code_lines[i].count("}")
                j = i + 1
                # Handle Go signatures where `{` is on the next line.
                while j < n and depth == 0 and "{" not in code_lines[i]:
                    depth += code_lines[j].count("{") - code_lines[j].count("}")
                    j += 1
                    if depth > 0:
                        break
                while j < n and depth > 0:
                    depth += code_lines[j].count("{") - code_lines[j].count("}")
                    j += 1
                end_ln = j
                overlaps = added_lines is None or any(start_ln <= ln <= end_ln for ln in added_lines)
                if overlaps:
                    fn_non_blank = sum(1 for ln in code_lines[i:j] if ln.strip())
                    if max_func_lines > 0 and fn_non_blank > max_func_lines:
                        findings.append(
                            _finding(
                                code="STRUCT-GOD-FUNCTION",
                                severity=severity,
                                file=rel_path,
                                line=start_ln,
                                message=(
                                    f"{rel_path}:{start_ln} function '{fn_name}' has {fn_non_blank} "
                                    f"code lines > {max_func_lines} [Heuristic]."
                                ),
                                remediation="Split the function into smaller focused helpers.",
                                meta={"function": fn_name, "code_lines": fn_non_blank},
                            )
                        )
                i = max(j, i + 1)
                continue
            i += 1
    return findings


def _module_bucket(rel_path: str) -> str:
    parts = [p for p in _dc._normalize_relpath(rel_path).split("/") if p]
    if len(parts) <= 1:
        return "<root>"
    if parts[0] in ("src", "lib", "packages", "apps") and len(parts) >= 3:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def check_scope_sprawl(
    paths: Sequence[str],
    *,
    max_module_spread: int = DEFAULT_MAX_MODULE_SPREAD,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect scope-creep sprawl touching too many unrelated production module directories."""
    if max_module_spread <= 0:
        return []
    prod_files: List[str] = []
    buckets: Set[str] = set()
    for raw in paths:
        norm = _dc._normalize_relpath(raw)
        if not norm:
            continue
        if _dc._is_test_file(norm) or _dc._is_markdown_path(norm):
            continue
        if norm.startswith("docs/"):
            continue
        if _dc._is_code_path(norm):
            prod_files.append(norm)
            buckets.add(_module_bucket(norm))

    if len(buckets) > max_module_spread and len(prod_files) >= max_module_spread + 1:
        sorted_buckets = sorted(buckets)
        return [
            _finding(
                code="STRUCT-SCOPE-SPRAWL",
                severity=severity,
                message=(
                    f"Single change spans {len(buckets)} unrelated production areas "
                    f"({', '.join(sorted_buckets)}) across {len(prod_files)} code files "
                    f"(limit: <= {max_module_spread}) [Heuristic]."
                ),
                remediation="Keep each AI turn and PR focused on one module or split unrelated cleanups into separate changes.",
                meta={
                    "module_areas": sorted_buckets,
                    "prod_files": len(prod_files),
                    "limit": max_module_spread,
                },
            )
        ]
    return []


def check_structural_diff(
    diff_text: str,
    *,
    repo_root: Optional[Path | str] = None,
    strict_structural: bool = False,
    max_func_lines: int = DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = DEFAULT_MAX_FILE_LINES,
    max_module_spread: int = DEFAULT_MAX_MODULE_SPREAD,
) -> Dict[str, Any]:
    """Run all structural compounding-slop checks on a unified diff."""
    parsed = _dc.parse_unified_diff(diff_text)
    files = parsed["files"]
    root_path = Path(repo_root).resolve() if repo_root is not None else None
    severity = _sev(strict_structural)
    findings: List[Dict[str, Any]] = []

    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]] = {}
    extra_texts: Dict[str, str] = {}
    changed_paths: List[str] = []

    for entry in files:
        path = entry["path"]
        if not path or entry["is_deleted"]:
            continue
        changed_paths.append(path)
        if not _dc._is_code_path(path):
            continue

        added_lines = {ln for ln, _ in entry["added_lines"]}
        net_delta = len(entry["added_lines"]) - len(entry["deleted_lines"])
        if not added_lines:
            continue

        source: Optional[str] = None
        if root_path is not None and (root_path / path).is_file():
            try:
                source = (root_path / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        elif entry["is_new"]:
            source = "\n".join(text for _, text in entry["added_lines"])

        if source is not None:
            target_sources[path] = (source, added_lines)
            extra_texts[path] = source
            findings.extend(
                check_test_theater_in_source(
                    path, source, added_lines=added_lines, repo_root=root_path, severity=severity
                )
            )
            findings.extend(
                check_silent_fallbacks_in_source(
                    path, source, added_lines=added_lines, severity=severity
                )
            )
            findings.extend(
                check_god_growth_in_source(
                    path,
                    source,
                    added_lines=added_lines,
                    net_loc_delta=net_delta,
                    max_func_lines=max_func_lines,
                    max_func_branches=max_func_branches,
                    max_file_lines=max_file_lines,
                    severity=severity,
                )
            )
        else:
            # Hunk-only fallback when full file is unavailable on disk.
            for hunk in entry["hunks"]:
                visible = [(k, ln, txt) for k, ln, txt in hunk["lines"] if k != "-"]
                if not visible:
                    continue
                added_1based = {i + 1 for i, (k, _, _) in enumerate(visible) if k == "+"}
                if not added_1based:
                    continue
                hunk_text = "\n".join(txt for _, _, txt in visible)
                line_map = {i + 1: ln for i, (_, ln, _) in enumerate(visible)}
                raw: List[Dict[str, Any]] = []
                raw.extend(
                    check_test_theater_in_source(
                        path, hunk_text, added_lines=added_1based, severity=severity
                    )
                )
                raw.extend(
                    check_silent_fallbacks_in_source(
                        path, hunk_text, added_lines=added_1based, severity=severity
                    )
                )
                findings.extend(_dc._remap_finding_lines(raw, path, line_map))

    # Cross-file checks (dead compat + duplicate blocks + scope sprawl).
    for path, (source, added_lines) in sorted(target_sources.items()):
        findings.extend(
            check_dead_compat_in_source(
                path,
                source,
                added_lines=added_lines,
                repo_root=root_path,
                extra_sources=extra_texts,
                severity=severity,
            )
        )

    findings.extend(
        check_duplicate_blocks(
            target_sources,
            repo_root=root_path,
            severity=severity,
        )
    )
    findings.extend(
        check_scope_sprawl(
            changed_paths,
            max_module_spread=max_module_spread,
            severity=severity,
        )
    )

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] != "error"]
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def check_structural_files(
    files: Sequence[str | Path],
    *,
    repo_root: Optional[Path | str] = None,
    strict_structural: bool = False,
    max_func_lines: int = DEFAULT_MAX_FUNC_LINES,
    max_func_branches: int = DEFAULT_MAX_FUNC_BRANCHES,
    max_file_lines: int = DEFAULT_MAX_FILE_LINES,
    max_module_spread: int = 0,
) -> Dict[str, Any]:
    """Run all structural compounding-slop checks directly on a list of files."""
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    severity = _sev(strict_structural)
    findings: List[Dict[str, Any]] = []
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]] = {}
    extra_texts: Dict[str, str] = {}
    norm_paths: List[str] = []

    for raw in files:
        p = Path(raw)
        if p.is_absolute():
            try:
                rel = str(p.resolve().relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(p).replace("\\", "/")
            disk_path = p
        else:
            rel = _dc._normalize_relpath(str(raw))
            disk_path = root / rel
        if not disk_path.is_file():
            continue
        norm_paths.append(rel)
        if not _dc._is_code_path(rel):
            continue
        try:
            text = disk_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        target_sources[rel] = (text, None)
        extra_texts[rel] = text

        findings.extend(
            check_test_theater_in_source(rel, text, repo_root=root, severity=severity)
        )
        findings.extend(check_silent_fallbacks_in_source(rel, text, severity=severity))
        findings.extend(
            check_god_growth_in_source(
                rel,
                text,
                max_func_lines=max_func_lines,
                max_func_branches=max_func_branches,
                max_file_lines=max_file_lines,
                severity=severity,
            )
        )

    for rel, (text, _) in sorted(target_sources.items()):
        findings.extend(
            check_dead_compat_in_source(
                rel,
                text,
                repo_root=root,
                extra_sources=extra_texts,
                severity=severity,
            )
        )

    findings.extend(
        check_duplicate_blocks(
            target_sources,
            repo_root=root,
            severity=severity,
        )
    )
    if max_module_spread > 0:
        findings.extend(
            check_scope_sprawl(
                norm_paths,
                max_module_spread=max_module_spread,
                severity=severity,
            )
        )

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] != "error"]
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
