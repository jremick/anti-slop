#!/usr/bin/env python3
"""AI-era architectural compounding-slop detectors for diffs and source files.

Catches cross-module architectural decay patterns that pass isolated smoke tests
but compound across future AI coding sessions:
  1. ARCH-CIRCULAR-IMPORT: static circular module dependency cycles in Python
     (skipping TYPE_CHECKING, __main__, and deferred function-local imports)
     and JS/TS (skipping import/export type-only edges and test files).
  2. ARCH-SINGLE-IMPL-WRAPPER: speculative single-implementation indirection
     (Python ABC/Protocol with <= 1 concrete implementation, or trivial
     pass-through *Factory/*Wrapper/*Impl classes; JS/TS method-bearing
     abstract classes, method-bearing interfaces with a single *Impl class,
     or trivial *Factory/*Wrapper classes).
  3. ARCH-BOUNDARY-SCATTER: raw environment-variable reads for the same
     non-runtime key scattered across >= 3 distinct production modules
     instead of centralized boundary config validation.

Zero third-party dependencies (Python 3.9+ / 3.11+ stdlib only).
"""

from __future__ import annotations

import ast
from collections import deque
from pathlib import Path
import posixpath
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402


DEFAULT_MIN_SCATTER_MODULES = 3

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

EXTRA_TEST_DIR_NAMES = frozenset({
    "test",
    "tests",
    "__tests__",
    "runtime-tests",
    "__mocks__",
    "__fixtures__",
})

DTS_SUFFIXES = (".d.ts", ".d.mts", ".d.cts")
JS_TS_RESOLVE_EXTS = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs")
JS_TO_TS_EXT_MAP: Dict[str, Tuple[str, ...]] = {
    ".js": (".ts", ".tsx", ".js", ".jsx"),
    ".jsx": (".tsx", ".ts", ".jsx", ".js"),
    ".mjs": (".mts", ".mjs"),
    ".cjs": (".cts", ".cjs"),
}

UNIVERSAL_RUNTIME_ENV_VARS = frozenset({
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "LOGNAME",
    "SHELL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "CI",
    "DEBUG",
    "NODE_ENV",
    "TERM",
    "COLORTERM",
    "NO_COLOR",
    "FORCE_COLOR",
    "TZ",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PWD",
    "OLDPWD",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "PYTHONUTF8",
    "VIRTUAL_ENV",
    "XDG_CONFIG_HOME",
    "XDG_CACHE_HOME",
    "XDG_DATA_HOME",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "all_proxy",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "APPDATA",
    "LOCALAPPDATA",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "GITHUB_ACTIONS",
})

JS_OBJECT_PROTO_PROPS = frozenset({
    "toString",
    "valueOf",
    "hasOwnProperty",
    "isPrototypeOf",
    "propertyIsEnumerable",
    "toLocaleString",
    "constructor",
    "__proto__",
})

PY_DATA_BASES = frozenset({
    "NamedTuple",
    "TypedDict",
    "Enum",
    "IntEnum",
    "StrEnum",
    "Flag",
    "IntFlag",
    "Exception",
    "BaseException",
})

PY_DATA_DECORATORS = frozenset({
    "dataclass",
    "attrs",
    "define",
    "frozen",
})

PY_PROTOCOL_TYPING_DUNDERS = frozenset({
    "__call__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__iter__",
    "__aiter__",
    "__next__",
    "__anext__",
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__len__",
    "__contains__",
    "__fspath__",
    "__bool__",
    "__bytes__",
    "__str__",
    "__repr__",
    "__hash__",
    "__eq__",
    "__lt__",
    "__le__",
    "__gt__",
    "__ge__",
    "__buffer__",
    "__index__",
    "__int__",
    "__float__",
    "__copy__",
    "__deepcopy__",
})

JS_IMPORT_FROM_RE = re.compile(
    r"(?:^|[;\n])[ \t]*(import)\s+(type\s+)?([\s\S]*?)\s+from\s+(['\"])([^'\"\n]+)\4",
)
JS_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"(?:^|[;\n])[ \t]*(import)\s+(['\"])([^'\"\n]+)\2",
)
JS_EXPORT_FROM_RE = re.compile(
    r"(?:^|[;\n])[ \t]*(export)\s+(type\s+)?(\*(?:\s+as\s+[A-Za-z_$][\w$]*)?|\{[\s\S]*?\})\s+from\s+(['\"])([^'\"\n]+)\4",
)
JS_REQUIRE_RE = re.compile(
    r"(?<![.\w$])require\s*\(\s*(['\"])([^'\"\n]+)\1\s*\)",
)

JS_ENV_DOT_RE = re.compile(
    r"(?<![.\w$])process\s*\.\s*env\s*(?:\?\.)?\s*\.\s*([A-Za-z_$][A-Za-z0-9_$]*)(?!\s*=(?!=))",
)
JS_ENV_BRACKET_RE = re.compile(
    r"(?<![.\w$])process\s*\.\s*env\s*(?:\?\.)?\s*\[\s*(['\"])([^'\"\n]+)\1\s*\](?!\s*=(?!=))",
)

JS_CLASS_DECL_RE = re.compile(
    r"^\s*(export\s+)?(?:default\s+)?(?:declare\s+)?(abstract\s+)?class\s+([A-Za-z_$][\w$]*)\b(.*)$"
)
JS_INTERFACE_DECL_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?interface\s+([A-Za-z_$][\w$]*)\b(.*)$"
)
JS_REGEX_PREFIX_KEYWORDS = frozenset({
    "return",
    "case",
    "throw",
    "in",
    "of",
    "typeof",
    "void",
    "delete",
    "new",
    "yield",
    "await",
    "else",
    "do",
})
JS_METHOD_SIG_RE = re.compile(
    r"^\s*(?:public\s+|private\s+|protected\s+|readonly\s+|static\s+|abstract\s+|async\s+|override\s+)*"
    r"([A-Za-z_$][\w$]*)\s*(?:<[^>{};]*>)?\s*\([^)]*\)\s*(?::\s*[^;{]+)?\s*(?:;|\{)"
)
JS_NEW_CALL_RE = re.compile(r"\bnew\s+([A-Z][A-Za-z0-9_$]*)\s*(?:<[^>]*>)?\s*\(")
JS_DELEGATE_STMT_RE = re.compile(
    r"^(?:return\s+)?(?:await\s+)?this\.([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)\s*\(([^;{}]*)\)\s*;?$"
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


def _is_dts_path(rel_path: str) -> bool:
    low = rel_path.lower()
    return any(low.endswith(suf) for suf in DTS_SUFFIXES)


def _is_test_or_excluded_module(rel_path: str) -> bool:
    norm = _dc._normalize_relpath(rel_path)
    if not norm:
        return True
    if _dc._is_test_file(norm):
        return True
    if _is_dts_path(norm):
        return True
    parts = norm.split("/")
    if any(part in EXTRA_TEST_DIR_NAMES for part in parts[:-1]):
        return True
    leaf = parts[-1].lower()
    if leaf.endswith((".test-d.ts", ".spec-d.ts", ".stories.ts", ".stories.tsx")):
        return True
    return False


def _is_supported_arch_module(rel_path: str) -> bool:
    if _is_test_or_excluded_module(rel_path):
        return False
    suffix = Path(rel_path).suffix.lower()
    return suffix == ".py" or _dc._is_js_ts_path(rel_path)


def _bench_case_prefix(rel_path: str) -> Optional[str]:
    norm = _dc._normalize_relpath(rel_path)
    parts = norm.split("/")
    if len(parts) >= 3 and parts[0] == "benchmarks" and parts[1] == "sources":
        return f"benchmarks/sources/{parts[2]}/"
    return None


def _collect_production_sources(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    repo_root: Optional[Path] = None,
) -> Tuple[Dict[str, str], Set[str]]:
    """Return (all_prod_sources, prod_target_paths) with target_sources overriding disk."""
    all_sources: Dict[str, str] = {}
    prod_targets: Set[str] = set()
    bench_prefixes: Set[str] = set()

    for raw_rel, (text, _) in sorted(target_sources.items()):
        rel = _dc._normalize_relpath(raw_rel)
        if not _is_supported_arch_module(rel):
            continue
        all_sources[rel] = text
        prod_targets.add(rel)
        bpref = _bench_case_prefix(rel)
        if bpref is not None:
            bench_prefixes.add(bpref)

    if repo_root is not None:
        root = repo_root.resolve()
        if root.is_dir():
            for disk_path in sorted(root.rglob("*")):
                if not disk_path.is_file():
                    continue
                try:
                    rel_parts = disk_path.relative_to(root).parts
                except ValueError:
                    continue
                if any(part in EXCLUDED_SCAN_DIRS for part in rel_parts):
                    continue
                rel = "/".join(rel_parts)
                if len(rel_parts) >= 2 and rel_parts[:2] == ("benchmarks", "sources"):
                    if not bench_prefixes or not any(rel.startswith(p) for p in bench_prefixes):
                        continue
                if rel in all_sources:
                    continue
                if not _is_supported_arch_module(rel):
                    continue
                try:
                    all_sources[rel] = disk_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue

    return all_sources, prod_targets


def _can_start_js_regex(out: Sequence[str]) -> bool:
    """Return True if a `/` at this position in JS/TS can begin a regex literal rather than division."""
    j = len(out) - 1
    while j >= 0 and out[j] in (" ", "\t", "\r", "\n"):
        j -= 1
    if j < 0:
        return True
    prev = out[j]
    if prev in "([{:;,=!?&|+-*%^~<>":
        return True
    if prev.isalnum() or prev in ("_", "$"):
        k = j
        while k >= 0 and (out[k].isalnum() or out[k] in ("_", "$")):
            k -= 1
        word = "".join(out[k + 1 : j + 1])
        return word in JS_REGEX_PREFIX_KEYWORDS
    return False


def _strip_js_comments_and_templates(source: str) -> str:
    """Strip // and /* */ comments and mask template-literal & regex bodies while preserving newlines and quotes."""
    out: List[str] = []
    i = 0
    n = len(source)
    in_single = False
    in_double = False
    in_template = False
    in_regex = False
    in_regex_class = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if in_regex:
            if ch == "\n":
                in_regex = False
                in_regex_class = False
                out.append("\n")
                i += 1
                continue
            if ch == "\\" and i + 1 < n and nxt != "\n":
                out.append("  ")
                i += 2
                continue
            if ch == "[":
                in_regex_class = True
            elif ch == "]":
                in_regex_class = False
            elif ch == "/" and not in_regex_class:
                in_regex = False
                out.append("/")
                i += 1
                continue
            out.append(" ")
            i += 1
            continue

        if in_single or in_double:
            q = "'" if in_single else '"'
            if ch == "\\" and i + 1 < n:
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            out.append(ch)
            if ch == q:
                in_single = False
                in_double = False
            i += 1
            continue

        if in_template:
            if ch == "\\" and i + 1 < n:
                out.append(" " if nxt != "\n" else "\n")
                out.append(" ")
                i += 2
                continue
            if ch == "`":
                in_template = False
                out.append("`")
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue

        if ch == "/" and nxt == "/":
            in_line_comment = True
            out.append("  ")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            out.append("  ")
            i += 2
            continue
        if ch == "/" and _can_start_js_regex(out):
            in_regex = True
            in_regex_class = False
            out.append("/")
            i += 1
            continue
        if ch == "'":
            in_single = True
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue
        if ch == "`":
            in_template = True
            out.append("`")
            i += 1
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def _offset_to_lineno(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------------------
# 1. ARCH-CIRCULAR-IMPORT
# ---------------------------------------------------------------------------

def _is_type_checking_expr(expr: ast.expr, aliases: Dict[str, str]) -> bool:
    if isinstance(expr, ast.Name):
        resolved = _dc._resolve_dotted(expr.id, aliases)
        return expr.id == "TYPE_CHECKING" or resolved.endswith(".TYPE_CHECKING")
    if isinstance(expr, ast.Attribute):
        resolved = _dc._resolve_dotted(_dc._dotted_name(expr), aliases)
        return expr.attr == "TYPE_CHECKING" or resolved.endswith(".TYPE_CHECKING")
    if isinstance(expr, ast.BoolOp) and isinstance(expr.op, ast.And):
        return any(_is_type_checking_expr(val, aliases) for val in expr.values)
    return False


def _is_not_type_checking_expr(expr: ast.expr, aliases: Dict[str, str]) -> bool:
    return isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not) and _is_type_checking_expr(
        expr.operand, aliases
    )


def _is_main_guard_expr(expr: ast.expr) -> bool:
    if not isinstance(expr, ast.Compare) or len(expr.ops) != 1 or len(expr.comparators) != 1:
        return False
    if not isinstance(expr.ops[0], ast.Eq):
        return False
    left, right = expr.left, expr.comparators[0]
    if isinstance(left, ast.Name) and left.id == "__name__" and isinstance(right, ast.Constant) and right.value == "__main__":
        return True
    if isinstance(right, ast.Name) and right.id == "__name__" and isinstance(left, ast.Constant) and left.value == "__main__":
        return True
    return False


def _iter_py_static_imports(
    stmts: Sequence[ast.stmt],
    aliases: Dict[str, str],
) -> Iterable[ast.stmt]:
    """Yield module/class-level Import and ImportFrom nodes, skipping TYPE_CHECKING, __main__, and def bodies."""
    for stmt in stmts:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            yield stmt
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Function-local imports are deferred at call time, not static import-time cycles.
            continue
        elif isinstance(stmt, ast.ClassDef):
            yield from _iter_py_static_imports(stmt.body, aliases)
        elif isinstance(stmt, ast.If):
            test = stmt.test
            if _is_type_checking_expr(test, aliases) or _is_main_guard_expr(test):
                yield from _iter_py_static_imports(stmt.orelse, aliases)
            elif _is_not_type_checking_expr(test, aliases):
                yield from _iter_py_static_imports(stmt.body, aliases)
            elif isinstance(test, ast.Constant) and not bool(test.value):
                yield from _iter_py_static_imports(stmt.orelse, aliases)
            else:
                yield from _iter_py_static_imports(stmt.body, aliases)
                yield from _iter_py_static_imports(stmt.orelse, aliases)
        elif isinstance(stmt, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While)):
            yield from _iter_py_static_imports(stmt.body, aliases)
            if hasattr(stmt, "orelse"):
                yield from _iter_py_static_imports(stmt.orelse, aliases)
        elif isinstance(stmt, ast.Try):
            yield from _iter_py_static_imports(stmt.body, aliases)
            for handler in stmt.handlers:
                yield from _iter_py_static_imports(handler.body, aliases)
            yield from _iter_py_static_imports(stmt.orelse, aliases)
            yield from _iter_py_static_imports(stmt.finalbody, aliases)
        elif hasattr(ast, "TryStar") and isinstance(stmt, ast.TryStar):
            yield from _iter_py_static_imports(stmt.body, aliases)
            for handler in stmt.handlers:
                yield from _iter_py_static_imports(handler.body, aliases)
            yield from _iter_py_static_imports(stmt.orelse, aliases)
            yield from _iter_py_static_imports(stmt.finalbody, aliases)


def _build_py_module_index(py_files: Iterable[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Return (dotted_name -> rel_path, rel_path -> primary_dotted_name)."""
    mod_to_file: Dict[str, str] = {}
    file_to_mod: Dict[str, str] = {}

    for rel in sorted(py_files):
        parts = rel.split("/")
        if parts[-1] == "__init__.py":
            mod_parts = parts[:-1]
        else:
            mod_parts = parts[:-1] + [parts[-1][:-3]]
        if not mod_parts:
            continue

        full_mod = ".".join(mod_parts)
        mod_to_file.setdefault(full_mod, rel)
        primary = full_mod

        # Support src/ and lib/ package layouts (e.g. src/urllib3/util/retry.py -> urllib3.util.retry).
        if len(mod_parts) >= 2 and mod_parts[0] in ("src", "lib", "python"):
            stripped_mod = ".".join(mod_parts[1:])
            mod_to_file.setdefault(stripped_mod, rel)
            primary = stripped_mod
        elif len(mod_parts) >= 4 and mod_parts[:2] == ["benchmarks", "sources"]:
            # Support scanning directly inside benchmarks/sources/<case>/...
            case_mod = ".".join(mod_parts[3:])
            if case_mod:
                mod_to_file.setdefault(case_mod, rel)
                primary = case_mod

        file_to_mod[rel] = primary

    return mod_to_file, file_to_mod


def _resolve_py_relative_file(
    importer_rel: str,
    level: int,
    module: Optional[str],
    py_file_set: Set[str],
) -> Optional[str]:
    parts = importer_rel.split("/")
    # Package directory of the importing module.
    pkg_dir = parts[:-1]
    ascend = max(0, level - 1)
    if ascend > len(pkg_dir):
        return None
    base_parts = pkg_dir[: len(pkg_dir) - ascend]
    mod_parts = module.split(".") if module else []
    target_parts = base_parts + mod_parts
    if not target_parts:
        return None
    cand_mod = "/".join(target_parts) + ".py"
    if cand_mod in py_file_set:
        return cand_mod
    cand_pkg = "/".join(target_parts) + "/__init__.py"
    if cand_pkg in py_file_set:
        return cand_pkg
    return None


def _extract_py_import_edges(
    rel_path: str,
    source: str,
    mod_to_file: Dict[str, str],
    py_file_set: Set[str],
) -> Dict[str, List[Tuple[int, int]]]:
    """Return {target_rel_path: [(start_line, end_line), ...]} for static Python imports."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    aliases = _dc._python_import_aliases(tree)
    edges: Dict[str, List[Tuple[int, int]]] = {}

    def _add_edge(dst: Optional[str], node: ast.stmt) -> None:
        if dst is None or dst == rel_path:
            return
        start_ln = getattr(node, "lineno", 1) or 1
        end_ln = getattr(node, "end_lineno", start_ln) or start_ln
        edges.setdefault(dst, []).append((start_ln, end_ln))

    for node in _iter_py_static_imports(tree.body, aliases):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                dst = mod_to_file.get(name)
                if dst is None:
                    # Try progressively shorter prefixes if importing a nested symbol/package.
                    segs = name.split(".")
                    for k in range(len(segs) - 1, 0, -1):
                        cand = mod_to_file.get(".".join(segs[:k]))
                        if cand is not None:
                            dst = cand
                            break
                _add_edge(dst, node)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            mod = node.module or ""
            if level > 0:
                base_dst = _resolve_py_relative_file(rel_path, level, mod or None, py_file_set)
                matched_sub = False
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    sub_mod = f"{mod}.{alias.name}" if mod else alias.name
                    sub_dst = _resolve_py_relative_file(rel_path, level, sub_mod, py_file_set)
                    if sub_dst is not None:
                        _add_edge(sub_dst, node)
                        matched_sub = True
                    elif base_dst is not None:
                        _add_edge(base_dst, node)
                if not matched_sub and any(a.name == "*" for a in node.names):
                    _add_edge(base_dst, node)
            elif mod:
                base_dst = mod_to_file.get(mod)
                matched_any = False
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    sub_dst = mod_to_file.get(f"{mod}.{alias.name}")
                    if sub_dst is not None:
                        _add_edge(sub_dst, node)
                        matched_any = True
                    elif base_dst is not None:
                        _add_edge(base_dst, node)
                        matched_any = True
                if not matched_any and base_dst is not None:
                    _add_edge(base_dst, node)

    return edges


def _is_js_all_type_specifiers(spec_clause: str) -> bool:
    """Return True if an import/export clause only imports inline `type` specifiers."""
    stripped = spec_clause.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    inner = stripped[1:-1].strip()
    if not inner:
        return True
    items = [part.strip() for part in inner.split(",") if part.strip()]
    if not items:
        return True
    return all(re.match(r"^type\s+[A-Za-z_$][\w$]*", item) is not None for item in items)


def _resolve_js_ts_specifier(
    importer_rel: str,
    spec: str,
    js_file_set: Set[str],
) -> Optional[str]:
    if not (spec.startswith("./") or spec.startswith("../") or spec in (".", "..")):
        return None
    importer_dir = posixpath.dirname(importer_rel)
    joined = posixpath.normpath(posixpath.join(importer_dir, spec))
    if joined.startswith("../") or joined == "..":
        return None
    if joined.startswith("./"):
        joined = joined[2:]

    if joined in js_file_set:
        return joined

    # Handle TS ESM `.js` -> `.ts` / `.tsx` extension remapping.
    dot_idx = joined.rfind(".")
    slash_idx = joined.rfind("/")
    if dot_idx > slash_idx:
        ext = joined[dot_idx:].lower()
        stem = joined[:dot_idx]
        if ext in JS_TO_TS_EXT_MAP:
            for alt_ext in JS_TO_TS_EXT_MAP[ext]:
                cand = stem + alt_ext
                if cand in js_file_set:
                    return cand

    for ext in JS_TS_RESOLVE_EXTS:
        cand = joined + ext
        if cand in js_file_set:
            return cand

    for ext in JS_TS_RESOLVE_EXTS:
        cand = posixpath.join(joined, f"index{ext}")
        if cand in js_file_set:
            return cand

    return None


def _extract_js_ts_import_edges(
    rel_path: str,
    source: str,
    js_file_set: Set[str],
) -> Dict[str, List[Tuple[int, int]]]:
    """Return {target_rel_path: [(start_line, end_line), ...]} for static JS/TS runtime imports."""
    cleaned = _strip_js_comments_and_templates(source)
    edges: Dict[str, List[Tuple[int, int]]] = {}

    def _record(spec: str, start_off: int, end_off: int) -> None:
        dst = _resolve_js_ts_specifier(rel_path, spec, js_file_set)
        if dst is None or dst == rel_path:
            return
        s_ln = _offset_to_lineno(cleaned, start_off)
        e_ln = _offset_to_lineno(cleaned, end_off)
        edges.setdefault(dst, []).append((s_ln, e_ln))

    for m in JS_IMPORT_FROM_RE.finditer(cleaned):
        if m.group(2):  # `import type ...`
            continue
        clause = m.group(3)
        if _is_js_all_type_specifiers(clause):
            continue
        _record(m.group(5), m.start(1), m.end())

    for m in JS_SIDE_EFFECT_IMPORT_RE.finditer(cleaned):
        _record(m.group(3), m.start(1), m.end())

    for m in JS_EXPORT_FROM_RE.finditer(cleaned):
        if m.group(2):  # `export type ...`
            continue
        clause = m.group(3)
        if _is_js_all_type_specifiers(clause):
            continue
        _record(m.group(5), m.start(1), m.end())

    for m in JS_REQUIRE_RE.finditer(cleaned):
        _record(m.group(2), m.start(), m.end())

    return edges


def _tarjan_sccs(graph: Dict[str, Set[str]]) -> List[Set[str]]:
    """Iterative Tarjan SCC over directed graph -> list of strongly connected component sets."""
    index = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    sccs: List[Set[str]] = []

    all_nodes = sorted(set(graph.keys()) | {dst for dsts in graph.values() for dst in dsts})
    for root in all_nodes:
        if root in indices:
            continue
        call_stack: List[Tuple[str, List[str], int]] = [(root, sorted(graph.get(root, ())), 0)]
        indices[root] = lowlink[root] = index
        index += 1
        stack.append(root)
        on_stack.add(root)

        while call_stack:
            v, neighbors, ni = call_stack[-1]
            if ni < len(neighbors):
                call_stack[-1] = (v, neighbors, ni + 1)
                w = neighbors[ni]
                if w not in indices:
                    indices[w] = lowlink[w] = index
                    index += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, sorted(graph.get(w, ())), 0))
                elif w in on_stack:
                    if indices[w] < lowlink[v]:
                        lowlink[v] = indices[w]
            else:
                call_stack.pop()
                if call_stack:
                    parent = call_stack[-1][0]
                    if lowlink[v] < lowlink[parent]:
                        lowlink[parent] = lowlink[v]
                if lowlink[v] == indices[v]:
                    comp: Set[str] = set()
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        comp.add(w)
                        if w == v:
                            break
                    sccs.append(comp)
    return sccs


def _shortest_path_in_scc(
    graph: Dict[str, Set[str]],
    scc: Set[str],
    start: str,
    goal: str,
) -> Optional[List[str]]:
    if start == goal:
        return [start]
    queue: deque[str] = deque([start])
    parent: Dict[str, Optional[str]] = {start: None}
    while queue:
        cur = queue.popleft()
        for nxt in sorted(graph.get(cur, ())):
            if nxt not in scc or nxt in parent:
                continue
            parent[nxt] = cur
            if nxt == goal:
                path: List[str] = []
                node: Optional[str] = goal
                while node is not None:
                    path.append(node)
                    node = parent[node]
                path.reverse()
                return path
            queue.append(nxt)
    return None


def _canonicalize_cycle(cycle_nodes: Sequence[str]) -> Tuple[str, ...]:
    if not cycle_nodes:
        return ()
    min_node = min(cycle_nodes)
    idx = list(cycle_nodes).index(min_node)
    return tuple(cycle_nodes[idx:]) + tuple(cycle_nodes[:idx])


def _edge_touches_added(
    spans: Sequence[Tuple[int, int]],
    added_lines: Optional[Set[int]],
) -> Optional[int]:
    if not spans:
        return None
    if added_lines is None:
        return min(s for s, _ in spans)
    matching = [s for s, e in spans if any(s <= ln <= e for ln in added_lines)]
    return min(matching) if matching else None


def check_circular_imports(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    *,
    repo_root: Optional[Path] = None,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect minimal canonical circular import cycles involving at least one target module."""
    all_sources, prod_targets = _collect_production_sources(target_sources, repo_root=repo_root)
    if not prod_targets:
        return []

    py_files = [rel for rel in all_sources if Path(rel).suffix.lower() == ".py"]
    js_files = [rel for rel in all_sources if _dc._is_js_ts_path(rel)]
    py_file_set = set(py_files)
    js_file_set = set(js_files)
    mod_to_file, _ = _build_py_module_index(py_files)

    edge_spans: Dict[str, Dict[str, List[Tuple[int, int]]]] = {}
    graph: Dict[str, Set[str]] = {}

    for rel in py_files:
        edges = _extract_py_import_edges(rel, all_sources[rel], mod_to_file, py_file_set)
        if edges:
            edge_spans[rel] = edges
            graph[rel] = set(edges.keys())

    for rel in js_files:
        edges = _extract_js_ts_import_edges(rel, all_sources[rel], js_file_set)
        if edges:
            edge_spans[rel] = edges
            graph[rel] = set(edges.keys())

    norm_added: Dict[str, Optional[Set[int]]] = {
        _dc._normalize_relpath(k): v[1] for k, v in target_sources.items()
    }
    diff_mode = any(norm_added.get(t) is not None for t in prod_targets)

    sccs = _tarjan_sccs(graph)
    canonical_cycles: Set[Tuple[str, ...]] = set()

    for scc in sccs:
        if len(scc) < 2:
            continue
        targets_in_scc = sorted(scc & prod_targets)
        if not targets_in_scc:
            continue
        for t in targets_in_scc:
            for nxt in sorted(graph.get(t, ())):
                if nxt not in scc:
                    continue
                path = _shortest_path_in_scc(graph, scc, nxt, t)
                if path is not None:
                    # path is [nxt, ..., t]; cycle order is [t, nxt, ..., prev]
                    cycle_nodes = [t] + path[:-1]
                    canonical_cycles.add(_canonicalize_cycle(cycle_nodes))

    findings: List[Dict[str, Any]] = []
    for canon in sorted(canonical_cycles):
        cycle_len = len(canon)
        # In diff mode, only flag cycles where at least one cyclic import edge was added/edited.
        report_file: Optional[str] = None
        report_line: Optional[int] = None

        for idx, src in enumerate(canon):
            if src not in prod_targets:
                continue
            dst = canon[(idx + 1) % cycle_len]
            spans = edge_spans.get(src, {}).get(dst, [])
            hit_line = _edge_touches_added(spans, norm_added.get(src))
            if hit_line is not None:
                report_file = src
                report_line = hit_line
                break

        if report_file is None:
            if diff_mode:
                continue
            # File-scan fallback: pick first target in canonical order.
            for idx, src in enumerate(canon):
                if src in prod_targets:
                    dst = canon[(idx + 1) % cycle_len]
                    spans = edge_spans.get(src, {}).get(dst, [])
                    report_file = src
                    report_line = min((s for s, _ in spans), default=1)
                    break

        if report_file is None:
            continue

        chain = " -> ".join(list(canon) + [canon[0]])
        findings.append(
            _finding(
                code="ARCH-CIRCULAR-IMPORT",
                severity=severity,
                file=report_file,
                line=report_line,
                message=(
                    f"{report_file}:{report_line} participates in a circular import cycle: {chain}."
                ),
                remediation=(
                    "Break the cycle by extracting shared types/contracts into a lower-level module "
                    "or moving type-only imports behind `if TYPE_CHECKING:` / `import type`."
                ),
                meta={
                    "cycle": list(canon),
                    "chain": chain,
                    "length": cycle_len,
                },
            )
        )

    return findings


# ---------------------------------------------------------------------------
# 2. ARCH-SINGLE-IMPL-WRAPPER
# ---------------------------------------------------------------------------

def _py_extract_dunder_all(tree: ast.Module) -> Set[str]:
    exported: Set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                exported.add(elt.value)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == "__all__":
            if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        exported.add(elt.value)
    return exported


def _py_class_is_data_or_exception(cls: ast.ClassDef) -> bool:
    for dec in cls.decorator_list:
        if _dc._decorator_name(dec) in PY_DATA_DECORATORS:
            return True
    for base in cls.bases:
        bname = _dc._base_name(base)
        if bname in PY_DATA_BASES or bname.endswith(("Error", "Exception")):
            return True
    return False


def _py_class_kind(cls: ast.ClassDef) -> str:
    """Return 'protocol', 'abc', or 'concrete'."""
    for base in cls.bases:
        bname = _dc._base_name(base)
        if bname == "Protocol":
            return "protocol"
    for base in cls.bases:
        bname = _dc._base_name(base)
        if bname in ("ABC", "ABCMeta"):
            return "abc"
    for kw in cls.keywords:
        if kw.arg == "metaclass" and _dc._base_name(kw.value) == "ABCMeta":
            return "abc"
    for item in cls.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in item.decorator_list:
                if _dc._decorator_name(dec) in (
                    "abstractmethod",
                    "abstractclassmethod",
                    "abstractstaticmethod",
                    "abstractproperty",
                ):
                    return "abc"
    return "concrete"


def _py_class_methods(cls: ast.ClassDef) -> List[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def _py_class_non_dunder_method_names(cls: ast.ClassDef) -> Set[str]:
    return {
        fn.name
        for fn in _py_class_methods(cls)
        if not (fn.name.startswith("__") and fn.name.endswith("__"))
    }


def _iter_py_runtime_classes(
    stmts: Sequence[ast.stmt],
    aliases: Dict[str, str],
) -> Iterable[ast.ClassDef]:
    """Yield runtime top-level/nested classes, skipping `if TYPE_CHECKING:` blocks."""
    for stmt in stmts:
        if isinstance(stmt, ast.ClassDef):
            yield stmt
        elif isinstance(stmt, ast.If):
            if _is_type_checking_expr(stmt.test, aliases):
                yield from _iter_py_runtime_classes(stmt.orelse, aliases)
            elif _is_not_type_checking_expr(stmt.test, aliases):
                yield from _iter_py_runtime_classes(stmt.body, aliases)
            elif isinstance(stmt.test, ast.Constant) and not bool(stmt.test.value):
                yield from _iter_py_runtime_classes(stmt.orelse, aliases)
            else:
                yield from _iter_py_runtime_classes(stmt.body, aliases)
                yield from _iter_py_runtime_classes(stmt.orelse, aliases)


def _py_delegate_target_attr(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
    """If fn is a trivial 1-to-1 delegation to self.<attr>.<method>(...), return <attr>."""
    body = _dc._strip_docstring(fn.body)
    if len(body) != 1:
        return None
    stmt = body[0]
    expr: Optional[ast.expr] = None
    if isinstance(stmt, ast.Return):
        expr = stmt.value
    elif isinstance(stmt, ast.Expr):
        expr = stmt.value
    if expr is None:
        return None
    if isinstance(expr, ast.Await):
        expr = expr.value

    is_prop = any(_dc._decorator_name(d) == "property" for d in fn.decorator_list)
    if is_prop and isinstance(expr, ast.Attribute):
        inner = expr.value
        if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name) and inner.value.id == "self":
            return inner.attr
        return None

    if not isinstance(expr, ast.Call):
        return None
    if not isinstance(expr.func, ast.Attribute):
        return None
    owner = expr.func.value
    if not (isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Name) and owner.value.id == "self"):
        return None

    # Require simple pass-through arguments (no nested logic/comprehensions/lambdas/nested calls).
    for arg in expr.args:
        val = arg.value if isinstance(arg, ast.Starred) else arg
        if not isinstance(val, (ast.Name, ast.Constant)):
            return None
    for kw in expr.keywords:
        if not isinstance(kw.value, (ast.Name, ast.Constant)):
            return None
    return owner.attr


def _py_init_is_trivial(cls: ast.ClassDef) -> bool:
    for fn in _py_class_methods(cls):
        if fn.name != "__init__":
            continue
        body = _dc._strip_docstring(fn.body)
        for stmt in body:
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1:
                    return False
                t = stmt.targets[0]
                if not (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"):
                    return False
                if not isinstance(stmt.value, (ast.Name, ast.Constant)):
                    return False
            elif isinstance(stmt, ast.AnnAssign):
                t = stmt.target
                if not (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"):
                    return False
                if stmt.value is not None and not isinstance(stmt.value, (ast.Name, ast.Constant)):
                    return False
            elif isinstance(stmt, ast.Pass):
                continue
            else:
                return False
    return True


def _py_is_trivial_passthrough_wrapper(cls: ast.ClassDef) -> Optional[str]:
    """Return wrapped attribute name if cls is a trivial 1-to-1 delegation Wrapper/Impl."""
    if not cls.name.endswith(("Wrapper", "Impl")):
        return None
    if _py_class_is_data_or_exception(cls):
        return None
    if not _py_init_is_trivial(cls):
        return None

    non_dunders = [
        fn for fn in _py_class_methods(cls)
        if not (fn.name.startswith("__") and fn.name.endswith("__"))
    ]
    if not non_dunders:
        return None

    attrs: Set[str] = set()
    for fn in non_dunders:
        attr = _py_delegate_target_attr(fn)
        if attr is None:
            return None
        attrs.add(attr)
    if len(attrs) == 1:
        return next(iter(attrs))
    return None


def _py_is_trivial_single_impl_factory(cls: ast.ClassDef) -> Optional[str]:
    """Return lone constructed class name if *Factory class only ever creates <= 1 concrete class."""
    if not cls.name.endswith("Factory"):
        return None
    if _py_class_is_data_or_exception(cls):
        return None

    non_dunders = [
        fn for fn in _py_class_methods(cls)
        if not (fn.name.startswith("__") and fn.name.endswith("__")) or fn.name == "__call__"
    ]
    if not non_dunders:
        return None

    # Exempt dynamic registry factories (e.g. register() method or dict-based dispatch).
    for fn in non_dunders:
        if "register" in fn.name.lower():
            return None

    returned_constructors: Set[str] = set()
    for fn in non_dunders:
        for node in ast.walk(fn):
            if isinstance(node, ast.Subscript):
                # Subscript lookup like `registry[kind](...)` indicates dynamic multi-impl dispatch.
                return None
            if isinstance(node, ast.Return) and node.value is not None:
                val = node.value
                if isinstance(val, ast.Call):
                    cname = _dc._dotted_name(val.func)
                    leaf = cname.split(".")[-1] if cname else ""
                    if leaf and leaf[0].isupper():
                        returned_constructors.add(leaf)
                    elif leaf:
                        # Returning a dynamic/helper call we can't prove is single-impl.
                        return None
                elif isinstance(val, ast.Name):
                    # Check if a local variable holds constructed class(es).
                    continue

    # Also scan direct `return var` where `var = SomeClass(...)` inside factory methods.
    if not returned_constructors:
        for fn in non_dunders:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    cname = _dc._dotted_name(node.func)
                    leaf = cname.split(".")[-1] if cname else ""
                    if leaf and leaf[0].isupper() and not leaf.endswith(("Error", "Exception")):
                        returned_constructors.add(leaf)

    if len(returned_constructors) == 1:
        return next(iter(returned_constructors))
    return None


def _extract_js_brace_block(lines: Sequence[str], start_idx: int) -> Optional[Tuple[int, str]]:
    """Return (end_idx_exclusive, block_body_text) for the `{ ... }` block starting on or after start_idx."""
    n = len(lines)
    depth = 0
    started = False
    collected: List[str] = []
    idx = start_idx
    while idx < n:
        line = lines[idx]
        for ch in line:
            if ch == "{":
                if started:
                    collected.append(ch)
                started = True
                depth += 1
            elif ch == "}":
                depth -= 1
                if started and depth > 0:
                    collected.append(ch)
                if started and depth == 0:
                    return idx + 1, "".join(collected)
            elif started:
                collected.append(ch)
        if started:
            collected.append("\n")
        elif idx > start_idx + 3:
            return None
        idx += 1
    return None


def _strip_angle_generics(text: str) -> str:
    """Remove balanced `<...>` TypeScript generic parameter lists so `extends` inside `<T extends X>` is ignored."""
    out: List[str] = []
    depth = 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            if depth > 0:
                depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _is_ts_types_contract_file(rel_path: str) -> bool:
    norm = _dc._normalize_relpath(rel_path).lower()
    parts = norm.split("/")
    leaf = parts[-1] if parts else ""
    if leaf in ("types.ts", "types.tsx", "types.mts", "types.cts"):
        return True
    if len(parts) >= 2 and parts[-2] == "types" and leaf.startswith("index."):
        return True
    return False


def _parse_js_ts_declarations(rel_path: str, source: str) -> Dict[str, List[Dict[str, Any]]]:
    """Parse top-level/exported JS/TS classes and interfaces with brace-matched bodies."""
    cleaned = _strip_js_comments_and_templates(source)
    lines = cleaned.splitlines()
    classes: List[Dict[str, Any]] = []
    interfaces: List[Dict[str, Any]] = []

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        m_cls = JS_CLASS_DECL_RE.match(line)
        if m_cls and "declare " not in line:
            is_exported = bool(m_cls.group(1))
            is_abstract = bool(m_cls.group(2))
            name = m_cls.group(3)
            header_tail = m_cls.group(4)
            # Gather multi-line header up to `{`.
            j = i
            while "{" not in header_tail and j + 1 < n and j - i < 4:
                j += 1
                header_tail += " " + lines[j]
            header_before_brace = _strip_angle_generics(header_tail.split("{", 1)[0])
            extends_m = re.search(r"\bextends\s+([A-Za-z_$][\w$.]*)", header_before_brace)
            extends_name = extends_m.group(1).split(".")[-1] if extends_m else None
            impl_names: List[str] = []
            impl_m = re.search(r"\bimplements\s+([^{]+)", header_before_brace)
            if impl_m:
                for part in impl_m.group(1).split(","):
                    tok = part.strip().split(".")[-1]
                    if re.match(r"^[A-Za-z_$][\w$]*$", tok):
                        impl_names.append(tok)
            blk = _extract_js_brace_block(lines, i)
            if blk is not None:
                end_idx, body = blk
                classes.append({
                    "file": rel_path,
                    "line": i + 1,
                    "name": name,
                    "is_exported": is_exported,
                    "is_abstract": is_abstract,
                    "extends": extends_name,
                    "implements": impl_names,
                    "body": body,
                })
                i = end_idx
                continue

        m_iface = JS_INTERFACE_DECL_RE.match(line)
        if m_iface and "declare " not in line:
            name = m_iface.group(1)
            blk = _extract_js_brace_block(lines, i)
            if blk is not None:
                end_idx, body = blk
                interfaces.append({
                    "file": rel_path,
                    "line": i + 1,
                    "name": name,
                    "body": body,
                })
                i = end_idx
                continue

        i += 1

    return {"classes": classes, "interfaces": interfaces}


def _js_interface_has_methods(body: str) -> bool:
    """Return True if a TS interface body declares at least one method signature (not plain data DTO)."""
    depth = 0
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if depth == 0 and line:
            # Skip index signatures `[key: string]: ...` and call signatures `(...): ...`.
            if not line.startswith("[") and not line.startswith("("):
                # Match method declaration `foo(a: string): number;` (not property `foo: string;` or `foo?: (x: T) => void`).
                if re.match(
                    r"^(?:readonly\s+)?([A-Za-z_$][\w$]*)\s*\??\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::|$|;)",
                    line,
                ):
                    return True
        depth += raw_line.count("{") - raw_line.count("}")
    return False


def _js_extract_class_methods(body: str) -> List[Tuple[str, str]]:
    """Return [(method_name, inner_body_text), ...] for concrete methods at class depth 0."""
    lines = body.splitlines()
    methods: List[Tuple[str, str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith(("get ", "set ", "abstract ")):
            # Skip abstract declarations without body; properties handled below.
            if stripped.startswith("abstract "):
                i += 1
                continue
        m = re.match(
            r"^\s*(?:public\s+|private\s+|protected\s+|static\s+|async\s+|override\s+)*"
            r"([A-Za-z_$][\w$]*)\s*(?:<[^>]*>)?\s*\([^)]*\)\s*(?::\s*[^{;=]+)?\s*\{",
            line,
        )
        if m:
            mname = m.group(1)
            if mname not in ("if", "for", "while", "switch", "catch", "function"):
                blk = _extract_js_brace_block(lines, i)
                if blk is not None:
                    end_idx, mbody = blk
                    methods.append((mname, mbody))
                    i = end_idx
                    continue
        i += 1
    return methods


def _js_is_trivial_passthrough_wrapper(cls_info: Dict[str, Any]) -> Optional[str]:
    name = cls_info["name"]
    if cls_info["is_abstract"] or not name.endswith(("Wrapper", "Impl")):
        return None
    methods = _js_extract_class_methods(cls_info["body"])
    non_ctor = [(mname, mbody) for mname, mbody in methods if mname != "constructor"]
    if not non_ctor:
        return None
    attrs: Set[str] = set()
    for _, mbody in non_ctor:
        stmts = [ln.strip() for ln in mbody.splitlines() if ln.strip()]
        if len(stmts) != 1:
            return None
        dm = JS_DELEGATE_STMT_RE.match(stmts[0])
        if not dm:
            return None
        attrs.add(dm.group(1))
    if len(attrs) == 1:
        return next(iter(attrs))
    return None


def _js_is_trivial_single_impl_factory(cls_info: Dict[str, Any]) -> Optional[str]:
    name = cls_info["name"]
    if cls_info["is_abstract"] or not name.endswith("Factory"):
        return None
    methods = _js_extract_class_methods(cls_info["body"])
    non_ctor = [(mname, mbody) for mname, mbody in methods if mname != "constructor"]
    if not non_ctor:
        return None
    if any("register" in mname.lower() for mname, _ in non_ctor):
        return None
    constructed: Set[str] = set()
    for _, mbody in non_ctor:
        if re.search(r"\[[^\]]+\]\s*\(", mbody):
            return None
        for nm in JS_NEW_CALL_RE.finditer(mbody):
            cname = nm.group(1)
            if not cname.endswith("Error"):
                constructed.add(cname)
    if len(constructed) == 1:
        return next(iter(constructed))
    return None


def _js_abstract_class_has_methods(body: str) -> bool:
    for line in body.splitlines():
        if re.match(r"^\s*(?:public\s+|protected\s+)?abstract\s+[A-Za-z_$][\w$]*\s*(?:<[^>]*>)?\s*\(", line):
            return True
    return bool(_js_extract_class_methods(body))


def check_single_impl_wrappers(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    *,
    repo_root: Optional[Path] = None,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect speculative single-implementation interfaces, ABCs, factories, and pass-through wrappers."""
    all_sources, prod_targets = _collect_production_sources(target_sources, repo_root=repo_root)
    if not prod_targets:
        return []

    norm_added: Dict[str, Optional[Set[int]]] = {
        _dc._normalize_relpath(k): v[1] for k, v in target_sources.items()
    }
    findings: List[Dict[str, Any]] = []

    # ---- Python analysis across all production Python modules ----
    py_files = sorted(rel for rel in all_sources if Path(rel).suffix.lower() == ".py")
    if any(t in py_files for t in prod_targets):
        py_module_exports: Dict[str, Set[str]] = {}
        py_pkg_exports: Dict[str, Set[str]] = {}
        py_concrete_classes: List[Tuple[str, ast.ClassDef, Set[str], Set[str]]] = []
        # (rel, cls, base_names, non_dunder_method_names)
        py_target_classes: List[Tuple[str, ast.ClassDef, str]] = []

        for rel in py_files:
            try:
                tree = ast.parse(all_sources[rel])
            except SyntaxError:
                continue
            exported = _py_extract_dunder_all(tree)
            py_module_exports[rel] = exported
            if rel.endswith("/__init__.py") or rel == "__init__.py":
                pkg_dir = posixpath.dirname(rel)
                py_pkg_exports.setdefault(pkg_dir, set()).update(exported)

            aliases = _dc._python_import_aliases(tree)
            for cls in _iter_py_runtime_classes(tree.body, aliases):
                kind = _py_class_kind(cls)
                bases = {_dc._base_name(b) for b in cls.bases if _dc._base_name(b)}
                methods = _py_class_non_dunder_method_names(cls)
                if kind == "concrete":
                    py_concrete_classes.append((rel, cls, bases, methods))
                if rel in prod_targets:
                    py_target_classes.append((rel, cls, kind))

        # Index direct subclasses by base class name (including transitive concrete subclasses).
        all_subclasses: Dict[str, Set[str]] = {}
        concrete_by_name: Dict[str, Tuple[str, Set[str]]] = {}
        for rel, cls, bases, methods in py_concrete_classes:
            concrete_by_name[cls.name] = (rel, methods)
            for b in bases:
                all_subclasses.setdefault(b, set()).add(cls.name)

        def _count_concrete_subclasses(base_name: str) -> Set[str]:
            visited: Set[str] = set()
            queue: deque[str] = deque(all_subclasses.get(base_name, ()))
            while queue:
                cur = queue.popleft()
                if cur in visited:
                    continue
                visited.add(cur)
                for sub in all_subclasses.get(cur, ()):
                    if sub not in visited:
                        queue.append(sub)
            return visited

        def _is_exported_in_all(rel: str, name: str) -> bool:
            if name in py_module_exports.get(rel, ()):
                return True
            pkg_dir = posixpath.dirname(rel)
            while True:
                if name in py_pkg_exports.get(pkg_dir, ()):
                    return True
                if not pkg_dir:
                    break
                parent = posixpath.dirname(pkg_dir)
                if parent == pkg_dir:
                    break
                pkg_dir = parent
            return False

        for rel, cls, kind in py_target_classes:
            added = norm_added.get(rel)
            if added is not None and cls.lineno not in added:
                continue
            if _py_class_is_data_or_exception(cls):
                continue
            if _is_exported_in_all(rel, cls.name):
                continue

            if kind in ("abc", "protocol"):
                non_dunder_methods = _py_class_non_dunder_method_names(cls)
                all_method_names = {fn.name for fn in _py_class_methods(cls)}

                # Exempt pure data/attribute Protocols and stdlib dunder-only Protocols (__call__, __iter__, etc.).
                if kind == "protocol":
                    if not non_dunder_methods:
                        continue
                    if all_method_names and all_method_names <= PY_PROTOCOL_TYPING_DUNDERS:
                        continue

                concrete_impls = _count_concrete_subclasses(cls.name)
                if kind == "protocol":
                    # Also count structural implementors (concrete classes implementing all declared methods).
                    for _, c_cls, _, c_methods in py_concrete_classes:
                        if non_dunder_methods <= c_methods:
                            concrete_impls.add(c_cls.name)
                    # Private typing Protocols with 0 in-repo implementors typically type external/stdlib objects.
                    if cls.name.startswith("_") and len(concrete_impls) == 0:
                        continue

                if len(concrete_impls) <= 1:
                    impl_note = (
                        f"only 1 concrete implementation ({next(iter(concrete_impls))})"
                        if len(concrete_impls) == 1
                        else "0 concrete implementations in the repository"
                    )
                    label = "Protocol" if kind == "protocol" else "ABC"
                    findings.append(
                        _finding(
                            code="ARCH-SINGLE-IMPL-WRAPPER",
                            severity=severity,
                            file=rel,
                            line=cls.lineno,
                            message=(
                                f"{rel}:{cls.lineno} defines {label} '{cls.name}' with {impl_note}."
                            ),
                            remediation=(
                                "Use a direct concrete class or function until a second real implementation "
                                "exists (or export an intentional public extension contract via __all__)."
                            ),
                            meta={
                                "kind": f"python_{kind}",
                                "class": cls.name,
                                "implementations": sorted(concrete_impls),
                            },
                        )
                    )
                continue

            # Concrete class: check trivial *Factory or pass-through *Wrapper/*Impl.
            factory_target = _py_is_trivial_single_impl_factory(cls)
            if factory_target is not None:
                findings.append(
                    _finding(
                        code="ARCH-SINGLE-IMPL-WRAPPER",
                        severity=severity,
                        file=rel,
                        line=cls.lineno,
                        message=(
                            f"{rel}:{cls.lineno} defines speculative single-implementation factory "
                            f"'{cls.name}' that only constructs '{factory_target}'."
                        ),
                        remediation=(
                            "Instantiate the concrete class or call a direct function until multiple "
                            "implementations actually need factory dispatch."
                        ),
                        meta={
                            "kind": "python_factory",
                            "class": cls.name,
                            "target": factory_target,
                        },
                    )
                )
                continue

            wrapped_attr = _py_is_trivial_passthrough_wrapper(cls)
            if wrapped_attr is not None:
                findings.append(
                    _finding(
                        code="ARCH-SINGLE-IMPL-WRAPPER",
                        severity=severity,
                        file=rel,
                        line=cls.lineno,
                        message=(
                            f"{rel}:{cls.lineno} defines pass-through wrapper '{cls.name}' whose methods "
                            f"only delegate 1-to-1 to 'self.{wrapped_attr}'."
                        ),
                        remediation=(
                            "Call the underlying object directly or inline real boundary behavior instead "
                            "of maintaining an extra pass-through indirection layer."
                        ),
                        meta={
                            "kind": "python_wrapper",
                            "class": cls.name,
                            "wrapped_attr": wrapped_attr,
                        },
                    )
                )

    # ---- JS/TS analysis across all production JS/TS modules ----
    js_files = sorted(rel for rel in all_sources if _dc._is_js_ts_path(rel))
    if any(t in js_files for t in prod_targets):
        all_js_classes: List[Dict[str, Any]] = []
        all_js_interfaces: List[Dict[str, Any]] = []
        for rel in js_files:
            parsed = _parse_js_ts_declarations(rel, all_sources[rel])
            all_js_classes.extend(parsed["classes"])
            all_js_interfaces.extend(parsed["interfaces"])

        extends_map: Dict[str, Set[str]] = {}
        implements_map: Dict[str, Set[str]] = {}
        factory_targets: Set[str] = set()
        for cls_info in all_js_classes:
            if not cls_info["is_abstract"]:
                if cls_info["extends"]:
                    extends_map.setdefault(cls_info["extends"], set()).add(cls_info["name"])
                for iface in cls_info["implements"]:
                    implements_map.setdefault(iface, set()).add(cls_info["name"])
                ft = _js_is_trivial_single_impl_factory(cls_info)
                if ft is not None:
                    factory_targets.add(ft)

        # 1. Method-bearing abstract classes with <= 1 concrete subclass.
        for cls_info in all_js_classes:
            rel = cls_info["file"]
            if rel not in prod_targets:
                continue
            added = norm_added.get(rel)
            if added is not None and cls_info["line"] not in added:
                continue

            if cls_info["is_abstract"]:
                if not _js_abstract_class_has_methods(cls_info["body"]):
                    continue
                subs = extends_map.get(cls_info["name"], set())
                # Exempt exported pure-abstract external-runtime type stubs in types.ts with 0 subclasses
                # (e.g., Web/Edge platform contracts like `export abstract class FetchEventLike`).
                if (
                    len(subs) == 0
                    and cls_info.get("is_exported")
                    and _is_ts_types_contract_file(rel)
                    and not _js_extract_class_methods(cls_info["body"])
                ):
                    continue
                if len(subs) <= 1:
                    sub_note = (
                        f"only 1 concrete subclass ({next(iter(subs))})"
                        if len(subs) == 1
                        else "0 concrete subclasses in the repository"
                    )
                    findings.append(
                        _finding(
                            code="ARCH-SINGLE-IMPL-WRAPPER",
                            severity=severity,
                            file=rel,
                            line=cls_info["line"],
                            message=(
                                f"{rel}:{cls_info['line']} defines abstract class '{cls_info['name']}' "
                                f"with {sub_note}."
                            ),
                            remediation=(
                                "Use a direct concrete class or function until a second real subclass exists."
                            ),
                            meta={
                                "kind": "js_abstract_class",
                                "class": cls_info["name"],
                                "implementations": sorted(subs),
                            },
                        )
                    )
                continue

            ft = _js_is_trivial_single_impl_factory(cls_info)
            if ft is not None:
                findings.append(
                    _finding(
                        code="ARCH-SINGLE-IMPL-WRAPPER",
                        severity=severity,
                        file=rel,
                        line=cls_info["line"],
                        message=(
                            f"{rel}:{cls_info['line']} defines speculative single-implementation factory "
                            f"'{cls_info['name']}' that only constructs '{ft}'."
                        ),
                        remediation=(
                            "Instantiate the concrete class or call a direct helper until multiple "
                            "implementations actually need factory dispatch."
                        ),
                        meta={
                            "kind": "js_factory",
                            "class": cls_info["name"],
                            "target": ft,
                        },
                    )
                )
                continue

            wrapped = _js_is_trivial_passthrough_wrapper(cls_info)
            if wrapped is not None:
                findings.append(
                    _finding(
                        code="ARCH-SINGLE-IMPL-WRAPPER",
                        severity=severity,
                        file=rel,
                        line=cls_info["line"],
                        message=(
                            f"{rel}:{cls_info['line']} defines pass-through wrapper '{cls_info['name']}' "
                            f"whose methods only delegate 1-to-1 to 'this.{wrapped}'."
                        ),
                        remediation=(
                            "Call the underlying service directly instead of maintaining a trivial pass-through wrapper."
                        ),
                        meta={
                            "kind": "js_wrapper",
                            "class": cls_info["name"],
                            "wrapped_attr": wrapped,
                        },
                    )
                )

        # 2. Method-bearing interfaces with a single *Impl class (or lone impl paired with a trivial *Factory).
        for iface_info in all_js_interfaces:
            rel = iface_info["file"]
            if rel not in prod_targets:
                continue
            added = norm_added.get(rel)
            if added is not None and iface_info["line"] not in added:
                continue
            if not _js_interface_has_methods(iface_info["body"]):
                continue
            impls = implements_map.get(iface_info["name"], set())
            if len(impls) == 1:
                sole_impl = next(iter(impls))
                if sole_impl.endswith("Impl") or sole_impl in factory_targets:
                    findings.append(
                        _finding(
                            code="ARCH-SINGLE-IMPL-WRAPPER",
                            severity=severity,
                            file=rel,
                            line=iface_info["line"],
                            message=(
                                f"{rel}:{iface_info['line']} defines method-bearing interface "
                                f"'{iface_info['name']}' with only a single implementation '{sole_impl}'."
                            ),
                            remediation=(
                                "Remove the single-implementation service interface and use the concrete "
                                "implementation or plain functions until a second implementation exists."
                            ),
                            meta={
                                "kind": "js_interface_single_impl",
                                "interface": iface_info["name"],
                                "implementations": [sole_impl],
                            },
                        )
                    )

    return findings


# ---------------------------------------------------------------------------
# 3. ARCH-BOUNDARY-SCATTER
# ---------------------------------------------------------------------------

def _extract_py_env_reads(source: str) -> Dict[str, List[int]]:
    """Return {env_key: [lineno, ...]} for raw Python env-var reads."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}

    aliases = _dc._python_import_aliases(tree)
    reads: Dict[str, List[int]] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            resolved = _dc._resolve_dotted(_dc._dotted_name(node.func), aliases)
            if resolved not in ("os.getenv", "os.environ.get", "environ.get"):
                continue
            key_node: Optional[ast.expr] = node.args[0] if node.args else None
            if key_node is None:
                for kw in node.keywords:
                    if kw.arg == "key":
                        key_node = kw.value
                        break
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str) and key_node.value.strip():
                reads.setdefault(key_node.value, []).append(node.lineno)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            resolved = _dc._resolve_dotted(_dc._dotted_name(node.value), aliases)
            if resolved not in ("os.environ", "environ"):
                continue
            slc = (
                node.slice.value
                if hasattr(ast, "Index") and isinstance(node.slice, ast.Index)
                else node.slice
            )
            if isinstance(slc, ast.Constant) and isinstance(slc.value, str) and slc.value.strip():
                reads.setdefault(slc.value, []).append(node.lineno)

    return reads


def _extract_js_ts_env_reads(source: str) -> Dict[str, List[int]]:
    """Return {env_key: [lineno, ...]} for raw JS/TS process.env reads."""
    cleaned = _strip_js_comments_and_templates(source)
    reads: Dict[str, List[int]] = {}

    for m in JS_ENV_DOT_RE.finditer(cleaned):
        key = m.group(1)
        if key in JS_OBJECT_PROTO_PROPS:
            continue
        reads.setdefault(key, []).append(_offset_to_lineno(cleaned, m.start()))

    for m in JS_ENV_BRACKET_RE.finditer(cleaned):
        key = m.group(2).strip()
        if not key or key in JS_OBJECT_PROTO_PROPS:
            continue
        reads.setdefault(key, []).append(_offset_to_lineno(cleaned, m.start()))

    return reads


def check_boundary_scatter(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    *,
    repo_root: Optional[Path] = None,
    min_modules: int = DEFAULT_MIN_SCATTER_MODULES,
    severity: str = "warning",
) -> List[Dict[str, Any]]:
    """Detect raw env-var reads for the same non-runtime key scattered across >= 3 production modules."""
    if min_modules <= 1:
        return []
    all_sources, prod_targets = _collect_production_sources(target_sources, repo_root=repo_root)
    if not prod_targets:
        return []

    norm_added: Dict[str, Optional[Set[int]]] = {
        _dc._normalize_relpath(k): v[1] for k, v in target_sources.items()
    }

    # key -> {rel_path: sorted_linenos}
    key_locations: Dict[str, Dict[str, List[int]]] = {}
    for rel, text in sorted(all_sources.items()):
        suffix = Path(rel).suffix.lower()
        if suffix == ".py":
            reads = _extract_py_env_reads(text)
        elif _dc._is_js_ts_path(rel):
            reads = _extract_js_ts_env_reads(text)
        else:
            continue
        for key, lines in reads.items():
            if key in UNIVERSAL_RUNTIME_ENV_VARS:
                continue
            key_locations.setdefault(key, {})[rel] = sorted(set(lines))

    findings: List[Dict[str, Any]] = []
    for key in sorted(key_locations):
        mod_map = key_locations[key]
        if len(mod_map) < min_modules:
            continue

        # Flag only when at least one target file introduced/added (or in file mode, contains) a read of this key.
        trigger_file: Optional[str] = None
        trigger_line: Optional[int] = None
        for rel in sorted(prod_targets):
            lines = mod_map.get(rel)
            if not lines:
                continue
            added = norm_added.get(rel)
            if added is None:
                trigger_file = rel
                trigger_line = lines[0]
                break
            hit_lines = [ln for ln in lines if ln in added]
            if hit_lines:
                trigger_file = rel
                trigger_line = hit_lines[0]
                break

        if trigger_file is None or trigger_line is None:
            continue

        sorted_mods = sorted(mod_map.keys())
        preview = ", ".join(sorted_mods[:5])
        if len(sorted_mods) > 5:
            preview += f", +{len(sorted_mods) - 5} more"
        findings.append(
            _finding(
                code="ARCH-BOUNDARY-SCATTER",
                severity=severity,
                file=trigger_file,
                line=trigger_line,
                message=(
                    f"{trigger_file}:{trigger_line} reads raw env var '{key}', which is now "
                    f"scattered across {len(sorted_mods)} production modules ({preview})."
                ),
                remediation=(
                    "Centralize reading and validating environment configuration in one dedicated "
                    "boundary/config module and pass typed settings into business logic."
                ),
                meta={
                    "env_key": key,
                    "module_count": len(sorted_mods),
                    "modules": sorted_mods,
                },
            )
        )

    return findings


def check_architecture_sources(
    target_sources: Dict[str, Tuple[str, Optional[Set[int]]]],
    *,
    repo_root: Optional[Path] = None,
    severity: str = "warning",
    min_scatter_modules: int = DEFAULT_MIN_SCATTER_MODULES,
) -> List[Dict[str, Any]]:
    """Run all architectural compounding-slop detectors over target sources and repository context."""
    if not target_sources:
        return []
    findings: List[Dict[str, Any]] = []
    findings.extend(
        check_circular_imports(
            target_sources,
            repo_root=repo_root,
            severity=severity,
        )
    )
    findings.extend(
        check_single_impl_wrappers(
            target_sources,
            repo_root=repo_root,
            severity=severity,
        )
    )
    findings.extend(
        check_boundary_scatter(
            target_sources,
            repo_root=repo_root,
            min_modules=min_scatter_modules,
            severity=severity,
        )
    )
    return findings
