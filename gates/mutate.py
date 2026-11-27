#!/usr/bin/env python3
"""Diff-scoped mutation testing CLI for Python and JS/TS repositories (`anti-slop-mutate`).

Inspired by Google Critique diff-based mutation with arid-node suppression
(Petrovic et al., arXiv:2102.11378): tests whether your test suite actually
catches real bugs injected strictly on the executable Python or JS/TS lines
changed in your current diff (or explicit --files / line ranges).

Safety guarantees:
  - NEVER mutates the user's working tree in place: copies the repository into
    a fresh tempfile.TemporaryDirectory() (ignoring .git, .venv, node_modules,
    __pycache__, runs-local, results) and mutates strictly inside the temp copy.
  - Verifies baseline tests pass on the unmutated temp copy first; exits 2 if
    baseline tests already fail or time out.
  - Sets PYTHONDONTWRITEBYTECODE=1 so stale .pyc files never mask a mutant.

Zero third-party dependencies (Python 3.11+ stdlib only; compatible with 3.9+).
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402
from gates import review as _review  # noqa: E402


DEFAULT_MAX_MUTANTS = 24
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MIN_KILL_RATE = 0.65

PYTHON_EXTENSIONS = frozenset({".py"})
JS_TS_EXTENSIONS = frozenset({".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"})
SUPPORTED_EXTENSIONS = PYTHON_EXTENSIONS | JS_TS_EXTENSIONS

COPY_IGNORE_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    "runs-local", "results", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", "dist", "build",
})

ARID_CALL_NAMES = frozenset({
    "print", "debug", "info", "warning", "warn",
    "error", "exception", "critical", "fatal", "log",
})

JS_TS_IMPORT_RE = re.compile(r"^\s*import\b")
JS_TS_PURE_EXPORT_RE = re.compile(r"^\s*export\s+(?:\*|\{)")
JS_TS_TYPE_DECL_RE = re.compile(r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type)\b")
JS_TS_DECLARE_RE = re.compile(r"^\s*(?:export\s+)?declare\b")
JS_TS_LOGGING_RE = re.compile(r"^\s*(?:console|logger|log)\.\w+\s*\(")
JS_TS_STRUCTURAL_ONLY_RE = re.compile(
    r"^\s*(?:[\{\}\(\)\[\];,]+|else\s*\{|\}\s*else\s*\{|try\s*\{|finally\s*\{|\}?\s*catch\b[^\{]*\{)\s*$"
)
JS_TS_HEADER_ONLY_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:async\s+)?(?:class|function\*?)\b.*\{\s*$"
)
JS_TS_PROP_TYPE_ONLY_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|readonly|static)\s+)*[A-Za-z_$][\w$]*\??\s*:\s*[^=]+;\s*$"
)
JS_TS_REGEX_PREFIX_RE = re.compile(r"(?:^|[(\[{,;=!?:&|]|\b(?:return|throw|case|in|of|typeof|void))\s*$")
JS_TS_DIV_PREFIX_RE = re.compile(r"[\w$)\]]\s*$")
JS_TS_CASE_RE = re.compile(r"^\s*case\s+\d+\s*:")
JS_TS_IF_WHILE_RE = re.compile(r"\b(if|while)\s*\(")
JS_TS_RETURN_RE = re.compile(r"^(\s*return\s+)(.+?)(;?\s*)$")
JS_TS_THROW_RE = re.compile(r"\bthrow\b")
JS_TS_INT_LITERAL_RE = re.compile(r"(?<![.\w$])(\d+)(?![.\w$])")

JS_TS_COMPARE_RULES: Tuple[Tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"==="), "!==", "=== -> !=="),
    (re.compile(r"!=="), "===", "!== -> ==="),
    (re.compile(r"(?<![=!<>])==(?!=)"), "!=", "== -> !="),
    (re.compile(r"(?<![=!<>])!=(?!=)"), "==", "!= -> =="),
    (re.compile(r"(?<![<])<=(?!=)"), "<", "<= -> <"),
    (re.compile(r"(?<![>=])>=(?!=)"), ">", ">= -> >"),
    (re.compile(r"(?<=\s)<(?=\s)"), "<=", "< -> <="),
    (re.compile(r"(?<=\s)>(?=\s)"), ">=", "> -> >="),
)

JS_TS_BOOL_RULES: Tuple[Tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"&&(?!=)"), "||", "&& -> ||"),
    (re.compile(r"\|\|(?!=)"), "&&", "|| -> &&"),
    (re.compile(r"\btrue\b"), "false", "true -> false"),
    (re.compile(r"\bfalse\b"), "true", "false -> true"),
)

JS_TS_ARITH_RULES: Tuple[Tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"(?<=\s)\+(?=\s)"), "-", "+ -> -"),
    (re.compile(r"(?<=\s)-(?=\s)"), "+", "- -> +"),
    (re.compile(r"(?<=\s)\*(?=\s)"), "/", "* -> /"),
    (re.compile(r"(?<=\s)/(?=\s)"), "*", "/ -> *"),
)


def detect_language(path: str | Path) -> Optional[str]:
    """Return 'python', 'js_ts', or None based on file extension."""
    suffix = Path(str(path)).suffix.lower()
    if suffix in PYTHON_EXTENSIONS:
        return "python"
    if suffix in JS_TS_EXTENSIONS:
        return "js_ts"
    return None


def is_mutable_path(path: str | Path) -> bool:
    """Return True when path is a supported non-test source file."""
    return detect_language(path) is not None and not _dc._is_test_file(str(path))

COMPARE_SWAPS: Dict[type, Tuple[str, type]] = {
    ast.Eq: ("== -> !=", ast.NotEq),
    ast.NotEq: ("!= -> ==", ast.Eq),
    ast.Lt: ("< -> <=", ast.LtE),
    ast.LtE: ("<= -> <", ast.Lt),
    ast.Gt: ("> -> >=", ast.GtE),
    ast.GtE: (">= -> >", ast.Gt),
    ast.Is: ("is -> is not", ast.IsNot),
    ast.IsNot: ("is not -> is", ast.Is),
    ast.In: ("in -> not in", ast.NotIn),
    ast.NotIn: ("not in -> in", ast.In),
}

BINOP_SWAPS: Dict[type, Tuple[str, type]] = {
    ast.Add: ("+ -> -", ast.Sub),
    ast.Sub: ("- -> +", ast.Add),
    ast.Mult: ("* -> -", ast.Sub),
    ast.FloorDiv: ("// -> *", ast.Mult),
    ast.Div: ("/ -> *", ast.Mult),
}

BOOLOP_SWAPS: Dict[type, Tuple[str, type]] = {
    ast.And: ("and -> or", ast.Or),
    ast.Or: ("or -> and", ast.And),
}

CATEGORY_ORDER: Tuple[str, ...] = (
    "condition", "compare", "validation", "return_value",
    "arithmetic", "boolean", "boundary",
)

LINE_SPEC_RE = re.compile(r"^\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*$")


def parse_file_target_spec(raw: str) -> Tuple[str, Optional[Set[int]]]:
    """Parse 'path.py', 'path.py:12', or 'path.py:10-25,40-45' into (path, line_set_or_None)."""
    if ":" not in raw:
        return raw, None
    head, tail = raw.rsplit(":", 1)
    if not head or not LINE_SPEC_RE.match(tail):
        return raw, None
    lines: Set[int] = set()
    for part in tail.split(","):
        if "-" in part:
            s_str, e_str = part.split("-", 1)
            start, end = int(s_str), int(e_str)
            if start <= 0 or end < start:
                raise ValueError(f"Invalid line range '{part}' in '{raw}'.")
            lines.update(range(start, end + 1))
        else:
            ln = int(part)
            if ln <= 0:
                raise ValueError(f"Invalid line number '{part}' in '{raw}'.")
            lines.add(ln)
    return head, lines


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq):
        return False
    pair = (test.left, test.comparators[0])
    has_dunder = any(isinstance(x, ast.Name) and x.id == "__name__" for x in pair)
    has_main = any(isinstance(x, ast.Constant) and x.value == "__main__" for x in pair)
    return has_dunder and has_main


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    return (
        (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING")
        or (isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING")
    )


def _is_arid_call(node: ast.Call) -> bool:
    func = node.func
    name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
    return name in ARID_CALL_NAMES


def _mark_subtree(node: Optional[ast.AST], arid: Set[int]) -> None:
    if node is None:
        return
    for sub in ast.walk(node):
        arid.add(id(sub))


def _mark_func_arid(node: ast.FunctionDef | ast.AsyncFunctionDef, arid: Set[int]) -> None:
    _mark_subtree(node.returns, arid)
    for dec in node.decorator_list:
        _mark_subtree(dec, arid)
    all_args = list(node.args.posonlyargs) + list(node.args.args) + list(node.args.kwonlyargs)
    for arg in all_args:
        _mark_subtree(arg.annotation, arid)
    for special in (node.args.vararg, node.args.kwarg):
        if special is not None:
            _mark_subtree(special.annotation, arid)


def _collect_arid_node_ids(tree: ast.Module) -> Set[int]:
    """Return ids of AST nodes in non-productive/arid contexts (docstrings, annotations, logging, __main__)."""
    arid: Set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            _mark_subtree(body[0], arid)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _mark_func_arid(node, arid)
        elif isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                _mark_subtree(dec, arid)
        elif isinstance(node, ast.AnnAssign):
            _mark_subtree(node.annotation, arid)
        elif isinstance(node, ast.If) and (_is_main_guard(node) or _is_type_checking_guard(node)):
            _mark_subtree(node, arid)
        elif isinstance(node, ast.Call) and _is_arid_call(node):
            _mark_subtree(node, arid)
    return arid


def _build_parent_map(tree: ast.AST) -> Dict[int, ast.AST]:
    parents: Dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _replace_child_node(parent: ast.AST, old_node: ast.AST, new_node: ast.AST) -> bool:
    for field_name, val in ast.iter_fields(parent):
        if val is old_node:
            setattr(parent, field_name, new_node)
            return True
        if isinstance(val, list):
            for i, item in enumerate(val):
                if item is old_node:
                    val[i] = new_node
                    return True
    return False


def _enclosing_stmt(node: ast.AST, parents: Dict[int, ast.AST]) -> Optional[ast.stmt]:
    cur: Optional[ast.AST] = node
    while cur is not None:
        if isinstance(cur, ast.stmt):
            return cur
        cur = parents.get(id(cur))
    return None


def _format_mutated_line(
    target: ast.AST,
    mutated_node: ast.AST,
    parents: Dict[int, ast.AST],
    category: str,
) -> str:
    """Produce a concise single-line preview of the mutated statement or header."""
    if category == "validation":
        return "pass"
    stmt = _enclosing_stmt(mutated_node, parents) or _enclosing_stmt(target, parents)
    try:
        if isinstance(stmt, ast.If):
            return f"if {ast.unparse(stmt.test)}:"
        if isinstance(stmt, ast.While):
            return f"while {ast.unparse(stmt.test)}:"
        if isinstance(stmt, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Return, ast.Assert, ast.Expr)):
            return ast.unparse(stmt).splitlines()[0]
        return ast.unparse(mutated_node).splitlines()[0]
    except (AttributeError, ValueError, RecursionError):
        return "<mutated>"


def _classify_literal_site(
    rel_path: str,
    idx: int,
    node: ast.Constant,
    lineno: int,
    parents: Dict[int, ast.AST],
) -> Optional[Tuple[str, int, str, int]]:
    if type(node.value) is bool:
        label = "True -> False" if node.value else "False -> True"
        return ("boolean", idx, f"{rel_path}:{lineno} boolean ({label})", lineno)
    if type(node.value) is int:
        parent = parents.get(id(node))
        if isinstance(parent, ast.UnaryOp) and isinstance(parent.op, ast.USub):
            return None
        new_val = node.value + 1 if node.value >= 0 else node.value - 1
        delta = "+1" if node.value >= 0 else "-1"
        return ("boundary", idx, f"{rel_path}:{lineno} boundary ({node.value} -> {new_val}, {delta})", lineno)
    return None


def _classify_node_site(
    rel_path: str,
    idx: int,
    node: ast.AST,
    lineno: int,
    parents: Dict[int, ast.AST],
) -> Optional[Tuple[str, int, str, int]]:
    if isinstance(node, (ast.If, ast.While, ast.IfExp)):
        return ("condition", idx, f"{rel_path}:{lineno} condition (negate)", lineno)
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in COMPARE_SWAPS:
        return ("compare", idx, f"{rel_path}:{lineno} compare ({COMPARE_SWAPS[type(node.ops[0])][0]})", lineno)
    if isinstance(node, ast.BinOp) and type(node.op) in BINOP_SWAPS:
        is_str_add = isinstance(node.op, ast.Add) and any(
            isinstance(side, ast.Constant) and isinstance(side.value, (str, bytes))
            for side in (node.left, node.right)
        )
        if not is_str_add:
            return ("arithmetic", idx, f"{rel_path}:{lineno} arithmetic ({BINOP_SWAPS[type(node.op)][0]})", lineno)
    if isinstance(node, ast.BoolOp) and type(node.op) in BOOLOP_SWAPS:
        return ("boolean", idx, f"{rel_path}:{lineno} boolean ({BOOLOP_SWAPS[type(node.op)][0]})", lineno)
    if isinstance(node, ast.Constant):
        return _classify_literal_site(rel_path, idx, node, lineno, parents)
    if isinstance(node, ast.Return):
        if isinstance(node.value, ast.Constant) and type(node.value.value) is bool:
            return None
        is_none = node.value is None or (isinstance(node.value, ast.Constant) and node.value.value is None)
        desc = "None -> 1" if is_none else "value -> None"
        return ("return_value", idx, f"{rel_path}:{lineno} return ({desc})", lineno)
    if isinstance(node, ast.Raise) and node.exc is not None:
        return ("validation", idx, f"{rel_path}:{lineno} validation (raise -> pass)", lineno)
    return None


def _collect_candidate_sites(
    rel_path: str,
    base_tree: ast.Module,
    target_lines: Optional[Set[int]],
) -> List[Tuple[str, int, str, int]]:
    """Collect (category, node_index, description, lineno) sites matching target_lines."""
    arid_ids = _collect_arid_node_ids(base_tree)
    parents = _build_parent_map(base_tree)
    sites: List[Tuple[str, int, str, int]] = []
    for idx, node in enumerate(ast.walk(base_tree)):
        if id(node) in arid_ids:
            continue
        lineno = getattr(node, "lineno", 0)
        if lineno <= 0 or (target_lines is not None and lineno not in target_lines):
            continue
        site = _classify_node_site(rel_path, idx, node, lineno, parents)
        if site is not None:
            sites.append(site)
    return sites


def _select_sites_round_robin(
    sites: Sequence[Tuple[str, int, str, int]],
    max_per_file: int,
) -> List[Tuple[str, int, str, int]]:
    """Sample sites round-robin across categories, preferring distinct lines first."""
    by_cat: Dict[str, List[Tuple[str, int, str, int]]] = {}
    for item in sites:
        by_cat.setdefault(item[0], []).append(item)

    selected: List[Tuple[str, int, str, int]] = []
    seen_indices: Set[int] = set()
    covered_lines: Set[int] = set()

    for pass_distinct in (True, False):
        round_idx = 0
        while len(selected) < max_per_file:
            added_any = False
            for cat in CATEGORY_ORDER:
                bucket = by_cat.get(cat) or []
                for cand in bucket[round_idx:]:
                    if cand[1] in seen_indices:
                        continue
                    if pass_distinct and cand[3] in covered_lines:
                        continue
                    selected.append(cand)
                    seen_indices.add(cand[1])
                    covered_lines.add(cand[3])
                    added_any = True
                    break
                if len(selected) >= max_per_file:
                    break
            if not added_any:
                break
            round_idx += 1
    return selected


def _mutate_constant_node(
    target: ast.Constant,
    cat: str,
    parents: Dict[int, ast.AST],
) -> Optional[ast.AST]:
    parent = parents.get(id(target))
    if parent is None:
        return None
    if cat == "boolean" and type(target.value) is bool:
        replacement = ast.Constant(value=not target.value)
    elif cat == "boundary" and type(target.value) is int:
        new_val = target.value + 1 if target.value >= 0 else target.value - 1
        replacement = ast.Constant(value=new_val)
    else:
        return None
    if not _replace_child_node(parent, target, replacement):
        return None
    parents[id(replacement)] = parent
    return replacement


def _apply_mutation(
    tree_copy: ast.Module,
    target_idx: int,
    cat: str,
) -> Optional[Tuple[ast.AST, ast.AST, Dict[int, ast.AST]]]:
    """Mutate tree_copy in place at target_idx; return (orig_target, mutated_node, parents) or None."""
    parents = _build_parent_map(tree_copy)
    target = list(ast.walk(tree_copy))[target_idx]
    mutated_node: ast.AST = target

    if cat == "condition" and isinstance(target, (ast.If, ast.While, ast.IfExp)):
        is_not = isinstance(target.test, ast.UnaryOp) and isinstance(target.test.op, ast.Not)
        target.test = target.test.operand if is_not else ast.UnaryOp(op=ast.Not(), operand=target.test)
    elif cat == "compare" and isinstance(target, ast.Compare) and len(target.ops) == 1:
        target.ops[0] = COMPARE_SWAPS[type(target.ops[0])][1]()
    elif cat == "arithmetic" and isinstance(target, ast.BinOp):
        target.op = BINOP_SWAPS[type(target.op)][1]()
    elif cat == "boolean" and isinstance(target, ast.BoolOp):
        target.op = BOOLOP_SWAPS[type(target.op)][1]()
    elif isinstance(target, ast.Constant):
        replaced = _mutate_constant_node(target, cat, parents)
        if replaced is None:
            return None
        mutated_node = replaced
    elif cat == "return_value" and isinstance(target, ast.Return):
        is_none = target.value is None or (isinstance(target.value, ast.Constant) and target.value.value is None)
        target.value = ast.Constant(value=1 if is_none else None)
    elif cat == "validation" and isinstance(target, ast.Raise):
        parent = parents.get(id(target))
        if parent is None or not _replace_child_node(parent, target, ast.Pass()):
            return None
    else:
        return None
    return target, mutated_node, parents


def _mask_single_js_ts_line(
    line: str,
    in_block: bool,
    in_template: bool,
) -> Tuple[str, bool, bool, bool]:
    """Mask one JS/TS line while tracking block-comment and template-literal state."""
    n = len(line)
    chars: List[str] = [" "] * n
    quoted = False
    in_quote: Optional[str] = None
    i = 0

    while i < n:
        ch = line[i]
        if in_block:
            if line[i : i + 2] == "*/":
                in_block = False
                i += 2
            else:
                i += 1
            continue
        if in_template or in_quote is not None:
            quoted = True
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            delim = "`" if in_template else in_quote
            if ch == delim:
                chars[i] = ch
                if in_template:
                    in_template = False
                else:
                    in_quote = None
            i += 1
            continue
        if line[i : i + 2] == "//":
            break
        if line[i : i + 2] == "/*":
            in_block = True
            i += 2
            continue
        if ch in ("'", '"', "`"):
            quoted = True
            chars[i] = ch
            if ch == "`":
                in_template = True
            else:
                in_quote = ch
            i += 1
            continue
        if ch == "/" and JS_TS_REGEX_PREFIX_RE.search("".join(chars[:i])):
            end_rx = _scan_js_regex_end(line, i)
            if end_rx is not None:
                i = end_rx
                continue
        chars[i] = ch
        i += 1

    return "".join(chars), quoted, in_block, in_template


def _mask_js_ts_lines(lines: Sequence[str]) -> Tuple[List[str], List[bool]]:
    """Mask JS/TS comments, string/template interiors, and regex literals with spaces (1:1 indices)."""
    masked_lines: List[str] = []
    has_quotes: List[bool] = []
    in_block = False
    in_template = False
    for line in lines:
        masked, quoted, in_block, in_template = _mask_single_js_ts_line(line, in_block, in_template)
        masked_lines.append(masked)
        has_quotes.append(quoted)
    return masked_lines, has_quotes


def _scan_js_regex_end(line: str, start: int) -> Optional[int]:
    """Return index past closing `/flags` for a same-line JS regex literal, or None."""
    n = len(line)
    i = start + 1
    in_class = False
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            i += 1
            while i < n and line[i].isalpha():
                i += 1
            return i
        i += 1
    return None


def _is_balanced_single_line(text: str) -> bool:
    """Return True if (), [], {} are balanced and never drop below 0 within text."""
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: List[str] = []
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack[-1] != pairs[ch]:
                return False
            stack.pop()
    return not stack


def _find_matching_paren(text: str, open_idx: int) -> Optional[int]:
    depth = 0
    for idx in range(open_idx, len(text)):
        ch = text[idx]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return idx
    return None


def _collect_js_ts_arid_lines(masked_lines: Sequence[str]) -> Set[int]:
    """Return 1-based line numbers for comments, blank lines, imports/exports, types, and console logging."""
    arid: Set[int] = set()
    skip_brace_depth = 0
    in_import = False
    in_type_alias = False
    in_log_parens = 0

    for idx, mline in enumerate(masked_lines):
        ln = idx + 1
        stripped = mline.strip()
        if not stripped:
            arid.add(ln)
            continue
        if skip_brace_depth > 0:
            arid.add(ln)
            skip_brace_depth += mline.count("{") - mline.count("}")
            if skip_brace_depth < 0:
                skip_brace_depth = 0
            continue
        if in_import:
            arid.add(ln)
            if ";" in stripped or " from " in stripped:
                in_import = False
            continue
        if in_type_alias:
            arid.add(ln)
            if ";" in stripped or (not stripped.endswith(("|", "&")) and not stripped.startswith(("|", "&"))):
                in_type_alias = False
            continue
        if in_log_parens > 0:
            arid.add(ln)
            in_log_parens += mline.count("(") - mline.count(")")
            if in_log_parens < 0:
                in_log_parens = 0
            continue

        if JS_TS_TYPE_DECL_RE.match(stripped) or JS_TS_DECLARE_RE.match(stripped):
            arid.add(ln)
            delta = mline.count("{") - mline.count("}")
            if delta > 0:
                skip_brace_depth = delta
            elif ";" not in stripped and stripped.endswith(("=", "|", "&")):
                in_type_alias = True
            continue
        if JS_TS_IMPORT_RE.match(stripped) or JS_TS_PURE_EXPORT_RE.match(stripped):
            arid.add(ln)
            if "{" in stripped and "}" not in stripped:
                in_import = True
            continue
        if JS_TS_LOGGING_RE.match(stripped):
            arid.add(ln)
            pdelta = mline.count("(") - mline.count(")")
            if pdelta > 0:
                in_log_parens = pdelta
            continue
        if (
            JS_TS_STRUCTURAL_ONLY_RE.match(stripped)
            or JS_TS_HEADER_ONLY_RE.match(stripped)
            or JS_TS_PROP_TYPE_ONLY_RE.match(stripped)
        ):
            arid.add(ln)
    return arid


def _collect_js_ts_return_sites(
    raw_line: str,
    masked_line: str,
) -> Tuple[List[Tuple[str, str, str]], bool, bool]:
    """Return ([(cat, label, mutated_line)], is_return_bool, is_return_zero)."""
    ret_m = JS_TS_RETURN_RE.match(masked_line)
    if ret_m is None:
        return [], False, False
    expr_masked = ret_m.group(2).strip()
    expr_start, expr_end = ret_m.start(2), ret_m.end(2)
    raw_expr = raw_line[expr_start:expr_end].strip()
    if expr_masked == "true":
        return [("return_value", "return true -> return false", raw_line[:expr_start] + "false" + raw_line[expr_end:])], True, False
    if expr_masked == "false":
        return [("return_value", "return false -> return true", raw_line[:expr_start] + "true" + raw_line[expr_end:])], True, False
    if expr_masked == "0":
        return [("return_value", "return 0 -> return 1", raw_line[:expr_start] + "1" + raw_line[expr_end:])], False, True
    if (
        expr_masked not in ("null", "undefined")
        and raw_expr
        and _is_balanced_single_line(expr_masked)
        and not expr_masked.endswith((",", "?", ":", "&&", "||", "+", "-", "*", "/", "(", "[", "{"))
    ):
        return [("return_value", "return value -> return 0", raw_line[:expr_start] + "0" + raw_line[expr_end:])], False, False
    return [], False, False


def _collect_js_ts_operator_sites(
    raw_line: str,
    masked_line: str,
    has_quote: bool,
    is_return_bool: bool,
) -> List[Tuple[str, str, str]]:
    """Collect compare, boolean, and arithmetic swap mutations for one JS/TS line."""
    out: List[Tuple[str, str, str]] = []
    for pat, repl, label in JS_TS_COMPARE_RULES:
        for m in pat.finditer(masked_line):
            out.append(("compare", label, raw_line[: m.start()] + repl + raw_line[m.end() :]))
    for pat, repl, label in JS_TS_BOOL_RULES:
        if is_return_bool and repl in ("true", "false"):
            continue
        for m in pat.finditer(masked_line):
            out.append(("boolean", label, raw_line[: m.start()] + repl + raw_line[m.end() :]))
    for pat, repl, label in JS_TS_ARITH_RULES:
        if label.startswith("+") and has_quote:
            continue
        for m in pat.finditer(masked_line):
            if label.startswith("/") and not JS_TS_DIV_PREFIX_RE.search(masked_line[: m.start()]):
                continue
            out.append(("arithmetic", label, raw_line[: m.start()] + repl + raw_line[m.end() :]))
    return out


def _collect_js_ts_line_sites(
    rel_path: str,
    lineno: int,
    raw_line: str,
    masked_line: str,
    has_quote: bool,
    start_idx: int,
) -> List[Tuple[str, int, str, int, str]]:
    """Collect single-line JS/TS mutation candidates: (category, site_id, desc, lineno, mutated_line)."""
    raw_candidates: List[Tuple[str, str, str]] = []

    cond_m = JS_TS_IF_WHILE_RE.search(masked_line)
    if cond_m is not None:
        open_idx = cond_m.end() - 1
        close_idx = _find_matching_paren(masked_line, open_idx)
        if close_idx is not None:
            inner = raw_line[open_idx + 1 : close_idx].strip()
            if inner:
                raw_candidates.append(("condition", "negate", raw_line[: open_idx + 1] + f"!({inner})" + raw_line[close_idx:]))

    ret_cands, is_return_bool, is_return_zero = _collect_js_ts_return_sites(raw_line, masked_line)
    raw_candidates.extend(ret_cands)
    raw_candidates.extend(_collect_js_ts_operator_sites(raw_line, masked_line, has_quote, is_return_bool))

    throw_m = JS_TS_THROW_RE.search(masked_line)
    if throw_m is not None:
        tail = masked_line[throw_m.start() :].strip()
        if _is_balanced_single_line(tail) and not tail.endswith((",", "(", "[", "{", "+", "&&", "||")):
            raw_candidates.append(("validation", "throw -> noop", raw_line[: throw_m.start()] + ";"))

    if not is_return_zero and not JS_TS_CASE_RE.match(masked_line):
        for m in JS_TS_INT_LITERAL_RE.finditer(masked_line):
            val = int(m.group(1))
            new_val = val + 1
            raw_candidates.append(("boundary", f"{val} -> {new_val}", raw_line[: m.start(1)] + str(new_val) + raw_line[m.end(1) :]))

    sites: List[Tuple[str, int, str, int, str]] = []
    next_id = start_idx
    for cat, label, mutated_line in raw_candidates:
        if mutated_line != raw_line:
            sites.append((cat, next_id, f"{rel_path}:{lineno} {cat} ({label})", lineno, mutated_line))
            next_id += 1
    return sites


def generate_js_ts_mutants(
    rel_path: str,
    source: str,
    *,
    target_lines: Optional[Set[int]] = None,
    max_per_file: int = DEFAULT_MAX_MUTANTS,
) -> List[Dict[str, Any]]:
    """Generate deterministic single-site JS/TS mutants scoped to target_lines."""
    raw_lines = source.splitlines()
    if not raw_lines:
        return []
    masked_lines, has_quotes = _mask_js_ts_lines(raw_lines)
    arid_lines = _collect_js_ts_arid_lines(masked_lines)

    full_sites: List[Tuple[str, int, str, int, str]] = []
    for idx, raw_line in enumerate(raw_lines):
        lineno = idx + 1
        if lineno in arid_lines:
            continue
        if target_lines is not None and lineno not in target_lines:
            continue
        full_sites.extend(
            _collect_js_ts_line_sites(
                rel_path,
                lineno,
                raw_line,
                masked_lines[idx],
                has_quotes[idx],
                len(full_sites),
            )
        )
    if not full_sites:
        return []

    by_id = {item[1]: item[4] for item in full_sites}
    rr_input = [(cat, sid, desc, ln) for cat, sid, desc, ln, _ in full_sites]
    selected = _select_sites_round_robin(rr_input, max_per_file)

    trailing_nl = "\n" if source.endswith("\n") else ""
    mutants: List[Dict[str, Any]] = []
    seen_sources: Set[str] = set()
    for cat, sid, desc, lineno in selected:
        mut_line = by_id[sid]
        new_lines = list(raw_lines)
        new_lines[lineno - 1] = mut_line
        mutated_source = "\n".join(new_lines) + trailing_nl
        if mutated_source == source or mutated_source in seen_sources:
            continue
        seen_sources.add(mutated_source)
        mutants.append({
            "file": rel_path,
            "line": lineno,
            "operator": cat,
            "description": desc,
            "original_line": raw_lines[lineno - 1].strip(),
            "mutated_line": mut_line.strip(),
            "mutated_source": mutated_source,
        })
    return mutants


def generate_scoped_mutants(
    rel_path: str,
    source: str,
    *,
    target_lines: Optional[Set[int]] = None,
    max_per_file: int = DEFAULT_MAX_MUTANTS,
) -> List[Dict[str, Any]]:
    """Generate deterministic single-site Python AST or JS/TS mutants scoped to target_lines."""
    lang = detect_language(rel_path)
    if lang == "js_ts":
        return generate_js_ts_mutants(
            rel_path, source, target_lines=target_lines, max_per_file=max_per_file
        )
    if lang != "python":
        return []
    try:
        base_tree = ast.parse(source)
    except SyntaxError:
        return []

    sites = _collect_candidate_sites(rel_path, base_tree, target_lines)
    if not sites:
        return []

    selected = _select_sites_round_robin(sites, max_per_file)
    source_lines = source.splitlines()
    mutants: List[Dict[str, Any]] = []
    seen_sources: Set[str] = set()

    for cat, target_idx, desc, lineno in selected:
        tree_copy = copy.deepcopy(base_tree)
        applied = _apply_mutation(tree_copy, target_idx, cat)
        if applied is None:
            continue
        target, mutated_node, parents = applied
        ast.fix_missing_locations(tree_copy)
        try:
            mutated_source = ast.unparse(tree_copy) + "\n"
        except (AttributeError, ValueError, RecursionError):
            continue
        if mutated_source == source or mutated_source in seen_sources:
            continue
        seen_sources.add(mutated_source)

        orig_line = source_lines[lineno - 1].strip() if 1 <= lineno <= len(source_lines) else ""
        mutants.append({
            "file": rel_path,
            "line": lineno,
            "operator": cat,
            "description": desc,
            "original_line": orig_line,
            "mutated_line": _format_mutated_line(target, mutated_node, parents, cat),
            "mutated_source": mutated_source,
        })
    return mutants


def _copy_ignore(_directory: str, entries: List[str]) -> Set[str]:
    return {name for name in entries if name in COPY_IGNORE_DIRS or name.endswith((".pyc", ".pyo"))}


def _rewrite_cmd_for_copy(test_cmd: Sequence[str], src_root: Path, copy_root: Path) -> List[str]:
    effective: List[str] = []
    for arg in test_cmd:
        try:
            p = Path(arg)
            if p.is_absolute():
                effective.append(str(copy_root / p.resolve().relative_to(src_root)))
                continue
        except (OSError, ValueError):
            pass
        effective.append(arg)
    return effective


def _interleave_buckets(
    buckets: Sequence[Sequence[Dict[str, Any]]],
    max_mutants: int,
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    round_idx = 0
    while len(selected) < max_mutants:
        added = False
        for bucket in buckets:
            if round_idx < len(bucket):
                selected.append(bucket[round_idx])
                added = True
                if len(selected) >= max_mutants:
                    break
        if not added:
            break
        round_idx += 1
    return selected


def targets_from_diff(diff_text: str) -> Dict[str, Optional[Set[int]]]:
    """Extract {rel_path: set_of_added_lines} for non-test Python and JS/TS files in a unified diff."""
    parsed = _dc.parse_unified_diff(diff_text)
    targets: Dict[str, Optional[Set[int]]] = {}
    for entry in parsed["files"]:
        rel = entry["path"]
        if not rel or entry["is_deleted"]:
            continue
        if not is_mutable_path(rel):
            continue
        added = {ln for ln, _ in entry["added_lines"]}
        if added and not (rel in targets and targets[rel] is None):
            targets.setdefault(rel, set()).update(added)
    return targets


def _public_mutant_record(m: Dict[str, Any]) -> Dict[str, Any]:
    return {k: m[k] for k in ("file", "line", "operator", "description", "original_line", "mutated_line")}


def _baseline_failure_report(
    *,
    mode: str,
    cmd_list: List[str],
    min_kill_rate: float,
    error: str,
    returncode: Optional[int] = None,
    duration_s: float = 0.0,
    output_tail: str = "",
) -> Dict[str, Any]:
    baseline: Dict[str, Any] = {
        "passed": False,
        "returncode": returncode,
        "duration_s": round(duration_s, 3),
        "error": error,
    }
    if output_tail:
        baseline["output_tail"] = output_tail
    return {
        "ok": False,
        "exit_code": 2,
        "mode": mode,
        "test_cmd": cmd_list,
        "baseline": baseline,
        "scope": {"files_targeted": [], "changed_lines": {}},
        "summary": {
            "mutants_generated": 0, "mutants_tested": 0, "killed": 0,
            "survived": 0, "timed_out": 0, "kill_rate": None,
            "min_kill_rate": min_kill_rate,
        },
        "survived_mutants": [], "killed_mutants": [], "timed_out_mutants": [],
    }


def _run_baseline_check(
    effective_cmd: Sequence[str],
    copy_root: Path,
    env: Dict[str, str],
    timeout_s: float,
) -> Tuple[bool, float, Optional[int], str, str]:
    """Run unmutated test command; return (passed, duration_s, returncode, error, output_tail)."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            effective_cmd, cwd=copy_root, env=env, capture_output=True,
            text=True, timeout=max(timeout_s * 2.0, 20.0), check=False,
        )
    except FileNotFoundError:
        return False, time.monotonic() - t0, None, f"Test command executable not found: {effective_cmd[0]}", ""
    except subprocess.TimeoutExpired:
        return False, time.monotonic() - t0, None, "Baseline test command timed out before mutation testing.", ""
    dur = time.monotonic() - t0
    if proc.returncode != 0:
        tail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()[-600:]
        err = f"Baseline tests failed (exit {proc.returncode}); fix failing tests before mutation testing."
        return False, dur, proc.returncode, err, tail
    return True, dur, 0, "", ""


def _evaluate_mutants(
    selected_mutants: Sequence[Dict[str, Any]],
    originals: Dict[str, str],
    copy_root: Path,
    effective_cmd: Sequence[str],
    env: Dict[str, str],
    timeout_s: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    killed_list: List[Dict[str, Any]] = []
    survived_list: List[Dict[str, Any]] = []
    timed_out_list: List[Dict[str, Any]] = []
    for mutant in selected_mutants:
        rel = mutant["file"]
        target_file = copy_root / rel
        pub = _public_mutant_record(mutant)
        try:
            target_file.write_text(mutant["mutated_source"], encoding="utf-8")
            try:
                proc = subprocess.run(
                    effective_cmd, cwd=copy_root, env=env, capture_output=True,
                    text=True, timeout=timeout_s, check=False,
                )
                (killed_list if proc.returncode != 0 else survived_list).append(pub)
            except subprocess.TimeoutExpired:
                killed_list.append(pub)
                timed_out_list.append(pub)
        finally:
            target_file.write_text(originals[rel], encoding="utf-8")
    return killed_list, survived_list, timed_out_list


def _default_test_cmd_for_targets(targets: Dict[str, Optional[Set[int]]]) -> List[str]:
    langs = {detect_language(rel) for rel in targets if is_mutable_path(rel)}
    if langs == {"js_ts"}:
        return ["node", "--test"]
    return [sys.executable, "-B", "-m", "unittest", "discover"]


def run_diff_mutation(
    repo_root: Path | str,
    targets: Dict[str, Optional[Set[int]]],
    *,
    test_cmd: Optional[Sequence[str]] = None,
    max_mutants: int = DEFAULT_MAX_MUTANTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    min_kill_rate: float = DEFAULT_MIN_KILL_RATE,
    mode: str = "diff",
) -> Dict[str, Any]:
    """Run diff-scoped Python/JS/TS mutation testing inside an isolated temporary copy of repo_root."""
    src_root = Path(repo_root).resolve()
    cmd_list = list(test_cmd) if test_cmd else _default_test_cmd_for_targets(targets)
    if not src_root.is_dir():
        return _baseline_failure_report(
            mode=mode, cmd_list=cmd_list, min_kill_rate=min_kill_rate,
            error=f"Repository root directory not found: {src_root}",
        )

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    with tempfile.TemporaryDirectory(prefix="antislop_mutate_") as tmp:
        copy_root = Path(tmp) / src_root.name
        shutil.copytree(src_root, copy_root, symlinks=True, ignore=_copy_ignore)
        effective_cmd = _rewrite_cmd_for_copy(cmd_list, src_root, copy_root)

        base_ok, base_dur, base_rc, base_err, base_tail = _run_baseline_check(
            effective_cmd, copy_root, env, timeout_s
        )
        if not base_ok:
            return _baseline_failure_report(
                mode=mode, cmd_list=cmd_list, min_kill_rate=min_kill_rate,
                error=base_err, returncode=base_rc, duration_s=base_dur, output_tail=base_tail,
            )

        valid_targets = [
            (_dc._normalize_relpath(rel), targets[rel])
            for rel in sorted(targets)
            if is_mutable_path(_dc._normalize_relpath(rel))
            and (copy_root / _dc._normalize_relpath(rel)).is_file()
        ]
        originals: Dict[str, str] = {}
        changed_lines_map: Dict[str, Optional[List[int]]] = {}
        buckets: List[List[Dict[str, Any]]] = []
        for rel, line_set in valid_targets:
            text = (copy_root / rel).read_text(encoding="utf-8")
            originals[rel] = text
            changed_lines_map[rel] = sorted(line_set) if line_set is not None else None
            bucket = generate_scoped_mutants(rel, text, target_lines=line_set, max_per_file=max_mutants)
            if bucket:
                buckets.append(bucket)

        selected = _interleave_buckets(buckets, max_mutants)
        killed_list, survived_list, timed_out_list = _evaluate_mutants(
            selected, originals, copy_root, effective_cmd, env, timeout_s
        )

        tested = len(selected)
        kill_rate: Optional[float] = round(len(killed_list) / tested, 4) if tested > 0 else None
        passed_gate = True if tested == 0 else (kill_rate is not None and kill_rate >= min_kill_rate)
        return {
            "ok": passed_gate,
            "exit_code": 0 if passed_gate else 1,
            "mode": mode,
            "test_cmd": cmd_list,
            "baseline": {"passed": True, "returncode": 0, "duration_s": round(base_dur, 3), "error": None},
            "scope": {"files_targeted": [rel for rel, _ in valid_targets], "changed_lines": changed_lines_map},
            "summary": {
                "mutants_generated": sum(len(b) for b in buckets),
                "mutants_tested": tested,
                "killed": len(killed_list),
                "survived": len(survived_list),
                "timed_out": len(timed_out_list),
                "kill_rate": kill_rate,
                "min_kill_rate": min_kill_rate,
            },
            "survived_mutants": survived_list,
            "killed_mutants": killed_list,
            "timed_out_mutants": timed_out_list,
        }


def run_mutation_for_files(
    workspace_root: Path | str,
    rel_paths: Sequence[str],
    *,
    test_cmd: Optional[Sequence[str]] = None,
    max_mutants: int = DEFAULT_MAX_MUTANTS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    min_kill_rate: float = DEFAULT_MIN_KILL_RATE,
) -> Dict[str, Any]:
    """Run whole-file Python/JS/TS mutation testing across explicit relative file paths."""
    targets: Dict[str, Optional[Set[int]]] = {
        _dc._normalize_relpath(rel): None for rel in rel_paths
    }
    return run_diff_mutation(
        workspace_root,
        targets,
        test_cmd=test_cmd,
        max_mutants=max_mutants,
        timeout_s=timeout_s,
        min_kill_rate=min_kill_rate,
        mode="files",
    )


def _format_survived_section(survived: Sequence[Dict[str, Any]], *, markdown: bool) -> List[str]:
    lines: List[str] = []
    if markdown:
        lines.extend(["### Survived Mutants (Test Suite Blind Spots)", ""])
        for idx, m in enumerate(survived, start=1):
            lines.append(f"{idx}. `{m['file']}:{m['line']}` (`{m['operator']}`)")
            lines.append(f"   - **Original:** `{m['original_line']}`")
            lines.append(f"   - **Mutated:** `{m['mutated_line']}`")
            lines.append("")
    else:
        heading = "Survived Mutants (Test Suite Blind Spots)"
        lines.extend([heading, "-" * len(heading)])
        for idx, m in enumerate(survived, start=1):
            lines.append(f"{idx}. {m['file']}:{m['line']} [{m['operator']}] ({m['description']})")
            lines.append(f"   Original: {m['original_line']}")
            lines.append(f"   Mutated:  {m['mutated_line']}")
            lines.append("")
    return lines


def format_mutation_report(report: Dict[str, Any], *, markdown: bool = False) -> str:
    """Format mutation testing results in crisp plain English or Markdown."""
    baseline = report["baseline"]
    summary = report["summary"]
    survived = report["survived_mutants"]
    header = ["## Anti-Slop Diff-Scoped Mutation Report", ""] if markdown else [
        "Anti-Slop Diff-Scoped Mutation Report", "=====================================",
    ]
    if not baseline["passed"]:
        status_line = f"- **Baseline tests:** FAILED ({baseline['error']})" if markdown else f"Baseline tests: FAILED ({baseline['error']})"
        lines = header + [status_line]
        if baseline.get("output_tail"):
            lines.extend(["", baseline["output_tail"]])
        return "\n".join(lines).rstrip()

    tested, killed, surv_n, timed_out = (
        summary["mutants_tested"], summary["killed"], summary["survived"], summary["timed_out"],
    )
    rate_str = f"{summary['kill_rate']:.1%}" if summary["kill_rate"] is not None else "N/A"
    min_rate = summary["min_kill_rate"]
    status = "PASS" if report["ok"] else "FAIL"
    n_files = len(report["scope"]["files_targeted"])
    if markdown:
        lines = header + [
            f"- **Baseline tests:** PASSED ({baseline['duration_s']:.2f}s)",
            f"- **Targeted files:** {n_files}",
            f"- **Mutants:** {tested} tested, {killed} killed ({timed_out} timed out), {surv_n} survived",
            f"- **Kill rate:** {rate_str} (threshold: {min_rate:.0%}) -> **{status}**",
            "",
        ]
    else:
        lines = header + [
            f"Baseline tests: PASSED ({baseline['duration_s']:.2f}s)",
            f"Targeted files: {n_files}",
            f"Mutants tested: {tested} | Killed: {killed} ({timed_out} timed out) | Survived: {surv_n}",
            f"Kill rate: {rate_str} (minimum: {min_rate:.0%}) -> {status}",
            "",
        ]
    if tested == 0:
        lines.append("No mutable executable Python or JS/TS lines found in the selected scope.")
    elif not survived:
        lines.append(f"All {tested} mutants on your changed lines were killed by the test suite.")
    else:
        lines.extend(_format_survived_section(survived, markdown=markdown))
    return "\n".join(lines).rstrip()


def _resolve_targets_from_files(
    raw_specs: Sequence[str],
    *,
    raw_root: Path,
    root: Path,
    toplevel: Optional[Path],
) -> Dict[str, Optional[Set[int]]]:
    targets: Dict[str, Optional[Set[int]]] = {}
    for raw in raw_specs:
        path_str, line_set = parse_file_target_spec(raw)
        p = Path(path_str)
        rel = _dc._normalize_relpath(path_str)
        if p.is_absolute():
            try:
                rel = str(p.resolve().relative_to(root)).replace("\\", "/")
            except ValueError:
                raise ValueError(f"File '{path_str}' is outside repo root '{root}'.")
        elif toplevel is not None and raw_root != toplevel:
            cand = (raw_root / p).resolve()
            if cand.is_file():
                try:
                    rel = str(cand.relative_to(toplevel)).replace("\\", "/")
                except ValueError:
                    pass
        if rel not in targets:
            targets[rel] = line_set
        elif targets[rel] is None or line_set is None:
            targets[rel] = None
        else:
            targets[rel].update(line_set)
    return targets


def _resolve_diff_text(args: argparse.Namespace, root: Path) -> str:
    if args.diff is not None:
        return sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
    if args.base is not None:
        rc, diff_text, git_err = _review._collect_git_diff(root, base_ref=args.base)
        if rc != 0:
            raise ValueError(f"Unable to read git diff in {root}: {git_err.strip()}")
        return diff_text
    piped = "" if sys.stdin.isatty() else sys.stdin.read()
    if piped.strip():
        return piped
    rc, diff_text, git_err = _review._collect_git_diff(root, include_untracked=not args.no_untracked)
    if rc != 0:
        raise ValueError(
            f"Unable to read git diff in {root}: {git_err.strip()} "
            "(pass --files or --diff outside a git repository)."
        )
    return diff_text


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run diff-scoped mutation testing in an isolated temp copy to verify "
            "whether your tests catch real bugs introduced on your changed Python or JS/TS lines."
        )
    )
    parser.add_argument("--diff", default=None, help="Path to unified diff, or '-' for stdin.")
    parser.add_argument("--base", default=None, help="Git base ref to diff against (e.g., origin/main).")
    parser.add_argument("--no-untracked", action="store_true", help="Exclude untracked source files when auto-diffing git.")
    parser.add_argument("--files", nargs="+", default=None, help="Explicit Python or JS/TS files to mutate (optional :LINE or :START-END).")
    parser.add_argument("--repo-root", default=".", help="Target repository root (default: '.').")
    parser.add_argument("--test-cmd", default=None, help='Test command to run (default: unittest for Python, "node --test" for JS/TS).')
    parser.add_argument("--max-mutants", type=int, default=DEFAULT_MAX_MUTANTS, help=f"Max mutants (default: {DEFAULT_MAX_MUTANTS}).")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help=f"Per-mutant timeout seconds (default: {DEFAULT_TIMEOUT_S:g}).")
    parser.add_argument("--min-kill-rate", type=float, default=DEFAULT_MIN_KILL_RATE, help=f"Minimum kill rate to exit 0 (default: {DEFAULT_MIN_KILL_RATE}; 0 for report-only).")
    parser.add_argument("--markdown", action="store_true", help="Format output as Markdown.")
    parser.add_argument("--json", action="store_true", dest="emit_json", help="Emit structured JSON.")
    parser.add_argument("paths", nargs="*", metavar="PATH", help="Optional positional Python or JS/TS file targets.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.max_mutants < 1 or args.timeout <= 0 or not (0.0 <= args.min_kill_rate <= 1.0):
        print("error: invalid numeric threshold (--max-mutants >= 1, --timeout > 0, 0.0 <= --min-kill-rate <= 1.0)", file=sys.stderr)
        return 2

    raw_root = Path(args.repo_root).resolve()
    toplevel = _review._resolve_git_toplevel(raw_root) if args.repo_root == "." else None
    root = toplevel if toplevel is not None else raw_root
    cmd_tokens = shlex.split(args.test_cmd) if args.test_cmd else None

    try:
        raw_files = list(args.files or []) + list(args.paths or [])
        if raw_files:
            mode = "files"
            targets = _resolve_targets_from_files(raw_files, raw_root=raw_root, root=root, toplevel=toplevel)
        else:
            mode = "diff"
            targets = targets_from_diff(_resolve_diff_text(args, root))
        report = run_diff_mutation(
            root, targets, test_cmd=cmd_tokens, max_mutants=args.max_mutants,
            timeout_s=args.timeout, min_kill_rate=args.min_kill_rate, mode=mode,
        )
    except (OSError, ValueError) as exc:
        if args.emit_json:
            print(json.dumps({"ok": False, "exit_code": 2, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.emit_json else format_mutation_report(report, markdown=args.markdown))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
