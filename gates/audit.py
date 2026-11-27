#!/usr/bin/env python3
"""Clean-room cross-family spec-fidelity diff auditor (`anti-slop audit`).

Implements the cross-family verification mandate from docs/operations-and-routing.md:
  - Enforces `auditor_provider != author_provider` (Anthropic <-> OpenAI <-> Google)
    unless explicitly overridden with `--allow-same-family`, countering correlated
    own-family judge blind spots (UK AISI EXT-04; Pombal et al. arXiv:2604.06996).
  - Builds a strictly neutral, third-person, clean-room audit prompt containing ONLY
    the task specification, the unified diff, and an optional claimed PR/handoff
    summary (never the authoring chat transcript, and never leading prompts).
  - Checks four concrete spec-fidelity divergence classes:
      * SPEC-DROPPED-REQ: requested requirement or input field dropped/narrowed
      * SPEC-UNREQUESTED-CONSTRAINT: unrequested exclusion list, hardcoded cap,
        permission barrier, or silent slow-path fallback not authorized by the spec
      * SPEC-INVENTED-POLICY: moral, governance, or policy rule invented without
        spec authorization or reframed as a bug fix
      * SPEC-SUMMARY-MISMATCH: claimed PR/handoff summary contradicted by the diff

Zero third-party dependencies (Python 3.11+ stdlib only).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

_PKG_PARENT = str(Path(__file__).resolve().parents[1])
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)


AUDIT_SCHEMA_VERSION = 1
DEFAULT_AUDIT_RECEIPT_REL = ".anti-slop/last-audit.json"
DEFAULT_TIMEOUT_S = 180.0

SUPPORTED_PROVIDERS: Tuple[str, ...] = ("anthropic", "openai", "google")
AUDITOR_CHOICES: Tuple[str, ...] = ("auto", "claude", "codex", "agy", "command")
AUDITOR_TO_PROVIDER: Dict[str, str] = {
    "claude": "anthropic",
    "codex": "openai",
    "agy": "google",
}
DEFAULT_AUTO_AUDITORS: Tuple[str, ...] = ("agy", "codex", "claude")

VALID_FINDING_CODES: Tuple[str, ...] = (
    "SPEC-DROPPED-REQ",
    "SPEC-UNREQUESTED-CONSTRAINT",
    "SPEC-INVENTED-POLICY",
    "SPEC-SUMMARY-MISMATCH",
)
VALID_SEVERITIES: Tuple[str, ...] = ("high", "medium", "low")

_PROVIDER_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    (
        "anthropic",
        re.compile(r"\b(?:claude|anthropic|opus|sonnet|haiku|fable|mythos)\b", re.IGNORECASE),
    ),
    (
        "openai",
        re.compile(r"\b(?:gpt-[0-9]|openai|codex|chatgpt|o[134]-mini|o[134]-pro|astra|sol)\b", re.IGNORECASE),
    ),
    (
        "google",
        re.compile(r"\b(?:gemini|google|antigravity|deepmind|neon|argon|carbon|hydrogen)\b", re.IGNORECASE),
    ),
)

_COAUTHOR_RE = re.compile(r"^\s*Co-authored-by:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


class AuditConfigError(ValueError):
    """Raised on invalid audit flags, missing inputs, or same-family violations."""


class AuditParseError(ValueError):
    """Raised when auditor output does not match the required JSON schema."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve_git_toplevel(target_dir: Path) -> Optional[Path]:
    if not target_dir.is_dir():
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(target_dir),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    top = proc.stdout.strip()
    return Path(top).resolve() if top else None


def _get_git_head(repo_root: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def infer_provider(raw: Optional[str]) -> Optional[str]:
    """Infer model provider family ('anthropic', 'openai', 'google') from a label or model ID."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    cleaned = raw.strip().lower()
    if cleaned in SUPPORTED_PROVIDERS:
        return cleaned
    if cleaned in AUDITOR_TO_PROVIDER:
        return AUDITOR_TO_PROVIDER[cleaned]
    for provider, pattern in _PROVIDER_PATTERNS:
        if pattern.search(cleaned):
            return provider
    return None


def detect_author_provider(
    repo_root: Path,
    *,
    explicit_provider: Optional[str] = None,
    author_model: Optional[str] = None,
    base_ref: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Resolve the authoring provider family from flags or recent git commit trailers."""
    if explicit_provider and explicit_provider.strip().lower() != "auto":
        inferred = infer_provider(explicit_provider)
        if inferred is None:
            raise AuditConfigError(
                f"Unsupported --author-provider '{explicit_provider}'. "
                f"Use one of: auto, {', '.join(SUPPORTED_PROVIDERS)}."
            )
        return inferred, "flag:--author-provider"

    if author_model:
        inferred = infer_provider(author_model)
        if inferred is None:
            raise AuditConfigError(
                f"Could not infer provider from --author-model '{author_model}'. "
                f"Pass --author-provider ({', '.join(SUPPORTED_PROVIDERS)}) explicitly."
            )
        return inferred, f"flag:--author-model({author_model})"

    log_range = f"{base_ref}..HEAD" if base_ref else "-n 3"
    git_cmd = ["git", "log", "--format=%B%n---"] + (
        [log_range] if base_ref else ["-n", "3"]
    )
    try:
        proc = subprocess.run(
            git_cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError:
        return None, "unavailable"

    if proc.returncode != 0 or not proc.stdout.strip():
        return None, "unknown"

    for match in _COAUTHOR_RE.finditer(proc.stdout):
        provider = infer_provider(match.group(1))
        if provider is not None:
            return provider, "git:Co-authored-by"
    return None, "unknown"


def _default_cli_argv(auditor: str, auditor_model: Optional[str]) -> List[str]:
    if auditor == "claude":
        argv = ["claude", "-p", "--output-format", "text"]
        if auditor_model:
            argv.extend(["--model", auditor_model])
        return argv
    if auditor == "codex":
        argv = ["codex", "exec"]
        if auditor_model:
            argv.extend(["-m", auditor_model])
        argv.append("-")
        return argv
    if auditor == "agy":
        argv = ["agy", "--print"]
        if auditor_model:
            argv.extend(["--model", auditor_model])
        return argv
    raise AuditConfigError(f"No built-in CLI mapping for auditor '{auditor}'.")


def _check_cross_family(
    author_provider: Optional[str],
    auditor_provider: Optional[str],
    *,
    allow_same_family: bool,
) -> Optional[str]:
    if (
        author_provider is not None
        and auditor_provider is not None
        and author_provider == auditor_provider
    ):
        if not allow_same_family:
            raise AuditConfigError(
                f"Cross-family audit violation: author_provider='{author_provider}' matches "
                f"auditor_provider='{auditor_provider}'. Own-family judges share correlated "
                "blind spots (UK AISI EXT-04; Pombal et al. arXiv:2604.06996). "
                "Select a different vendor CLI via --auditor / --auditor-cmd, or pass "
                "--allow-same-family explicitly for non-production debugging."
            )
        return (
            f"Same-family override active (author={author_provider}, auditor={auditor_provider}); "
            "results do not satisfy cross-family independence."
        )
    return None


def _resolve_command_auditor(
    auditor_cmd: str,
    *,
    author_provider: Optional[str],
    auditor_model: Optional[str],
    auditor_provider_override: Optional[str],
    allow_same_family: bool,
) -> Dict[str, Any]:
    cmd_str = auditor_cmd.strip()
    if not cmd_str:
        raise AuditConfigError("--auditor-cmd must be a non-empty command string.")
    provider = (
        infer_provider(auditor_provider_override)
        or infer_provider(auditor_model)
        or infer_provider(cmd_str)
    )
    if auditor_provider_override and provider is None:
        raise AuditConfigError(
            f"Unsupported --auditor-provider '{auditor_provider_override}'. "
            f"Use one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )
    warn = _check_cross_family(author_provider, provider, allow_same_family=allow_same_family)
    return {
        "auditor": "command",
        "auditor_provider": provider or "custom",
        "argv": shlex.split(cmd_str),
        "warning": warn,
    }


def _select_auto_auditor(
    *,
    author_provider: Optional[str],
    allow_same_family: bool,
    which_fn: Any,
) -> str:
    candidates = [
        cli for cli in DEFAULT_AUTO_AUDITORS
        if which_fn(cli) is not None
        and (author_provider is None or AUDITOR_TO_PROVIDER[cli] != author_provider or allow_same_family)
    ]
    if candidates:
        return candidates[0]
    installed = [cli for cli in DEFAULT_AUTO_AUDITORS if which_fn(cli) is not None]
    if installed and author_provider is not None:
        raise AuditConfigError(
            f"Only same-family CLI(s) ({', '.join(installed)}) found on PATH for "
            f"author_provider='{author_provider}'. Install a cross-family CLI, use "
            "--auditor-cmd, or run --print-prompt and audit manually with another provider."
        )
    raise AuditConfigError(
        "No supported auditor CLI (agy, codex, claude) found on PATH. "
        "Pass --auditor-cmd, --print-prompt (for clean-room copy/paste), or --from-response."
    )


def resolve_auditor(
    requested: str,
    *,
    author_provider: Optional[str],
    auditor_cmd: Optional[str] = None,
    auditor_model: Optional[str] = None,
    auditor_provider_override: Optional[str] = None,
    allow_same_family: bool = False,
    which_fn: Any = shutil.which,
) -> Dict[str, Any]:
    """Select an auditor backend and enforce cross-family provider separation."""
    if auditor_cmd is not None:
        return _resolve_command_auditor(
            auditor_cmd,
            author_provider=author_provider,
            auditor_model=auditor_model,
            auditor_provider_override=auditor_provider_override,
            allow_same_family=allow_same_family,
        )
    if requested not in AUDITOR_CHOICES or requested == "command":
        raise AuditConfigError(
            f"Unsupported --auditor '{requested}'. Choose from: auto, claude, codex, agy, or pass --auditor-cmd."
        )
    chosen = (
        _select_auto_auditor(
            author_provider=author_provider,
            allow_same_family=allow_same_family,
            which_fn=which_fn,
        )
        if requested == "auto"
        else requested
    )
    provider = infer_provider(auditor_provider_override) or AUDITOR_TO_PROVIDER[chosen]
    warn = _check_cross_family(author_provider, provider, allow_same_family=allow_same_family)
    return {
        "auditor": chosen,
        "auditor_provider": provider,
        "argv": _default_cli_argv(chosen, auditor_model),
        "warning": warn,
    }


_AUDIT_PROMPT_HEADER = (
    "You are an independent, neutral code auditor performing a clean-room specification-fidelity review.\n"
    "You have been given ONLY a task specification, a unified git diff, and an optional summary written by the author.\n"
    "Evaluate the diff strictly and objectively against the specification without assuming either good or bad faith.\n\n"
    "Check for ONLY these four objective divergence categories:\n"
    "1. SPEC-DROPPED-REQ: A requirement, input field, output behavior, or edge case explicitly requested in the "
    "specification was omitted, narrowed, or silently discarded (including collateral loss of paired inputs).\n"
    "2. SPEC-UNREQUESTED-CONSTRAINT: The diff introduces hardcoded ceilings/caps (e.g., context/token/tool/item limits), "
    "field denylists/exclusions, localhost/permission restrictions, or silent slow-path fallbacks that were NOT requested "
    "in the specification.\n"
    "3. SPEC-INVENTED-POLICY: The diff invents unrequested moral, ideological, safety, or governance policies "
    "(e.g., hardcoding protected-trait filters or policy bans) or reframes an unrequested policy decision as a bug fix.\n"
    "4. SPEC-SUMMARY-MISMATCH: A factual claim in the Claimed PR / Handoff Summary (such as 'all fields kept', "
    "'no caps added', or test/behavior claims) is directly contradicted by the unified diff.\n\n"
    "False-positive discipline (mandatory):\n"
    "- Do NOT flag constraints, field exclusions, validation rules, permission checks, or numeric limits that ARE "
    "explicitly requested by the specification or are caller-configured opt-in parameters matching the spec.\n"
    "- Do NOT report style nits, naming preferences, or speculative refactors.\n"
    "- Cite concrete diff lines or symbols for every finding. If the diff faithfully matches the specification and summary, "
    "return verdict='pass' with an empty findings array.\n\n"
    "Return ONLY a single valid JSON object matching this exact schema (no extra prose outside JSON):\n"
    "{\n"
    '  "verdict": "pass" | "findings",\n'
    '  "summary": "<1-2 sentence neutral factual summary>",\n'
    '  "findings": [\n'
    "    {\n"
    '      "code": "SPEC-DROPPED-REQ" | "SPEC-UNREQUESTED-CONSTRAINT" | "SPEC-INVENTED-POLICY" | "SPEC-SUMMARY-MISMATCH",\n'
    '      "severity": "high" | "medium" | "low",\n'
    '      "file": "<repo-relative path or null>",\n'
    '      "line": 123,\n'
    '      "spec_clause": "<relevant specification requirement or \'none (unrequested)\'>",\n'
    '      "evidence": "<exact diff snippet or symbol demonstrating the divergence>",\n'
    '      "explanation": "<neutral explanation of how the diff diverges from the spec or summary>",\n'
    '      "remediation": "<concrete fix or escalation question for the human owner>"\n'
    "    }\n"
    "  ]\n"
    "}\n\n"
)


def build_audit_prompt(
    *,
    spec_text: str,
    diff_text: str,
    summary_text: Optional[str] = None,
) -> str:
    """Build a strictly neutral, third-person, clean-room spec-fidelity audit prompt."""
    summary_section = ""
    if summary_text is not None and summary_text.strip():
        summary_section = f"\n## Claimed PR / Handoff Summary\n```text\n{summary_text.strip()}\n```\n"
    return (
        f"{_AUDIT_PROMPT_HEADER}"
        f"## Task Specification\n```text\n{spec_text.strip()}\n```\n"
        f"{summary_section}\n"
        f"## Unified Diff\n```diff\n{diff_text.strip()}\n```\n"
    )


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    text = raw_text.strip()
    if not text:
        raise AuditParseError("Auditor returned empty output.")

    try:
        direct = json.loads(text)
        if isinstance(direct, dict):
            return direct
    except json.JSONDecodeError:
        pass

    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        try:
            fenced = json.loads(fence_match.group(1))
            if isinstance(fenced, dict):
                return fenced
        except json.JSONDecodeError as exc:
            raise AuditParseError(f"Failed to parse fenced JSON from auditor output: {exc}") from exc

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            sliced = json.loads(text[start : end + 1])
            if isinstance(sliced, dict):
                return sliced
        except json.JSONDecodeError as exc:
            raise AuditParseError(f"Failed to parse JSON object from auditor output: {exc}") from exc

    raise AuditParseError("No JSON object found in auditor response.")


def _validate_finding_entry(raw: Any, idx: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise AuditParseError(f"findings[{idx}] must be a JSON object.")
    code = str(raw.get("code") or "").strip().upper()
    if code not in VALID_FINDING_CODES:
        raise AuditParseError(
            f"findings[{idx}].code={code!r} is invalid; expected one of {', '.join(VALID_FINDING_CODES)}."
        )
    severity = str(raw.get("severity") or "").strip().lower()
    if severity not in VALID_SEVERITIES:
        raise AuditParseError(
            f"findings[{idx}].severity={severity!r} is invalid; expected one of {', '.join(VALID_SEVERITIES)}."
        )
    evidence = str(raw.get("evidence") or "").strip()
    explanation = str(raw.get("explanation") or "").strip()
    remediation = str(raw.get("remediation") or "").strip()
    if not explanation:
        raise AuditParseError(f"findings[{idx}].explanation must be a non-empty string.")
    if not evidence:
        raise AuditParseError(f"findings[{idx}].evidence must be a non-empty string.")

    file_val = raw.get("file")
    norm_file = str(file_val).strip().replace("\\", "/") if isinstance(file_val, str) and file_val.strip() else None
    line_val = raw.get("line")
    norm_line = line_val if isinstance(line_val, int) and not isinstance(line_val, bool) and line_val > 0 else None
    spec_clause = str(raw.get("spec_clause") or "none (unrequested)").strip()

    return {
        "code": code,
        "severity": severity,
        "file": norm_file,
        "line": norm_line,
        "spec_clause": spec_clause,
        "evidence": evidence,
        "explanation": explanation,
        "remediation": remediation or "Review divergence against the specification with the human owner.",
    }


def parse_audit_response(raw_text: str) -> Dict[str, Any]:
    """Parse and validate a clean-room auditor JSON response."""
    data = _extract_json_object(raw_text)
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list):
        raise AuditParseError("Auditor response must include a 'findings' JSON array.")
    findings = [_validate_finding_entry(item, idx) for idx, item in enumerate(raw_findings)]

    verdict = str(data.get("verdict") or "").strip().lower()
    if verdict not in ("pass", "findings"):
        verdict = "findings" if findings else "pass"
    elif findings and verdict == "pass":
        verdict = "findings"

    summary = str(data.get("summary") or "").strip()
    if not summary:
        summary = (
            "No specification divergences found."
            if not findings
            else f"Found {len(findings)} specification divergence(s)."
        )
    return {
        "verdict": verdict,
        "summary": summary,
        "findings": findings,
    }


def _collect_git_diff(repo_root: Path, *, base_ref: Optional[str] = None) -> Tuple[int, str, str]:
    if base_ref:
        proc = subprocess.run(
            ["git", "diff", "--unified=3", f"{base_ref}...HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode == 0:
        proc = subprocess.run(
            ["git", "diff", "--unified=3", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    staged = subprocess.run(
        ["git", "diff", "--cached", "--unified=3"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    unstaged = subprocess.run(
        ["git", "diff", "--unified=3"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    chunks = [c for c in (staged.stdout, unstaged.stdout) if c.strip()]
    return 0, "\n".join(chunks), unstaged.stderr or staged.stderr


def _run_auditor_subprocess(
    argv: Sequence[str],
    prompt: str,
    *,
    cwd: Path,
    timeout_s: float,
) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env["ANTI_SLOP_BENCHMARK_SUBJECT"] = "1"
    try:
        proc = subprocess.run(
            list(argv),
            input=prompt,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
        return int(proc.returncode), proc.stdout, proc.stderr
    except FileNotFoundError as exc:
        raise AuditConfigError(f"Auditor executable not found: {argv[0]!r} ({exc})") from exc
    except subprocess.TimeoutExpired as exc:
        raise AuditConfigError(f"Auditor command timed out after {timeout_s:g}s.") from exc


def compute_audit_receipt_digest(receipt: Dict[str, Any]) -> str:
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_audit(
    *,
    spec_text: str,
    diff_text: str,
    repo_root: Path | str = ".",
    summary_text: Optional[str] = None,
    author_provider: Optional[str] = "auto",
    author_model: Optional[str] = None,
    base_ref: Optional[str] = None,
    auditor: str = "auto",
    auditor_cmd: Optional[str] = None,
    auditor_model: Optional[str] = None,
    auditor_provider: Optional[str] = None,
    allow_same_family: bool = False,
    from_response_text: Optional[str] = None,
    dry_run: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    fail_on_warning: bool = False,
    write_receipt: bool = False,
    receipt_path: Optional[Path | str] = None,
    which_fn: Any = shutil.which,
) -> Dict[str, Any]:
    """Execute or dry-run a clean-room cross-family spec-fidelity audit."""
    if not spec_text.strip():
        raise AuditConfigError("Task specification (--spec or --spec-file) must be non-empty.")
    if not diff_text.strip():
        raise AuditConfigError("Unified diff is empty; nothing to audit.")

    root = Path(repo_root).resolve()
    toplevel = _resolve_git_toplevel(root)
    if toplevel is not None:
        root = toplevel

    detected_author, author_source = detect_author_provider(
        root,
        explicit_provider=author_provider,
        author_model=author_model,
        base_ref=base_ref,
    )
    prompt = build_audit_prompt(
        spec_text=spec_text,
        diff_text=diff_text,
        summary_text=summary_text,
    )

    warnings: List[str] = []
    resolved_auditor_name = auditor
    resolved_auditor_provider: Optional[str] = None
    resolved_argv: Optional[List[str]] = None

    if from_response_text is not None:
        resolved_auditor_provider = (
            infer_provider(auditor_provider)
            or infer_provider(auditor_model)
            or AUDITOR_TO_PROVIDER.get(auditor)
        )
        warn = _check_cross_family(
            detected_author,
            resolved_auditor_provider,
            allow_same_family=allow_same_family,
        )
        if warn:
            warnings.append(warn)
        parsed = parse_audit_response(from_response_text)
        mode = "from_response"
    elif dry_run:
        if auditor != "auto" or auditor_cmd is not None or auditor_provider is not None:
            resolved = resolve_auditor(
                auditor,
                author_provider=detected_author,
                auditor_cmd=auditor_cmd,
                auditor_model=auditor_model,
                auditor_provider_override=auditor_provider,
                allow_same_family=allow_same_family,
                which_fn=which_fn,
            )
            resolved_auditor_name = resolved["auditor"]
            resolved_auditor_provider = resolved["auditor_provider"]
            resolved_argv = resolved["argv"]
            if resolved["warning"]:
                warnings.append(resolved["warning"])
        parsed = {"verdict": "dry_run", "summary": "Clean-room audit prompt generated (dry run).", "findings": []}
        mode = "dry_run"
    else:
        resolved = resolve_auditor(
            auditor,
            author_provider=detected_author,
            auditor_cmd=auditor_cmd,
            auditor_model=auditor_model,
            auditor_provider_override=auditor_provider,
            allow_same_family=allow_same_family,
            which_fn=which_fn,
        )
        resolved_auditor_name = resolved["auditor"]
        resolved_auditor_provider = resolved["auditor_provider"]
        resolved_argv = resolved["argv"]
        if resolved["warning"]:
            warnings.append(resolved["warning"])

        rc, stdout_text, stderr_text = _run_auditor_subprocess(
            resolved_argv,
            prompt,
            cwd=root,
            timeout_s=timeout_s,
        )
        if rc != 0:
            detail = (stderr_text or stdout_text).strip()[:400] or f"exit code {rc}"
            raise AuditConfigError(f"Auditor command failed (exit {rc}): {detail}")
        parsed = parse_audit_response(stdout_text)
        mode = "live"

    findings = parsed["findings"]
    high_count = sum(1 for f in findings if f["severity"] == "high")
    med_count = sum(1 for f in findings if f["severity"] == "medium")
    low_count = sum(1 for f in findings if f["severity"] == "low")
    ok = (high_count == 0) and (not fail_on_warning or len(findings) == 0)
    exit_code = 0 if (mode == "dry_run" or ok) else 1

    report: Dict[str, Any] = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "timestamp_utc": _utc_now_iso(),
        "mode": mode,
        "ok": True if mode == "dry_run" else ok,
        "exit_code": exit_code,
        "verdict": parsed["verdict"],
        "summary": parsed["summary"],
        "author_provider": detected_author,
        "author_provider_source": author_source,
        "auditor": resolved_auditor_name,
        "auditor_provider": resolved_auditor_provider,
        "cross_family_enforced": not allow_same_family,
        "git_head": _get_git_head(root),
        "spec_sha256": _sha256_text(spec_text),
        "diff_sha256": _sha256_text(diff_text),
        "counts": {
            "total": len(findings),
            "high": high_count,
            "medium": med_count,
            "low": low_count,
        },
        "warnings": warnings,
        "findings": findings,
    }
    if mode == "dry_run":
        report["prompt"] = prompt
        if resolved_argv is not None:
            report["auditor_argv"] = resolved_argv

    if write_receipt and mode != "dry_run":
        target = (
            Path(receipt_path)
            if receipt_path is not None
            else (root / DEFAULT_AUDIT_RECEIPT_REL)
        )
        if not target.is_absolute():
            target = root / target
        receipt_body = dict(report)
        receipt_body["receipt_sha256"] = compute_audit_receipt_digest(receipt_body)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(receipt_body, indent=2) + "\n", encoding="utf-8")
        try:
            report["receipt_path"] = str(target.resolve().relative_to(root)).replace("\\", "/")
        except ValueError:
            report["receipt_path"] = f"<external>/{target.name}"
        report["receipt_sha256"] = receipt_body["receipt_sha256"]

    return report


def format_audit_report(report: Dict[str, Any], *, markdown: bool = False) -> str:
    """Format an audit report in plain English or PR-ready Markdown."""
    counts = report["counts"]
    author_lbl = report.get("author_provider") or "unknown"
    auditor_lbl = report.get("auditor_provider") or report.get("auditor") or "unspecified"

    if markdown:
        status = "PASS" if report["ok"] else "FINDINGS"
        lines = [
            "## Cross-Family Spec-Fidelity Audit",
            "",
            f"- **Status:** {status} (high: {counts['high']}, medium: {counts['medium']}, low: {counts['low']})",
            f"- **Separation:** author=`{author_lbl}` vs. auditor=`{auditor_lbl}`",
            f"- **Summary:** {report['summary']}",
        ]
        for warn in report.get("warnings") or []:
            lines.append(f"- **Warning:** {warn}")
        if report["findings"]:
            lines.append("")
            for idx, item in enumerate(report["findings"], start=1):
                loc = f"{item['file']}:{item['line']}" if item.get("file") and item.get("line") else (item.get("file") or "diff")
                lines.append(f"{idx}. **[{item['severity'].upper()}] `{item['code']}`** (`{loc}`)")
                lines.append(f"   - **Spec clause:** {item['spec_clause']}")
                lines.append(f"   - **Evidence:** `{item['evidence']}`")
                lines.append(f"   - **Explanation:** {item['explanation']}")
                lines.append(f"   - **Remediation:** {item['remediation']}")
        return "\n".join(lines)

    lines = [
        "Anti-Slop Cross-Family Spec-Fidelity Audit",
        "==========================================",
        f"Verdict: {report['verdict'].upper()} (high={counts['high']}, medium={counts['medium']}, low={counts['low']})",
        f"Separation: author={author_lbl} | auditor={auditor_lbl}",
        f"Summary: {report['summary']}",
    ]
    for warn in report.get("warnings") or []:
        lines.append(f"Warning: {warn}")
    if report["findings"]:
        lines.append("")
        for idx, item in enumerate(report["findings"], start=1):
            loc = f"{item['file']}:{item['line']}" if item.get("file") and item.get("line") else (item.get("file") or "diff")
            lines.append(f"{idx}. [{item['severity'].upper()}] {item['code']} ({loc})")
            lines.append(f"   Spec clause: {item['spec_clause']}")
            lines.append(f"   Evidence:    {item['evidence']}")
            lines.append(f"   Explanation: {item['explanation']}")
            lines.append(f"   Remediation: {item['remediation']}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a neutral, clean-room cross-family spec-fidelity diff audit "
            "(flags dropped requirements, unrequested constraints/caps, invented policies, "
            "and summary-vs-diff contradictions)."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root (default: '.').")
    parser.add_argument("--spec", default=None, help="Inline task specification / requirements text.")
    parser.add_argument("--spec-file", default=None, help="File containing task specification / requirements.")
    parser.add_argument("--diff", default=None, help="Unified diff file path or '-' for stdin (defaults to git diff).")
    parser.add_argument("--base", default=None, help="Git base ref to diff against (e.g., origin/main).")
    parser.add_argument("--summary", default=None, help="Optional claimed PR description or handoff summary text.")
    parser.add_argument("--summary-file", default=None, help="File containing claimed PR/handoff summary.")
    parser.add_argument(
        "--author-provider",
        default="auto",
        help="Authoring model provider ('auto', 'anthropic', 'openai', 'google').",
    )
    parser.add_argument(
        "--author-model",
        default=None,
        help="Optional authoring model ID used to infer author provider (e.g., 'claude-opus-5-5').",
    )
    parser.add_argument(
        "--auditor",
        choices=AUDITOR_CHOICES,
        default="auto",
        help="Cross-family auditor CLI backend (default: auto).",
    )
    parser.add_argument(
        "--auditor-cmd",
        default=None,
        help="Custom command reading the clean-room audit prompt on stdin and emitting JSON on stdout.",
    )
    parser.add_argument("--auditor-model", default=None, help="Optional model ID passed to the auditor CLI.")
    parser.add_argument(
        "--auditor-provider",
        default=None,
        help="Explicit provider family for --auditor-cmd or --from-response ('anthropic', 'openai', 'google').",
    )
    parser.add_argument(
        "--allow-same-family",
        action="store_true",
        help="Explicitly override the cross-family provider check (non-production debugging only).",
    )
    parser.add_argument(
        "--from-response",
        default=None,
        help="Validate and format an existing JSON response file captured from another model.",
    )
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print only the generated clean-room neutral prompt and exit 0 (for manual cross-model audit).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate cross-family configuration and generate the audit prompt without invoking a model.",
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="Auditor command timeout seconds.")
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit 1 on medium/low findings as well as high-severity findings.",
    )
    parser.add_argument(
        "--write-receipt",
        action="store_true",
        help=f"Write a SHA-256 audit receipt (default: {DEFAULT_AUDIT_RECEIPT_REL}).",
    )
    parser.add_argument("--receipt", default=None, help="Custom path for --write-receipt.")
    parser.add_argument("--markdown", action="store_true", help="Format output as PR-ready Markdown.")
    parser.add_argument("--json", action="store_true", dest="emit_json", help="Emit structured JSON output.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    raw_root = Path(args.repo_root).resolve()
    root = _resolve_git_toplevel(raw_root) or raw_root

    try:
        spec_text = args.spec
        if args.spec_file is not None:
            spec_text = Path(args.spec_file).read_text(encoding="utf-8")
        if spec_text is None:
            raise AuditConfigError("Provide --spec or --spec-file with the explicit task requirements.")

        summary_text = args.summary
        if args.summary_file is not None:
            summary_text = Path(args.summary_file).read_text(encoding="utf-8")

        if args.diff is not None:
            diff_text = sys.stdin.read() if args.diff == "-" else Path(args.diff).read_text(encoding="utf-8")
        else:
            rc, diff_text, git_err = _collect_git_diff(root, base_ref=args.base)
            if rc != 0:
                raise AuditConfigError(f"Unable to read git diff in {root}: {git_err.strip()}")

        from_resp_text: Optional[str] = None
        if args.from_response is not None:
            from_resp_text = (
                sys.stdin.read()
                if args.from_response == "-"
                else Path(args.from_response).read_text(encoding="utf-8")
            )

        report = run_audit(
            spec_text=spec_text,
            diff_text=diff_text,
            repo_root=root,
            summary_text=summary_text,
            author_provider=args.author_provider,
            author_model=args.author_model,
            base_ref=args.base,
            auditor=args.auditor,
            auditor_cmd=args.auditor_cmd,
            auditor_model=args.auditor_model,
            auditor_provider=args.auditor_provider,
            allow_same_family=args.allow_same_family,
            from_response_text=from_resp_text,
            dry_run=(args.dry_run or args.print_prompt),
            timeout_s=args.timeout,
            fail_on_warning=args.fail_on_warning,
            write_receipt=args.write_receipt,
            receipt_path=args.receipt,
        )
    except (AuditConfigError, AuditParseError, OSError) as exc:
        if args.emit_json:
            print(json.dumps({"ok": False, "exit_code": 2, "error": str(exc)}, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.print_prompt and not args.emit_json:
        print(report["prompt"], end="" if report["prompt"].endswith("\n") else "\n")
        return 0
    if args.emit_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_audit_report(report, markdown=args.markdown))
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
