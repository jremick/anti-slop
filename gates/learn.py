#!/usr/bin/env python3
"""Verified self-learning loop (R7) for catching and preventing recurring AI slop.

Implements a lightweight, human-gated lifecycle:
  catch -> capture -> propose -> verify -> approve -> enforce -> retire

Key guarantees:
  - Stable IDs (L-001, L-002, ...): retiring a rule leaves a permanent gap and
    preserves its captured bad/valid regression examples; IDs are never reused.
  - Narrowest-layer escalation ladder: prefers deterministic checks first,
    canonical codebase examples second, and short scoped prompt rules last.
  - Mandatory 3-way automated verification before approval:
      1) Must catch the captured bad example.
      2) Must NOT falsely flag the valid neighbouring case.
      3) Must pass an existing-repository false-positive scan.
  - Explicit human approval gate bound by a SHA-256 content hash of the
    verified proposal; unapproved or post-verification-tampered rules are never
    enforced.

Zero third-party dependencies (Python 3.11+ stdlib only).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import importlib.resources
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import tokenize
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402
from gates import structural as _struct  # noqa: E402


SCHEMA_VERSION = 1
LIBRARY_SCHEMA_VERSION = 1
DEFAULT_STORE_REL = ".anti-slop/learned/rules.json"
DEFAULT_TELEMETRY_REL = ".anti-slop/telemetry.jsonl"
DEFAULT_MINE_COMMITS = 30
DEFAULT_STALE_DAYS = 60
VALID_LAYERS = ("deterministic_check", "codebase_example", "prompt_rule")
VALID_LIBRARY_LAYERS = ("deterministic_check", "prompt_rule")
VALID_EVIDENCE_STATUSES = (
    "External empirical study",
    "Local measured",
    "Practitioner hypothesis",
)
VALID_SEVERITIES = ("warning", "error")
VALID_MATCH_MODES = ("line", "multiline")
MAX_PROMPT_RULE_WORDS = 45

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
    ".anti-slop",
})

OVERBROAD_PATTERNS = frozenset({
    ".*",
    ".+",
    ".*?",
    ".+?",
    "^.*$",
    "^.+$",
    "\\s*",
    "\\w+",
    "[\\s\\S]*",
    "[\\s\\S]+",
})


class LearnError(ValueError):
    """Invalid input or lifecycle state transition in the learned-rule store."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _word_count(text: str) -> int:
    return len([w for w in text.split() if any(ch.isalnum() for ch in w)])


def _canonical_sha256(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_proposal_sha256(rule: Dict[str, Any]) -> str:
    """Hash the captured cases + proposal definition so edits invalidate old verification/approval."""
    captured = rule.get("captured") or {}
    proposal = rule.get("proposal") or {}
    material = {
        "bad_example": captured.get("bad_example", ""),
        "valid_neighbouring_case": captured.get("valid_neighbouring_case", ""),
        "layer": proposal.get("layer"),
        "severity": proposal.get("severity"),
        "file_glob": proposal.get("file_glob"),
        "pattern": proposal.get("pattern"),
        "match_mode": proposal.get("match_mode"),
        "canonical_path": proposal.get("canonical_path"),
        "rule_text": proposal.get("rule_text"),
        "why_not_deterministic": proposal.get("why_not_deterministic"),
        "remediation": proposal.get("remediation"),
        "retirement_trigger": proposal.get("retirement_trigger"),
    }
    return _canonical_sha256(material)


def default_store_path(repo_root: Path | str = ".") -> Path:
    return Path(repo_root).resolve() / DEFAULT_STORE_REL


def default_telemetry_path(repo_root: Path | str = ".") -> Path:
    return Path(repo_root).resolve() / DEFAULT_TELEMETRY_REL


def load_store(store_path: Path | str) -> Dict[str, Any]:
    path = Path(store_path)
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "next_id": 1,
            "rules": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LearnError(f"Failed to read learned-rule store {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise LearnError(f"Unsupported or corrupted learned-rule store schema in {path}.")
    next_id = data.get("next_id")
    if (
        not isinstance(data.get("rules"), list)
        or isinstance(next_id, bool)
        or not isinstance(next_id, int)
        or next_id < 1
    ):
        raise LearnError(f"Corrupted learned-rule store fields in {path}.")
    return data


def save_store(store_path: Path | str, data: Dict[str, Any]) -> Path:
    path = Path(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _find_rule(data: Dict[str, Any], rule_id: str) -> Dict[str, Any]:
    norm_id = rule_id.strip().upper()
    for item in data["rules"]:
        if str(item.get("id", "")).upper() == norm_id:
            return item
    raise LearnError(f"Rule ID '{rule_id}' not found in store.")


def _load_mutable_rule(
    store_path: Path | str,
    rule_id: str,
    *,
    retired_message: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    data = load_store(store_path)
    entry = _find_rule(data, rule_id)
    if entry["status"] == "retired":
        raise LearnError(retired_message.format(rule_id=entry["id"]))
    return data, entry


def capture_pattern(
    store_path: Path | str,
    *,
    title: str,
    bad_example: str,
    desired_outcome: str,
    valid_neighbouring_case: str,
    why_it_matters: str = "",
    file_glob: str = "*.py",
    source_context: str = "",
) -> Dict[str, Any]:
    """Capture a slipped slop pattern with its bad example and valid neighbouring case."""
    if not title.strip():
        raise LearnError("Title is required.")
    if not bad_example.strip():
        raise LearnError("bad_example must be non-empty.")
    if not desired_outcome.strip():
        raise LearnError("desired_outcome must be non-empty.")
    if not valid_neighbouring_case.strip():
        raise LearnError("valid_neighbouring_case must be non-empty.")
    if bad_example.strip() == valid_neighbouring_case.strip():
        raise LearnError("bad_example and valid_neighbouring_case must differ.")

    data = load_store(store_path)
    existing_ids = {str(r.get("id", "")).upper() for r in data["rules"]}
    seq = int(data["next_id"])
    while f"L-{seq:03d}" in existing_ids:
        seq += 1
    rule_id = f"L-{seq:03d}"
    data["next_id"] = seq + 1

    now = _utc_now()
    entry: Dict[str, Any] = {
        "id": rule_id,
        "title": title.strip(),
        "status": "captured",
        "created_at": now,
        "updated_at": now,
        "captured": {
            "bad_example": bad_example,
            "desired_outcome": desired_outcome.strip(),
            "valid_neighbouring_case": valid_neighbouring_case,
            "why_it_matters": why_it_matters.strip() or desired_outcome.strip(),
            "file_glob": file_glob.strip() or "*.py",
            "source_context": source_context.strip(),
        },
        "proposal": None,
        "verification": None,
        "approval": None,
        "retirement": None,
    }
    data["rules"].append(entry)
    save_store(store_path, data)
    return entry


def suggest_prevention(rule: Dict[str, Any]) -> Dict[str, Any]:
    """Suggest the smallest prevention layer by comparing bad vs valid examples."""
    captured = rule.get("captured") or {}
    bad = str(captured.get("bad_example") or "")
    valid = str(captured.get("valid_neighbouring_case") or "")

    bad_lines = [ln.strip() for ln in bad.splitlines() if ln.strip()]
    valid_lines_set = {ln.strip() for ln in valid.splitlines() if ln.strip()}
    distinct_bad_lines = [ln for ln in bad_lines if ln not in valid_lines_set]

    # Look for a concrete syntactic call or token present in bad but absent in valid.
    call_re = re.compile(r"[A-Za-z_][\w.]*\s*\([^()\n]{0,40}\)|[A-Za-z_][\w.]*\s*=\s*[^,\n]{1,30}")
    candidate_pattern: Optional[str] = None
    for ln in distinct_bad_lines:
        m = call_re.search(ln)
        if m:
            snippet = m.group(0).strip()
            if len(snippet) >= 5 and snippet not in valid:
                candidate_pattern = re.escape(snippet)
                break
    if candidate_pattern is None:
        for ln in distinct_bad_lines:
            if len(ln) >= 6 and ln not in valid:
                candidate_pattern = re.escape(ln)
                break

    if candidate_pattern is not None:
        return {
            "recommended_layer": "deterministic_check",
            "reason": (
                "A concrete syntactic pattern differentiates the bad example from the valid "
                "neighbouring case. Start with a deterministic check (zero standing prompt tokens)."
            ),
            "candidate_pattern": candidate_pattern,
            "file_glob": captured.get("file_glob", "*.py"),
            "next_step": (
                f"Review or tighten the regex, then run: anti-slop-learn propose {rule['id']} "
                f"--layer deterministic_check --pattern <REGEX> --remediation <FIX> "
                f"--retirement-trigger <WHEN_TO_RETIRE>"
            ),
        }

    return {
        "recommended_layer": "codebase_example",
        "reason": (
            "No single syntactic signature separates the bad and valid examples cleanly. "
            "Prefer a canonical codebase helper/example next, or a short scoped prompt rule last."
        ),
        "candidate_pattern": None,
        "file_glob": captured.get("file_glob", "*.py"),
        "next_step": (
            f"Run: anti-slop-learn propose {rule['id']} --layer codebase_example "
            f"--canonical-path <PATH> --remediation <FIX> --retirement-trigger <WHEN_TO_RETIRE>"
        ),
    }


def _validate_regex_pattern(pattern: str, match_mode: str) -> re.Pattern[str]:
    cleaned = pattern.strip()
    if not cleaned:
        raise LearnError("deterministic_check requires a non-empty --pattern.")
    if cleaned in OVERBROAD_PATTERNS or len(cleaned) < 3:
        raise LearnError(
            f"Pattern {pattern!r} is too short or catch-all; write a targeted pattern."
        )
    flags = re.MULTILINE | re.DOTALL if match_mode == "multiline" else 0
    try:
        compiled = re.compile(cleaned, flags)
    except re.error as exc:
        raise LearnError(f"Invalid regex pattern {pattern!r}: {exc}") from exc
    if compiled.search("") is not None:
        raise LearnError(
            f"Pattern {pattern!r} matches the empty string; tighten it to match concrete code."
        )
    return compiled


def propose_prevention(
    store_path: Path | str,
    rule_id: str,
    *,
    layer: str,
    remediation: str,
    retirement_trigger: str,
    severity: str = "warning",
    file_glob: Optional[str] = None,
    pattern: Optional[str] = None,
    match_mode: str = "line",
    canonical_path: Optional[str] = None,
    rule_text: Optional[str] = None,
    why_not_deterministic: Optional[str] = None,
) -> Dict[str, Any]:
    """Attach the smallest prevention proposal to a captured rule (resets prior verification/approval)."""
    if layer not in VALID_LAYERS:
        raise LearnError(f"layer must be one of {', '.join(VALID_LAYERS)}.")
    if severity not in VALID_SEVERITIES:
        raise LearnError(f"severity must be one of {', '.join(VALID_SEVERITIES)}.")
    if match_mode not in VALID_MATCH_MODES:
        raise LearnError(f"match_mode must be one of {', '.join(VALID_MATCH_MODES)}.")
    if not remediation.strip():
        raise LearnError("remediation is required.")
    if not retirement_trigger.strip():
        raise LearnError("retirement_trigger is required (define when to retire this rule).")

    data, entry = _load_mutable_rule(
        store_path,
        rule_id,
        retired_message="Rule {rule_id} is retired and permanently locked. Capture a new rule instead.",
    )

    eff_glob = (file_glob or entry["captured"].get("file_glob") or "*.py").strip()

    if layer == "deterministic_check":
        if pattern is None:
            raise LearnError("deterministic_check requires --pattern.")
        _validate_regex_pattern(pattern, match_mode)
    elif layer == "codebase_example":
        if not canonical_path or not canonical_path.strip():
            raise LearnError("codebase_example requires --canonical-path pointing to a repo file.")
    elif layer == "prompt_rule":
        if not rule_text or not rule_text.strip():
            raise LearnError("prompt_rule requires --rule-text.")
        if _word_count(rule_text) > MAX_PROMPT_RULE_WORDS:
            raise LearnError(
                f"prompt_rule text is {_word_count(rule_text)} words (max {MAX_PROMPT_RULE_WORDS}). "
                "Keep prompt rules tight or move the check to deterministic_check."
            )
        if not why_not_deterministic or not why_not_deterministic.strip():
            raise LearnError(
                "prompt_rule is the last resort and requires --why-not-deterministic explaining "
                "why a deterministic check or codebase example cannot prevent this pattern."
            )

    entry["proposal"] = {
        "layer": layer,
        "severity": severity,
        "file_glob": eff_glob,
        "pattern": pattern.strip() if pattern is not None else None,
        "match_mode": match_mode,
        "canonical_path": canonical_path.strip() if canonical_path is not None else None,
        "rule_text": rule_text.strip() if rule_text is not None else None,
        "why_not_deterministic": (
            why_not_deterministic.strip() if why_not_deterministic is not None else None
        ),
        "remediation": remediation.strip(),
        "retirement_trigger": retirement_trigger.strip(),
    }
    entry["proposal"]["proposal_sha256"] = compute_proposal_sha256(entry)
    entry["status"] = "proposed"
    entry["verification"] = None
    entry["approval"] = None
    entry["updated_at"] = _utc_now()

    save_store(store_path, data)
    return entry


def _glob_to_regex(pat: str) -> re.Pattern[str]:
    """Convert a POSIX path glob (including `**/` zero-or-more dirs) to a regex."""
    norm_pat = _dc._normalize_relpath(pat)
    out: List[str] = ["^"]
    i = 0
    n = len(norm_pat)
    while i < n:
        if norm_pat[i : i + 3] == "**/":
            out.append("(?:.*/)?")
            i += 3
            continue
        if norm_pat[i : i + 3] == "/**":
            if i + 3 == n:
                out.append("(?:/.*)?")
                i += 3
                continue
        if norm_pat[i : i + 2] == "**":
            out.append(".*")
            i += 2
            continue
        ch = norm_pat[i]
        if ch == "*":
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        elif ch == "[":
            j = i + 1
            if j < n and norm_pat[j] in ("!", "^"):
                j += 1
            if j < n and norm_pat[j] == "]":
                j += 1
            while j < n and norm_pat[j] != "]":
                j += 1
            if j >= n:
                out.append(re.escape(ch))
            else:
                inner = norm_pat[i + 1 : j]
                if inner.startswith("!"):
                    inner = "^" + inner[1:]
                out.append(f"[{inner}]")
                i = j
        else:
            out.append(re.escape(ch))
        i += 1
    out.append("$")
    return re.compile("".join(out))


def _matches_file_glob(rel_path: str, file_glob: str) -> bool:
    norm = _dc._normalize_relpath(rel_path)
    basename = Path(norm).name
    patterns = [p.strip() for p in file_glob.split(",") if p.strip()]
    for pat in patterns:
        if "/" in pat or "**" in pat:
            if _glob_to_regex(pat).match(norm):
                return True
        else:
            if fnmatch.fnmatch(basename, pat) or fnmatch.fnmatch(norm, pat):
                return True
    return False


def _strip_py_comments_preserve_lines(text: str) -> str:
    """Replace Python `# ...` comments with spaces while keeping strings and line numbers intact."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text
    comment_spans: List[Tuple[int, int, int]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comment_spans.append((tok.start[0], tok.start[1], tok.end[1]))
    except (tokenize.TokenError, IndentationError):
        return text
    if not comment_spans:
        return text
    for lineno, start_col, end_col in reversed(comment_spans):
        idx = lineno - 1
        if 0 <= idx < len(lines):
            ln = lines[idx]
            lines[idx] = ln[:start_col] + (" " * max(0, end_col - start_col)) + ln[end_col:]
    return "".join(lines)


def _strip_c_like_comments_preserve_lines(text: str) -> str:
    """Replace JS/TS/Go `//` and `/* ... */` comments with spaces while preserving strings and line numbers."""
    lines = text.splitlines(keepends=True)
    out_lines: List[str] = []
    in_block = False
    in_backtick = False

    for raw in lines:
        ending = ""
        if raw.endswith("\r\n"):
            body, ending = raw[:-2], "\r\n"
        elif raw.endswith("\n"):
            body, ending = raw[:-1], "\n"
        else:
            body = raw
        chars: List[str] = []
        in_single = False
        in_double = False
        i = 0
        n = len(body)
        while i < n:
            if in_block:
                if body[i : i + 2] == "*/":
                    chars.extend((" ", " "))
                    in_block = False
                    i += 2
                    continue
                chars.append(" ")
                i += 1
                continue
            if in_backtick:
                ch = body[i]
                chars.append(ch)
                if ch == "\\" and i + 1 < n:
                    chars.append(body[i + 1])
                    i += 2
                    continue
                if ch == "`":
                    in_backtick = False
                i += 1
                continue
            if in_single or in_double:
                q = "'" if in_single else '"'
                ch = body[i]
                chars.append(ch)
                if ch == "\\" and i + 1 < n:
                    chars.append(body[i + 1])
                    i += 2
                    continue
                if ch == q:
                    in_single = False
                    in_double = False
                i += 1
                continue
            if body[i : i + 2] == "//":
                chars.extend([" "] * (n - i))
                break
            if body[i : i + 2] == "/*":
                in_block = True
                chars.extend((" ", " "))
                i += 2
                continue
            ch = body[i]
            if ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "`":
                in_backtick = True
            chars.append(ch)
            i += 1
        out_lines.append("".join(chars) + ending)
    return "".join(out_lines)


def _strip_comments_for_path(text: str, rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower()
    if suffix == ".py":
        return _strip_py_comments_preserve_lines(text)
    if _dc._is_js_ts_path(rel_path) or _dc._is_go_path(rel_path):
        return _strip_c_like_comments_preserve_lines(text)
    return text


def _glob_targets_languages(file_glob: str) -> Tuple[bool, bool]:
    """Return (strip_python_comments, strip_c_like_comments) inferred from file_glob."""
    pats = [p.strip().lower() for p in (file_glob or "").split(",") if p.strip()]
    if not pats:
        return True, True
    py = False
    clike = False
    clike_exts = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go")
    for p in pats:
        if p.endswith(".py"):
            py = True
        elif any(p.endswith(ext) for ext in clike_exts):
            clike = True
        elif p.endswith((".md", ".markdown", ".txt", ".json", ".yml", ".yaml", ".toml")):
            continue
        else:
            py = True
            clike = True
    return py, clike


def _should_ignore_code_comments(
    bad_example: str,
    compiled: re.Pattern[str],
    match_mode: str,
    file_glob: str = "*.py",
) -> bool:
    """Ignore comments on code scans unless the captured bad example itself targets a comment."""
    strip_py, strip_clike = _glob_targets_languages(file_glob)
    cleaned = bad_example
    if strip_py:
        cleaned = _strip_py_comments_preserve_lines(cleaned)
    if strip_clike:
        cleaned = _strip_c_like_comments_preserve_lines(cleaned)
    return bool(_find_pattern_hits_in_text(cleaned, compiled, match_mode))


def _find_pattern_hits_in_text(
    text: str,
    compiled: re.Pattern[str],
    match_mode: str,
    *,
    added_lines: Optional[Set[int]] = None,
    rel_path: Optional[str] = None,
    ignore_comments: bool = False,
) -> List[Tuple[int, str]]:
    scan_text = _strip_comments_for_path(text, rel_path) if (ignore_comments and rel_path) else text
    hits: List[Tuple[int, str]] = []
    if match_mode == "line":
        for lineno, line in enumerate(scan_text.splitlines(), start=1):
            if added_lines is not None and lineno not in added_lines:
                continue
            m = compiled.search(line)
            if m:
                hits.append((lineno, m.group(0).strip()))
        return hits

    # Multiline mode: compute 1-based line number from match start offset.
    for m in compiled.finditer(scan_text):
        lineno = scan_text.count("\n", 0, m.start()) + 1
        end_lineno = scan_text.count("\n", 0, m.end()) + 1
        if added_lines is not None and not any(lineno <= ln <= end_lineno for ln in added_lines):
            continue
        snippet = m.group(0).splitlines()[0].strip() if m.group(0) else ""
        hits.append((lineno, snippet))
    return hits


def _iter_repo_matching_files(
    repo_root: Path,
    file_glob: str,
    *,
    include_tests: bool = False,
) -> Iterable[Tuple[str, Path]]:
    root = repo_root.resolve()
    if not root.is_dir():
        return
    glob_targets_tests = "test" in file_glob.lower()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel_parts = path.relative_to(root).parts
        except ValueError:
            continue
        if any(part in EXCLUDED_SCAN_DIRS for part in rel_parts):
            continue
        if len(rel_parts) >= 2 and rel_parts[:2] == ("benchmarks", "sources"):
            continue
        rel = "/".join(rel_parts)
        if not include_tests and not glob_targets_tests and _dc._is_test_file(rel):
            continue
        if _matches_file_glob(rel, file_glob):
            yield rel, path


def verify_rule(
    store_path: Path | str,
    rule_id: str,
    *,
    repo_root: Path | str = ".",
    max_repo_hits: int = 0,
    include_tests_in_scan: bool = False,
) -> Dict[str, Any]:
    """Automatically verify a proposed rule against bad case, valid neighbour, and repo scan."""
    if isinstance(max_repo_hits, bool) or max_repo_hits < 0:
        raise LearnError("max_repo_hits must be a non-negative integer.")
    data, entry = _load_mutable_rule(
        store_path,
        rule_id,
        retired_message="Rule {rule_id} is retired and cannot be verified.",
    )
    proposal = entry.get("proposal")
    if not isinstance(proposal, dict):
        raise LearnError(
            f"Rule {entry['id']} has no proposal yet. Run 'propose' before 'verify'."
        )

    captured = entry["captured"]
    root = Path(repo_root).resolve()
    layer = proposal["layer"]
    prop_hash = compute_proposal_sha256(entry)
    notes: List[str] = []

    if layer == "deterministic_check":
        compiled = _validate_regex_pattern(proposal["pattern"], proposal["match_mode"])
        ignore_comments = _should_ignore_code_comments(
            captured["bad_example"],
            compiled,
            proposal["match_mode"],
            file_glob=str(proposal.get("file_glob") or "*.py"),
        )
        bad_hits = _find_pattern_hits_in_text(
            captured["bad_example"], compiled, proposal["match_mode"]
        )
        valid_hits = _find_pattern_hits_in_text(
            captured["valid_neighbouring_case"], compiled, proposal["match_mode"]
        )

        repo_files = 0
        repo_hits = 0
        repo_samples: List[str] = []
        for rel, disk_path in _iter_repo_matching_files(
            root,
            proposal["file_glob"],
            include_tests=include_tests_in_scan,
        ):
            repo_files += 1
            try:
                content = disk_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            file_hits = _find_pattern_hits_in_text(
                content,
                compiled,
                proposal["match_mode"],
                rel_path=rel,
                ignore_comments=ignore_comments,
            )
            if file_hits:
                repo_hits += len(file_hits)
                for ln, snippet in file_hits:
                    if len(repo_samples) < 10:
                        repo_samples.append(f"{rel}:{ln}: {snippet[:80]}")

        bad_ok = len(bad_hits) > 0
        valid_ok = len(valid_hits) == 0
        repo_ok = repo_hits <= max_repo_hits
        if not bad_ok:
            notes.append("FAILED: pattern did not match the captured bad_example.")
        if not valid_ok:
            notes.append(
                f"FAILED: pattern falsely matched valid_neighbouring_case ({len(valid_hits)} hit(s))."
            )
        if not repo_ok:
            notes.append(
                f"FAILED: existing repo scan found {repo_hits} hit(s) across {repo_files} files "
                f"(allowed <= {max_repo_hits}). Tighten the pattern or clean existing matches first."
            )

        passed = bad_ok and valid_ok and repo_ok
        verification = {
            "verified_at": _utc_now(),
            "proposal_sha256": prop_hash,
            "mechanical": True,
            "passed": passed,
            "bad_case_caught": bad_ok,
            "bad_case_hits": len(bad_hits),
            "valid_neighbour_clean": valid_ok,
            "valid_neighbour_hits": len(valid_hits),
            "repo_scan_files": repo_files,
            "repo_scan_hits": repo_hits,
            "max_repo_hits": max_repo_hits,
            "repo_sample_hits": repo_samples,
            "notes": notes,
        }
    elif layer == "codebase_example":
        raw_ref = str(proposal.get("canonical_path") or "").strip()
        ref_path = (root / raw_ref).resolve()
        inside_root = ref_path == root or root in ref_path.parents
        exists = inside_root and ref_path.is_file()
        if not exists:
            notes.append(f"FAILED: canonical_path '{raw_ref}' does not exist inside {root}.")
        notes.append(
            "NOTE: codebase_example is structurally checked for path existence, not statically enforced on diffs."
        )
        verification = {
            "verified_at": _utc_now(),
            "proposal_sha256": prop_hash,
            "mechanical": False,
            "passed": exists,
            "bad_case_caught": None,
            "bad_case_hits": None,
            "valid_neighbour_clean": None,
            "valid_neighbour_hits": None,
            "repo_scan_files": 0,
            "repo_scan_hits": 0,
            "max_repo_hits": max_repo_hits,
            "repo_sample_hits": [],
            "notes": notes,
        }
    else:  # prompt_rule
        rule_text = str(proposal.get("rule_text") or "")
        wc = _word_count(rule_text)
        why = str(proposal.get("why_not_deterministic") or "").strip()
        trigger = str(proposal.get("retirement_trigger") or "").strip()
        passed = bool(rule_text.strip()) and wc <= MAX_PROMPT_RULE_WORDS and bool(why) and bool(trigger)
        if wc > MAX_PROMPT_RULE_WORDS:
            notes.append(f"FAILED: prompt_rule exceeds {MAX_PROMPT_RULE_WORDS} words ({wc}).")
        if not why:
            notes.append("FAILED: missing why_not_deterministic justification.")
        if not trigger:
            notes.append("FAILED: missing retirement_trigger.")
        notes.append(
            "NOTE: prompt_rule cannot be mechanically proven by static scan; prove value via paired multi-turn evaluation before keeping permanently."
        )
        verification = {
            "verified_at": _utc_now(),
            "proposal_sha256": prop_hash,
            "mechanical": False,
            "passed": passed,
            "bad_case_caught": None,
            "bad_case_hits": None,
            "valid_neighbour_clean": None,
            "valid_neighbour_hits": None,
            "repo_scan_files": 0,
            "repo_scan_hits": 0,
            "max_repo_hits": max_repo_hits,
            "repo_sample_hits": [],
            "notes": notes,
        }

    entry["proposal"]["proposal_sha256"] = prop_hash
    entry["verification"] = verification
    entry["status"] = "verified" if verification["passed"] else "verification_failed"
    entry["approval"] = None
    entry["updated_at"] = _utc_now()
    save_store(store_path, data)
    return entry


def approve_rule(
    store_path: Path | str,
    rule_id: str,
    *,
    approved_by: str,
    note: str = "",
) -> Dict[str, Any]:
    """Explicit human approval gate. Strictly requires a fresh passing verification."""
    if not approved_by.strip():
        raise LearnError("Human approval requires a non-empty --by reviewer identifier.")

    data, entry = _load_mutable_rule(
        store_path,
        rule_id,
        retired_message="Rule {rule_id} is retired and cannot be re-approved.",
    )
    if entry["status"] != "verified":
        raise LearnError(
            f"Rule {entry['id']} has status '{entry['status']}'. "
            "Only rules with status 'verified' can be approved; run 'verify' first."
        )
    verif = entry.get("verification") or {}
    current_hash = compute_proposal_sha256(entry)
    if not verif.get("passed") or verif.get("proposal_sha256") != current_hash:
        raise LearnError(
            f"Rule {entry['id']} changed after verification (hash mismatch). Re-run 'verify' before approving."
        )

    now = _utc_now()
    entry["approval"] = {
        "approved_by": approved_by.strip(),
        "approved_at": now,
        "note": note.strip(),
        "approved_proposal_sha256": current_hash,
    }
    entry["status"] = "approved"
    entry["updated_at"] = now
    save_store(store_path, data)
    return entry


def retire_rule(
    store_path: Path | str,
    rule_id: str,
    *,
    reason: str,
) -> Dict[str, Any]:
    """Retire a rule cleanly: stops enforcement, preserves regression cases, keeps ID unused."""
    if not reason.strip():
        raise LearnError("Retirement requires a non-empty --reason.")

    data, entry = _load_mutable_rule(
        store_path,
        rule_id,
        retired_message="Rule {rule_id} is already retired.",
    )

    now = _utc_now()
    entry["status"] = "retired"
    entry["retirement"] = {
        "retired_at": now,
        "reason": reason.strip(),
    }
    entry["updated_at"] = now
    save_store(store_path, data)
    return entry


def _is_valid_approved_entry(entry: Dict[str, Any]) -> bool:
    """Fail-closed check: entry must be approved, human-signed, freshly verified, and hash-intact."""
    if entry.get("status") != "approved":
        return False
    proposal = entry.get("proposal")
    verification = entry.get("verification")
    approval = entry.get("approval")
    if not isinstance(proposal, dict) or not isinstance(verification, dict) or not isinstance(approval, dict):
        return False
    if verification.get("passed") is not True:
        return False
    if not str(approval.get("approved_by") or "").strip():
        return False
    expected_hash = compute_proposal_sha256(entry)
    if verification.get("proposal_sha256") != expected_hash:
        return False
    if approval.get("approved_proposal_sha256") != expected_hash:
        return False
    return True


def load_active_deterministic_rules(
    store_path: Path | str,
    *,
    require_exists: bool = False,
) -> List[Dict[str, Any]]:
    """Return ONLY approved, verified, tamper-checked deterministic rules from store_path."""
    path = Path(store_path)
    if not path.is_file():
        if require_exists:
            raise LearnError(f"Learned-rules store not found: {path}")
        return []
    data = load_store(path)
    active: List[Dict[str, Any]] = []
    for entry in data["rules"]:
        if not _is_valid_approved_entry(entry):
            continue
        proposal = entry["proposal"]
        if proposal.get("layer") != "deterministic_check":
            continue
        match_mode = str(proposal.get("match_mode") or "line")
        try:
            compiled = _validate_regex_pattern(
                str(proposal.get("pattern") or ""),
                match_mode,
            )
        except LearnError:
            continue
        captured = entry.get("captured") or {}
        ignore_comments = _should_ignore_code_comments(
            str(captured.get("bad_example") or ""),
            compiled,
            match_mode,
            file_glob=str(proposal.get("file_glob") or "*.py"),
        )
        active.append({
            "entry": entry,
            "compiled": compiled,
            "ignore_comments": ignore_comments,
        })
    return active


def _learned_finding(
    entry: Dict[str, Any],
    *,
    rel_path: str,
    lineno: int,
    snippet: str,
) -> Dict[str, Any]:
    proposal = entry["proposal"]
    captured = entry["captured"]
    item = _dc._finding(
        code=f"LEARNED-{entry['id']}",
        severity=proposal["severity"],
        file=rel_path,
        line=lineno,
        message=(
            f"{rel_path}:{lineno} matched approved learned rule {entry['id']} "
            f"({entry['title']}): '{snippet[:60]}'."
        ),
        remediation=proposal["remediation"],
    )
    item["meta"] = {
        "learned_id": entry["id"],
        "title": entry["title"],
        "why_it_matters": captured.get("why_it_matters", ""),
        "desired_outcome": captured.get("desired_outcome", ""),
    }
    return item


def check_learned_rules_in_diff(
    diff_text: str,
    store_path: Path | str,
    *,
    repo_root: Optional[Path | str] = None,
    require_exists: bool = False,
) -> Dict[str, Any]:
    """Enforce all approved deterministic learned rules on added lines of a unified diff."""
    active = load_active_deterministic_rules(store_path, require_exists=require_exists)
    if not active:
        return {"ok": True, "errors": [], "warnings": []}

    parsed = _dc.parse_unified_diff(diff_text)
    root = Path(repo_root).resolve() if repo_root is not None else None
    findings: List[Dict[str, Any]] = []

    for fentry in parsed["files"]:
        path = fentry["path"]
        if not path or fentry["is_deleted"]:
            continue
        added_lines = {ln for ln, _ in fentry["added_lines"]}
        if not added_lines:
            continue

        disk_text: Optional[str] = None
        if root is not None and (root / path).is_file():
            try:
                disk_text = (root / path).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        elif fentry["is_new"]:
            disk_text = "\n".join(txt for _, txt in fentry["added_lines"])

        for item in active:
            rule = item["entry"]
            prop = rule["proposal"]
            if not _matches_file_glob(path, prop["file_glob"]):
                continue
            compiled = item["compiled"]
            mode = prop["match_mode"]
            ignore_comments = bool(item.get("ignore_comments", False))

            if disk_text is not None:
                hits = _find_pattern_hits_in_text(
                    disk_text,
                    compiled,
                    mode,
                    added_lines=added_lines,
                    rel_path=path,
                    ignore_comments=ignore_comments,
                )
                for ln, snippet in hits:
                    findings.append(
                        _learned_finding(rule, rel_path=path, lineno=ln, snippet=snippet)
                    )
            else:
                for hunk in fentry["hunks"]:
                    visible = [(k, ln, txt) for k, ln, txt in hunk["lines"] if k != "-"]
                    if not visible:
                        continue
                    added_1based = {i + 1 for i, (k, _, _) in enumerate(visible) if k == "+"}
                    if not added_1based:
                        continue
                    hunk_text = "\n".join(txt for _, _, txt in visible)
                    line_map = {i + 1: ln for i, (_, ln, _) in enumerate(visible)}
                    for ln1, snippet in _find_pattern_hits_in_text(
                        hunk_text,
                        compiled,
                        mode,
                        added_lines=added_1based,
                        rel_path=path,
                        ignore_comments=ignore_comments,
                    ):
                        real_ln = line_map.get(ln1, ln1)
                        findings.append(
                            _learned_finding(rule, rel_path=path, lineno=real_ln, snippet=snippet)
                        )

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] != "error"]
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def check_learned_rules_in_files(
    files: Sequence[str | Path],
    store_path: Path | str,
    *,
    repo_root: Optional[Path | str] = None,
    require_exists: bool = False,
) -> Dict[str, Any]:
    """Enforce all approved deterministic learned rules directly on a list of files."""
    active = load_active_deterministic_rules(store_path, require_exists=require_exists)
    if not active:
        return {"ok": True, "errors": [], "warnings": []}

    root = Path(repo_root).resolve() if repo_root is not None else Path.cwd().resolve()
    findings: List[Dict[str, Any]] = []

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
        try:
            content = disk_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for item in active:
            rule = item["entry"]
            prop = rule["proposal"]
            if not _matches_file_glob(rel, prop["file_glob"]):
                continue
            for ln, snippet in _find_pattern_hits_in_text(
                content,
                item["compiled"],
                prop["match_mode"],
                rel_path=rel,
                ignore_comments=bool(item.get("ignore_comments", False)),
            ):
                findings.append(
                    _learned_finding(rule, rel_path=rel, lineno=ln, snippet=snippet)
                )

    errors = [f for f in findings if f["severity"] == "error"]
    warnings = [f for f in findings if f["severity"] != "error"]
    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def export_approved_prompt_rules(store_path: Path | str) -> str:
    """Render approved prompt_rule and codebase_example entries cleanly (separate from core.md)."""
    data = load_store(store_path)
    lines: List[str] = []
    for entry in data["rules"]:
        if not _is_valid_approved_entry(entry):
            continue
        prop = entry["proposal"]
        layer = prop.get("layer")
        if layer == "prompt_rule":
            lines.append(f"- **{entry['id']} ({entry['title']}):** {prop['rule_text']}")
        elif layer == "codebase_example":
            lines.append(
                f"- **{entry['id']} ({entry['title']}):** Follow canonical example "
                f"`{prop['canonical_path']}` ({prop['remediation']})."
            )
    if not lines:
        return ""
    header = "# Approved project-local learned guidelines (kept separate from standard/core.md)\n\n"
    return header + "\n".join(lines) + "\n"


def _default_library_catalog_path() -> Optional[Path]:
    candidate = Path(__file__).resolve().parents[1] / "library" / "catalog.json"
    if candidate.is_file():
        return candidate
    return None


def load_library_catalog(catalog_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load the curated optional rule library catalog (repo checkout or packaged wheel)."""
    raw_text: Optional[str] = None
    source_label = "library/catalog.json"
    if catalog_path is not None:
        p = Path(catalog_path)
        source_label = str(p)
        try:
            raw_text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise LearnError(f"Failed to read library catalog {p}: {exc}") from exc
    else:
        local = _default_library_catalog_path()
        if local is not None:
            source_label = str(local)
            try:
                raw_text = local.read_text(encoding="utf-8")
            except OSError as exc:
                raise LearnError(f"Failed to read library catalog {local}: {exc}") from exc
        else:
            try:
                resource = importlib.resources.files("library").joinpath("catalog.json")
                raw_text = resource.read_text(encoding="utf-8")
            except (ModuleNotFoundError, FileNotFoundError, OSError, AttributeError) as exc:
                raise LearnError(f"Unable to locate packaged library/catalog.json: {exc}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise LearnError(f"Invalid JSON in library catalog {source_label}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != LIBRARY_SCHEMA_VERSION:
        raise LearnError(
            f"Unsupported library catalog schema_version in {source_label} "
            f"(expected {LIBRARY_SCHEMA_VERSION})."
        )
    if not isinstance(data.get("optional_packs"), list):
        raise LearnError(f"Library catalog {source_label} is missing optional_packs list.")
    return data


def validate_library_catalog(
    catalog: Optional[Dict[str, Any]] = None,
    *,
    catalog_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Validate library/catalog.json schema, unique IDs, prompt limits, and self-tests."""
    data = catalog if catalog is not None else load_library_catalog(catalog_path)
    errors: List[str] = []

    if data.get("schema_version") != LIBRARY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {LIBRARY_SCHEMA_VERSION}.")

    default_core = data.get("default_core")
    if not isinstance(default_core, dict):
        errors.append("default_core must be an object.")
    else:
        for req_key in (
            "summary",
            "selection_criteria",
            "layer_a_diff_checks",
            "layer_b_structural_checks",
            "standing_core_rules",
        ):
            if not default_core.get(req_key):
                errors.append(f"default_core.{req_key} must be non-empty.")

    packs = data.get("optional_packs")
    if not isinstance(packs, list) or not packs:
        errors.append("optional_packs must be a non-empty list.")
        packs = []

    seen_pack_ids: Set[str] = set()
    seen_rule_ids: Set[str] = set()
    det_count = 0
    prompt_count = 0

    for p_idx, pack in enumerate(packs):
        if not isinstance(pack, dict):
            errors.append(f"optional_packs[{p_idx}] must be an object.")
            continue
        pack_id = str(pack.get("id") or "").strip()
        if not pack_id:
            errors.append(f"optional_packs[{p_idx}].id must be non-empty.")
            continue
        norm_pack = pack_id.lower()
        if norm_pack in seen_pack_ids:
            errors.append(f"Duplicate optional pack id '{pack_id}'.")
        seen_pack_ids.add(norm_pack)
        for p_field in ("name", "description", "when_to_enable"):
            if not str(pack.get(p_field) or "").strip():
                errors.append(f"Pack '{pack_id}' missing non-empty '{p_field}'.")
        rules = pack.get("rules")
        if not isinstance(rules, list) or not rules:
            errors.append(f"Pack '{pack_id}' must contain at least one rule.")
            continue

        for r_idx, rule in enumerate(rules):
            if not isinstance(rule, dict):
                errors.append(f"Pack '{pack_id}' rules[{r_idx}] must be an object.")
                continue
            rid = str(rule.get("id") or "").strip()
            if not rid or not rid.startswith("OPT-"):
                errors.append(f"Pack '{pack_id}' rules[{r_idx}] id '{rid}' must start with 'OPT-'.")
            norm_rid = rid.upper()
            if norm_rid in seen_rule_ids:
                errors.append(f"Duplicate optional rule id '{rid}'.")
            seen_rule_ids.add(norm_rid)
            if str(rule.get("pack") or "").strip() != pack_id:
                errors.append(f"Rule '{rid}' pack '{rule.get('pack')}' does not match '{pack_id}'.")

            for req_str in (
                "title",
                "file_glob",
                "remediation",
                "bad_example",
                "valid_neighbouring_case",
                "why_optional",
                "evidence_ref",
                "retirement_trigger",
            ):
                if not str(rule.get(req_str) or "").strip():
                    errors.append(f"Rule '{rid}' missing non-empty '{req_str}'.")

            bad_ex = str(rule.get("bad_example") or "")
            valid_ex = str(rule.get("valid_neighbouring_case") or "")
            if bad_ex.strip() and bad_ex.strip() == valid_ex.strip():
                errors.append(f"Rule '{rid}' bad_example and valid_neighbouring_case must differ.")

            severity = str(rule.get("severity") or "")
            if severity not in VALID_SEVERITIES:
                errors.append(f"Rule '{rid}' invalid severity '{severity}'.")

            ev_status = str(rule.get("evidence_status") or "")
            if ev_status not in VALID_EVIDENCE_STATUSES:
                errors.append(
                    f"Rule '{rid}' invalid evidence_status '{ev_status}' "
                    f"(expected one of {', '.join(VALID_EVIDENCE_STATUSES)})."
                )

            layer = str(rule.get("layer") or "")
            if layer not in VALID_LIBRARY_LAYERS:
                errors.append(f"Rule '{rid}' invalid layer '{layer}'.")
                continue

            if layer == "deterministic_check":
                det_count += 1
                pattern = str(rule.get("pattern") or "")
                match_mode = str(rule.get("match_mode") or "line")
                if match_mode not in VALID_MATCH_MODES:
                    errors.append(f"Rule '{rid}' invalid match_mode '{match_mode}'.")
                    continue
                try:
                    compiled = _validate_regex_pattern(pattern, match_mode)
                except LearnError as exc:
                    errors.append(f"Rule '{rid}' invalid pattern: {exc}")
                    continue
                bad_hits = _find_pattern_hits_in_text(bad_ex, compiled, match_mode)
                valid_hits = _find_pattern_hits_in_text(valid_ex, compiled, match_mode)
                if not bad_hits:
                    errors.append(f"Rule '{rid}' pattern failed to catch its own bad_example.")
                if valid_hits:
                    errors.append(
                        f"Rule '{rid}' pattern falsely matched its own valid_neighbouring_case "
                        f"({len(valid_hits)} hit(s))."
                    )
            else:
                prompt_count += 1
                rule_text = str(rule.get("rule_text") or "")
                wc = _word_count(rule_text)
                if not rule_text.strip():
                    errors.append(f"Rule '{rid}' prompt_rule requires non-empty rule_text.")
                elif wc > MAX_PROMPT_RULE_WORDS:
                    errors.append(
                        f"Rule '{rid}' prompt_rule is {wc} words (max {MAX_PROMPT_RULE_WORDS})."
                    )
                if not str(rule.get("why_not_deterministic") or "").strip():
                    errors.append(f"Rule '{rid}' prompt_rule requires non-empty why_not_deterministic.")

    excluded = data.get("excluded_considered")
    if not isinstance(excluded, list) or not excluded:
        errors.append("excluded_considered must be a non-empty list.")
        excluded = []
    seen_excl_ids: Set[str] = set()
    for e_idx, item in enumerate(excluded):
        if not isinstance(item, dict):
            errors.append(f"excluded_considered[{e_idx}] must be an object.")
            continue
        eid = str(item.get("id") or "").strip()
        if not eid or not eid.startswith("EXCL-"):
            errors.append(f"excluded_considered[{e_idx}] id '{eid}' must start with 'EXCL-'.")
        if eid.upper() in seen_excl_ids:
            errors.append(f"Duplicate excluded id '{eid}'.")
        seen_excl_ids.add(eid.upper())
        for e_field in ("title", "category", "why_excluded", "evidence_ref", "what_we_do_instead"):
            if not str(item.get(e_field) or "").strip():
                errors.append(f"Excluded '{eid}' missing non-empty '{e_field}'.")
        ev_status = str(item.get("evidence_status") or "")
        if ev_status not in VALID_EVIDENCE_STATUSES:
            errors.append(f"Excluded '{eid}' invalid evidence_status '{ev_status}'.")

    if errors:
        raise LearnError("Library catalog validation failed:\n- " + "\n- ".join(errors))

    return {
        "ok": True,
        "packs": len(packs),
        "rules": len(seen_rule_ids),
        "deterministic_rules": det_count,
        "prompt_rules": prompt_count,
        "excluded": len(seen_excl_ids),
    }


def list_library_catalog(catalog_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Return structured summary of default core, optional packs, and excluded items."""
    data = load_library_catalog(catalog_path)
    default_core = data.get("default_core") or {}
    packs_out: List[Dict[str, Any]] = []
    for pack in data.get("optional_packs") or []:
        packs_out.append({
            "id": pack["id"],
            "name": pack["name"],
            "description": pack["description"],
            "when_to_enable": pack["when_to_enable"],
            "rules": [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "layer": r["layer"],
                    "severity": r["severity"],
                    "evidence_status": r["evidence_status"],
                    "file_glob": r["file_glob"],
                }
                for r in pack.get("rules") or []
            ],
        })
    return {
        "schema_version": data["schema_version"],
        "catalog_version": data.get("catalog_version", ""),
        "default_core": {
            "layer_a_count": len(default_core.get("layer_a_diff_checks") or []),
            "layer_b_count": len(default_core.get("layer_b_structural_checks") or []),
            "standing_rules_count": len(
                (default_core.get("standing_core_rules") or {}).get("rules") or []
            ),
        },
        "optional_packs": packs_out,
        "excluded_count": len(data.get("excluded_considered") or []),
    }


def show_library_item(
    target: str,
    *,
    catalog_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Resolve a pack ID, OPT-* rule ID, or EXCL-* excluded ID from library/catalog.json."""
    needle = target.strip()
    if not needle:
        raise LearnError("Provide a pack ID (e.g. network-timeouts) or rule ID (e.g. OPT-NET-01).")
    data = load_library_catalog(catalog_path)
    lower = needle.lower()
    upper = needle.upper()

    pack_ids: List[str] = []
    for pack in data.get("optional_packs") or []:
        pack_ids.append(pack["id"])
        if str(pack["id"]).lower() == lower:
            return {
                "kind": "pack",
                "pack": pack,
                "rules": list(pack.get("rules") or []),
            }
        for rule in pack.get("rules") or []:
            if str(rule["id"]).upper() == upper:
                return {
                    "kind": "rule",
                    "pack": {
                        "id": pack["id"],
                        "name": pack["name"],
                        "description": pack["description"],
                    },
                    "rule": rule,
                    "rules": [rule],
                }

    for item in data.get("excluded_considered") or []:
        if str(item["id"]).upper() == upper:
            return {"kind": "excluded", "item": item}

    raise LearnError(
        f"Library target '{target}' not found. Available packs: {', '.join(pack_ids)}."
    )


def _active_library_rule_map(data: Dict[str, Any]) -> Dict[str, str]:
    """Map active approved library rule IDs (OPT-*) to their learned store ID (L-xxx)."""
    active: Dict[str, str] = {}
    for entry in data.get("rules") or []:
        if not _is_valid_approved_entry(entry):
            continue
        lib_id = entry.get("library_rule_id")
        if not lib_id:
            ctx = str((entry.get("captured") or {}).get("source_context") or "")
            if ctx.startswith("library:") and "/" in ctx:
                lib_id = ctx.rsplit("/", 1)[-1]
        if lib_id:
            active[str(lib_id).upper()] = str(entry["id"])
    return active


def enable_library_rules(
    store_path: Path | str,
    target: str,
    *,
    approved_by: str,
    repo_root: Path | str = ".",
    max_repo_hits: int = 0,
    include_tests_in_scan: bool = False,
    dry_run: bool = False,
    catalog_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Import, 3-way verify, and human-approve an optional pack or OPT-* rule into store_path.

    Never bypasses verification: every imported rule runs through capture_pattern ->
    propose_prevention -> verify_rule -> approve_rule on a staged store copy, and
    store_path is updated only if every requested rule passes verification (and dry_run is False).
    """
    if not approved_by.strip():
        raise LearnError("Enabling optional library rules requires a non-empty --by approver.")
    if isinstance(max_repo_hits, bool) or max_repo_hits < 0:
        raise LearnError("max_repo_hits must be a non-negative integer.")

    resolved = show_library_item(target, catalog_path=catalog_path)
    if resolved["kind"] == "excluded":
        item = resolved["item"]
        raise LearnError(
            f"{item['id']} ({item['title']}) is in excluded_considered and cannot be enabled via library enable."
        )

    store = Path(store_path)
    current_data = load_store(store)
    active_map = _active_library_rule_map(current_data)
    rules_to_process: List[Dict[str, Any]] = list(resolved["rules"])

    results: List[Dict[str, Any]] = []
    all_passed = True
    newly_verified_count = 0

    with tempfile.TemporaryDirectory(prefix="antislop_lib_") as tmp_dir:
        staged_store = Path(tmp_dir) / "rules.json"
        save_store(staged_store, current_data)

        for rule in rules_to_process:
            rid = str(rule["id"])
            existing_lid = active_map.get(rid.upper())
            if existing_lid is not None:
                results.append({
                    "library_rule_id": rid,
                    "pack": rule["pack"],
                    "learned_id": existing_lid,
                    "title": rule["title"],
                    "layer": rule["layer"],
                    "status": "skipped_already_active",
                    "passed": True,
                    "verification": None,
                })
                continue

            cap_entry = capture_pattern(
                staged_store,
                title=f"[{rid}] {rule['title']}",
                bad_example=str(rule["bad_example"]),
                desired_outcome=str(rule["remediation"]),
                valid_neighbouring_case=str(rule["valid_neighbouring_case"]),
                why_it_matters=str(rule["why_optional"]),
                file_glob=str(rule["file_glob"]),
                source_context=f"library:{rule['pack']}/{rid}",
            )
            staged_data = load_store(staged_store)
            staged_entry = _find_rule(staged_data, cap_entry["id"])
            staged_entry["library_rule_id"] = rid
            staged_entry["library_pack"] = rule["pack"]
            save_store(staged_store, staged_data)

            propose_prevention(
                staged_store,
                cap_entry["id"],
                layer=str(rule["layer"]),
                severity=str(rule["severity"]),
                file_glob=str(rule["file_glob"]),
                pattern=rule.get("pattern"),
                match_mode=str(rule.get("match_mode") or "line"),
                rule_text=rule.get("rule_text"),
                why_not_deterministic=rule.get("why_not_deterministic"),
                remediation=str(rule["remediation"]),
                retirement_trigger=str(rule["retirement_trigger"]),
            )
            ver_entry = verify_rule(
                staged_store,
                cap_entry["id"],
                repo_root=repo_root,
                max_repo_hits=max_repo_hits,
                include_tests_in_scan=include_tests_in_scan,
            )
            verif = ver_entry["verification"]
            if verif["passed"]:
                app_entry = approve_rule(
                    staged_store,
                    cap_entry["id"],
                    approved_by=approved_by,
                    note=f"Enabled from optional library ({rule['pack']}/{rid}).",
                )
                newly_verified_count += 1
                results.append({
                    "library_rule_id": rid,
                    "pack": rule["pack"],
                    "learned_id": app_entry["id"],
                    "title": rule["title"],
                    "layer": rule["layer"],
                    "status": "would_enable" if dry_run else "enabled",
                    "passed": True,
                    "verification": app_entry["verification"],
                })
            else:
                all_passed = False
                results.append({
                    "library_rule_id": rid,
                    "pack": rule["pack"],
                    "learned_id": None,
                    "title": rule["title"],
                    "layer": rule["layer"],
                    "status": "verification_failed",
                    "passed": False,
                    "verification": verif,
                })

        if all_passed and not dry_run and newly_verified_count > 0:
            save_store(store, load_store(staged_store))
        elif not all_passed:
            for item in results:
                if item["status"] in ("enabled", "would_enable"):
                    item["status"] = "verified_not_saved"
                    item["learned_id"] = None

    return {
        "ok": all_passed,
        "target": target,
        "kind": resolved["kind"],
        "dry_run": dry_run,
        "store_path": str(store),
        "enabled_count": sum(1 for r in results if r["status"] in ("enabled", "would_enable")),
        "skipped_count": sum(1 for r in results if r["status"] == "skipped_already_active"),
        "failed_count": sum(1 for r in results if not r["passed"]),
        "results": results,
    }


_FIX_SUBJECT_RE = re.compile(r"^(?:fix|bugfix|hotfix)(?:\([^)]*\))?!?:", re.IGNORECASE)
_REVERT_SUBJECT_RE = re.compile(r"^(?:revert\b|rollback\b)", re.IGNORECASE)


def _parse_utc_iso(ts: str) -> Optional[datetime]:
    raw = (ts or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_telemetry_jsonl(telemetry_path: Path) -> Dict[str, Any]:
    """Parse optional local hook/review telemetry JSONL safely (read-only)."""
    code_counts: Dict[str, int] = {}
    code_last_seen: Dict[str, str] = {}
    events_by_type: Dict[str, int] = {}
    harnesses: Dict[str, int] = {}
    file_ext_counts: Dict[str, int] = {}
    records_parsed = 0
    malformed_lines = 0
    blocked_events = 0
    allowed_events = 0
    earliest_dt: Optional[datetime] = None
    latest_dt: Optional[datetime] = None
    earliest_ts: Optional[str] = None
    latest_ts: Optional[str] = None

    if not telemetry_path.is_file():
        return {
            "exists": False,
            "path": str(telemetry_path),
            "records_parsed": 0,
            "malformed_lines": 0,
            "blocked_events": 0,
            "allowed_events": 0,
            "events_by_type": {},
            "harnesses": {},
            "file_ext_counts": {},
            "code_counts": {},
            "code_last_seen": {},
            "earliest_ts": None,
            "latest_ts": None,
        }

    try:
        raw_lines = telemetry_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        raw_lines = []

    for raw in raw_lines:
        stripped = raw.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            malformed_lines += 1
            continue
        if not isinstance(obj, dict):
            malformed_lines += 1
            continue

        records_parsed += 1
        if obj.get("blocked") is True:
            blocked_events += 1
        else:
            allowed_events += 1

        event = str(obj.get("event") or "unknown").strip() or "unknown"
        events_by_type[event] = events_by_type.get(event, 0) + 1

        harness = str(obj.get("harness") or "").strip()
        if harness:
            harnesses[harness] = harnesses.get(harness, 0) + 1

        ts_raw = str(obj.get("ts") or "").strip()
        dt = _parse_utc_iso(ts_raw)
        if dt is not None:
            norm_ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            if earliest_dt is None or dt < earliest_dt:
                earliest_dt = dt
                earliest_ts = norm_ts
            if latest_dt is None or dt > latest_dt:
                latest_dt = dt
                latest_ts = norm_ts
        else:
            norm_ts = None

        codes = obj.get("codes")
        if isinstance(codes, list):
            for raw_code in codes:
                if not isinstance(raw_code, str):
                    continue
                code = raw_code.strip()
                if not code:
                    continue
                code_counts[code] = code_counts.get(code, 0) + 1
                if norm_ts is not None:
                    prev = code_last_seen.get(code)
                    if prev is None or norm_ts > prev:
                        code_last_seen[code] = norm_ts

        exts = obj.get("file_exts")
        if isinstance(exts, list):
            for raw_ext in exts:
                if isinstance(raw_ext, str) and raw_ext.strip():
                    ext = raw_ext.strip().lower()
                    file_ext_counts[ext] = file_ext_counts.get(ext, 0) + 1

    return {
        "exists": True,
        "path": str(telemetry_path),
        "records_parsed": records_parsed,
        "malformed_lines": malformed_lines,
        "blocked_events": blocked_events,
        "allowed_events": allowed_events,
        "events_by_type": dict(sorted(events_by_type.items())),
        "harnesses": dict(sorted(harnesses.items())),
        "file_ext_counts": dict(sorted(file_ext_counts.items())),
        "code_counts": dict(sorted(code_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "code_last_seen": dict(sorted(code_last_seen.items())),
        "earliest_ts": earliest_ts,
        "latest_ts": latest_ts,
    }


def _is_excluded_mining_path(rel_path: str) -> bool:
    norm = _dc._normalize_relpath(rel_path)
    parts = Path(norm).parts
    if any(part in EXCLUDED_SCAN_DIRS for part in parts):
        return True
    if len(parts) >= 2 and parts[:2] == ("benchmarks", "sources"):
        return True
    return False


def _filter_unified_diff_for_mining(diff_text: str) -> str:
    """Drop diff sections under excluded directories (results, fixtures, .anti-slop, etc.)."""
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append(current)

    kept: List[str] = []
    for block in blocks:
        target_path: Optional[str] = None
        for ln in block[1:8]:
            if ln.startswith("+++ b/"):
                target_path = ln[6:].strip()
                break
            if ln.startswith("+++ /dev/null"):
                target_path = ""
                break
        if target_path is None:
            parts = block[0].strip().split(" b/", 1)
            if len(parts) == 2:
                target_path = parts[1].strip()
        if not target_path or _is_excluded_mining_path(target_path):
            continue
        kept.extend(block)
    return "".join(kept)


def _compile_uninstalled_opt_rules(
    catalog: Dict[str, Any],
    active_lib_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    compiled_rules: List[Dict[str, Any]] = []
    for pack in catalog.get("optional_packs") or []:
        for rule in pack.get("rules") or []:
            if rule.get("layer") != "deterministic_check":
                continue
            rid = str(rule.get("id") or "")
            if rid.upper() in active_lib_map:
                continue
            match_mode = str(rule.get("match_mode") or "line")
            try:
                compiled = _validate_regex_pattern(str(rule.get("pattern") or ""), match_mode)
            except LearnError:
                continue
            file_glob = str(rule.get("file_glob") or "*")
            ignore_comments = _should_ignore_code_comments(
                str(rule.get("bad_example") or ""),
                compiled,
                match_mode,
                file_glob=file_glob,
            )
            compiled_rules.append({
                "rule": rule,
                "pack": pack,
                "compiled": compiled,
                "match_mode": match_mode,
                "file_glob": file_glob,
                "ignore_comments": ignore_comments,
                "targets_tests": "test" in file_glob.lower(),
            })
    return compiled_rules


def _scan_commit_diff_opt_rules(
    parsed_diff: Dict[str, Any],
    compiled_opt_rules: Sequence[Dict[str, Any]],
    short_sha: str,
    opt_hits_by_rule: Dict[str, Dict[str, Any]],
) -> None:
    for fentry in parsed_diff.get("files") or []:
        path = str(fentry.get("path") or "")
        if not path or fentry.get("is_deleted") or _is_excluded_mining_path(path):
            continue
        is_test = _dc._is_test_file(path)
        for item in compiled_opt_rules:
            if is_test and not item["targets_tests"]:
                continue
            if not _matches_file_glob(path, item["file_glob"]):
                continue
            rid = str(item["rule"]["id"])
            matched_in_file: List[Tuple[int, str]] = []
            for hunk in fentry.get("hunks") or []:
                visible = [(k, ln, txt) for k, ln, txt in hunk["lines"] if k != "-"]
                if not visible:
                    continue
                added_1based = {i + 1 for i, (k, _, _) in enumerate(visible) if k == "+"}
                if not added_1based:
                    continue
                hunk_text = "\n".join(txt for _, _, txt in visible)
                line_map = {i + 1: ln for i, (_, ln, _) in enumerate(visible)}
                for ln1, snippet in _find_pattern_hits_in_text(
                    hunk_text,
                    item["compiled"],
                    item["match_mode"],
                    added_lines=added_1based,
                    rel_path=path,
                    ignore_comments=item["ignore_comments"],
                ):
                    matched_in_file.append((line_map.get(ln1, ln1), snippet))
            if matched_in_file:
                bucket = opt_hits_by_rule.setdefault(
                    rid,
                    {
                        "rule": item["rule"],
                        "pack": item["pack"],
                        "commits": [],
                        "total_hits": 0,
                        "sample_hits": [],
                    },
                )
                if short_sha not in bucket["commits"]:
                    bucket["commits"].append(short_sha)
                bucket["total_hits"] += len(matched_in_file)
                for real_ln, snippet in matched_in_file:
                    if len(bucket["sample_hits"]) < 5:
                        bucket["sample_hits"].append(f"{short_sha} {path}:{real_ln}: {snippet[:60]}")


def _mine_git_history(
    root: Path,
    commits: int,
    compiled_opt_rules: Sequence[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Read-only git log/show mining across the last N non-merge commits."""
    opt_hits_by_rule: Dict[str, Dict[str, Any]] = {}
    git_code_stats: Dict[str, Dict[str, Any]] = {}
    empty_summary: Dict[str, Any] = {
        "available": False,
        "commits_scanned": 0,
        "fix_commit_count": 0,
        "revert_commit_count": 0,
        "fix_commit_ratio": 0.0,
        "churn_signals": [],
        "high_churn_files": [],
        "diff_and_structural_code_counts": {},
    }
    if commits == 0:
        empty_summary["available"] = True
        return empty_summary, opt_hits_by_rule, git_code_stats

    try:
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return empty_summary, opt_hits_by_rule, git_code_stats
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return empty_summary, opt_hits_by_rule, git_code_stats

    log_proc = subprocess.run(
        ["git", "log", "--no-merges", "-n", str(commits), "--format=%H%x1f%aI%x1f%s"],
        cwd=root,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if log_proc.returncode != 0:
        empty_summary["available"] = True
        return empty_summary, opt_hits_by_rule, git_code_stats

    commit_rows: List[Tuple[str, str, str]] = []
    for line in log_proc.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            commit_rows.append((parts[0].strip(), parts[1].strip(), parts[2].strip()))

    fix_count = 0
    revert_count = 0
    churn_signals: List[Dict[str, str]] = []
    file_touch_counts: Dict[str, Dict[str, Any]] = {}

    for full_sha, author_iso, subject in commit_rows:
        short_sha = full_sha[:7]
        is_revert = bool(_REVERT_SUBJECT_RE.search(subject))
        is_fix = (not is_revert) and bool(_FIX_SUBJECT_RE.search(subject))
        if is_revert:
            revert_count += 1
            if len(churn_signals) < 10:
                churn_signals.append({"kind": "revert", "commit": short_sha, "date": author_iso, "subject": subject})
        elif is_fix:
            fix_count += 1
            if len(churn_signals) < 10:
                churn_signals.append({"kind": "fix", "commit": short_sha, "date": author_iso, "subject": subject})

        diff_proc = subprocess.run(
            ["git", "show", "--format=", "--unified=3", "--no-color", "--no-ext-diff", full_sha],
            cwd=root,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        if diff_proc.returncode != 0 or not diff_proc.stdout.strip():
            continue
        filtered_diff = _filter_unified_diff_for_mining(diff_proc.stdout)
        if not filtered_diff.strip():
            continue

        parsed = _dc.parse_unified_diff(filtered_diff)
        for fentry in parsed.get("files") or []:
            fpath = str(fentry.get("path") or "")
            if not fpath or _is_excluded_mining_path(fpath):
                continue
            ft = file_touch_counts.setdefault(
                fpath,
                {"file": fpath, "commit_count": 0, "fix_or_revert_count": 0, "sample_commits": []},
            )
            ft["commit_count"] += 1
            if is_fix or is_revert:
                ft["fix_or_revert_count"] += 1
            if len(ft["sample_commits"]) < 5:
                ft["sample_commits"].append(short_sha)

        if compiled_opt_rules:
            _scan_commit_diff_opt_rules(parsed, compiled_opt_rules, short_sha, opt_hits_by_rule)

        diff_res = _dc.check_diff(
            filtered_diff,
            repo_root=None,
            allow_test_edit=True,
            no_budget=True,
        )
        struct_res = _struct.check_structural_diff(filtered_diff, repo_root=None)
        commit_findings = (
            list(diff_res.get("errors") or [])
            + list(diff_res.get("warnings") or [])
            + list(struct_res.get("errors") or [])
            + list(struct_res.get("warnings") or [])
        )
        seen_in_commit: Set[str] = set()
        for finding in commit_findings:
            code = str(finding.get("code") or "").strip()
            if not code:
                continue
            stat = git_code_stats.setdefault(code, {"commit_count": 0, "hit_count": 0, "commits": []})
            stat["hit_count"] += 1
            if code not in seen_in_commit:
                seen_in_commit.add(code)
                stat["commit_count"] += 1
                if len(stat["commits"]) < 5:
                    stat["commits"].append(short_sha)

    scanned = len(commit_rows)
    high_churn_files = sorted(
        [
            item
            for item in file_touch_counts.values()
            if item["fix_or_revert_count"] >= 2
        ],
        key=lambda x: (-x["fix_or_revert_count"], -x["commit_count"], x["file"]),
    )[:10]

    summary = {
        "available": True,
        "commits_scanned": scanned,
        "fix_commit_count": fix_count,
        "revert_commit_count": revert_count,
        "fix_commit_ratio": round((fix_count + revert_count) / scanned, 4) if scanned else 0.0,
        "churn_signals": churn_signals,
        "high_churn_files": high_churn_files,
        "diff_and_structural_code_counts": dict(
            sorted(
                ((code, st["commit_count"]) for code, st in git_code_stats.items()),
                key=lambda kv: (-kv[1], kv[0]),
            )
        ),
    }
    return summary, opt_hits_by_rule, git_code_stats


def _build_recommended_library_packs(
    opt_hits_by_rule: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_pack: Dict[str, Dict[str, Any]] = {}
    for rid, info in sorted(opt_hits_by_rule.items()):
        pack = info["pack"]
        pack_id = str(pack["id"])
        rule = info["rule"]
        entry = by_pack.setdefault(
            pack_id,
            {
                "pack_id": pack_id,
                "pack_name": pack["name"],
                "description": pack["description"],
                "when_to_enable": pack["when_to_enable"],
                "commits": [],
                "total_hits": 0,
                "matched_rules": [],
            },
        )
        for sha in info["commits"]:
            if sha not in entry["commits"]:
                entry["commits"].append(sha)
        entry["total_hits"] += info["total_hits"]
        entry["matched_rules"].append({
            "id": rid,
            "title": rule["title"],
            "severity": rule["severity"],
            "commit_count": len(info["commits"]),
            "total_hits": info["total_hits"],
            "sample_commits": info["commits"][:5],
            "sample_hits": info["sample_hits"][:5],
        })

    recommended: List[Dict[str, Any]] = []
    for pack_id, entry in by_pack.items():
        recommended.append({
            "pack_id": pack_id,
            "pack_name": entry["pack_name"],
            "description": entry["description"],
            "when_to_enable": entry["when_to_enable"],
            "matched_commits_count": len(entry["commits"]),
            "sample_commits": entry["commits"][:5],
            "total_hits": entry["total_hits"],
            "matched_rules": sorted(
                entry["matched_rules"], key=lambda r: (-r["commit_count"], r["id"])
            ),
            "verify_command": f"anti-slop learn library enable {pack_id} --by <your-name> --dry-run",
            "enable_command": f"anti-slop learn library enable {pack_id} --by <your-name>",
        })
    recommended.sort(key=lambda p: (-p["matched_commits_count"], -p["total_hits"], p["pack_id"]))
    return recommended


def _find_retirement_candidates(
    store_data: Dict[str, Any],
    telemetry_summary: Dict[str, Any],
    stale_days: int,
    now_dt: datetime,
) -> List[Dict[str, Any]]:
    code_counts: Dict[str, int] = telemetry_summary.get("code_counts") or {}
    code_last_seen: Dict[str, str] = telemetry_summary.get("code_last_seen") or {}
    records_parsed = int(telemetry_summary.get("records_parsed") or 0)
    candidates: List[Dict[str, Any]] = []

    for entry in store_data.get("rules") or []:
        if not _is_valid_approved_entry(entry):
            continue
        rule_id = str(entry["id"])
        learned_code = f"LEARNED-{rule_id}"
        hits = code_counts.get(learned_code, 0) + code_counts.get(rule_id, 0)
        last_hit_ts = code_last_seen.get(learned_code) or code_last_seen.get(rule_id)

        approval = entry.get("approval") or {}
        approved_at = str(
            approval.get("approved_at") or entry.get("updated_at") or entry.get("created_at") or ""
        )
        approved_dt = _parse_utc_iso(approved_at)
        age_days = round((now_dt - approved_dt).total_seconds() / 86400.0, 1) if approved_dt else None

        stale = False
        reason = ""
        days_since_hit: Optional[float] = None
        if hits == 0 and age_days is not None and age_days >= stale_days:
            stale = True
            if records_parsed > 0:
                reason = (
                    f"Zero hits across {records_parsed} telemetry record(s) over {age_days:.1f} days "
                    f"since approval (threshold: {stale_days} days)."
                )
            else:
                reason = (
                    f"Zero recorded hits (no telemetry log yet) and rule is {age_days:.1f} days old "
                    f"(threshold: {stale_days} days); check retirement trigger."
                )
        elif hits > 0 and last_hit_ts:
            last_dt = _parse_utc_iso(last_hit_ts)
            if last_dt is not None:
                days_since_hit = round((now_dt - last_dt).total_seconds() / 86400.0, 1)
                if days_since_hit >= stale_days:
                    stale = True
                    reason = (
                        f"Zero hits in the last {days_since_hit:.1f} days "
                        f"(last seen {last_hit_ts}; threshold: {stale_days} days)."
                    )

        if stale:
            proposal = entry.get("proposal") or {}
            candidates.append({
                "id": rule_id,
                "title": entry["title"],
                "layer": proposal.get("layer"),
                "approved_at": approved_at,
                "age_days": age_days,
                "telemetry_hits": hits,
                "last_hit_ts": last_hit_ts,
                "days_since_last_hit": days_since_hit,
                "retirement_trigger": proposal.get("retirement_trigger", ""),
                "reason": reason,
                "retire_command": f'anti-slop learn retire {rule_id} --reason "<reason>"',
            })

    candidates.sort(key=lambda c: (-(c["age_days"] or 0.0), c["id"]))
    return candidates


def _build_recurring_patterns(
    telemetry_summary: Dict[str, Any],
    git_code_stats: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    t_counts: Dict[str, int] = telemetry_summary.get("code_counts") or {}
    t_last: Dict[str, str] = telemetry_summary.get("code_last_seen") or {}
    all_codes = set(t_counts.keys()) | set(git_code_stats.keys())
    recurring: List[Dict[str, Any]] = []

    for code in sorted(all_codes):
        t_cnt = int(t_counts.get(code, 0))
        g_info = git_code_stats.get(code) or {}
        g_commits = int(g_info.get("commit_count", 0))
        g_hits = int(g_info.get("hit_count", 0))
        total = t_cnt + g_commits
        if total < 2:
            continue
        sources: List[str] = []
        if t_cnt > 0:
            sources.append("telemetry")
        if g_commits > 0:
            sources.append("git")
        if code.startswith("LEARNED-"):
            action = "Existing learned rule is actively catching repeat slop; keep enforced or fix root cause in canonical examples."
        elif g_commits >= 2 and t_cnt == 0:
            action = "Pattern is slipping into git commits uncaught by local hooks; install blocking hooks or CI diff checks."
        else:
            action = "Recurring pattern; fix root cause via canonical example, linter config, or scoped learned rule if not already blocked."
        recurring.append({
            "code": code,
            "telemetry_count": t_cnt,
            "git_commit_count": g_commits,
            "git_hit_count": g_hits,
            "total_count": total,
            "sources": sources,
            "last_seen_ts": t_last.get(code),
            "sample_commits": list(g_info.get("commits") or [])[:5],
            "suggested_action": action,
        })

    recurring.sort(key=lambda item: (-item["total_count"], item["code"]))
    return recurring


def _build_mine_next_steps(
    recurring_patterns: Sequence[Dict[str, Any]],
    recommended_packs: Sequence[Dict[str, Any]],
    retirement_candidates: Sequence[Dict[str, Any]],
    telemetry_summary: Dict[str, Any],
    git_summary: Dict[str, Any],
) -> List[str]:
    steps: List[str] = []
    for pack in recommended_packs[:3]:
        pid = pack["pack_id"]
        steps.append(
            f"Inspect and dry-run verify optional pack '{pid}' "
            f"({pack['matched_commits_count']} commit(s)): "
            f"anti-slop learn library show {pid} && "
            f"anti-slop learn library enable {pid} --by <your-name> --dry-run"
        )
    for cand in retirement_candidates[:3]:
        steps.append(
            f"Review stale rule {cand['id']} ({cand['title']}) against its retirement trigger; "
            f"retire if obsolete: anti-slop learn retire {cand['id']} --reason \"<reason>\""
        )
    for pat in recurring_patterns[:3]:
        if pat["git_commit_count"] >= 2 and pat["telemetry_count"] == 0:
            steps.append(
                f"Pattern {pat['code']} appeared in {pat['git_commit_count']} recent commit(s) without hook blocks: "
                "install blocking agent hooks via anti-slop hook --install <claude|antigravity|codex>."
            )
            break
    if git_summary.get("high_churn_files"):
        top_file = git_summary["high_churn_files"][0]
        steps.append(
            f"Inspect high-churn file {top_file['file']} "
            f"({top_file['fix_or_revert_count']} fix/revert commit(s)) for missing characterization tests or structural coupling."
        )
    if not steps:
        if not telemetry_summary.get("exists"):
            steps.append(
                "No recurring slop or stale rules found. Optional: enable local hook telemetry "
                "(ANTI_SLOP_TELEMETRY=1) or widen --commits to monitor over a longer history."
            )
        else:
            steps.append(
                "No recurring slop, uninstalled pack matches, or stale learned rules found in the current window."
            )
    return steps


def mine_patterns(
    repo_root: Path | str = ".",
    *,
    store_path: Optional[Path | str] = None,
    telemetry_path: Optional[Path | str] = None,
    commits: int = DEFAULT_MINE_COMMITS,
    stale_days: int = DEFAULT_STALE_DAYS,
    catalog_path: Optional[Path | str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Read-only continuous monitoring: mine hook telemetry + git history for recurring slop and stale rules.

    Strictly read-only: never creates, edits, or approves rules in .anti-slop/learned/rules.json.
    """
    if isinstance(commits, bool) or not isinstance(commits, int) or commits < 0:
        raise LearnError("commits must be a non-negative integer.")
    if isinstance(stale_days, bool) or not isinstance(stale_days, int) or stale_days < 0:
        raise LearnError("stale_days must be a non-negative integer.")

    root = Path(repo_root).resolve()
    store = Path(store_path) if store_path is not None else default_store_path(root)
    telemetry = Path(telemetry_path) if telemetry_path is not None else default_telemetry_path(root)
    now_dt = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)

    store_data = load_store(store)
    active_lib_map = _active_library_rule_map(store_data)
    catalog = load_library_catalog(catalog_path)
    compiled_opt_rules = _compile_uninstalled_opt_rules(catalog, active_lib_map)

    telemetry_summary = _parse_telemetry_jsonl(telemetry)
    git_summary, opt_hits_by_rule, git_code_stats = _mine_git_history(
        root, commits, compiled_opt_rules
    )

    recurring_patterns = _build_recurring_patterns(telemetry_summary, git_code_stats)
    recommended_library_packs = _build_recommended_library_packs(opt_hits_by_rule)
    retirement_candidates = _find_retirement_candidates(
        store_data, telemetry_summary, stale_days, now_dt
    )
    suggested_next_steps = _build_mine_next_steps(
        recurring_patterns,
        recommended_library_packs,
        retirement_candidates,
        telemetry_summary,
        git_summary,
    )

    return {
        "ok": True,
        "read_only": True,
        "repo_root": str(root),
        "store_path": str(store),
        "telemetry_path": str(telemetry),
        "commits_requested": commits,
        "stale_days": stale_days,
        "telemetry_summary": telemetry_summary,
        "git_summary": git_summary,
        "recurring_patterns": recurring_patterns,
        "recommended_library_packs": recommended_library_packs,
        "retirement_candidates": retirement_candidates,
        "suggested_next_steps": suggested_next_steps,
    }


def _format_mine_report(report: Dict[str, Any]) -> str:
    t = report["telemetry_summary"]
    g = report["git_summary"]
    lines = [
        "Anti-Slop Continuous Mining Report (read-only)",
        f"  Telemetry: {t['records_parsed']} record(s), {t['blocked_events']} blocked, "
        f"{t['malformed_lines']} malformed line(s) skipped ({'present' if t['exists'] else 'not found'})",
        f"  Git scan:  {g['commits_scanned']} non-merge commit(s), "
        f"{g['fix_commit_count']} fix / {g['revert_commit_count']} revert commit(s)",
        "",
    ]

    recurring = report["recurring_patterns"]
    lines.append(f"Recurring patterns (count >= 2): {len(recurring)}")
    if recurring:
        for item in recurring:
            src = "+".join(item["sources"])
            commits_str = f" [commits: {', '.join(item['sample_commits'])}]" if item["sample_commits"] else ""
            lines.append(
                f"  - {item['code']}: total={item['total_count']} "
                f"(telemetry={item['telemetry_count']}, git_commits={item['git_commit_count']}, {src}){commits_str}"
            )
    else:
        lines.append("  None found.")
    lines.append("")

    packs = report["recommended_library_packs"]
    lines.append(f"Recommended optional library packs (uninstalled): {len(packs)}")
    if packs:
        for pack in packs:
            rule_ids = ", ".join(r["id"] for r in pack["matched_rules"])
            shas = ", ".join(pack["sample_commits"])
            lines.append(
                f"  - {pack['pack_id']} ({pack['pack_name']}): "
                f"{pack['matched_commits_count']} commit(s), {pack['total_hits']} hit(s) "
                f"[{rule_ids}; sample commits: {shas}]"
            )
            lines.append(f"      verify: {pack['verify_command']}")
    else:
        lines.append("  None matched recent commits.")
    lines.append("")

    retire = report["retirement_candidates"]
    lines.append(f"Retirement candidates (zero hits >= {report['stale_days']} days): {len(retire)}")
    if retire:
        for cand in retire:
            lines.append(f"  - {cand['id']} ({cand['title']}): {cand['reason']}")
            if cand["retirement_trigger"]:
                lines.append(f"      trigger: {cand['retirement_trigger']}")
            lines.append(f"      retire:  {cand['retire_command']}")
    else:
        lines.append("  None flagged.")
    lines.append("")

    lines.append("Suggested next steps (verify before human approval):")
    for idx, step in enumerate(report["suggested_next_steps"], start=1):
        lines.append(f"  {idx}. {step}")
    lines.append("")
    lines.append(
        "Read-only check: .anti-slop/learned/rules.json was not modified. "
        "Run verification and obtain explicit human approval before enabling or retiring rules."
    )
    return "\n".join(lines)


def _format_library_list(summary: Dict[str, Any]) -> str:
    dc = summary["default_core"]
    lines = [
        f"Optional Rule Library (v{summary.get('catalog_version') or '1'})",
        (
            f"Default core: {dc['layer_a_count']} Layer A diff checks, "
            f"{dc['layer_b_count']} Layer B structural checks, "
            f"{dc['standing_rules_count']} core rules | "
            f"Deliberately excluded: {summary['excluded_count']}"
        ),
        "",
        "PACK                     RULE ID     LAYER                SEVERITY  EVIDENCE STATUS           TITLE",
        "-----------------------  ----------  -------------------  --------  ------------------------  ------------------------------",
    ]
    for pack in summary["optional_packs"]:
        for r in pack["rules"]:
            lines.append(
                f"{pack['id']:<23}  {r['id']:<10}  {r['layer']:<19}  "
                f"{r['severity']:<8}  {r['evidence_status']:<24}  {r['title']}"
            )
    lines.append("")
    lines.append("Inspect a pack or rule: anti-slop-learn library show <pack-or-rule-id>")
    lines.append("Enable with 3-way check: anti-slop-learn library enable <pack-or-rule-id> --by <your-name>")
    return "\n".join(lines)


def _format_library_show(resolved: Dict[str, Any]) -> str:
    if resolved["kind"] == "excluded":
        item = resolved["item"]
        return "\n".join([
            f"{item['id']} (DELIBERATELY EXCLUDED): {item['title']}",
            f"  Category:        {item['category']}",
            f"  Evidence status: {item['evidence_status']} ({item['evidence_ref']})",
            f"  Why excluded:    {item['why_excluded']}",
            f"  Instead:         {item['what_we_do_instead']}",
        ])

    lines: List[str] = []
    pack = resolved["pack"]
    if resolved["kind"] == "pack":
        lines.append(f"Pack: {pack['id']} ({pack['name']})")
        lines.append(f"  Description:    {pack['description']}")
        lines.append(f"  When to enable: {pack['when_to_enable']}")
        lines.append("")

    for rule in resolved["rules"]:
        lines.append(f"Rule {rule['id']} ({rule['title']})")
        lines.append(f"  Pack:            {rule['pack']}")
        lines.append(f"  Layer / Sev:     {rule['layer']} / {rule['severity']} (glob: {rule['file_glob']})")
        lines.append(f"  Evidence status: {rule['evidence_status']} ({rule['evidence_ref']})")
        if rule["layer"] == "deterministic_check":
            lines.append(f"  Pattern:         {rule['pattern']}")
        else:
            wc = _word_count(str(rule.get("rule_text") or ""))
            lines.append(f"  Rule text ({wc}w): {rule['rule_text']}")
            lines.append(f"  Why not det.:    {rule['why_not_deterministic']}")
        lines.append(f"  Why optional:    {rule['why_optional']}")
        lines.append(f"  Remediation:     {rule['remediation']}")
        lines.append(f"  Retire trigger:  {rule['retirement_trigger']}")
        lines.append("  Bad example:")
        for ln in str(rule["bad_example"]).rstrip("\n").splitlines():
            lines.append(f"    | {ln}")
        lines.append("  Valid neighbouring case:")
        for ln in str(rule["valid_neighbouring_case"]).rstrip("\n").splitlines():
            lines.append(f"    | {ln}")
        lines.append("")

    return "\n".join(lines).rstrip()


def _format_library_enable(result: Dict[str, Any]) -> str:
    mode = " [dry-run]" if result["dry_run"] else ""
    header_status = "PASSED" if result["ok"] else "FAILED"
    lines = [f"Library enable {header_status}{mode} for '{result['target']}':"]
    for item in result["results"]:
        lid = f" -> {item['learned_id']}" if item["learned_id"] else ""
        lines.append(
            f"  - {item['library_rule_id']}{lid} [{item['status']}]: {item['title']} ({item['layer']})"
        )
        verif = item.get("verification")
        if isinstance(verif, dict) and not item["passed"]:
            if verif.get("mechanical"):
                lines.append(
                    f"      bad_case_caught={verif['bad_case_caught']} "
                    f"valid_neighbour_clean={verif['valid_neighbour_clean']} "
                    f"repo_scan_hits={verif['repo_scan_hits']}/{verif['max_repo_hits']} "
                    f"across {verif['repo_scan_files']} file(s)"
                )
                for sample in verif.get("repo_sample_hits") or []:
                    lines.append(f"      hit: {sample}")
            for note in verif.get("notes") or []:
                lines.append(f"      {note}")
    if not result["ok"]:
        lines.append(
            "No rules were saved because verification failed. Fix existing matches, "
            "enable a single OPT-* rule ID, or re-run with --max-repo-hits N."
        )
    return "\n".join(lines)


def _read_text_arg(inline: Optional[str], file_path: Optional[str], label: str) -> str:
    if file_path is not None:
        try:
            return Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise LearnError(f"Failed to read --{label}-file {file_path}: {exc}") from exc
    if inline is not None:
        return inline
    raise LearnError(f"Provide either --{label} or --{label}-file.")


def _format_rule_list(data: Dict[str, Any]) -> str:
    rules = data.get("rules") or []
    if not rules:
        return "No learned rules recorded yet. Start with: anti-slop-learn capture ..."
    lines = ["ID     STATUS                LAYER                 TITLE"]
    lines.append("-----  --------------------  --------------------  ------------------------------")
    for r in rules:
        layer = (r.get("proposal") or {}).get("layer") or "-"
        lines.append(f"{r['id']:<5}  {r['status']:<20}  {layer:<20}  {r['title']}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verified self-learning loop (R7): capture slipped AI slop patterns, "
            "propose the smallest prevention, verify against bad/valid/repo cases, "
            "gate on human approval, and retire cleanly without reusing IDs."
        )
    )
    parser.add_argument(
        "--store",
        default=None,
        help=f"Path to learned rules JSON store (default: <repo-root>/{DEFAULT_STORE_REL}).",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root used for repo false-positive scans and path checks (default: '.').",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit structured JSON output.",
    )

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", default=argparse.SUPPRESS, help="Path to learned rules JSON store.")
    common.add_argument("--repo-root", default=argparse.SUPPRESS, help="Repository root.")
    common.add_argument("--json", action="store_true", dest="emit_json", default=argparse.SUPPRESS, help="Emit JSON output.")

    sub = parser.add_subparsers(dest="command", required=True)

    p_cap = sub.add_parser("capture", parents=[common], help="Capture a slipped slop pattern with bad + valid examples.")
    p_cap.add_argument("--title", required=True, help="Short plain-English name for the pattern.")
    p_cap.add_argument("--bad-code", default=None, help="Inline bad example snippet.")
    p_cap.add_argument("--bad-file", default=None, help="File containing the bad example snippet.")
    p_cap.add_argument("--desired", required=True, help="Plain-English description of desired behavior.")
    p_cap.add_argument("--valid-code", default=None, help="Inline valid neighbouring snippet.")
    p_cap.add_argument("--valid-file", default=None, help="File containing the valid neighbouring snippet.")
    p_cap.add_argument("--why", default="", help="Why this matters / how it compounds.")
    p_cap.add_argument("--file-glob", default="*.py", help="Target file glob (default: '*.py').")
    p_cap.add_argument("--context", default="", help="Optional source file, PR, or commit reference.")

    p_sug = sub.add_parser("suggest", parents=[common], help="Suggest the narrowest prevention layer for a captured rule.")
    p_sug.add_argument("rule_id", help="Rule ID (e.g., L-001).")

    p_prop = sub.add_parser("propose", parents=[common], help="Attach the smallest prevention proposal to a captured rule.")
    p_prop.add_argument("rule_id", help="Rule ID (e.g., L-001).")
    p_prop.add_argument("--layer", required=True, choices=VALID_LAYERS)
    p_prop.add_argument("--severity", default="warning", choices=VALID_SEVERITIES)
    p_prop.add_argument("--file-glob", default=None)
    p_prop.add_argument("--pattern", default=None, help="Regex pattern for deterministic_check.")
    p_prop.add_argument("--match-mode", default="line", choices=VALID_MATCH_MODES)
    p_prop.add_argument("--canonical-path", default=None, help="Repo file path for codebase_example.")
    p_prop.add_argument("--rule-text", default=None, help="Concise rule text (<=45 words) for prompt_rule.")
    p_prop.add_argument("--why-not-deterministic", default=None, help="Required justification for prompt_rule.")
    p_prop.add_argument("--remediation", required=True, help="How to fix the pattern when caught.")
    p_prop.add_argument("--retirement-trigger", required=True, help="Condition under which to retire this rule.")

    p_ver = sub.add_parser("verify", parents=[common], help="Verify a proposed rule against bad case, valid neighbour, and repo scan.")
    p_ver.add_argument("rule_id", help="Rule ID (e.g., L-001).")
    p_ver.add_argument("--max-repo-hits", type=int, default=0, help="Max tolerated hits in existing repo (default: 0).")
    p_ver.add_argument("--include-tests", action="store_true", help="Include test files in repo scan.")

    p_app = sub.add_parser("approve", parents=[common], help="Human approval gate to activate a verified rule.")
    p_app.add_argument("rule_id", help="Rule ID (e.g., L-001).")
    p_app.add_argument("--by", required=True, help="Human reviewer approving the rule.")
    p_app.add_argument("--note", default="", help="Optional approval note.")

    p_ret = sub.add_parser("retire", parents=[common], help="Cleanly retire a rule while preserving its ID gap and examples.")
    p_ret.add_argument("rule_id", help="Rule ID (e.g., L-001).")
    p_ret.add_argument("--reason", required=True, help="Why the rule is being retired.")

    sub.add_parser("list", parents=[common], help="List all captured, verified, approved, and retired rules.")

    p_show = sub.add_parser("show", parents=[common], help="Inspect full JSON record for one rule ID.")
    p_show.add_argument("rule_id", help="Rule ID (e.g., L-001).")

    p_chk = sub.add_parser("check", parents=[common], help="Run all approved deterministic learned rules on a diff or files.")
    p_chk.add_argument("--diff", default=None, help="Unified diff file or '-' for stdin.")
    p_chk.add_argument("--files", nargs="+", default=None, help="Files to inspect directly.")

    sub.add_parser("export-prompt", parents=[common], help="Export approved prompt_rule / codebase_example entries.")

    p_lib = sub.add_parser(
        "library",
        parents=[common],
        help="Browse, inspect, and selectively enable curated optional rule packs.",
    )
    lib_sub = p_lib.add_subparsers(dest="library_command", required=True)
    lib_sub.add_parser("list", parents=[common], help="List available optional packs and rules.")

    p_lib_show = lib_sub.add_parser(
        "show",
        parents=[common],
        help="Show examples, valid neighbour, why optional, and evidence status for a pack or rule ID.",
    )
    p_lib_show.add_argument("target", help="Pack ID (e.g., network-timeouts), OPT-* rule ID, or EXCL-* ID.")

    p_lib_en = lib_sub.add_parser(
        "enable",
        parents=[common],
        help="Import, run full 3-way verification, and approve an optional pack or OPT-* rule.",
    )
    p_lib_en.add_argument("target", help="Pack ID (e.g., network-timeouts) or OPT-* rule ID.")
    p_lib_en.add_argument("--by", required=True, help="Human reviewer approving the enabled rule(s).")
    p_lib_en.add_argument(
        "--max-repo-hits",
        type=int,
        default=0,
        help="Max tolerated hits in existing repository files (default: 0).",
    )
    p_lib_en.add_argument(
        "--include-tests",
        action="store_true",
        help="Include test files in existing-repository scan.",
    )
    p_lib_en.add_argument(
        "--dry-run",
        action="store_true",
        help="Run full 3-way verification without modifying the learned-rule store.",
    )

    p_mine = sub.add_parser(
        "mine",
        parents=[common],
        help="Read-only continuous monitoring: mine local telemetry and recent git commits for recurring slop, optional packs, and stale rules.",
    )
    p_mine.add_argument(
        "--telemetry",
        default=None,
        help=f"Path to local hook/review telemetry JSONL (default: <repo-root>/{DEFAULT_TELEMETRY_REL}).",
    )
    p_mine.add_argument(
        "--commits",
        type=int,
        default=DEFAULT_MINE_COMMITS,
        help=f"Recent non-merge commits to inspect (default: {DEFAULT_MINE_COMMITS}; 0 skips git mining).",
    )
    p_mine.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help=f"Days without hits before flagging an approved rule as a retirement candidate (default: {DEFAULT_STALE_DAYS}).",
    )

    args = parser.parse_args(argv)
    store_path = Path(args.store) if args.store else default_store_path(args.repo_root)

    try:
        if args.command == "capture":
            bad_code = _read_text_arg(args.bad_code, args.bad_file, "bad-code")
            valid_code = _read_text_arg(args.valid_code, args.valid_file, "valid-code")
            entry = capture_pattern(
                store_path,
                title=args.title,
                bad_example=bad_code,
                desired_outcome=args.desired,
                valid_neighbouring_case=valid_code,
                why_it_matters=args.why,
                file_glob=args.file_glob,
                source_context=args.context,
            )
            suggestion = suggest_prevention(entry)
            payload = {"entry": entry, "suggestion": suggestion}
            if args.emit_json:
                print(json.dumps(payload, indent=2))
            else:
                print(f"Captured {entry['id']}: {entry['title']} (status: {entry['status']})")
                print(f"Recommended layer: {suggestion['recommended_layer']}")
                if suggestion["candidate_pattern"]:
                    print(f"Candidate pattern: {suggestion['candidate_pattern']}")
                print(f"Next step: {suggestion['next_step']}")
            return 0

        if args.command == "suggest":
            data = load_store(store_path)
            entry = _find_rule(data, args.rule_id)
            suggestion = suggest_prevention(entry)
            if args.emit_json:
                print(json.dumps(suggestion, indent=2))
            else:
                print(f"{entry['id']} ({entry['title']}): recommended layer = {suggestion['recommended_layer']}")
                print(f"Reason: {suggestion['reason']}")
                if suggestion["candidate_pattern"]:
                    print(f"Candidate pattern: {suggestion['candidate_pattern']}")
                print(f"Next: {suggestion['next_step']}")
            return 0

        if args.command == "propose":
            entry = propose_prevention(
                store_path,
                args.rule_id,
                layer=args.layer,
                remediation=args.remediation,
                retirement_trigger=args.retirement_trigger,
                severity=args.severity,
                file_glob=args.file_glob,
                pattern=args.pattern,
                match_mode=args.match_mode,
                canonical_path=args.canonical_path,
                rule_text=args.rule_text,
                why_not_deterministic=args.why_not_deterministic,
            )
            if args.emit_json:
                print(json.dumps(entry, indent=2))
            else:
                print(
                    f"Proposed {entry['id']} ({entry['proposal']['layer']}). "
                    f"Next: anti-slop-learn verify {entry['id']}"
                )
            return 0

        if args.command == "verify":
            entry = verify_rule(
                store_path,
                args.rule_id,
                repo_root=args.repo_root,
                max_repo_hits=args.max_repo_hits,
                include_tests_in_scan=args.include_tests,
            )
            verif = entry["verification"]
            if args.emit_json:
                print(json.dumps(entry, indent=2))
            else:
                status_lbl = "PASSED" if verif["passed"] else "FAILED"
                print(f"Verification {status_lbl} for {entry['id']} ({entry['title']}):")
                if verif["mechanical"]:
                    print(f"  1. Bad case caught:       {verif['bad_case_caught']} ({verif['bad_case_hits']} hit(s))")
                    print(f"  2. Valid neighbour clean: {verif['valid_neighbour_clean']} ({verif['valid_neighbour_hits']} hit(s))")
                    print(
                        f"  3. Repo scan clean:       {verif['repo_scan_hits']}/{verif['max_repo_hits']} hits "
                        f"across {verif['repo_scan_files']} file(s)"
                    )
                    for sample in verif["repo_sample_hits"]:
                        print(f"     - {sample}")
                for note in verif["notes"]:
                    print(f"  {note}")
                if verif["passed"]:
                    print(f"Next (human gate): anti-slop-learn approve {entry['id']} --by <your-name>")
            return 0 if verif["passed"] else 1

        if args.command == "approve":
            entry = approve_rule(
                store_path,
                args.rule_id,
                approved_by=args.by,
                note=args.note,
            )
            if args.emit_json:
                print(json.dumps(entry, indent=2))
            else:
                print(
                    f"Approved {entry['id']} ({entry['title']}) by {entry['approval']['approved_by']}. "
                    "Active immediately for diff/review enforcement."
                )
            return 0

        if args.command == "retire":
            entry = retire_rule(store_path, args.rule_id, reason=args.reason)
            if args.emit_json:
                print(json.dumps(entry, indent=2))
            else:
                print(
                    f"Retired {entry['id']} ({entry['title']}). "
                    "Rule is no longer enforced; regression examples and ID gap are preserved."
                )
            return 0

        if args.command == "list":
            data = load_store(store_path)
            if args.emit_json:
                print(json.dumps(data, indent=2))
            else:
                print(_format_rule_list(data))
            return 0

        if args.command == "show":
            data = load_store(store_path)
            entry = _find_rule(data, args.rule_id)
            print(json.dumps(entry, indent=2))
            return 0

        if args.command == "check":
            if args.diff is not None:
                if args.diff == "-":
                    diff_text = sys.stdin.read()
                else:
                    try:
                        diff_text = Path(args.diff).read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError) as exc:
                        raise LearnError(f"Failed to read --diff {args.diff}: {exc}") from exc
                res = check_learned_rules_in_diff(
                    diff_text,
                    store_path,
                    repo_root=args.repo_root,
                    require_exists=args.store is not None,
                )
            elif args.files:
                res = check_learned_rules_in_files(
                    args.files,
                    store_path,
                    repo_root=args.repo_root,
                    require_exists=args.store is not None,
                )
            else:
                raise LearnError("Provide --diff <file|-> or --files <path...>.")
            if args.emit_json:
                print(json.dumps(res, indent=2))
            elif res["errors"] or res["warnings"]:
                print(_dc._format_human(res), file=sys.stderr)
            return 0 if res["ok"] else 1

        if args.command == "export-prompt":
            rendered = export_approved_prompt_rules(store_path)
            if args.emit_json:
                print(json.dumps({"markdown": rendered}, indent=2))
            elif rendered:
                print(rendered, end="")
            else:
                print("No approved prompt_rule or codebase_example entries.")
            return 0

        if args.command == "library":
            if args.library_command == "list":
                summary = list_library_catalog()
                if args.emit_json:
                    print(json.dumps(summary, indent=2))
                else:
                    print(_format_library_list(summary))
                return 0

            if args.library_command == "show":
                resolved = show_library_item(args.target)
                if args.emit_json:
                    print(json.dumps(resolved, indent=2))
                else:
                    print(_format_library_show(resolved))
                return 0

            if args.library_command == "enable":
                res = enable_library_rules(
                    store_path,
                    args.target,
                    approved_by=args.by,
                    repo_root=args.repo_root,
                    max_repo_hits=args.max_repo_hits,
                    include_tests_in_scan=args.include_tests,
                    dry_run=args.dry_run,
                )
                if args.emit_json:
                    print(json.dumps(res, indent=2))
                else:
                    print(_format_library_enable(res))
                return 0 if res["ok"] else 1

        if args.command == "mine":
            report = mine_patterns(
                args.repo_root,
                store_path=store_path,
                telemetry_path=args.telemetry,
                commits=args.commits,
                stale_days=args.stale_days,
            )
            if args.emit_json:
                print(json.dumps(report, indent=2))
            else:
                print(_format_mine_report(report))
            return 0

    except LearnError as exc:
        if args.emit_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
