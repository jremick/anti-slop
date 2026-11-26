"""Deterministic, zero-dependency automated graders for coding benchmark cases.

Each grader exposes `grade(candidate_path, ...)` returning a JSON-serializable
dict `{"case_id": str, "passed": bool, "checks": [{"id", "passed", "detail"}]}`
and a CLI entrypoint exiting 0 on pass and 1 on fail.
"""

from __future__ import annotations

import ast
from contextlib import contextmanager
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import sysconfig
import tokenize
from types import ModuleType
from typing import Any, Iterator
import uuid


_MARKER_RE = re.compile(r"\b(TODO|FIXME|XXX)\b", re.IGNORECASE)
_CHATBOT_OPENER_RE = re.compile(
    r"^\s*(?:sure|certainly|of course|absolutely|happy to|glad to|here(?:'s| is)|below is|i(?:'ve| have) (?:updated|written|drafted|shortened|prepared))\b",
    re.IGNORECASE,
)
_CHATBOT_CLOSER_RE = re.compile(
    r"(?:^|[.!?\n]\s*)(?:"
    r"(?:please\s+)?let\s+me\s+know\s+if\b|"
    r"(?:i\s+)?hope\s+this\s+helps\b|"
    r"feel\s+free\s+to\b|"
    r"(?:i(?:['\u2019]m|\s+am|['\u2019]d|\s+would)?\s*(?:be\s+)?)?happy\s+to\s+(?:help|adjust|clarify|discuss|assist|revise|walk\s+through|make\s+changes)\b|"
    r"(?:please\s+)?do(?:n['\u2019]t|\s+not)\s+hesitate\s+to\b|"
    r"if\s+you(?:['\u2019]d|\s+would)?\s+(?:like|want|need)\s+(?:me\s+to|any(?:thing)?\s+(?:else|further|other))\b|"
    r"if\s+you\s+have\s+any\s+(?:other\s+)?questions\b"
    r")",
    re.IGNORECASE,
)
_DECORATIVE_EMOJI_RE = re.compile(r"[\U0001f680\u2728\U0001f525\U0001f389\U0001f4a1\U0001f3af\U0001f31f\U0001f4aa]")
_FENCE_LINE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_INLINE_BACKTICK_RE = re.compile(r"(?<!`)(`+)([^`\n]+?)\1(?!`)")
_WORD_COUNT_META_RE = re.compile(
    r"(?:^|\n)\s*(?:[\(\[\*_`—–-]+\s*)?(?:word\s*count\s*[:=]\s*\d+|\d+\s+words\b)(?:\s*[\)\]\*_`\.]+)?\s*$",
    re.IGNORECASE,
)


def _strip_fenced_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` or ~~~) while preserving non-fenced prose lines."""
    out_lines: list[str] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        match = _FENCE_LINE_RE.match(line)
        if match:
            marker = match.group(1)
            rest = line[match.end():].strip()
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len and rest == "":
                in_fence = False
            continue
        if not in_fence:
            out_lines.append(line)
    return "\n".join(out_lines)


def _strip_inline_code_spans(text: str) -> str:
    """Remove inline Markdown backtick spans (`...`) so quoted code/literals do not false-positive."""
    return _INLINE_BACKTICK_RE.sub("", text)


def _trailing_prose_segment(non_fenced: str) -> str:
    """Return the final non-empty alphanumeric prose paragraph after dropping word-count footers and HRs."""
    trimmed = _WORD_COUNT_META_RE.sub("", non_fenced.strip()).strip()
    if not trimmed:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", trimmed) if p.strip()]
    for para in reversed(paragraphs):
        if any(ch.isalnum() for ch in para):
            return para
    return paragraphs[-1] if paragraphs else trimmed


def inspect_text_constraints(
    text: str,
    max_words: int | None = None,
    check_closers: bool = False,
    check_emojis: bool = False,
) -> dict[str, Any]:
    """Deterministically measure lexical/raw word counts and wrapper/meta-commentary hits."""
    raw_tokens = text.split()
    lexical_tokens = [tok for tok in raw_tokens if any(ch.isalnum() for ch in tok)]
    first_nonempty = next((line.strip() for line in text.splitlines() if line.strip()), "")
    has_opener = bool(_CHATBOT_OPENER_RE.search(first_nonempty))
    has_wordcount_footer = bool(_WORD_COUNT_META_RE.search(text.strip()))

    non_fenced = _strip_fenced_code_blocks(text)
    prose_without_inline_code = _strip_inline_code_spans(non_fenced)
    trailing_prose = _trailing_prose_segment(prose_without_inline_code)
    closer_match = _CHATBOT_CLOSER_RE.search(trailing_prose)
    has_closer = bool(closer_match)
    emoji_hits = sorted(set(_DECORATIVE_EMOJI_RE.findall(prose_without_inline_code)))
    has_decorative_emoji = bool(emoji_hits)

    issues: list[str] = []
    if max_words is not None and len(lexical_tokens) > max_words:
        issues.append(f"lexical word count {len(lexical_tokens)} exceeds cap {max_words} (raw={len(raw_tokens)})")
    if has_opener:
        issues.append(f"chatbot/wrapper opener detected: {first_nonempty[:60]!r}")
    if has_wordcount_footer:
        issues.append("meta word-count postscript detected")
    if check_closers and has_closer and closer_match is not None:
        issues.append(f"chatbot closer detected: {closer_match.group(0).strip()!r}")
    if check_emojis and has_decorative_emoji:
        issues.append(f"decorative emoji detected: {''.join(emoji_hits)}")
    return {
        "raw_words": len(raw_tokens),
        "lexical_words": len(lexical_tokens),
        "max_words": max_words,
        "has_opener": has_opener,
        "has_wordcount_footer": has_wordcount_footer,
        "has_closer": has_closer,
        "has_decorative_emoji": has_decorative_emoji,
        "passed": not issues,
        "issues": issues,
    }


def _stdlib_module_names() -> frozenset[str]:
    names = getattr(sys, "stdlib_module_names", None)
    if names is not None:
        return frozenset(names)
    discovered: set[str] = set(sys.builtin_module_names) | {"__future__", "builtins"}
    for key in ("stdlib", "platstdlib"):
        raw_dir = sysconfig.get_paths().get(key)
        if not raw_dir:
            continue
        std_dir = Path(raw_dir)
        if not std_dir.is_dir():
            continue
        for entry in std_dir.iterdir():
            if entry.name == "site-packages":
                continue
            if entry.is_dir() and (entry / "__init__.py").is_file():
                discovered.add(entry.name)
            elif entry.is_file() and entry.suffix == ".py":
                discovered.add(entry.stem)
        dynload = std_dir / "lib-dynload"
        if dynload.is_dir():
            for entry in dynload.iterdir():
                if entry.is_file():
                    discovered.add(entry.name.split(".", 1)[0])
    return frozenset(discovered)


_STDLIB_MODULES = _stdlib_module_names()


def make_check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    """Create a normalized check-result record."""
    return {
        "id": check_id,
        "passed": bool(passed),
        "detail": detail,
    }


def build_report(case_id: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """Combine individual check records with non-compensatory pass/fail logic."""
    return {
        "case_id": case_id,
        "passed": bool(checks) and all(check["passed"] for check in checks),
        "checks": checks,
    }


def emit_report(report: dict[str, Any]) -> int:
    """Print structured JSON grading output and return CLI exit code (0/1)."""
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def sha256_file(path: Path) -> str:
    """Return lowercase SHA-256 hex digest of a file's raw bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_candidate_ast(path: Path) -> tuple[str, ast.Module]:
    """Read and parse a Python candidate file."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    return source, tree


def load_candidate_module(path: Path, prefix: str = "grader_candidate") -> ModuleType:
    """Load a candidate Python file in an isolated ephemeral module namespace."""
    module_name = f"_{prefix}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot create module spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


@contextmanager
def load_candidate_package(parent_dir: Path, package_name: str) -> Iterator[ModuleType]:
    """Import a candidate Python package from `parent_dir` cleanly without sys.modules leaks."""
    parent_str = str(parent_dir.resolve())
    saved_modules: dict[str, ModuleType] = {}
    for key in list(sys.modules):
        if key == package_name or key.startswith(f"{package_name}."):
            saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, parent_str)
    importlib.invalidate_caches()
    try:
        pkg = importlib.import_module(package_name)
        yield pkg
    finally:
        try:
            sys.path.remove(parent_str)
        except ValueError:
            pass
        for key in list(sys.modules):
            if key == package_name or key.startswith(f"{package_name}."):
                sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


def find_non_stdlib_imports(
    tree: ast.Module,
    *,
    allowed_packages: frozenset[str] | set[str] = frozenset(),
    allow_relative: bool = False,
) -> list[str]:
    """Return any imported top-level module not in Python's standard library or `allowed_packages`."""
    stdlib = _STDLIB_MODULES | set(allowed_packages)
    disallowed: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top not in stdlib:
                    disallowed.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                if not allow_relative:
                    disallowed.append(f".{node.module or ''}")
                continue
            if node.module:
                top = node.module.split(".", 1)[0]
                if top not in stdlib:
                    disallowed.append(node.module)
    return sorted(set(disallowed))


def find_broad_excepts(node: ast.AST, context_label: str) -> list[str]:
    """Flag bare `except:` or broad `except Exception` / `except BaseException` handlers."""
    issues: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.ExceptHandler):
            if sub.type is None:
                issues.append(f"{context_label} uses bare except at line {sub.lineno}")
            elif isinstance(sub.type, ast.Name) and sub.type.id in {"Exception", "BaseException"}:
                issues.append(f"{context_label} uses broad except {sub.type.id} at line {sub.lineno}")
            elif isinstance(sub.type, ast.Tuple):
                for elt in sub.type.elts:
                    if isinstance(elt, ast.Name) and elt.id in {"Exception", "BaseException"}:
                        issues.append(f"{context_label} uses broad except {elt.id} at line {sub.lineno}")
    return issues


def _is_docstring_stmt(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _is_abstract_or_protocol_func(func: ast.AST, parent_class: ast.ClassDef | None) -> bool:
    if isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for decorator in func.decorator_list:
            if isinstance(decorator, ast.Name) and decorator.id in {"abstractmethod", "overload"}:
                return True
            if isinstance(decorator, ast.Attribute) and decorator.attr in {"abstractmethod", "overload"}:
                return True
    if parent_class is not None:
        for base in parent_class.bases:
            if isinstance(base, ast.Name) and base.id == "Protocol":
                return True
            if isinstance(base, ast.Attribute) and base.attr == "Protocol":
                return True
    return False


def _is_not_implemented_raise(node: ast.AST) -> bool:
    if not isinstance(node, ast.Raise) or node.exc is None:
        return False
    exc_node = node.exc
    if isinstance(exc_node, ast.Call):
        exc_node = exc_node.func
    return (isinstance(exc_node, ast.Name) and exc_node.id == "NotImplementedError") or (
        isinstance(exc_node, ast.Attribute) and exc_node.attr == "NotImplementedError"
    )


def _class_base_names(cls: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in cls.bases:
        if isinstance(base, ast.Name):
            names.add(base.id)
        elif isinstance(base, ast.Attribute):
            names.add(base.attr)
    return names


def _is_pure_not_implemented_method(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    stmts = [s for s in func.body if not _is_docstring_stmt(s)]
    return len(stmts) == 1 and _is_not_implemented_raise(stmts[0])


def _is_overridden_base_hook(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    parent_class: ast.ClassDef | None,
    subclasses_by_base: dict[str, list[ast.ClassDef]],
) -> bool:
    """True when `func` is a pure `raise NotImplementedError` hook overridden by a concrete subclass."""
    if parent_class is None or not _is_pure_not_implemented_method(func):
        return False
    subclasses = subclasses_by_base.get(parent_class.name, [])
    if not subclasses:
        return False
    concrete_overrides = 0
    for sub in subclasses:
        sub_bases = _class_base_names(sub)
        is_sub_abstract = (
            sub.name.startswith(("Abstract", "_Abstract"))
            or "ABC" in sub_bases
            or "Protocol" in sub_bases
        )
        matching = [
            item
            for item in sub.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == func.name
        ]
        if not matching:
            if not is_sub_abstract:
                return False
            continue
        if any(not _is_pure_not_implemented_method(m) for m in matching):
            concrete_overrides += 1
        elif not is_sub_abstract:
            return False
    return concrete_overrides > 0


def find_stub_or_placeholder_issues(source: str, tree: ast.Module) -> list[str]:
    """Detect TODO/FIXME comments, NotImplementedError raises, and bare stub bodies."""
    issues: list[str] = []

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok_type, tok_str, (line_no, _), _, _ in tokens:
            if tok_type == tokenize.COMMENT:
                match = _MARKER_RE.search(tok_str)
                if match:
                    issues.append(f"placeholder comment {match.group(1)} at line {line_no}")
    except tokenize.TokenError as exc:
        issues.append(f"tokenization error: {exc}")

    subclasses_by_base: dict[str, list[ast.ClassDef]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for base_name in _class_base_names(node):
                subclasses_by_base.setdefault(base_name, []).append(node)

    def visit(
        node: ast.AST,
        parent_class: ast.ClassDef | None = None,
        allow_not_implemented: bool = False,
    ) -> None:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                visit(item, parent_class=node, allow_not_implemented=False)
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_abstract = _is_abstract_or_protocol_func(node, parent_class)
            is_hook = _is_overridden_base_hook(node, parent_class, subclasses_by_base)
            if not is_abstract:
                stmts = [s for s in node.body if not _is_docstring_stmt(s)]
                if len(stmts) == 1:
                    only = stmts[0]
                    if isinstance(only, ast.Pass):
                        issues.append(f"bare pass stub in function '{node.name}' at line {node.lineno}")
                    elif (
                        isinstance(only, ast.Expr)
                        and isinstance(only.value, ast.Constant)
                        and only.value.value is Ellipsis
                    ):
                        issues.append(f"ellipsis stub in function '{node.name}' at line {node.lineno}")
            allow_ni = is_abstract or is_hook
            for item in node.body:
                visit(item, parent_class=None, allow_not_implemented=allow_ni)
            return
        if _is_not_implemented_raise(node):
            if not allow_not_implemented:
                issues.append(f"raises NotImplementedError at line {node.lineno}")
            return
        for child in ast.iter_child_nodes(node):
            visit(child, parent_class=None, allow_not_implemented=allow_not_implemented)

    for stmt in tree.body:
        visit(stmt)

    return issues


def top_level_public_defs(tree: ast.Module) -> set[str]:
    """Return top-level non-underscore function and class names."""
    names: set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not stmt.name.startswith("_"):
                names.add(stmt.name)
    return names


def collect_called_names(node: ast.AST) -> set[str]:
    """Collect simple function names and attribute method names called under `node`."""
    called: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name):
                called.add(func.id)
            elif isinstance(func, ast.Attribute):
                called.add(func.attr)
                if isinstance(func.value, ast.Name):
                    called.add(f"{func.value.id}.{func.attr}")
    return called


def get_function_node(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Find a top-level function definition by name."""
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            return stmt
    return None
