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
import io
import json
from pathlib import Path
import re
import sys
import tokenize
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from gates import diff_check as _dc  # noqa: E402


SCHEMA_VERSION = 1
DEFAULT_STORE_REL = ".anti-slop/learned/rules.json"
VALID_LAYERS = ("deterministic_check", "codebase_example", "prompt_rule")
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


def _should_ignore_code_comments(
    bad_example: str,
    compiled: re.Pattern[str],
    match_mode: str,
) -> bool:
    """Ignore comments on code scans unless the captured bad example itself targets a comment."""
    stripped_py = _strip_py_comments_preserve_lines(bad_example)
    stripped_both = _strip_c_like_comments_preserve_lines(stripped_py)
    return bool(_find_pattern_hits_in_text(stripped_both, compiled, match_mode))


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
            captured["bad_example"], compiled, proposal["match_mode"]
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
            str(captured.get("bad_example") or ""), compiled, match_mode
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

    except LearnError as exc:
        if args.emit_json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
