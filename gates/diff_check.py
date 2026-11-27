#!/usr/bin/env python3
"""Deterministic Layer-1 diff and Markdown prose gate.

Checks unified diffs, modified file lists, and PR bodies for:
  1. Stub/placeholder additions (TODO, FIXME, NotImplementedError, bare pass
     in non-abstract bodies) in added lines.
  2. Unauthorized edits under tests/ unless --allow-test-edit is set.
  3. Newly added test-skip/waiver annotations (DIFF-TEST-SKIP) in test diffs
     even when --allow-test-edit is set (override only with --allow-test-skip).
  4. Unjustified lint/type suppression comments (DIFF-SUPPRESSION), silent
     broad exception catches (DIFF-SILENT-CATCH), debug leftovers
     (DIFF-DEBUG-LEFTOVER), and hardcoded local host home paths
     (DIFF-HOST-PATH).
  5. Configurable net-LOC (--max-net-loc 400 [Heuristic]) and file-count
     (--max-files 10 [Heuristic]) budgets.
  6. Objective chatbot praise openers (DIFF-CHATBOT-OPENER), closing filler
     (DIFF-CHATBOT-CLOSER), and decorative AI emojis (DIFF-DECORATIVE-EMOJI,
     warning by default or error with --strict-prose) outside fenced code
     blocks.
  7. Backticked local file-path verification in Markdown docs without
     false-positiving on CLI flags, globs, URLs, prose slash-pairs, or code
     identifiers.

Stdlib Python only (zero external dependencies). Exits 0 on 0 errors, 1 on error.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
from pathlib import Path
import re
import sys
import tokenize
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


# [Heuristic] Starting diff budgets; calibrate locally against repo PR telemetry.
DEFAULT_MAX_NET_LOC = 400
DEFAULT_MAX_FILES = 10

CODE_EXTENSIONS = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs",
    ".rb", ".php", ".sh", ".bash", ".zsh", ".scala",
})

MARKDOWN_EXTENSIONS = frozenset({".md", ".markdown"})

KNOWN_PATH_EXTENSIONS = frozenset({
    ".py", ".md", ".markdown", ".json", ".jsonl", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh", ".txt",
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs",
    ".css", ".html", ".xml", ".csv", ".sql",
})

KNOWN_FILENAMES = frozenset({
    "Makefile", "Dockerfile", "LICENSE", "VERSION", "CODEOWNERS",
    ".gitignore", ".vale.ini", ".cursorignore",
})

ABSTRACT_DECORATORS = frozenset({
    "abstractmethod",
    "abstractclassmethod",
    "abstractstaticmethod",
    "abstractproperty",
    "overload",
})

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")

TODO_FIXME_RE = re.compile(
    r"(?:(?:#|//|/\*|--)\s*(?:TODO|FIXME)\b|^\s*\*\s*(?:TODO|FIXME)\b|(?:#|//|/\*|\*|--).*\b(?:TODO|FIXME)\s*[:(\[])"
)
COMMENT_TODO_RE = re.compile(
    r"(?:^#\s*(?:TODO|FIXME)\b|\b(?:TODO|FIXME)\s*[:(\[])"
)
C_COMMENT_TODO_RE = re.compile(
    r"(?:^\s*\*?\s*(?:TODO|FIXME)\b|\b(?:TODO|FIXME)\s*[:(\[])"
)
NOT_IMPL_RE = re.compile(r"\braise\s+NotImplementedError\b|\bthrow\s+new\s+NotImplementedError\b")
BARE_PASS_RE = re.compile(r"^\s*pass\s*(?:#.*)?$")
INLINE_DEF_PASS_RE = re.compile(r"^\s*(?:async\s+)?def\s+\w+.*:\s*pass\s*(?:#.*)?$")
DEF_HEADER_RE = re.compile(r"^(\s*)(?:async\s+)?def\s+\w+")
CLASS_HEADER_RE = re.compile(r"^(\s*)class\s+(\w+)\s*(?:\(([^)]*)\))?\s*:")
CLASS_START_RE = re.compile(r"^\s*class\s+\w+")
DECORATOR_RE = re.compile(r"^(\s*)@([\w.]+)")

CHATBOT_OPENER_RE = re.compile(
    r"^(?:"
    r"Sure[,!.\s]|"
    r"Certainly[,!.\s]|"
    r"Here\s+is\s+|"
    r"Here's\s+|"
    r"Here\s+are\s+|"
    r"Great\s+question\b|"
    r"Good\s+question\b|"
    r"Excellent\s+question\b|"
    r"Of\s+course[,!]|"
    r"Happy\s+to\s+help\b|"
    r"I'd\s+be\s+happy\s+to\b|"
    r"I\s+would\s+be\s+happy\s+to\b|"
    r"Absolutely[,!]|"
    r"Thanks\s+for\s+asking\b|"
    r"Thank\s+you\s+for\s+asking\b"
    r")",
    re.IGNORECASE,
)

# Inline backtick spans (supports single or multi-backtick spans on one line).
INLINE_BACKTICK_RE = re.compile(r"(?<!`)(`+)([^`\n]+?)\1(?!`)")
BAD_PATH_CHARS_RE = re.compile(r"[\s*?\[\]{}<>$|=;,\"'\\^+~()]")
LINE_ANCHOR_SUFFIX_RE = re.compile(r"(?::\d+(?:-\d+)?|#[^\s#]+)$")
ALL_CAPS_PLACEHOLDER_RE = re.compile(r"^[A-Z][A-Z0-9_-]{2,}$")
REAL_UPPERCASE_SEGMENTS = frozenset({
    "README", "LICENSE", "VERSION", "CHANGELOG", "AGENTS",
    "CONTRIBUTING", "CODEOWNERS", "ISSUE_TEMPLATE", "PULL_REQUEST_TEMPLATE",
    "SECURITY", "NOTICE", "AUTHORS", "HISTORY",
})

JS_TS_EXTENSIONS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
GO_EXTENSIONS = frozenset({".go"})

TEST_FILENAME_RE = re.compile(
    r"^(?:test_.*\.py|.*_test\.py|.*\.(?:test|spec)\.(?:[cm]?[jt]sx?))$",
    re.IGNORECASE,
)

PY_SKIP_DECORATOR_TARGETS = frozenset({
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
    "unittest.case.skip",
    "unittest.case.skipIf",
    "unittest.case.skipUnless",
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "pytest.mark.xfail",
})
PY_SKIP_CALL_TARGETS = frozenset({
    "pytest.skip",
    "pytest.xfail",
})
PY_SKIP_FALLBACK_RES: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("@unittest.skip", re.compile(r"@\s*unittest\.(?:skip|skipIf|skipUnless)\b")),
    ("@pytest.mark.skip/xfail", re.compile(r"@\s*(?:pytest\.)?mark\.(?:skip|skipif|xfail)\b")),
    ("pytest.mark.skip/xfail", re.compile(r"\bpytest\.mark\.(?:skip|skipif|xfail)\b")),
    ("skipTest()", re.compile(r"\b(?:self|cls)\.skipTest\s*\(")),
    ("pytest.skip()", re.compile(r"\bpytest\.(?:skip|xfail)\s*\(")),
)
JS_SKIP_RE = re.compile(
    r"\b(?:(?:it|test|describe)\.skip(?:\.each)?|xit|xtest|xdescribe)\s*\("
)

PY_TYPE_IGNORE_RE = re.compile(r"#\s*type\s*:\s*ignore\b(.*)$", re.IGNORECASE)
PY_NOQA_RE = re.compile(r"#\s*noqa\b(.*)$", re.IGNORECASE)
NOQA_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*$")
TYPE_IGNORE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]*$")
DIRECTIVE_PREFIX_RE = re.compile(r"^(?:noqa\b|pylint\s*:|pyright\s*:|type\s*:\s*ignore\b|fmt\s*:)", re.IGNORECASE)
ESLINT_RULE_RE = re.compile(r"^[@a-zA-Z][a-zA-Z0-9_/@-]*$")
GO_LINTER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

BROAD_EXCEPT_LINE_RE = re.compile(
    r"^(\s*)except(?:\s*:\s*(.*)|"
    r"\s+(?:builtins\.)?(?:Exception|BaseException)(?:\s+as\s+\w+)?\s*:\s*(.*)|"
    r"\s*\([^)]*(?<![.\w])(?:builtins\.)?(?:Exception|BaseException)\b[^)]*\)(?:\s+as\s+\w+)?\s*:\s*(.*))$"
)
SILENT_PY_BODY_RE = re.compile(
    r"^(?:pass|\.\.\.|return(?:\s+(?:None|False|\[\]|\{\}))?)\s*(?:#.*)?$"
)
NON_FUNC_BLOCK_HEADER_RE = re.compile(
    r"^\s*(?:except\b|try\s*:|finally\s*:|if\b|elif\b|else\s*:|for\b|async\s+for\b|while\b|with\b|async\s+with\b|match\b|case\b)"
)

JS_EMPTY_CATCH_INLINE_RE = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}")
JS_CATCH_OPEN_RE = re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*$")

PY_DEBUG_CALL_TARGETS = frozenset({
    "breakpoint",
    "builtins.breakpoint",
    "pdb.set_trace",
    "ipdb.set_trace",
    "pudb.set_trace",
})
PY_DEBUG_FALLBACK_RE = re.compile(
    r"(?<![.\w])breakpoint\s*\(|\b(?:pdb|ipdb|pudb)\.set_trace\s*\("
)
JS_DEBUGGER_RE = re.compile(r"(?:^|[;{}()\s])debugger(?=\s*(?:;|$|[}\]]))")

HOST_PATH_POSIX_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-])/(?:Users|home)/([^/\s\"'`|)\\:;,\]]+)/"
)
HOST_PATH_WIN_RE = re.compile(
    r"(?<![A-Za-z0-9_.\-])[A-Za-z]:(?:\\\\|\\|/)Users(?:\\\\|\\|/)([^/\\\s\"'`|):;,\]]+)(?:\\\\|\\|/)",
    re.IGNORECASE,
)
REAL_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
HOST_PATH_PLACEHOLDER_USERS = frozenset({
    "user",
    "username",
    "yourname",
    "your-user",
    "your_user",
    "your-username",
    "your_username",
    "example",
    "placeholder",
    "redacted",
    "home",
    "name",
    "me",
    "someone",
    "xxx",
})

CHATBOT_CLOSER_RE = re.compile(
    r"\b(?:"
    r"let\s+me\s+know\s+if\s+you(?:['\u2019]d|\s+would)\s+like|"
    r"let\s+me\s+know\s+if\s+you\s+need|"
    r"let\s+me\s+know\s+if\s+you\s+want|"
    r"let\s+me\s+know\s+if\s+you\s+have\s+any\s+(?:other\s+)?questions|"
    r"please\s+let\s+me\s+know\s+if|"
    r"i\s+hope\s+this\s+helps|"
    r"hope\s+this\s+helps|"
    r"hope\s+that\s+helps|"
    r"feel\s+free\s+to\s+reach\s+out|"
    r"feel\s+free\s+to\s+ask|"
    r"feel\s+free\s+to\s+let\s+me\s+know|"
    r"happy\s+to\s+adjust|"
    r"happy\s+to\s+help\s+if|"
    r"i(?:['\u2019]m|\s+am|['\u2019]d|\s+would\s+be)\s+happy\s+to\s+(?:adjust|help)|"
    r"(?:don['\u2019]t|do\s+not)\s+hesitate\s+to\s+(?:reach\s+out|ask)"
    r")\b",
    re.IGNORECASE,
)

DECORATIVE_EMOJIS: Tuple[str, ...] = (
    "\U0001f680",  # rocket
    "\u2728",      # sparkles
    "\U0001f525",  # fire
    "\U0001f389",  # party popper
    "\U0001f4a1",  # light bulb
    "\U0001f3af",  # direct hit
    "\U0001f31f",  # glowing star
    "\U0001f4aa",  # flexed biceps
)
DECORATIVE_EMOJI_RE = re.compile("[" + "".join(re.escape(e) for e in DECORATIVE_EMOJIS) + "]")


def _finding(
    code: str,
    severity: str,
    message: str,
    remediation: str,
    *,
    file: Optional[str] = None,
    line: Optional[int] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "remediation": remediation,
    }
    if file is not None:
        item["file"] = file
    if line is not None:
        item["line"] = line
    return item


def _normalize_relpath(raw: str) -> str:
    cleaned = raw.strip().replace("\\", "/")
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _is_test_path(path: str) -> bool:
    norm = _normalize_relpath(path)
    return norm.startswith("tests/") or "/tests/" in norm


def _is_test_file(path: str) -> bool:
    norm = _normalize_relpath(path)
    if _is_test_path(norm):
        return True
    parts = norm.split("/")
    if any(part in ("test", "tests", "__tests__") for part in parts[:-1]):
        return True
    return bool(TEST_FILENAME_RE.match(parts[-1])) if parts else False


def _is_code_path(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTENSIONS


def _is_js_ts_path(path: str) -> bool:
    return Path(path).suffix.lower() in JS_TS_EXTENSIONS


def _is_go_path(path: str) -> bool:
    return Path(path).suffix.lower() in GO_EXTENSIONS


def _is_markdown_path(path: str) -> bool:
    return Path(path).suffix.lower() in MARKDOWN_EXTENSIONS


def _glob_segment_to_regex(segment: str) -> str:
    out: List[str] = []
    i = 0
    n = len(segment)
    while i < n:
        ch = segment[i]
        if ch == "*":
            out.append("[^/]*")
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        elif ch == "[":
            j = i + 1
            if j < n and segment[j] in ("!", "^"):
                j += 1
            if j < n and segment[j] == "]":
                j += 1
            while j < n and segment[j] != "]":
                j += 1
            if j >= n:
                out.append(re.escape(ch))
                i += 1
            else:
                body = segment[i + 1 : j].replace("\\", "\\\\")
                if body.startswith(("!", "^")):
                    out.append(f"(?!/)[^{body[1:]}]")
                else:
                    out.append(f"[{body}]")
                i = j + 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "".join(out)


def _compile_exclude_glob(pattern: str) -> Optional[re.Pattern[str]]:
    """Compile a '**'-aware POSIX path glob into an anchored regex."""
    raw = pattern.strip().replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    raw = raw.lstrip("/")
    if not raw:
        return None
    if raw.endswith("/"):
        raw += "**"

    if "/" not in raw:
        if raw == "**":
            return re.compile(r"^.*$")
        seg_re = _glob_segment_to_regex(raw)
        return re.compile(rf"^(?:.*/)?{seg_re}$")

    parts: List[str] = []
    for part in (p for p in raw.split("/") if p):
        if part == "**" and parts and parts[-1] == "**":
            continue
        parts.append(part)

    regex_parts: List[str] = ["^"]
    for idx, part in enumerate(parts):
        is_first = idx == 0
        is_last = idx == len(parts) - 1
        if part == "**":
            if is_first and is_last:
                regex_parts.append(".*")
            elif is_first:
                regex_parts.append("(?:.*/)?")
            elif is_last:
                regex_parts.append("/.*")
            else:
                regex_parts.append("/(?:.*/)?")
        else:
            seg_re = _glob_segment_to_regex(part)
            if not is_first and parts[idx - 1] != "**":
                regex_parts.append("/")
            regex_parts.append(seg_re)
    regex_parts.append("$")
    return re.compile("".join(regex_parts))


def _compile_exclude_patterns(exclude: Optional[Sequence[str]]) -> List[re.Pattern[str]]:
    if not exclude:
        return []
    compiled: List[re.Pattern[str]] = []
    for raw in exclude:
        pat = _compile_exclude_glob(str(raw))
        if pat is not None:
            compiled.append(pat)
    return compiled


def _is_excluded_path(path: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    if not patterns:
        return False
    norm = _normalize_relpath(path).lstrip("/")
    if not norm:
        return False
    return any(pat.match(norm) is not None for pat in patterns)


DEFAULT_PROTECTED_PATHS_REL = ".anti-slop/protected-paths.json"


def load_protected_paths(
    repo_root: Optional[Path | str] = None,
    extra_patterns: Optional[Sequence[str]] = None,
) -> List[str]:
    """Load protected path globs from <repo>/.anti-slop/protected-paths.json plus CLI extras.

    Whenever any protected pattern is configured, `.anti-slop/protected-paths.json`
    itself is automatically protected so agents cannot weaken the lock unapproved.
    """
    raw_globs: List[str] = []
    if repo_root is not None:
        cfg_path = Path(repo_root).resolve() / DEFAULT_PROTECTED_PATHS_REL
        if cfg_path.is_file():
            try:
                parsed = json.loads(cfg_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Failed to parse {DEFAULT_PROTECTED_PATHS_REL}: {exc}") from exc
            if not isinstance(parsed, dict) or not isinstance(parsed.get("protected_paths"), list):
                raise ValueError(
                    f"{DEFAULT_PROTECTED_PATHS_REL} must be a JSON object with a 'protected_paths' array."
                )
            for idx, item in enumerate(parsed["protected_paths"]):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(
                        f"{DEFAULT_PROTECTED_PATHS_REL} protected_paths[{idx}] must be a non-empty string."
                    )
                raw_globs.append(item.strip())

    if extra_patterns:
        for raw in extra_patterns:
            cleaned = str(raw).strip()
            if cleaned:
                raw_globs.append(cleaned)

    deduped: List[str] = []
    seen: Set[str] = set()
    for pat in raw_globs:
        if pat not in seen:
            seen.add(pat)
            deduped.append(pat)

    if deduped and DEFAULT_PROTECTED_PATHS_REL not in seen:
        deduped.append(DEFAULT_PROTECTED_PATHS_REL)
    return deduped


def _compile_protected_patterns(globs: Sequence[str]) -> List[Tuple[str, re.Pattern[str]]]:
    compiled: List[Tuple[str, re.Pattern[str]]] = []
    for raw in globs:
        pat = _compile_exclude_glob(raw)
        if pat is not None:
            compiled.append((raw, pat))
    return compiled


def match_protected_path(
    path: str,
    compiled: Sequence[Tuple[str, re.Pattern[str]]],
) -> Optional[str]:
    """Return the first matching protected glob for path, or None."""
    if not compiled:
        return None
    norm = _normalize_relpath(path).lstrip("/")
    if not norm:
        return None
    for raw_glob, pat in compiled:
        if pat.match(norm) is not None:
            return raw_glob
    return None


def _filter_unified_diff(diff_text: str, patterns: Sequence[re.Pattern[str]]) -> str:
    """Drop per-file sections from a unified diff whose path matches any exclude pattern."""
    if not patterns or not diff_text:
        return diff_text

    blocks: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    old_rem = 0
    new_rem = 0

    def _start_block(path_hint: str = "", old_hint: str = "") -> Dict[str, Any]:
        block: Dict[str, Any] = {
            "lines": [],
            "path": path_hint,
            "old_path": old_hint,
            "seen_minus": False,
            "has_plus_or_hunk": False,
        }
        blocks.append(block)
        return block

    for raw_line in diff_text.splitlines(keepends=True):
        stripped = raw_line.rstrip("\r\n")
        in_hunk = old_rem > 0 or new_rem > 0

        if stripped.startswith("diff --git "):
            parts = stripped.split()
            old_hint = _normalize_relpath(parts[2]) if len(parts) >= 3 else ""
            path_hint = _normalize_relpath(parts[3]) if len(parts) >= 4 else ""
            current = _start_block(path_hint=path_hint, old_hint=old_hint)
            old_rem = 0
            new_rem = 0
            current["lines"].append(raw_line)
            continue

        if in_hunk:
            if stripped.startswith(" "):
                old_rem = max(0, old_rem - 1)
                new_rem = max(0, new_rem - 1)
                if current is not None:
                    current["lines"].append(raw_line)
                continue
            if stripped.startswith("-"):
                old_rem = max(0, old_rem - 1)
                if current is not None:
                    current["lines"].append(raw_line)
                continue
            if stripped.startswith("+"):
                new_rem = max(0, new_rem - 1)
                if current is not None:
                    current["lines"].append(raw_line)
                continue
            if stripped.startswith("\\ No newline at end of file"):
                if current is not None:
                    current["lines"].append(raw_line)
                continue
            # Malformed/truncated hunk: fall through to header inspection.
            old_rem = 0
            new_rem = 0

        if stripped.startswith("--- "):
            src = stripped[4:].split("\t", 1)[0].strip()
            if current is None or current["has_plus_or_hunk"] or current["seen_minus"]:
                current = _start_block()
            current["seen_minus"] = True
            if src != "/dev/null":
                current["old_path"] = _normalize_relpath(src)
            current["lines"].append(raw_line)
            continue

        if stripped.startswith("+++ "):
            dst = stripped[4:].split("\t", 1)[0].strip()
            if current is None:
                current = _start_block()
            current["has_plus_or_hunk"] = True
            if dst == "/dev/null":
                if not current["path"] and current["old_path"]:
                    current["path"] = current["old_path"]
            else:
                current["path"] = _normalize_relpath(dst)
            current["lines"].append(raw_line)
            continue

        if stripped.startswith("rename to ") and current is not None:
            current["path"] = _normalize_relpath(stripped[len("rename to ") :])
            current["lines"].append(raw_line)
            continue

        hunk_match = HUNK_HEADER_RE.match(stripped)
        if hunk_match:
            if current is None:
                current = _start_block()
            current["has_plus_or_hunk"] = True
            old_rem = int(hunk_match.group(2)) if hunk_match.group(2) is not None else 1
            new_rem = int(hunk_match.group(4)) if hunk_match.group(4) is not None else 1
            current["lines"].append(raw_line)
            continue

        if current is not None:
            current["lines"].append(raw_line)

    kept_parts: List[str] = []
    for block in blocks:
        effective = block["path"] or block["old_path"]
        if effective and _is_excluded_path(effective, patterns):
            continue
        kept_parts.extend(block["lines"])
    return "".join(kept_parts)


def parse_unified_diff(diff_text: str) -> Dict[str, Any]:
    """Parse a unified diff string into per-file hunks and line statistics."""
    files: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    current_hunk: Optional[Dict[str, Any]] = None
    old_line = 0
    new_line = 0

    def _start_file(path_hint: Optional[str] = None) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "path": _normalize_relpath(path_hint) if path_hint else "",
            "old_path": "",
            "is_new": False,
            "is_deleted": False,
            "added_lines": [],
            "deleted_lines": [],
            "hunks": [],
        }
        files.append(entry)
        return entry

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("diff --git "):
            parts = raw_line.split()
            b_path = parts[3] if len(parts) >= 4 else ""
            current = _start_file(b_path)
            if len(parts) >= 3:
                current["old_path"] = _normalize_relpath(parts[2])
            current_hunk = None
            continue

        if raw_line.startswith("--- "):
            src = raw_line[4:].split("\t", 1)[0].strip()
            if current is None or (current["hunks"] or current["old_path"] or current["is_new"]):
                # Support diffs without leading 'diff --git' header.
                if current is None or current["hunks"]:
                    current = _start_file()
            if src == "/dev/null":
                current["is_new"] = True
            else:
                current["old_path"] = _normalize_relpath(src)
            current_hunk = None
            continue

        if raw_line.startswith("+++ "):
            dst = raw_line[4:].split("\t", 1)[0].strip()
            if current is None:
                current = _start_file()
            if dst == "/dev/null":
                current["is_deleted"] = True
                if not current["path"] and current["old_path"]:
                    current["path"] = current["old_path"]
            else:
                current["path"] = _normalize_relpath(dst)
            current_hunk = None
            continue

        if raw_line.startswith("rename to ") and current is not None:
            current["path"] = _normalize_relpath(raw_line[len("rename to "):])
            continue

        hunk_match = HUNK_HEADER_RE.match(raw_line)
        if hunk_match:
            if current is None:
                current = _start_file()
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(3))
            current_hunk = {
                "old_start": old_line,
                "new_start": new_line,
                "lines": [],
            }
            current["hunks"].append(current_hunk)
            continue

        if current is None or current_hunk is None:
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            text = raw_line[1:]
            current["added_lines"].append((new_line, text))
            current_hunk["lines"].append(("+", new_line, text))
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            text = raw_line[1:]
            current["deleted_lines"].append((old_line, text))
            current_hunk["lines"].append(("-", old_line, text))
            old_line += 1
        elif raw_line.startswith(" "):
            text = raw_line[1:]
            current_hunk["lines"].append((" ", new_line, text))
            old_line += 1
            new_line += 1
        elif raw_line.startswith("\\ No newline at end of file"):
            continue

    total_added = sum(len(f["added_lines"]) for f in files)
    total_deleted = sum(len(f["deleted_lines"]) for f in files)
    unique_paths = {f["path"] for f in files if f["path"]}

    return {
        "files": files,
        "stats": {
            "files_changed": len(unique_paths) if unique_paths else len(files),
            "added_lines": total_added,
            "deleted_lines": total_deleted,
            "net_loc": total_added - total_deleted,
        },
    }


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return ""


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _base_name(node.value)
    return ""


def _is_protocol_class(cls: ast.ClassDef) -> bool:
    return any(_base_name(base) == "Protocol" for base in cls.bases)


def _is_exception_class(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        name = _base_name(base)
        if name in ("Exception", "BaseException") or name.endswith("Error") or name.endswith("Exception"):
            return True
    return False


def _strip_docstring(body: List[ast.stmt]) -> List[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _is_raise_not_implemented(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Raise) or stmt.exc is None:
        return False
    exc = stmt.exc
    if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
        return True
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
        return True
    return False


def _python_comment_todo_lines(source: str) -> Optional[Set[int]]:
    """Return 1-based line numbers of Python COMMENT tokens containing TODO or FIXME."""
    todo_lines: Set[int] = set()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT and COMMENT_TODO_RE.search(tok.string):
                todo_lines.add(tok.start[0])
    except (tokenize.TokenError, IndentationError):
        return None
    return todo_lines


def _python_comments_by_line(source: str) -> Optional[Dict[int, List[str]]]:
    """Return mapping of 1-based line number -> list of Python COMMENT token strings."""
    comments: Dict[int, List[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                comments.setdefault(tok.start[0], []).append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return None
    return comments


def _dotted_name(node: ast.expr) -> str:
    parts: List[str] = []
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return ".".join(parts)
    return ""


def _python_import_aliases(tree: ast.AST) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name if alias.asname else local
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                aliases[local] = f"{mod}.{alias.name}" if mod else alias.name
    return aliases


def _resolve_dotted(dotted: str, aliases: Dict[str, str]) -> str:
    if not dotted:
        return ""
    head, sep, tail = dotted.partition(".")
    resolved_head = aliases.get(head, head)
    return f"{resolved_head}.{tail}" if sep else resolved_head


def _python_ast_test_skip_lines(source: str) -> Optional[Dict[int, str]]:
    """Return {1-based lineno: skip_construct} for Python test-skip/waiver AST nodes."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    aliases = _python_import_aliases(tree)
    hits: Dict[int, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                resolved = _resolve_dotted(_dotted_name(target), aliases)
                if resolved in PY_SKIP_DECORATOR_TARGETS:
                    hits.setdefault(dec.lineno, f"@{resolved}")
        elif isinstance(node, ast.Attribute):
            resolved = _resolve_dotted(_dotted_name(node), aliases)
            if resolved in PY_SKIP_DECORATOR_TARGETS:
                hits.setdefault(node.lineno, resolved)
        elif isinstance(node, ast.Call):
            dotted = _dotted_name(node.func)
            resolved = _resolve_dotted(dotted, aliases)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "skipTest":
                hits.setdefault(node.lineno, f"{dotted or 'skipTest'}()")
            elif resolved in PY_SKIP_CALL_TARGETS:
                hits.setdefault(node.lineno, f"{resolved}()")

    return hits


def _broad_except_label(exc_type: Optional[ast.expr], aliases: Dict[str, str]) -> Optional[str]:
    if exc_type is None:
        return "bare except:"
    if isinstance(exc_type, ast.Tuple):
        for elt in exc_type.elts:
            found = _broad_except_label(elt, aliases)
            if found is not None:
                return found
        return None
    resolved = _resolve_dotted(_dotted_name(exc_type), aliases)
    if resolved in ("Exception", "BaseException", "builtins.Exception", "builtins.BaseException"):
        return f"broad except {resolved.split('.')[-1]}:"
    return None


def _silent_handler_body(body: List[ast.stmt]) -> Optional[Tuple[int, str]]:
    effective = _strip_docstring(body)
    if len(effective) != 1:
        return None
    stmt = effective[0]
    if isinstance(stmt, ast.Pass):
        return stmt.lineno, "pass"
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    ):
        return stmt.lineno, "..."
    if isinstance(stmt, ast.Return):
        val = stmt.value
        if val is None:
            return stmt.lineno, "return"
        if isinstance(val, ast.Constant) and val.value is None:
            return stmt.lineno, "return None"
        if isinstance(val, ast.Constant) and val.value is False:
            return stmt.lineno, "return False"
        if isinstance(val, ast.List) and len(val.elts) == 0:
            return stmt.lineno, "return []"
        if isinstance(val, ast.Dict) and len(val.keys) == 0:
            return stmt.lineno, "return {}"
    return None


def _python_ast_silent_catch_handlers(source: str) -> Optional[List[Tuple[int, int, str]]]:
    """Return [(handler_lineno, body_lineno, desc), ...] for bare/broad silent catches."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    aliases = _python_import_aliases(tree)
    hits: List[Tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            broad = _broad_except_label(node.type, aliases)
            if broad is None:
                continue
            silent = _silent_handler_body(node.body)
            if silent is not None:
                body_lineno, body_desc = silent
                hits.append((node.lineno, body_lineno, f"{broad} {body_desc}"))
    hits.sort(key=lambda item: (item[0], item[1]))
    return hits


def _python_ast_debug_leftover_lines(source: str) -> Optional[Dict[int, str]]:
    """Return {1-based lineno: call_name} for Python debugger leftover calls."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    aliases = _python_import_aliases(tree)
    hits: Dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            resolved = _resolve_dotted(_dotted_name(node.func), aliases)
            if resolved in PY_DEBUG_CALL_TARGETS:
                hits.setdefault(node.lineno, f"{resolved}()")
    return hits


def _scan_py_lines_fallback(lines: Sequence[str]) -> Tuple[List[str], List[Tuple[int, str]]]:
    """Lightweight stateful Python string/comment splitter for diff hunks without full AST."""
    code_only: List[str] = []
    comments: List[Tuple[int, str]] = []
    triple_quote: Optional[str] = None

    for idx, line in enumerate(lines):
        lineno = idx + 1
        chars: List[str] = []
        in_single = False
        in_double = False
        i = 0
        n = len(line)
        while i < n:
            if triple_quote is not None:
                if line[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if line[i : i + 3] == triple_quote:
                    triple_quote = None
                    chars.append('""')
                    i += 3
                    continue
                i += 1
                continue

            if in_single or in_double:
                q = "'" if in_single else '"'
                if line[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if line[i] == q:
                    in_single = False
                    in_double = False
                    chars.append(q)
                    i += 1
                    continue
                i += 1
                continue

            if line[i] == "#":
                comments.append((lineno, line[i:]))
                break
            if line[i : i + 3] in ('"""', "'''"):
                triple_quote = line[i : i + 3]
                i += 3
                continue
            if line[i] == '"':
                in_double = True
                chars.append('"')
                i += 1
                continue
            if line[i] == "'":
                in_single = True
                chars.append("'")
                i += 1
                continue
            chars.append(line[i])
            i += 1

        code_only.append("".join(chars))

    return code_only, comments


def _scan_c_like_lines(lines: Sequence[str]) -> Tuple[List[str], List[Tuple[int, str]]]:
    """Stateful JS/TS/Go scanner returning (code_only_lines, [(1-based lineno, comment_body)])."""
    code_only: List[str] = []
    comments: List[Tuple[int, str]] = []
    in_block = False
    in_backtick = False

    for idx, line in enumerate(lines):
        lineno = idx + 1
        chars: List[str] = []
        block_buf: List[str] = []
        in_single = False
        in_double = False
        i = 0
        n = len(line)

        while i < n:
            if in_block:
                if line[i : i + 2] == "*/":
                    comments.append((lineno, "".join(block_buf)))
                    block_buf = []
                    in_block = False
                    chars.append(" ")
                    i += 2
                    continue
                block_buf.append(line[i])
                i += 1
                continue

            if in_backtick:
                if line[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if line[i] == "`":
                    in_backtick = False
                    chars.append("`")
                    i += 1
                    continue
                i += 1
                continue

            if in_single or in_double:
                q = "'" if in_single else '"'
                if line[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if line[i] == q:
                    in_single = False
                    in_double = False
                    chars.append(q)
                    i += 1
                    continue
                i += 1
                continue

            if line[i : i + 2] == "//":
                comments.append((lineno, line[i + 2 :]))
                break
            if line[i : i + 2] == "/*":
                in_block = True
                block_buf = []
                chars.append(" ")
                i += 2
                continue
            if line[i] == '"':
                in_double = True
                chars.append('"')
                i += 1
                continue
            if line[i] == "'":
                in_single = True
                chars.append("'")
                i += 1
                continue
            if line[i] == "`":
                in_backtick = True
                chars.append("`")
                i += 1
                continue
            chars.append(line[i])
            i += 1

        if in_block and block_buf:
            comments.append((lineno, "".join(block_buf)))
        code_only.append("".join(chars))

    return code_only, comments


def _py_suppression_issues(comment_text: str) -> List[str]:
    if not re.match(r"^\s*#\s*(?:type\s*:\s*ignore|noqa)\b", comment_text, re.IGNORECASE):
        return []
    issues: List[str] = []
    ti = PY_TYPE_IGNORE_RE.search(comment_text)
    if ti:
        rest = ti.group(1)
        bm = re.match(r"^\[\s*([^\]]+)\s*\](.*)$", rest)
        if not bm:
            issues.append("bare '# type: ignore' without specific [code] and reason")
        else:
            codes = [c.strip() for c in bm.group(1).split(",") if c.strip()]
            after = bm.group(2).strip()
            reason = re.sub(r"^(?:#|--|:|\u2014)+\s*", "", after).strip()
            if not codes or not all(TYPE_IGNORE_CODE_RE.match(c) for c in codes):
                issues.append("bare '# type: ignore' without a valid [code]")
            elif (
                not reason
                or DIRECTIVE_PREFIX_RE.match(reason)
                or not re.search(r"[A-Za-z]{2,}", reason)
            ):
                issues.append("unjustified '# type: ignore[...]' without a trailing reason")

    nq = PY_NOQA_RE.search(comment_text)
    if nq:
        rest = nq.group(1)
        nm = re.match(r"^\s*:\s*([^\s#]+(?:\s*,\s*[^\s#]+)*)", rest)
        if not nm:
            issues.append("bare '# noqa' without a specific rule code (e.g., '# noqa: E402')")
        else:
            codes = [c.strip() for c in nm.group(1).split(",") if c.strip()]
            if not codes or not all(NOQA_CODE_RE.match(c) for c in codes):
                issues.append("unjustified '# noqa' without specific rule code(s) (e.g., '# noqa: E402')")
    return issues


def _js_ts_suppression_issues(comment_body: str) -> List[str]:
    issues: List[str] = []
    if re.match(r"^\s*\*?\s*@ts-ignore\b", comment_body):
        issues.append("'@ts-ignore' suppression (use '@ts-expect-error -- <reason>' instead)")
        return issues

    te = re.match(r"^\s*\*?\s*@ts-expect-error\b(.*)$", comment_body)
    if te:
        reason = re.sub(r"^[\s:\-\u2014]+", "", te.group(1)).strip()
        if not re.search(r"[A-Za-z0-9]{2,}", reason):
            issues.append("bare '@ts-expect-error' without a trailing explanation")
        return issues

    es = re.match(r"^\s*\*?\s*(eslint-disable(?:-next-line|-line)?)\b(.*)$", comment_body)
    if es:
        directive = es.group(1)
        rest = es.group(2).strip()
        sep_m = re.match(r"^(.*?)\s+--(?:\s+(.*))?$", rest)
        if not sep_m:
            issues.append(f"bare '{directive}' without specific rule name(s) and '-- <reason>'")
            return issues
        rules_part = sep_m.group(1).strip()
        reason_part = (sep_m.group(2) or "").strip()
        rules = [r for r in re.split(r"[,\s]+", rules_part) if r]
        if (
            not rules
            or not all(ESLINT_RULE_RE.match(r) for r in rules)
            or not re.search(r"[A-Za-z0-9]{2,}", reason_part)
        ):
            issues.append(f"unjustified '{directive}' (requires specific rule name(s) and '-- <reason>')")
    return issues


def _go_suppression_issues(comment_body: str) -> List[str]:
    m = re.match(r"^\s*\*?\s*nolint\b(.*)$", comment_body, re.IGNORECASE)
    if not m:
        return []
    rest = m.group(1)
    lm = re.match(r"^:([A-Za-z0-9_,\-]+)(.*)$", rest)
    if not lm:
        return ["bare '// nolint' without linter name(s) and reason"]
    linters = [item.strip() for item in lm.group(1).split(",") if item.strip()]
    if not linters or any(not GO_LINTER_NAME_RE.match(item) or item.lower() == "all" for item in linters):
        return ["blanket or invalid '// nolint' without specific linter name(s) and reason"]
    after = lm.group(2).strip()
    reason = re.sub(r"^(?://|--|:|-)+\s*", "", after).strip()
    if not re.search(r"[A-Za-z]{2,}", reason):
        return ["'// nolint' without a trailing reason"]
    return []


def _is_real_host_username(user: str) -> bool:
    cleaned = user.strip()
    if not cleaned:
        return False
    if cleaned[0] in "<{$%[" or set(cleaned) <= {".", "\u2026"}:
        return False
    if cleaned.lower() in HOST_PATH_PLACEHOLDER_USERS:
        return False
    return bool(REAL_USERNAME_RE.match(cleaned))


def _find_host_path_matches(line: str) -> List[str]:
    matches: List[str] = []
    for regex in (HOST_PATH_POSIX_RE, HOST_PATH_WIN_RE):
        for m in regex.finditer(line):
            if _is_real_host_username(m.group(1)):
                matches.append(m.group(0))
    return matches


def _find_js_empty_catches(code_only_lines: Sequence[str]) -> List[Tuple[int, int]]:
    """Return [(catch_1based_lineno, close_1based_lineno), ...] for empty JS/TS catch blocks."""
    hits: List[Tuple[int, int]] = []
    n = len(code_only_lines)
    for idx, line in enumerate(code_only_lines):
        lineno = idx + 1
        if JS_EMPTY_CATCH_INLINE_RE.search(line):
            hits.append((lineno, lineno))
            continue
        if JS_CATCH_OPEN_RE.search(line):
            j = idx + 1
            while j < n and not code_only_lines[j].strip():
                j += 1
            if j < n and code_only_lines[j].lstrip().startswith("}"):
                hits.append((lineno, j + 1))
    return hits


def _find_py_hunk_silent_catches(
    visible_lines: Sequence[Tuple[str, int, str]],
) -> List[Tuple[int, int, str, bool]]:
    """Fallback Python silent-catch detector on non-deleted hunk lines.

    Returns [(handler_lineno, body_lineno, desc, any_line_added), ...].
    """
    hits: List[Tuple[int, int, str, bool]] = []
    n = len(visible_lines)
    for idx, (kind, lineno, text) in enumerate(visible_lines):
        m = BROAD_EXCEPT_LINE_RE.match(text)
        if not m:
            continue
        except_indent = len(m.group(1))
        inline_raw = next((g for g in m.groups()[1:] if g is not None), "")
        inline_code = inline_raw.split("#", 1)[0].strip()
        if inline_code:
            if SILENT_PY_BODY_RE.match(inline_code):
                hits.append((lineno, lineno, f"{text.strip().split(':', 1)[0]}: {inline_code}", kind == "+"))
            continue

        body_stmts: List[Tuple[str, int, str]] = []
        j = idx + 1
        while j < n:
            bkind, blineno, btext = visible_lines[j]
            stripped = btext.strip()
            if not stripped or stripped.startswith("#"):
                j += 1
                continue
            indent = len(btext) - len(btext.lstrip(" "))
            if indent <= except_indent:
                break
            # Skip single-line string docstring inside except block.
            if (
                not body_stmts
                and len(stripped) >= 6
                and (
                    (stripped.startswith('"""') and stripped.endswith('"""'))
                    or (stripped.startswith("'''") and stripped.endswith("'''"))
                )
            ):
                j += 1
                continue
            body_stmts.append((bkind, blineno, stripped))
            j += 1

        if len(body_stmts) == 1:
            bkind, blineno, bstripped = body_stmts[0]
            if SILENT_PY_BODY_RE.match(bstripped):
                header_label = text.strip().rstrip(":")
                body_code = bstripped.split("#", 1)[0].strip()
                hits.append((lineno, blineno, f"{header_label}: {body_code}", kind == "+" or bkind == "+"))
    return hits


def check_test_skips_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Detect test-skip/waiver annotations in Python or JS/TS test source text."""
    if not _is_test_file(rel_path):
        return []
    errors: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        ast_hits = _python_ast_test_skip_lines(source)
        if ast_hits is not None:
            for lineno in sorted(ast_hits):
                if added_lines is not None and lineno not in added_lines:
                    continue
                label = ast_hits[lineno]
                errors.append(
                    _finding(
                        code="DIFF-TEST-SKIP",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} adds test-skip/waiver annotation '{label}'.",
                        remediation="Fix the underlying failure instead of skipping tests, or pass --allow-test-skip if explicitly authorized.",
                    )
                )
            return errors

        code_only, _ = _scan_py_lines_fallback(source.splitlines())
        for lineno, code_line in enumerate(code_only, start=1):
            if added_lines is not None and lineno not in added_lines:
                continue
            for label, regex in PY_SKIP_FALLBACK_RES:
                if regex.search(code_line):
                    errors.append(
                        _finding(
                            code="DIFF-TEST-SKIP",
                            severity="error",
                            file=rel_path,
                            line=lineno,
                            message=f"{rel_path}:{lineno} adds test-skip/waiver annotation '{label}'.",
                            remediation="Fix the underlying failure instead of skipping tests, or pass --allow-test-skip if explicitly authorized.",
                        )
                    )
                    break
        return errors

    if _is_js_ts_path(rel_path):
        code_only, _ = _scan_c_like_lines(source.splitlines())
        for lineno, code_line in enumerate(code_only, start=1):
            if added_lines is not None and lineno not in added_lines:
                continue
            m = JS_SKIP_RE.search(code_line)
            if m:
                errors.append(
                    _finding(
                        code="DIFF-TEST-SKIP",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} adds test-skip/waiver call '{m.group(0).strip()}'.",
                        remediation="Fix the underlying failure instead of skipping tests, or pass --allow-test-skip if explicitly authorized.",
                    )
                )
    return errors


def check_suppressions_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Detect unjustified lint/type suppression comments in Python, JS/TS, or Go source text."""
    if not _is_code_path(rel_path):
        return []
    errors: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        by_line = _python_comments_by_line(source)
        if by_line is not None:
            comment_items: List[Tuple[int, str]] = [
                (ln, txt) for ln in sorted(by_line) for txt in by_line[ln]
            ]
        else:
            _, comment_items = _scan_py_lines_fallback(source.splitlines())
        for lineno, comment_text in comment_items:
            if added_lines is not None and lineno not in added_lines:
                continue
            for issue in _py_suppression_issues(comment_text):
                errors.append(
                    _finding(
                        code="DIFF-SUPPRESSION",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} adds {issue}.",
                        remediation="Fix the underlying lint/type error, or scope the suppression to a specific rule/code with an inline reason.",
                    )
                )
        return errors

    if _is_js_ts_path(rel_path):
        _, comments = _scan_c_like_lines(source.splitlines())
        for lineno, comment_body in comments:
            if added_lines is not None and lineno not in added_lines:
                continue
            for issue in _js_ts_suppression_issues(comment_body):
                errors.append(
                    _finding(
                        code="DIFF-SUPPRESSION",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} adds {issue}.",
                        remediation="Fix the underlying lint/type error, or use a scoped suppression with a specific rule and '-- <reason>'.",
                    )
                )
        return errors

    if _is_go_path(rel_path):
        _, comments = _scan_c_like_lines(source.splitlines())
        for lineno, comment_body in comments:
            if added_lines is not None and lineno not in added_lines:
                continue
            for issue in _go_suppression_issues(comment_body):
                errors.append(
                    _finding(
                        code="DIFF-SUPPRESSION",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} adds {issue}.",
                        remediation="Fix the linter finding or scope with '//nolint:<linter> // <reason>'.",
                    )
                )
    return errors


def check_silent_catches_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Detect bare/broad silent exception handlers in Python and empty catch blocks in JS/TS."""
    if not _is_code_path(rel_path):
        return []
    errors: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        ast_handlers = _python_ast_silent_catch_handlers(source)
        if ast_handlers is not None:
            for handler_lineno, body_lineno, desc in ast_handlers:
                if added_lines is not None and (
                    handler_lineno not in added_lines and body_lineno not in added_lines
                ):
                    continue
                report_line = (
                    handler_lineno
                    if (added_lines is None or handler_lineno in added_lines)
                    else body_lineno
                )
                errors.append(
                    _finding(
                        code="DIFF-SILENT-CATCH",
                        severity="error",
                        file=rel_path,
                        line=report_line,
                        message=f"{rel_path}:{report_line} swallows errors via silent handler ({desc}).",
                        remediation="Narrow the caught exception type or log/re-raise instead of silently swallowing broad exceptions.",
                    )
                )
            return errors

        visible = [("+", idx + 1, line) for idx, line in enumerate(source.splitlines())]
        for handler_lineno, body_lineno, desc, _ in _find_py_hunk_silent_catches(visible):
            if added_lines is not None and (
                handler_lineno not in added_lines and body_lineno not in added_lines
            ):
                continue
            report_line = (
                handler_lineno
                if (added_lines is None or handler_lineno in added_lines)
                else body_lineno
            )
            errors.append(
                _finding(
                    code="DIFF-SILENT-CATCH",
                    severity="error",
                    file=rel_path,
                    line=report_line,
                    message=f"{rel_path}:{report_line} swallows errors via silent handler ({desc}).",
                    remediation="Narrow the caught exception type or log/re-raise instead of silently swallowing broad exceptions.",
                )
            )
        return errors

    if _is_js_ts_path(rel_path):
        code_only, _ = _scan_c_like_lines(source.splitlines())
        for catch_lineno, close_lineno in _find_js_empty_catches(code_only):
            if added_lines is not None and (
                catch_lineno not in added_lines and close_lineno not in added_lines
            ):
                continue
            report_line = (
                catch_lineno
                if (added_lines is None or catch_lineno in added_lines)
                else close_lineno
            )
            errors.append(
                _finding(
                    code="DIFF-SILENT-CATCH",
                    severity="error",
                    file=rel_path,
                    line=report_line,
                    message=f"{rel_path}:{report_line} adds an empty JS/TS catch block.",
                    remediation="Handle, log, or rethrow the caught error instead of leaving an empty catch block.",
                )
            )
    return errors


def check_debug_leftovers_in_source(
    rel_path: str,
    source: str,
    *,
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Detect debug leftover statements (breakpoint(), pdb/ipdb.set_trace(), JS debugger)."""
    if not _is_code_path(rel_path):
        return []
    errors: List[Dict[str, Any]] = []
    suffix = Path(rel_path).suffix.lower()

    if suffix == ".py":
        ast_hits = _python_ast_debug_leftover_lines(source)
        if ast_hits is not None:
            for lineno in sorted(ast_hits):
                if added_lines is not None and lineno not in added_lines:
                    continue
                errors.append(
                    _finding(
                        code="DIFF-DEBUG-LEFTOVER",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} leaves debug call '{ast_hits[lineno]}' in code.",
                        remediation="Remove interactive debugger statements before committing.",
                    )
                )
            return errors

        code_only, _ = _scan_py_lines_fallback(source.splitlines())
        for lineno, code_line in enumerate(code_only, start=1):
            if added_lines is not None and lineno not in added_lines:
                continue
            m = PY_DEBUG_FALLBACK_RE.search(code_line)
            if m:
                errors.append(
                    _finding(
                        code="DIFF-DEBUG-LEFTOVER",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} leaves debug call '{m.group(0).strip()}' in code.",
                        remediation="Remove interactive debugger statements before committing.",
                    )
                )
        return errors

    if _is_js_ts_path(rel_path):
        code_only, _ = _scan_c_like_lines(source.splitlines())
        for lineno, code_line in enumerate(code_only, start=1):
            if added_lines is not None and lineno not in added_lines:
                continue
            if JS_DEBUGGER_RE.search(code_line):
                errors.append(
                    _finding(
                        code="DIFF-DEBUG-LEFTOVER",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} leaves a JS/TS 'debugger' statement in code.",
                        remediation="Remove interactive 'debugger;' statements before committing.",
                    )
                )
    return errors


def check_host_paths(
    text: str,
    *,
    source: str = "<text>",
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Detect hardcoded local machine home paths matching real usernames."""
    errors: List[Dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if added_lines is not None and lineno not in added_lines:
            continue
        found = _find_host_path_matches(line)
        if found:
            unique_hits = ", ".join(dict.fromkeys(found))
            errors.append(
                _finding(
                    code="DIFF-HOST-PATH",
                    severity="error",
                    file=source,
                    line=lineno,
                    message=f"{source}:{lineno} contains hardcoded local host home path ({unique_hits}).",
                    remediation="Replace local machine home paths with relative paths, Path.home()/env vars, or explicit placeholders like /Users/<user>/ or /Users/....",
                )
            )
    return errors


def _python_ast_stub_lines(source: str) -> Optional[Tuple[Set[int], Set[int], Set[int]]]:
    """Analyze Python source with AST.

    Returns (stub_pass_lines, stub_not_impl_lines, allowed_abstract_lines),
    or None if the source does not parse as valid Python.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    stub_pass: Set[int] = set()
    stub_not_impl: Set[int] = set()
    allowed_abstract: Set[int] = set()

    def _visit(node: ast.AST, in_protocol: bool = False, in_abstract_fn: bool = False) -> None:
        if isinstance(node, ast.ClassDef):
            cls_is_protocol = _is_protocol_class(node)
            cls_is_exc = _is_exception_class(node)
            effective_body = _strip_docstring(node.body)
            if cls_is_exc and len(effective_body) == 1 and isinstance(effective_body[0], ast.Pass):
                allowed_abstract.add(effective_body[0].lineno)
            for child in node.body:
                _visit(child, in_protocol=cls_is_protocol, in_abstract_fn=False)
            return

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_abstract = in_protocol or any(
                _decorator_name(dec) in ABSTRACT_DECORATORS for dec in node.decorator_list
            )
            effective_body = _strip_docstring(node.body)
            if len(effective_body) == 1 and isinstance(effective_body[0], ast.Pass):
                if is_abstract:
                    allowed_abstract.add(effective_body[0].lineno)
                else:
                    stub_pass.add(effective_body[0].lineno)
            for child in node.body:
                _visit(child, in_protocol=False, in_abstract_fn=is_abstract)
            return

        if isinstance(node, ast.Raise) and _is_raise_not_implemented(node):
            if in_abstract_fn:
                allowed_abstract.add(node.lineno)
            else:
                stub_not_impl.add(node.lineno)
            return

        for child in ast.iter_child_nodes(node):
            _visit(child, in_protocol=in_protocol, in_abstract_fn=in_abstract_fn)

    _visit(tree)
    return stub_pass, stub_not_impl, allowed_abstract


def _hunk_line_is_abstract_python(hunk_lines: List[Tuple[str, int, str]], target_idx: int) -> bool:
    """Heuristic fallback for unified diffs without full Python files on disk."""
    _, _, target_text = hunk_lines[target_idx]
    target_indent = len(target_text) - len(target_text.lstrip(" "))

    # Handle inline `def foo(...): pass` on the same line.
    if INLINE_DEF_PASS_RE.match(target_text):
        def_indent = target_indent
        idx = target_idx - 1
        while idx >= 0:
            kind, _, text = hunk_lines[idx]
            if kind == "-":
                idx -= 1
                continue
            stripped = text.strip()
            if not stripped or stripped.startswith("#"):
                idx -= 1
                continue
            dec_m = DECORATOR_RE.match(text)
            if dec_m and len(dec_m.group(1)) == def_indent:
                dec_leaf = dec_m.group(2).split(".")[-1]
                if dec_leaf in ABSTRACT_DECORATORS:
                    return True
                idx -= 1
                continue
            break
        return False

    # Walk backward through non-deleted lines to locate enclosing def/class.
    enclosing_def_idx: Optional[int] = None
    enclosing_def_indent: Optional[int] = None
    enclosing_class_line: Optional[str] = None

    idx = target_idx - 1
    while idx >= 0:
        kind, _, text = hunk_lines[idx]
        if kind == "-":
            idx -= 1
            continue
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            idx -= 1
            continue
        indent = len(text) - len(text.lstrip(" "))
        if enclosing_def_idx is None:
            cls_m = CLASS_HEADER_RE.match(text)
            if cls_m and indent < target_indent:
                bases = cls_m.group(3) or ""
                if re.search(r"\b(?:Protocol|Exception|BaseException|\w*Error|\w*Exception)\b", bases):
                    return True
                return False
            def_m = DEF_HEADER_RE.match(text)
            if def_m and indent < target_indent:
                enclosing_def_idx = idx
                enclosing_def_indent = indent
                idx -= 1
                continue
        else:
            # Check decorators at the same indentation as the enclosing def.
            dec_m = DECORATOR_RE.match(text)
            if dec_m and len(dec_m.group(1)) == enclosing_def_indent:
                dec_leaf = dec_m.group(2).split(".")[-1]
                if dec_leaf in ABSTRACT_DECORATORS:
                    return True
                idx -= 1
                continue
            cls_m = CLASS_HEADER_RE.match(text)
            if cls_m and indent < enclosing_def_indent:
                enclosing_class_line = text
                bases = cls_m.group(3) or ""
                if re.search(r"\bProtocol\b", bases):
                    return True
                break
            if indent <= enclosing_def_indent:
                break
        idx -= 1

    _ = enclosing_class_line
    return False


def _hunk_pass_is_non_function_block(
    hunk_lines: List[Tuple[str, int, str]],
    target_idx: int,
) -> bool:
    """Return True if a bare 'pass' sits directly under a class or non-function block."""
    _, _, target_text = hunk_lines[target_idx]
    target_indent = len(target_text) - len(target_text.lstrip(" "))
    idx = target_idx - 1
    while idx >= 0:
        kind, _, text = hunk_lines[idx]
        if kind == "-":
            idx -= 1
            continue
        stripped = text.strip()
        if not stripped or stripped.startswith("#"):
            idx -= 1
            continue
        indent = len(text) - len(text.lstrip(" "))
        if indent < target_indent:
            if stripped.startswith(")") and stripped.endswith(":"):
                # Multi-line header closing line (e.g. `class Foo(\n    str,\n):`);
                # walk back to its opening line at the same indentation.
                header_indent = indent
                idx -= 1
                while idx >= 0:
                    hkind, _, htext = hunk_lines[idx]
                    if hkind == "-":
                        idx -= 1
                        continue
                    hstripped = htext.strip()
                    if not hstripped or hstripped.startswith("#"):
                        idx -= 1
                        continue
                    hindent = len(htext) - len(htext.lstrip(" "))
                    if hindent <= header_indent:
                        return bool(
                            NON_FUNC_BLOCK_HEADER_RE.match(htext)
                            or CLASS_START_RE.match(htext)
                        )
                    idx -= 1
                return False
            return bool(NON_FUNC_BLOCK_HEADER_RE.match(text) or CLASS_START_RE.match(text))
        idx -= 1
    return False


def _check_code_stubs_in_hunks(
    file_entry: Dict[str, Any],
    repo_root: Optional[Path],
    errors: List[Dict[str, Any]],
) -> None:
    path = file_entry["path"]
    if not path or file_entry["is_deleted"] or not _is_code_path(path):
        return

    is_python = Path(path).suffix.lower() == ".py"
    is_c_like = _is_js_ts_path(path) or _is_go_path(path)
    ast_info: Optional[Tuple[Set[int], Set[int], Set[int]]] = None
    py_todo_lines: Optional[Set[int]] = None
    c_like_todo_lines: Optional[Set[int]] = None
    c_like_code_lines: Optional[List[str]] = None
    if repo_root is not None:
        disk_path = repo_root / path
        if disk_path.is_file():
            disk_source = disk_path.read_text(encoding="utf-8")
            if is_python:
                ast_info = _python_ast_stub_lines(disk_source)
                py_todo_lines = _python_comment_todo_lines(disk_source)
            elif is_c_like:
                c_like_code_lines, c_comments = _scan_c_like_lines(disk_source.splitlines())
                c_like_todo_lines = {
                    ln for ln, body in c_comments if C_COMMENT_TODO_RE.search(body)
                }

    for hunk in file_entry["hunks"]:
        hlines = hunk["lines"]
        hunk_py_todo: Optional[Set[int]] = None
        hunk_py_code: Optional[Dict[int, str]] = None
        hunk_c_todo: Optional[Set[int]] = None
        hunk_c_code: Optional[Dict[int, str]] = None

        if is_python and (py_todo_lines is None or ast_info is None):
            visible_indices = [i for i, (k, _, _) in enumerate(hlines) if k != "-"]
            visible_texts = [hlines[i][2] for i in visible_indices]
            py_code_only, py_comments = _scan_py_lines_fallback(visible_texts)
            if py_todo_lines is None:
                hunk_py_todo = {
                    visible_indices[ln - 1]
                    for ln, comment in py_comments
                    if COMMENT_TODO_RE.search(comment)
                }
            if ast_info is None:
                hunk_py_code = {
                    visible_indices[i]: py_code_only[i]
                    for i in range(len(visible_indices))
                }
        elif is_c_like and c_like_todo_lines is None:
            visible_indices = [i for i, (k, _, _) in enumerate(hlines) if k != "-"]
            visible_texts = [hlines[i][2] for i in visible_indices]
            c_code_only, c_comments = _scan_c_like_lines(visible_texts)
            hunk_c_todo = {
                visible_indices[ln - 1]
                for ln, body in c_comments
                if C_COMMENT_TODO_RE.search(body)
            }
            hunk_c_code = {
                visible_indices[i]: c_code_only[i]
                for i in range(len(visible_indices))
            }

        for idx, (kind, lineno, text) in enumerate(hlines):
            if kind != "+":
                continue
            if py_todo_lines is not None:
                has_todo = lineno in py_todo_lines
            elif hunk_py_todo is not None:
                has_todo = idx in hunk_py_todo
            elif c_like_todo_lines is not None:
                has_todo = lineno in c_like_todo_lines
            elif hunk_c_todo is not None:
                has_todo = idx in hunk_c_todo
            else:
                has_todo = bool(TODO_FIXME_RE.search(text))
            if has_todo:
                errors.append(
                    _finding(
                        code="DIFF-STUB-TODO",
                        severity="error",
                        file=path,
                        line=lineno,
                        message=f"{path}:{lineno} adds a TODO/FIXME placeholder stub.",
                        remediation="Complete the implementation or track follow-up work outside code stubs.",
                    )
                )

            if is_python:
                if ast_info is not None:
                    stub_pass, stub_not_impl, _ = ast_info
                    if lineno in stub_not_impl:
                        errors.append(
                            _finding(
                                code="DIFF-STUB-NOT-IMPLEMENTED",
                                severity="error",
                                file=path,
                                line=lineno,
                                message=f"{path}:{lineno} adds NotImplementedError in a non-abstract body.",
                                remediation="Implement the function body or mark an interface method with @abstractmethod.",
                            )
                        )
                    elif lineno in stub_pass:
                        errors.append(
                            _finding(
                                code="DIFF-STUB-PASS",
                                severity="error",
                                file=path,
                                line=lineno,
                                message=f"{path}:{lineno} adds a bare 'pass' stub in a non-abstract body.",
                                remediation="Implement the body or mark an interface method with @abstractmethod / Protocol.",
                            )
                        )
                else:
                    code_text = hunk_py_code.get(idx, text) if hunk_py_code is not None else text
                    if NOT_IMPL_RE.search(code_text):
                        if not _hunk_line_is_abstract_python(hlines, idx):
                            errors.append(
                                _finding(
                                    code="DIFF-STUB-NOT-IMPLEMENTED",
                                    severity="error",
                                    file=path,
                                    line=lineno,
                                    message=f"{path}:{lineno} adds NotImplementedError in a non-abstract body.",
                                    remediation="Implement the function body or mark an interface method with @abstractmethod.",
                                )
                            )
                    elif INLINE_DEF_PASS_RE.match(code_text) or (
                        BARE_PASS_RE.match(code_text) and not _hunk_pass_is_non_function_block(hlines, idx)
                    ):
                        if not _hunk_line_is_abstract_python(hlines, idx):
                            errors.append(
                                _finding(
                                    code="DIFF-STUB-PASS",
                                    severity="error",
                                    file=path,
                                    line=lineno,
                                    message=f"{path}:{lineno} adds a bare 'pass' stub in a non-abstract body.",
                                    remediation="Implement the body or mark an interface method with @abstractmethod / Protocol.",
                                )
                            )
            else:
                if c_like_code_lines is not None and 1 <= lineno <= len(c_like_code_lines):
                    code_text = c_like_code_lines[lineno - 1]
                elif hunk_c_code is not None:
                    code_text = hunk_c_code.get(idx, text)
                else:
                    code_text = text
                if NOT_IMPL_RE.search(code_text):
                    errors.append(
                        _finding(
                            code="DIFF-STUB-NOT-IMPLEMENTED",
                            severity="error",
                            file=path,
                            line=lineno,
                            message=f"{path}:{lineno} adds NotImplementedError placeholder.",
                            remediation="Implement the missing logic instead of shipping a placeholder.",
                        )
                    )


def _check_code_credibility_in_hunks(
    file_entry: Dict[str, Any],
    repo_root: Optional[Path],
    errors: List[Dict[str, Any]],
    *,
    allow_test_skip: bool = False,
) -> None:
    path = file_entry["path"]
    if not path or file_entry["is_deleted"] or not _is_code_path(path):
        return

    added_line_numbers: Set[int] = {ln for ln, _ in file_entry["added_lines"]}
    if not added_line_numbers:
        return

    disk_source: Optional[str] = None
    if repo_root is not None:
        disk_path = repo_root / path
        if disk_path.is_file():
            disk_source = disk_path.read_text(encoding="utf-8")

    if disk_source is not None:
        if not allow_test_skip and _is_test_file(path):
            errors.extend(
                check_test_skips_in_source(path, disk_source, added_lines=added_line_numbers)
            )
        errors.extend(
            check_suppressions_in_source(path, disk_source, added_lines=added_line_numbers)
        )
        errors.extend(
            check_silent_catches_in_source(path, disk_source, added_lines=added_line_numbers)
        )
        errors.extend(
            check_debug_leftovers_in_source(path, disk_source, added_lines=added_line_numbers)
        )
        errors.extend(
            check_host_paths(disk_source, source=path, added_lines=added_line_numbers)
        )
        return

    # Hunk-only fallback when disk file is unavailable: run the same source
    # checkers on each hunk's non-deleted lines and remap line numbers.
    for hunk in file_entry["hunks"]:
        visible: List[Tuple[str, int, str]] = [
            (kind, lineno, text)
            for kind, lineno, text in hunk["lines"]
            if kind != "-"
        ]
        if not visible:
            continue

        added_1based = {i + 1 for i, (kind, _, _) in enumerate(visible) if kind == "+"}
        if not added_1based:
            continue

        hunk_text = "\n".join(text for _, _, text in visible)
        line_map = {i + 1: lineno for i, (_, lineno, _) in enumerate(visible)}

        raw_findings: List[Dict[str, Any]] = []
        if not allow_test_skip and _is_test_file(path):
            raw_findings.extend(
                check_test_skips_in_source(path, hunk_text, added_lines=added_1based)
            )
        raw_findings.extend(
            check_suppressions_in_source(path, hunk_text, added_lines=added_1based)
        )
        raw_findings.extend(
            check_silent_catches_in_source(path, hunk_text, added_lines=added_1based)
        )
        raw_findings.extend(
            check_debug_leftovers_in_source(path, hunk_text, added_lines=added_1based)
        )
        raw_findings.extend(
            check_host_paths(hunk_text, source=path, added_lines=added_1based)
        )
        errors.extend(_remap_finding_lines(raw_findings, path, line_map))


def _check_code_stubs_in_file(rel_path: str, text: str, errors: List[Dict[str, Any]]) -> None:
    if not _is_code_path(rel_path):
        return
    is_python = Path(rel_path).suffix.lower() == ".py"
    is_c_like = _is_js_ts_path(rel_path) or _is_go_path(rel_path)
    ast_info = _python_ast_stub_lines(text) if is_python else None
    py_todo_lines = _python_comment_todo_lines(text) if is_python else None
    lines = text.splitlines()
    c_like_code_lines: Optional[List[str]] = None
    c_like_todo_lines: Optional[Set[int]] = None
    if is_c_like:
        c_like_code_lines, c_comments = _scan_c_like_lines(lines)
        c_like_todo_lines = {
            ln for ln, body in c_comments if C_COMMENT_TODO_RE.search(body)
        }

    for lineno, line in enumerate(lines, start=1):
        if py_todo_lines is not None:
            has_todo = lineno in py_todo_lines
        elif c_like_todo_lines is not None:
            has_todo = lineno in c_like_todo_lines
        else:
            has_todo = bool(TODO_FIXME_RE.search(line))
        if has_todo:
            errors.append(
                _finding(
                    code="DIFF-STUB-TODO",
                    severity="error",
                    file=rel_path,
                    line=lineno,
                    message=f"{rel_path}:{lineno} contains a TODO/FIXME placeholder stub.",
                    remediation="Complete the implementation or track follow-up work outside code stubs.",
                )
            )
        if is_python and ast_info is not None:
            stub_pass, stub_not_impl, _ = ast_info
            if lineno in stub_not_impl:
                errors.append(
                    _finding(
                        code="DIFF-STUB-NOT-IMPLEMENTED",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} contains NotImplementedError in a non-abstract body.",
                        remediation="Implement the function body or mark an interface method with @abstractmethod.",
                    )
                )
            elif lineno in stub_pass:
                errors.append(
                    _finding(
                        code="DIFF-STUB-PASS",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} contains a bare 'pass' stub in a non-abstract body.",
                        remediation="Implement the body or mark an interface method with @abstractmethod / Protocol.",
                    )
                )
        else:
            code_line = (
                c_like_code_lines[lineno - 1]
                if c_like_code_lines is not None and 1 <= lineno <= len(c_like_code_lines)
                else line
            )
            if NOT_IMPL_RE.search(code_line):
                errors.append(
                    _finding(
                        code="DIFF-STUB-NOT-IMPLEMENTED",
                        severity="error",
                        file=rel_path,
                        line=lineno,
                        message=f"{rel_path}:{lineno} contains NotImplementedError placeholder.",
                        remediation="Implement the missing logic instead of shipping a placeholder.",
                    )
                )


def _iter_non_fenced_lines(text: str) -> Iterable[Tuple[int, str]]:
    """Yield (1-based lineno, line) outside YAML frontmatter and fenced code blocks."""
    lines = text.splitlines()
    start_idx = 0

    # Skip optional YAML frontmatter at top of file.
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() in ("---", "..."):
                start_idx = idx + 1
                break

    in_fence = False
    fence_char = ""
    fence_len = 0

    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        lineno = idx + 1
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)
            rest = line[m.end():].strip()
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len and rest == "":
                in_fence = False
            continue
        if in_fence:
            continue
        yield lineno, line


def check_markdown_openers(text: str, *, source: str = "<markdown>") -> List[Dict[str, Any]]:
    """Flag objective chatbot/praise openers at the start of Markdown docs or PR bodies.

    Ignores YAML frontmatter and fenced code blocks (``` or ~~~). Checks the first
    non-empty prose line (and the first body prose line after a leading title heading).
    """
    errors: List[Dict[str, Any]] = []
    in_html_comment = False
    seen_heading = False

    for lineno, line in _iter_non_fenced_lines(text):
        stripped = line.strip()
        if not stripped:
            continue
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_html_comment = True
            continue
        if stripped.startswith("#"):
            # Skip leading document title heading(s), then check opening prose line.
            if not seen_heading:
                seen_heading = True
                continue
            break

        match = CHATBOT_OPENER_RE.match(stripped)
        if match:
            errors.append(
                _finding(
                    code="DIFF-CHATBOT-OPENER",
                    severity="error",
                    file=source,
                    line=lineno,
                    message=(
                        f"{source}:{lineno} starts with chatbot/praise opener "
                        f"'{match.group(0).strip()}'."
                    ),
                    remediation="Remove the conversational opener and start directly with the content or decision.",
                )
            )
        break

    return errors


def _has_all_caps_placeholder(candidate: str) -> bool:
    """Return True if any path segment looks like an ALL-CAPS template placeholder."""
    for seg in candidate.split("/"):
        if seg and ALL_CAPS_PLACEHOLDER_RE.match(seg) and seg not in REAL_UPPERCASE_SEGMENTS:
            return True
    return False


def _load_gitignored_paths(root: Path) -> Tuple[Set[str], Set[str]]:
    """Load literal ignored paths and ignored directory prefixes from <root>/.gitignore."""
    ignored_literals: Set[str] = set()
    ignored_dirs: Set[str] = set()
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return ignored_literals, ignored_dirs

    for raw_line in gitignore.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if any(ch in line for ch in ("*", "?", "[")):
            continue
        is_dir = line.endswith("/")
        norm = line.lstrip("/").rstrip("/")
        if not norm:
            continue
        ignored_literals.add(norm)
        if is_dir:
            ignored_dirs.add(norm)
    return ignored_literals, ignored_dirs


def _is_candidate_repo_path(token: str, top_level_dirs: Set[str]) -> Optional[str]:
    """Return normalized path candidate if token looks like a local repo path, else None."""
    cleaned = token.strip()
    if not cleaned:
        return None
    # Reject URLs, flags, anchors, npm scopes, absolute paths, and prose/code constructs.
    if "://" in cleaned or cleaned.startswith(("mailto:", "-", "@", "/", "#")):
        return None
    cleaned = LINE_ANCHOR_SUFFIX_RE.sub("", cleaned)
    if not cleaned:
        return None
    if BAD_PATH_CHARS_RE.search(cleaned):
        return None
    if ":" in cleaned:
        return None
    if "/" not in cleaned:
        return None

    # Trailing slash indicates an explicit directory reference (e.g., `gates/`, `tests/`).
    if cleaned.endswith("/"):
        stripped = cleaned.rstrip("/")
        if not stripped or len(stripped) < 2:
            return None
        if _has_all_caps_placeholder(stripped):
            return None
        return stripped

    if _has_all_caps_placeholder(cleaned):
        return None

    first_seg = cleaned.split("/", 1)[0]
    basename = cleaned.rsplit("/", 1)[-1]
    suffix = Path(basename).suffix.lower()

    if suffix in KNOWN_PATH_EXTENSIONS:
        return cleaned
    if basename in KNOWN_FILENAMES:
        return cleaned
    if first_seg in (".", "..") or first_seg in top_level_dirs:
        return cleaned
    return None


def check_markdown_paths(
    text: str,
    *,
    repo_root: Path | str,
    source: str = "<markdown>",
) -> List[Dict[str, Any]]:
    """Verify backticked local repository paths in Markdown outside fenced code blocks."""
    root = Path(repo_root).resolve()
    top_level_dirs: Set[str] = set()
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and not entry.name == ".git":
                top_level_dirs.add(entry.name)
    ignored_literals, ignored_dirs = _load_gitignored_paths(root)

    source_parent: Optional[Path] = None
    if source and not source.startswith("<"):
        candidate_source = root / source
        if candidate_source.parent.is_dir():
            source_parent = candidate_source.parent.resolve()

    errors: List[Dict[str, Any]] = []
    seen_missing: Set[Tuple[int, str]] = set()

    for lineno, line in _iter_non_fenced_lines(text):
        for match in INLINE_BACKTICK_RE.finditer(line):
            raw_token = match.group(2)
            candidate = _is_candidate_repo_path(raw_token, top_level_dirs)
            if candidate is None:
                continue

            norm_cand = candidate.rstrip("/")
            if norm_cand in ignored_literals or any(
                norm_cand == d or norm_cand.startswith(d + "/") for d in ignored_dirs
            ):
                continue

            exists = False
            try:
                from_root = (root / candidate).resolve()
                if (from_root == root or root in from_root.parents) and from_root.exists():
                    exists = True
            except OSError:
                exists = False

            if not exists and source_parent is not None:
                try:
                    from_source = (source_parent / candidate).resolve()
                    if (from_source == root or root in from_source.parents) and from_source.exists():
                        exists = True
                except OSError:
                    exists = False

            if not exists:
                key = (lineno, raw_token)
                if key not in seen_missing:
                    seen_missing.add(key)
                    errors.append(
                        _finding(
                            code="DIFF-BROKEN-DOC-PATH",
                            severity="error",
                            file=source,
                            line=lineno,
                            message=(
                                f"{source}:{lineno} references nonexistent local repo path "
                                f"`{raw_token}`."
                            ),
                            remediation="Fix the path, remove the stale reference, or move example paths into a fenced code block.",
                        )
                    )

    return errors


def _strip_inline_backticks(line: str) -> str:
    return INLINE_BACKTICK_RE.sub("", line)


def _iter_prose_lines_without_html_comments(text: str) -> Iterable[Tuple[int, str]]:
    """Yield (1-based lineno, line) outside YAML frontmatter, code fences, and HTML comments."""
    in_html_comment = False
    for lineno, line in _iter_non_fenced_lines(text):
        stripped = line.strip()
        if in_html_comment:
            if "-->" in stripped:
                in_html_comment = False
            continue
        if stripped.startswith("<!--"):
            if "-->" not in stripped:
                in_html_comment = True
            continue
        yield lineno, line


def check_markdown_closers(
    text: str,
    *,
    source: str = "<markdown>",
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Flag objective chatbot closing filler at the end of Markdown docs or PR bodies."""
    prose_lines: List[Tuple[int, str]] = [
        (lineno, line)
        for lineno, line in _iter_prose_lines_without_html_comments(text)
        if line.strip()
    ]
    if not prose_lines:
        return []

    errors: List[Dict[str, Any]] = []
    for lineno, line in prose_lines[-3:]:
        if added_lines is not None and lineno not in added_lines:
            continue
        cleaned = _strip_inline_backticks(line)
        match = CHATBOT_CLOSER_RE.search(cleaned)
        if match:
            errors.append(
                _finding(
                    code="DIFF-CHATBOT-CLOSER",
                    severity="error",
                    file=source,
                    line=lineno,
                    message=(
                        f"{source}:{lineno} ends with chatbot closing filler "
                        f"'{match.group(0).strip()}'."
                    ),
                    remediation="Remove conversational sign-off filler and end with the concrete decision, status, or verification step.",
                )
            )
    return errors


def check_decorative_emojis(
    text: str,
    *,
    source: str = "<markdown>",
    severity: str = "warning",
    added_lines: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Flag decorative AI emojis in Markdown headings or prose outside fenced code blocks."""
    findings: List[Dict[str, Any]] = []
    for lineno, line in _iter_prose_lines_without_html_comments(text):
        if added_lines is not None and lineno not in added_lines:
            continue
        cleaned = _strip_inline_backticks(line)
        found = list(dict.fromkeys(DECORATIVE_EMOJI_RE.findall(cleaned)))
        if found:
            joined = "".join(found)
            findings.append(
                _finding(
                    code="DIFF-DECORATIVE-EMOJI",
                    severity=severity,
                    file=source,
                    line=lineno,
                    message=f"{source}:{lineno} contains decorative AI emoji ({joined}).",
                    remediation="Remove decorative emojis from technical headings, docs, and PR descriptions.",
                )
            )
    return findings


def check_credibility_text(
    text: str,
    *,
    source: str = "<text>",
    repo_root: Optional[Path | str] = None,
    strict_prose: bool = False,
) -> Dict[str, Any]:
    """Run reusable engineering-credibility checks on Markdown docs, PR bodies, or review text."""
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    errors.extend(check_markdown_openers(text, source=source))
    errors.extend(check_markdown_closers(text, source=source))
    errors.extend(check_host_paths(text, source=source))
    if repo_root is not None:
        errors.extend(check_markdown_paths(text, repo_root=repo_root, source=source))

    emoji_severity = "error" if strict_prose else "warning"
    emoji_findings = check_decorative_emojis(text, source=source, severity=emoji_severity)
    if strict_prose:
        errors.extend(emoji_findings)
    else:
        warnings.extend(emoji_findings)

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def _reconstruct_markdown_from_diff(file_entry: Dict[str, Any]) -> Optional[str]:
    """Reconstruct checkable markdown text when disk file is unavailable."""
    if file_entry["is_deleted"]:
        return None
    if file_entry["is_new"]:
        return "\n".join(text for _, text in file_entry["added_lines"])
    # For modified existing files without disk access, only inspect hunks starting at line 1.
    if file_entry["hunks"] and file_entry["hunks"][0]["new_start"] == 1:
        lines = [text for kind, _, text in file_entry["hunks"][0]["lines"] if kind in (" ", "+")]
        return "\n".join(lines)
    return None


def _reconstruct_added_markdown_lines(file_entry: Dict[str, Any]) -> str:
    """Reconstruct non-deleted hunk lines so fence context stays intact."""
    chunks: List[str] = []
    for hunk in file_entry["hunks"]:
        chunks.extend(text for kind, _, text in hunk["lines"] if kind in (" ", "+"))
    return "\n".join(chunks)


def _remap_finding_lines(
    findings: List[Dict[str, Any]],
    source: str,
    line_map: Dict[int, int],
) -> List[Dict[str, Any]]:
    remapped: List[Dict[str, Any]] = []
    for item in findings:
        old_line = item.get("line")
        if isinstance(old_line, int) and old_line in line_map:
            new_line = line_map[old_line]
            updated = dict(item)
            updated["line"] = new_line
            prefix = f"{source}:{old_line}"
            if updated["message"].startswith(prefix):
                updated["message"] = f"{source}:{new_line}" + updated["message"][len(prefix):]
            remapped.append(updated)
        else:
            remapped.append(item)
    return remapped


def _check_markdown_hunks_without_disk(
    file_entry: Dict[str, Any],
    *,
    errors: List[Dict[str, Any]],
    warnings: List[Dict[str, Any]],
    strict_prose: bool,
) -> None:
    path = file_entry["path"]
    emoji_severity = "error" if strict_prose else "warning"
    emoji_target = errors if strict_prose else warnings

    if file_entry["is_new"]:
        full_text = "\n".join(text for _, text in file_entry["added_lines"])
        errors.extend(check_markdown_closers(full_text, source=path))
        errors.extend(check_host_paths(full_text, source=path))
        emoji_target.extend(check_decorative_emojis(full_text, source=path, severity=emoji_severity))
        return

    hunks = file_entry["hunks"]
    for hunk_idx, hunk in enumerate(hunks):
        visible = [(kind, lineno, text) for kind, lineno, text in hunk["lines"] if kind != "-"]
        if not visible:
            continue
        added_1based = {i + 1 for i, (kind, _, _) in enumerate(visible) if kind == "+"}
        if not added_1based:
            continue
        hunk_text = "\n".join(text for _, _, text in visible)
        line_map = {i + 1: lineno for i, (_, lineno, _) in enumerate(visible)}

        errors.extend(
            _remap_finding_lines(
                check_host_paths(hunk_text, source=path, added_lines=added_1based),
                path,
                line_map,
            )
        )
        emoji_target.extend(
            _remap_finding_lines(
                check_decorative_emojis(
                    hunk_text,
                    source=path,
                    severity=emoji_severity,
                    added_lines=added_1based,
                ),
                path,
                line_map,
            )
        )
        if hunk_idx == len(hunks) - 1:
            errors.extend(
                _remap_finding_lines(
                    check_markdown_closers(hunk_text, source=path, added_lines=added_1based),
                    path,
                    line_map,
                )
            )


def _ensure_repo_package_path() -> None:
    """Ensure sibling modules under `gates/` import cleanly whether invoked as script or package."""
    pkg_parent = str(Path(__file__).resolve().parents[1])
    if pkg_parent not in sys.path:
        sys.path.insert(0, pkg_parent)


def check_diff(
    diff_text: str,
    *,
    repo_root: Optional[Path | str] = None,
    allow_test_edit: bool = False,
    allow_test_skip: bool = False,
    no_budget: bool = False,
    max_net_loc: int = DEFAULT_MAX_NET_LOC,
    max_files: int = DEFAULT_MAX_FILES,
    pr_body: Optional[str] = None,
    pr_body_source: str = "<pr-body>",
    strict_prose: bool = False,
    structural: bool = False,
    strict_structural: bool = False,
    learned_rules: Optional[Path | str] = None,
    exclude: Optional[Sequence[str]] = None,
    protect_paths: Optional[Sequence[str]] = None,
    allow_protected_edit: bool = False,
) -> Dict[str, Any]:
    """Validate a unified diff against Layer-1 deterministic diff and prose gates."""
    if strict_structural:
        structural = True
    if no_budget:
        max_net_loc = 0
        max_files = 0
    exclude_patterns = _compile_exclude_patterns(exclude)
    if exclude_patterns:
        diff_text = _filter_unified_diff(diff_text, exclude_patterns)
    parsed = parse_unified_diff(diff_text)
    files = parsed["files"]
    stats = parsed["stats"]
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    root_path = Path(repo_root).resolve() if repo_root is not None else None
    protected_compiled = (
        []
        if allow_protected_edit
        else _compile_protected_patterns(load_protected_paths(root_path, protect_paths))
    )
    emoji_severity = "error" if strict_prose else "warning"
    emoji_target = errors if strict_prose else warnings

    # 1. File-count & net-LOC budgets.
    if max_files > 0 and stats["files_changed"] > max_files:
        errors.append(
            _finding(
                code="DIFF-MAX-FILES",
                severity="error",
                message=(
                    f"Modified file count ({stats['files_changed']}) exceeds budget "
                    f"of {max_files} [Heuristic]."
                ),
                remediation=f"Split the change into atomic PRs touching <= {max_files} files or raise --max-files.",
            )
        )

    if max_net_loc > 0 and stats["net_loc"] > max_net_loc:
        errors.append(
            _finding(
                code="DIFF-MAX-NET-LOC",
                severity="error",
                message=(
                    f"Net LOC (+{stats['net_loc']}; +{stats['added_lines']}/-{stats['deleted_lines']}) "
                    f"exceeds budget of {max_net_loc} [Heuristic]."
                ),
                remediation=f"Break the diff into smaller atomic changes (<= {max_net_loc} net LOC) or raise --max-net-loc.",
            )
        )

    # 2. Per-file checks.
    for file_entry in files:
        path = file_entry["path"]
        if not path:
            continue

        if not allow_test_edit and _is_test_path(path):
            errors.append(
                _finding(
                    code="DIFF-UNAUTHORIZED-TEST-EDIT",
                    severity="error",
                    file=path,
                    message=f"Unauthorized edit under tests/: '{path}'.",
                    remediation="Do not modify test files to match broken code; pass --allow-test-edit if authorized.",
                )
            )

        if protected_compiled:
            matched_glob = match_protected_path(path, protected_compiled)
            if matched_glob is None and file_entry.get("old_path"):
                matched_glob = match_protected_path(str(file_entry["old_path"]), protected_compiled)
            if matched_glob is not None:
                errors.append(
                    _finding(
                        code="DIFF-PROTECTED-PATH",
                        severity="error",
                        file=path,
                        message=f"Unauthorized edit to protected path '{path}' (matched '{matched_glob}').",
                        remediation=(
                            "Do not modify protected specs, decision docs, or human-owned invariant contracts "
                            "without explicit human authorization; pass --allow-protected-edit if authorized."
                        ),
                    )
                )

        _check_code_stubs_in_hunks(file_entry, root_path, errors)
        _check_code_credibility_in_hunks(
            file_entry,
            root_path,
            errors,
            allow_test_skip=allow_test_skip,
        )

        if _is_markdown_path(path) and not file_entry["is_deleted"]:
            disk_text: Optional[str] = None
            if root_path is not None and (root_path / path).is_file():
                disk_text = (root_path / path).read_text(encoding="utf-8")

            added_md_lines: Optional[Set[int]] = (
                None if file_entry["is_new"] else {ln for ln, _ in file_entry["added_lines"]}
            )

            if disk_text is not None:
                errors.extend(check_markdown_openers(disk_text, source=path))
                errors.extend(
                    check_markdown_closers(disk_text, source=path, added_lines=added_md_lines)
                )
                errors.extend(check_markdown_paths(disk_text, repo_root=root_path, source=path))
                errors.extend(check_host_paths(disk_text, source=path, added_lines=added_md_lines))
                emoji_target.extend(
                    check_decorative_emojis(
                        disk_text,
                        source=path,
                        severity=emoji_severity,
                        added_lines=added_md_lines,
                    )
                )
            else:
                reconstructed = _reconstruct_markdown_from_diff(file_entry)
                if reconstructed is not None:
                    errors.extend(check_markdown_openers(reconstructed, source=path))
                if root_path is not None:
                    added_md = _reconstruct_added_markdown_lines(file_entry)
                    if added_md:
                        errors.extend(check_markdown_paths(added_md, repo_root=root_path, source=path))
                _check_markdown_hunks_without_disk(
                    file_entry,
                    errors=errors,
                    warnings=warnings,
                    strict_prose=strict_prose,
                )

    # 3. Optional PR body checks.
    if pr_body is not None:
        pr_res = check_credibility_text(
            pr_body,
            source=pr_body_source,
            repo_root=root_path,
            strict_prose=strict_prose,
        )
        errors.extend(pr_res["errors"])
        warnings.extend(pr_res["warnings"])

    # 4. Optional AI-era structural compounding-slop checks.
    if structural:
        _ensure_repo_package_path()
        from gates import structural as _structural

        s_res = _structural.check_structural_diff(
            diff_text,
            repo_root=root_path,
            strict_structural=strict_structural,
        )
        errors.extend(s_res["errors"])
        warnings.extend(s_res["warnings"])

    # 5. Optional approved learned rules enforcement.
    if learned_rules is not None:
        _ensure_repo_package_path()
        from gates import learn as _learn

        l_res = _learn.check_learned_rules_in_diff(
            diff_text,
            learned_rules,
            repo_root=root_path,
            require_exists=True,
        )
        errors.extend(l_res["errors"])
        warnings.extend(l_res["warnings"])

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def check_diff_and_text(
    diff_text: str,
    *,
    text: Optional[str] = None,
    text_source: str = "<pr-body>",
    repo_root: Optional[Path | str] = None,
    allow_test_edit: bool = False,
    allow_test_skip: bool = False,
    no_budget: bool = False,
    max_net_loc: int = DEFAULT_MAX_NET_LOC,
    max_files: int = DEFAULT_MAX_FILES,
    strict_prose: bool = False,
    exclude: Optional[Sequence[str]] = None,
    protect_paths: Optional[Sequence[str]] = None,
    allow_protected_edit: bool = False,
) -> Dict[str, Any]:
    """Validate a unified diff together with an accompanying PR/review Markdown text."""
    return check_diff(
        diff_text,
        repo_root=repo_root,
        allow_test_edit=allow_test_edit,
        allow_test_skip=allow_test_skip,
        no_budget=no_budget,
        max_net_loc=max_net_loc,
        max_files=max_files,
        pr_body=text,
        pr_body_source=text_source,
        strict_prose=strict_prose,
        exclude=exclude,
        protect_paths=protect_paths,
        allow_protected_edit=allow_protected_edit,
    )


def check_files(
    files: Sequence[str | Path],
    *,
    repo_root: Optional[Path | str] = None,
    allow_test_edit: bool = False,
    allow_test_skip: bool = False,
    no_budget: bool = False,
    max_files: int = DEFAULT_MAX_FILES,
    pr_body: Optional[str] = None,
    strict_prose: bool = False,
    structural: bool = False,
    strict_structural: bool = False,
    learned_rules: Optional[Path | str] = None,
    exclude: Optional[Sequence[str]] = None,
    protect_paths: Optional[Sequence[str]] = None,
    allow_protected_edit: bool = False,
) -> Dict[str, Any]:
    """Validate an explicit list of modified files against Layer-1 diff and prose gates."""
    if strict_structural:
        structural = True
    if no_budget:
        max_files = 0
    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    protected_compiled = (
        []
        if allow_protected_edit
        else _compile_protected_patterns(load_protected_paths(root, protect_paths))
    )
    emoji_severity = "error" if strict_prose else "warning"
    emoji_target = errors if strict_prose else warnings

    norm_files: List[str] = []
    for raw in files:
        p = Path(raw)
        if p.is_absolute():
            try:
                rel = str(p.resolve().relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = str(p).replace("\\", "/")
        else:
            rel = _normalize_relpath(str(raw))
        norm_files.append(rel)

    exclude_patterns = _compile_exclude_patterns(exclude)
    if exclude_patterns:
        norm_files = [rel for rel in norm_files if not _is_excluded_path(rel, exclude_patterns)]

    stats = {
        "files_changed": len(norm_files),
        "added_lines": 0,
        "deleted_lines": 0,
        "net_loc": 0,
    }

    if max_files > 0 and len(norm_files) > max_files:
        errors.append(
            _finding(
                code="DIFF-MAX-FILES",
                severity="error",
                message=(
                    f"Modified file count ({len(norm_files)}) exceeds budget "
                    f"of {max_files} [Heuristic]."
                ),
                remediation=f"Split changes to <= {max_files} files or raise --max-files.",
            )
        )

    for rel in norm_files:
        if not allow_test_edit and _is_test_path(rel):
            errors.append(
                _finding(
                    code="DIFF-UNAUTHORIZED-TEST-EDIT",
                    severity="error",
                    file=rel,
                    message=f"Unauthorized edit under tests/: '{rel}'.",
                    remediation="Do not modify test files without authorization; pass --allow-test-edit if authorized.",
                )
            )

        if protected_compiled:
            matched_glob = match_protected_path(rel, protected_compiled)
            if matched_glob is not None:
                errors.append(
                    _finding(
                        code="DIFF-PROTECTED-PATH",
                        severity="error",
                        file=rel,
                        message=f"Unauthorized edit to protected path '{rel}' (matched '{matched_glob}').",
                        remediation=(
                            "Do not modify protected specs, decision docs, or human-owned invariant contracts "
                            "without explicit human authorization; pass --allow-protected-edit if authorized."
                        ),
                    )
                )

        disk_path = Path(rel) if Path(rel).is_absolute() else (root / rel)
        if not disk_path.is_file():
            continue

        text = disk_path.read_text(encoding="utf-8")
        if _is_code_path(rel):
            _check_code_stubs_in_file(rel, text, errors)
            if not allow_test_skip and _is_test_file(rel):
                errors.extend(check_test_skips_in_source(rel, text))
            errors.extend(check_suppressions_in_source(rel, text))
            errors.extend(check_silent_catches_in_source(rel, text))
            errors.extend(check_debug_leftovers_in_source(rel, text))
            errors.extend(check_host_paths(text, source=rel))
        elif _is_markdown_path(rel):
            errors.extend(check_markdown_openers(text, source=rel))
            errors.extend(check_markdown_closers(text, source=rel))
            errors.extend(check_markdown_paths(text, repo_root=root, source=rel))
            errors.extend(check_host_paths(text, source=rel))
            emoji_target.extend(
                check_decorative_emojis(text, source=rel, severity=emoji_severity)
            )

    if pr_body is not None:
        pr_res = check_credibility_text(
            pr_body,
            source="<pr-body>",
            repo_root=root,
            strict_prose=strict_prose,
        )
        errors.extend(pr_res["errors"])
        warnings.extend(pr_res["warnings"])

    if structural:
        _ensure_repo_package_path()
        from gates import structural as _structural

        s_res = _structural.check_structural_files(
            norm_files,
            repo_root=root,
            strict_structural=strict_structural,
        )
        errors.extend(s_res["errors"])
        warnings.extend(s_res["warnings"])

    if learned_rules is not None:
        _ensure_repo_package_path()
        from gates import learn as _learn

        l_res = _learn.check_learned_rules_in_files(
            norm_files,
            learned_rules,
            repo_root=root,
            require_exists=True,
        )
        errors.extend(l_res["errors"])
        warnings.extend(l_res["warnings"])

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


def _format_human(result: Dict[str, Any], *, explain: bool = False) -> str:
    explain_fn = None
    if explain:
        _ensure_repo_package_path()
        from gates import review as _review

        explain_fn = _review.explain_finding

    lines: List[str] = []
    for label, bucket in (("ERROR", result["errors"]), ("WARNING", result["warnings"])):
        for item in bucket:
            loc = ""
            if "file" in item:
                loc = f"{item['file']}:{item['line']}: " if "line" in item else f"{item['file']}: "
            lines.append(f"{loc}[{label}] {item['code']}: {item['message']}")
            lines.append(f"  remediation: {item['remediation']}")
            if explain_fn is not None:
                exp = explain_fn(item)
                lines.append(f"  why it matters: {exp['why_veterans_flag_it']}")
                lines.append(f"  how it compounds: {exp['how_it_compounds']}")
                if exp.get("evidence"):
                    lines.append(f"  evidence: {exp['evidence']}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic Layer-1 diff and Markdown prose checks."
    )
    parser.add_argument(
        "--diff",
        help="Path to a unified diff file, or '-' to read unified diff from stdin.",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        help="List of modified files to inspect directly (relative to --repo-root).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used to resolve local file paths (default: '.').",
    )
    parser.add_argument(
        "--allow-test-edit",
        action="store_true",
        help="Authorize edits under tests/.",
    )
    parser.add_argument(
        "--allow-test-skip",
        action="store_true",
        help="Authorize newly added test-skip/waiver annotations in test files.",
    )
    parser.add_argument(
        "--strict-prose",
        action="store_true",
        help="Promote prose warnings (e.g., DIFF-DECORATIVE-EMOJI) to hard errors.",
    )
    parser.add_argument(
        "--structural",
        action="store_true",
        help=(
            "Enable AI-era structural and architectural compounding-slop checks "
            "(test theater, silent fallbacks, duplicate blocks, dead compat paths, "
            "commented-out code, god growth, scope sprawl, circular imports, "
            "single-impl wrappers, env-var boundary scatter) as warnings."
        ),
    )
    parser.add_argument(
        "--strict-structural",
        action="store_true",
        help="Enable structural and architectural compounding-slop checks and promote them to hard errors.",
    )
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include plain-English explanations of why engineers flag each pattern and how it compounds.",
    )
    parser.add_argument(
        "--learned-rules",
        default=None,
        help="Path to an approved anti-slop-learn rules JSON store to enforce alongside built-in checks.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="Repeatable '**'-aware glob pattern for paths to skip (e.g., 'results/*/artifacts/**').",
    )
    parser.add_argument(
        "--protect-path",
        action="append",
        default=[],
        dest="protect_paths",
        metavar="GLOB",
        help=(
            "Repeatable '**'-aware glob pattern for protected specs, decision docs, or invariant tests "
            "(merged with <repo>/.anti-slop/protected-paths.json if present)."
        ),
    )
    parser.add_argument(
        "--allow-protected-edit",
        action="store_true",
        help="Authorize edits to paths locked by --protect-path or .anti-slop/protected-paths.json.",
    )
    parser.add_argument(
        "--no-budget",
        action="store_true",
        help="Disable heuristic --max-net-loc and --max-files diff budgets (enforce objective defects only).",
    )
    parser.add_argument(
        "--max-net-loc",
        type=int,
        default=DEFAULT_MAX_NET_LOC,
        help=f"Maximum net LOC additions allowed (default: {DEFAULT_MAX_NET_LOC} [Heuristic]; <=0 disables).",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=DEFAULT_MAX_FILES,
        help=f"Maximum modified file count allowed (default: {DEFAULT_MAX_FILES} [Heuristic]; <=0 disables).",
    )
    parser.add_argument(
        "--pr-body",
        default=None,
        help="PR description text to check for chatbot openers/closers, host paths, decorative emojis, and broken repo paths.",
    )
    parser.add_argument(
        "--pr-body-file",
        default=None,
        help="Path to a file containing PR description Markdown.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit structured JSON output to stdout.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="PATH",
        help="Optional positional file paths to inspect directly (equivalent to --files; convenient for pre-commit).",
    )
    args = parser.parse_args(argv)

    pr_body: Optional[str] = args.pr_body
    if args.pr_body_file is not None:
        pr_body = Path(args.pr_body_file).read_text(encoding="utf-8")

    effective_max_net_loc = 0 if args.no_budget else args.max_net_loc
    effective_max_files = 0 if args.no_budget else args.max_files
    target_files: List[str] = list(args.files or []) + list(args.paths or [])

    try:
        if args.diff is not None:
            if args.diff == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = Path(args.diff).read_text(encoding="utf-8")
            result = check_diff(
                diff_text,
                repo_root=args.repo_root,
                allow_test_edit=args.allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                no_budget=args.no_budget,
                max_net_loc=effective_max_net_loc,
                max_files=effective_max_files,
                pr_body=pr_body,
                strict_prose=args.strict_prose,
                structural=args.structural,
                strict_structural=args.strict_structural,
                learned_rules=args.learned_rules,
                exclude=args.exclude,
                protect_paths=args.protect_paths,
                allow_protected_edit=args.allow_protected_edit,
            )
        elif target_files:
            result = check_files(
                target_files,
                repo_root=args.repo_root,
                allow_test_edit=args.allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                no_budget=args.no_budget,
                max_files=effective_max_files,
                pr_body=pr_body,
                strict_prose=args.strict_prose,
                structural=args.structural,
                strict_structural=args.strict_structural,
                learned_rules=args.learned_rules,
                exclude=args.exclude,
                protect_paths=args.protect_paths,
                allow_protected_edit=args.allow_protected_edit,
            )
        elif pr_body is not None:
            result = check_files(
                [],
                repo_root=args.repo_root,
                allow_test_edit=args.allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                no_budget=args.no_budget,
                max_files=effective_max_files,
                pr_body=pr_body,
                strict_prose=args.strict_prose,
                structural=args.structural,
                strict_structural=args.strict_structural,
                learned_rules=args.learned_rules,
                exclude=args.exclude,
                protect_paths=args.protect_paths,
                allow_protected_edit=args.allow_protected_edit,
            )
        elif not sys.stdin.isatty():
            diff_text = sys.stdin.read()
            result = check_diff(
                diff_text,
                repo_root=args.repo_root,
                allow_test_edit=args.allow_test_edit,
                allow_test_skip=args.allow_test_skip,
                no_budget=args.no_budget,
                max_net_loc=effective_max_net_loc,
                max_files=effective_max_files,
                pr_body=pr_body,
                strict_prose=args.strict_prose,
                structural=args.structural,
                strict_structural=args.strict_structural,
                learned_rules=args.learned_rules,
                exclude=args.exclude,
                protect_paths=args.protect_paths,
                allow_protected_edit=args.allow_protected_edit,
            )
        else:
            parser.error("Provide --diff, --files / PATH, --pr-body/--pr-body-file, or pipe a unified diff on stdin.")
            return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.emit_json:
        print(json.dumps(result, indent=2))
    elif result["errors"] or result["warnings"]:
        print(_format_human(result, explain=args.explain), file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
