#!/usr/bin/env python3
"""Isolated local benchmark runner for anti-slop comparative experiments.

Deliberate manual execution tool — never invoked by scripts/check.py or CI.
Runs each (model, case, condition) in a fresh temporary workspace outside this
repository so repo maintenance files (AGENTS.md, graders, acceptance checks,
prior outputs) never contaminate benchmark subjects.

Stdlib Python only (zero external dependencies).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.graders import inspect_text_constraints  # noqa: E402
from scripts import benchmark  # noqa: E402


BASELINE_INSTRUCTION = (
    "Follow the user's request directly using only the files provided in this workspace.\n"
)

GATED_STRUCTURAL_INSTRUCTION = (
    BASELINE_INSTRUCTION
    + "\nAfter each stage, an automated anti-slop diff and structural review gate inspects your workspace changes. "
    + "If it reports blocking shortcuts or compounding slop risks, resolve every reported finding before finalizing.\n"
)

DEFAULT_MODELS: dict[str, dict[str, Any]] = {
    "gpt-6.2-astra": {
        "provider": "openai",
        "id": "gpt-6.2-astra",
        "reasoning": "medium",
        "harness": "codex-cli",
        "cli": "codex",
    },
    "gpt-6.2-sol": {
        "provider": "openai",
        "id": "gpt-6.2-sol",
        "reasoning": "medium",
        "harness": "codex-cli",
        "cli": "codex",
    },
    "claude-opus-5-5": {
        "provider": "anthropic",
        "id": "claude-opus-5-5",
        "reasoning": "medium",
        "harness": "claude-code",
        "cli": "claude",
    },
    "claude-fable-5-2": {
        "provider": "anthropic",
        "id": "claude-fable-5-2",
        "reasoning": "high",
        "harness": "claude-code",
        "cli": "claude",
    },
    "gemini-4-neon": {
        "provider": "google",
        "id": "gemini-4-neon",
        "reasoning": "high",
        "harness": "antigravity-cli",
        "cli": "agy",
        "cli_model": "gemini-4-neon-high",
    },
}

DEFAULT_CONDITIONS = ("baseline", "core-rules-v0.1.0", "core-rules-v0.2.0")

# Exact primary fixture file and required symbol per coding case.
CODING_PRIMARY_FIXTURES: dict[str, str] = {
    "C1": "benchmarks/sources/c1-counts.py",
    "C2": "benchmarks/sources/c2-invoice.py",
    "T1": "benchmarks/sources/t1-cache.py",
    "P1": "benchmarks/sources/p1-service.py",
}

CODING_REQUIRED_SYMBOLS: dict[str, str] = {
    "C1": "def total_by_category",
    "C2": "def invoice_total",
    "T1": "class TTLCache",
    "P1": "def verify_session_token",
}

FROZEN_MODEL_VERSIONS: dict[str, str] = {
    "gpt-6.2-astra": "gpt-6.2-astra (codex-cli requested; exact snapshot id unavailable in JSON output)",
    "gpt-6.2-sol": "gpt-6.2-sol (codex-cli requested; exact snapshot id unavailable in JSON output)",
    "claude-opus-5-5": "claude-opus-5-5 (claude-code firstParty canonical)",
    "claude-fable-5-2": "claude-fable-5-2 (claude-code firstParty canonical)",
    "gemini-4-neon": "gemini-4-neon-high (antigravity-cli Gemini 4 Neon High)",
}

READONLY_FIXTURES: dict[str, str] = {
    "T1": "benchmarks/sources/t1-test-visible.py",
    "P1": "benchmarks/sources/p1-legacy-auth.py",
}

WORKSPACE_GRADER_CASES: dict[str, str] = {
    "M1": "benchmarks/graders/grade_m1.py",
    "M2": "benchmarks/graders/grade_m2.py",
    "B2": "benchmarks/graders/grade_b2.py",
    "RW1": "benchmarks/graders/grade_rw1.py",
    "RW2": "benchmarks/graders/grade_rw2.py",
    "RW3": "benchmarks/graders/grade_rw3.py",
    "SE1": "benchmarks/graders/grade_se1.py",
    "SE3": "benchmarks/graders/grade_se3.py",
    "SE4": "benchmarks/graders/grade_se4.py",
    "EV1": "benchmarks/graders/grade_ev1.py",
    "EV2": "benchmarks/graders/grade_ev2.py",
    "CM1": "benchmarks/graders/grade_cm1.py",
    "CM2": "benchmarks/graders/grade_cm2.py",
}

CM1_CONDITION_VARIANTS: dict[str, str] = {
    "no-comments": "no_comments",
    "invariant-comments": "invariant_comments",
    "comment-traps": "comment_traps",
}

COMMENT_ABLATION_CASES: dict[str, dict[str, Any]] = {
    "CM1": {
        "source_root": "benchmarks/sources/cm1_comment_ablation",
        "pinned_files": ("webhooks.py",),
    },
    "CM2": {
        "source_root": "benchmarks/sources/cm2_multifile_comments",
        "pinned_files": (
            "models.py",
            "storage.py",
            "dedupe.py",
            "retry.py",
            "worker.py",
            "api.py",
        ),
    },
}

READONLY_CASES: frozenset[str] = frozenset({"S1", "S2", "D1", "W3", "RW4", "RW5", "RW6", "SE2"})

TEXT_WORD_CAPS: dict[str, dict[int, int]] = {
    "B2": {2: 90},
    "D1": {1: 140, 2: 75},
    "W3": {1: 160, 2: 85},
    "RW3": {2: 75},
    "RW4": {1: 130, 2: 65},
    "RW5": {2: 140},
    "RW6": {1: 135, 2: 75},
    "SE1": {2: 120},
    "SE2": {2: 115},
    "SE3": {2: 120},
    "SE4": {2: 120},
}

STRICT_CREDIBILITY_TEXT_CASES: frozenset[str] = frozenset({"SE1", "SE2", "SE3", "SE4"})

FABLE_DOWNGRADE_RE = re.compile(
    r"^claude-opus-(?:4[-.]8(?:[-.]\S*)?|5(?:-(?:20\d{6}|preview\S*))?)$",
    re.IGNORECASE,
)

_PYTHON_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_AGY_CONV_RE = re.compile(r"Created conversation ([0-9a-f-]{36})")
_AGY_LABEL_RE = re.compile(r'Propagating selected model override to backend: label="([^"]+)"')
_WRITE_LOCK = threading.Lock()

DEFAULT_CHILD_MAX_RSS_MB = 1536
DEFAULT_RSS_POLL_INTERVAL_S = 2.0
DEFAULT_MAX_WORKERS = 3


def _collect_descendant_and_pgid_processes(root_pid: int) -> list[tuple[int, int]]:
    """Return `(pid, rss_kib)` for processes in `root_pid`'s PGID or PPID subtree (excluding `root_pid`)."""
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,pgid=,rss="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []

    children_by_ppid: dict[int, list[int]] = {}
    rss_by_pid: dict[int, int] = {}
    pgid_matches: set[int] = set()
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
            pgid = int(parts[2])
            rss_kib = int(parts[3])
        except ValueError:
            continue
        children_by_ppid.setdefault(ppid, []).append(pid)
        rss_by_pid[pid] = rss_kib
        if pgid == root_pid and pid != root_pid:
            pgid_matches.add(pid)

    found: set[int] = set(pgid_matches)
    stack = list(children_by_ppid.get(root_pid, ()))
    while stack:
        cur = stack.pop()
        if cur == root_pid or cur in found:
            continue
        found.add(cur)
        stack.extend(children_by_ppid.get(cur, ()))

    return [(pid, rss_by_pid.get(pid, 0)) for pid in sorted(found)]


def _reap_process_tree(root_pid: int) -> None:
    """Force-kill the entire process group and any escaped descendants of `root_pid`."""
    descendants = [pid for pid, _ in _collect_descendant_and_pgid_processes(root_pid)]
    if hasattr(os, "killpg"):
        try:
            os.killpg(root_pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    for pid in descendants:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        os.kill(root_pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _run_stage_subprocess(
    cmd: list[str],
    *,
    cwd: Path | str,
    env: dict[str, str] | None,
    timeout_seconds: float,
    child_max_rss_mb: int = DEFAULT_CHILD_MAX_RSS_MB,
    rss_poll_interval_s: float = DEFAULT_RSS_POLL_INTERVAL_S,
) -> subprocess.CompletedProcess[str]:
    """Run a CLI or grader subprocess in its own process group with a child-RSS watchdog."""
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    stop_event = threading.Event()
    watchdog_notes: list[str] = []
    watchdog_thread: threading.Thread | None = None

    if child_max_rss_mb > 0:
        limit_kib = child_max_rss_mb * 1024

        def _watch_rss() -> None:
            while not stop_event.wait(rss_poll_interval_s):
                if proc.poll() is not None:
                    return
                for pid, rss_kib in _collect_descendant_and_pgid_processes(proc.pid):
                    if rss_kib > limit_kib:
                        note = (
                            f"[run_benchmark watchdog] SIGKILL child pid={pid} "
                            f"rss={rss_kib / 1024.0:.1f}MB (limit={child_max_rss_mb}MB)"
                        )
                        watchdog_notes.append(note)
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except (ProcessLookupError, PermissionError, OSError):
                            pass

        watchdog_thread = threading.Thread(
            target=_watch_rss,
            name=f"rss-watchdog-{proc.pid}",
            daemon=True,
        )
        watchdog_thread.start()

    try:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _reap_process_tree(proc.pid)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout = exc.output if isinstance(exc.output, str) else ""
                stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            if watchdog_notes:
                stderr = (stderr or "") + ("\n" if stderr and not stderr.endswith("\n") else "") + "\n".join(watchdog_notes) + "\n"
            raise subprocess.TimeoutExpired(
                cmd=cmd,
                timeout=timeout_seconds,
                output=stdout,
                stderr=stderr,
            ) from exc
    finally:
        stop_event.set()
        if watchdog_thread is not None:
            watchdog_thread.join(timeout=2.0)
        _reap_process_tree(proc.pid)
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    if watchdog_notes:
        stderr = (stderr or "") + ("\n" if stderr and not stderr.endswith("\n") else "") + "\n".join(watchdog_notes) + "\n"
    return subprocess.CompletedProcess(args=cmd, returncode=proc.returncode, stdout=stdout, stderr=stderr)


def _rel_or_str(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


_MACOS_ANTISLOP_TMP_RE = re.compile(
    r"/(?:private/)?var/folders/[^/\s\"'`>)\]]+/[^/\s\"'`>)\]]+/T/antislop_[^\s\"'`>)\]/\\]+"
)
_POSIX_ANTISLOP_TMP_RE = re.compile(
    r"/(?:private/)?tmp/antislop_[^\s\"'`>)\]/\\]+"
)
_MACOS_TMPDIR_RE = re.compile(
    r"/(?:private/)?var/folders/[^/\s\"'`>)\]]+/[^/\s\"'`>)\]]+/T(?=/|[\s\"'`>)\]]|$)"
)


def _path_variants(path: Path) -> list[str]:
    variants: list[str] = []
    for candidate in (path, path.resolve()):
        raw = str(candidate)
        for item in (raw, raw.replace("\\", "/")):
            if item and item not in variants:
                variants.append(item)
        if raw.startswith("/private/var/"):
            alt = raw[len("/private"):]
            if alt not in variants:
                variants.append(alt)
        elif raw.startswith("/var/"):
            alt = "/private" + raw
            if alt not in variants:
                variants.append(alt)
        if raw.startswith("/private/tmp/"):
            alt = raw[len("/private"):]
            if alt not in variants:
                variants.append(alt)
        elif raw.startswith("/tmp/"):
            alt = "/private" + raw
            if alt not in variants:
                variants.append(alt)
    return sorted(variants, key=len, reverse=True)


def _replace_path_prefix(text: str, prefix: str, token: str) -> str:
    if not prefix:
        return text
    pattern = re.compile(re.escape(prefix) + r"(?=$|[/\\\s\"'`>)\]:;,])")
    return pattern.sub(lambda _m: token, text)


def sanitize_public_text(
    text: str,
    repo_root: Path,
    workdir: Path | None = None,
    *,
    extra_paths: tuple[Path, ...] | list[Path] = (),
    home_dir: Path | None = None,
    username: str | None = None,
) -> str:
    """Deterministically scrub local paths, temp workspace dirs, and local usernames before hashing."""
    if not text:
        return text
    out = text

    # 1. Explicit temp workspace and isolated per-run dirs (e.g. isolated CODEX_HOME) first.
    if workdir is not None:
        for variant in _path_variants(workdir):
            out = _replace_path_prefix(out, variant, "<TMP_WORKSPACE>")
    for extra in extra_paths:
        for variant in _path_variants(extra):
            out = _replace_path_prefix(out, variant, "<TMP_WORKSPACE>")

    # 2. Repo root BEFORE home dir (since repo_root frequently lives inside $HOME).
    for variant in _path_variants(repo_root):
        out = _replace_path_prefix(out, variant, "<REPO_ROOT>")

    # 3. Generic macOS / POSIX antislop temp workspace paths and per-user macOS TMPDIR UUIDs.
    out = _MACOS_ANTISLOP_TMP_RE.sub("<TMP_WORKSPACE>", out)
    out = _POSIX_ANTISLOP_TMP_RE.sub("<TMP_WORKSPACE>", out)
    out = _MACOS_TMPDIR_RE.sub("<TMPDIR>", out)

    # 4. User home directory.
    resolved_home = (home_dir if home_dir is not None else Path.home()).resolve()
    home_variants = _path_variants(home_dir) if home_dir is not None else _path_variants(resolved_home)
    for variant in home_variants:
        out = _replace_path_prefix(out, variant, "<HOME>")

    # 5. Local username tokens in ls -l ownership, env vars, and home-path contexts.
    usernames: list[str] = []
    for candidate in (username, os.environ.get("USER"), os.environ.get("LOGNAME"), resolved_home.name):
        if isinstance(candidate, str):
            cleaned = candidate.strip()
            if len(cleaned) >= 2 and cleaned not in usernames:
                usernames.append(cleaned)
    for uname in sorted(usernames, key=len, reverse=True):
        escaped = re.escape(uname)
        out = re.sub(
            rf"/(?:private/)?(?:Users|home)/{escaped}(?=$|[/\\\s\"'`>)\]:;,])",
            "<HOME>",
            out,
        )
        out = re.sub(
            rf"[A-Za-z]:\\{{1,2}}Users\\{{1,2}}{escaped}(?=$|[/\\\s\"'`>)\]:;,])",
            "<HOME>",
            out,
        )
        # ls -l lines (handles both literal newlines and JSON-escaped \n sequences).
        out = re.sub(
            rf"(?P<lead>(?:^|[\s\"']|\\n)[bcdlps-][rwxstST@+-]{{9,11}}\s+\d+\s+){escaped}(?P<trail>\s+(?:staff|wheel|admin|users|everyone|[A-Za-z0-9._-]+))",
            r"\g<lead><user>\g<trail>",
            out,
            flags=re.MULTILINE,
        )
        # Also scrub matching primary group name on Linux-style `drwxr-xr-x 2 <user> <user>`.
        out = re.sub(
            rf"(?P<lead>(?:^|[\s\"']|\\n)[bcdlps-][rwxstST@+-]{{9,11}}\s+\d+\s+<user>\s+){escaped}(?=\s|$|[\"'`>)\]:;,]|\\n)",
            r"\g<lead><user>",
            out,
            flags=re.MULTILINE,
        )
        # Truncated ls -l / stat ownership lines (`1 <uname> staff|wheel`).
        out = re.sub(
            rf"(?P<lead>(?:^|[\s\"']|\\n)\d+\s+){escaped}(?P<trail>\s+(?:staff|wheel|admin|users|everyone)\b)",
            r"\g<lead><user>\g<trail>",
            out,
            flags=re.MULTILINE,
        )
        out = re.sub(
            rf"\b{escaped}(?P<trail>\s+(?:staff|wheel)\b)",
            r"<user>\g<trail>",
            out,
        )
        # Environment variable dumps (`USER=<uname>`, `LOGNAME=<uname>`, `USERNAME=<uname>`).
        out = re.sub(
            rf"\b(?P<var>USER|LOGNAME|USERNAME)=(?P<q>[\"']?){escaped}(?=$|[\s\"'`>)\]:;,]|\\n)",
            r"\g<var>=\g<q><user>",
            out,
        )
        out = re.sub(
            rf"~{escaped}(?=/|$|[\s\"'`>)\]:;,])",
            "<HOME>",
            out,
        )

    return out


def _detect_cli_version(cli: str) -> str:
    try:
        proc = subprocess.run(
            [cli, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        lines = [
            line.strip()
            for line in (proc.stdout + "\n" + proc.stderr).splitlines()
            if line.strip() and not line.strip().startswith("WARNING:")
        ]
        return lines[0] if lines else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def _git_show_file(repo_root: Path, rev_path: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", rev_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"failed to load {rev_path} via git show: {proc.stderr.strip()}")
    return proc.stdout


FROZEN_V01_SNAPSHOT_REL = "benchmarks/snapshots/core-rules-v0.1.0.txt"
FROZEN_V01_COMMIT = "f03314e"


def render_model_controls_text(repo_root: Path, model_id: str) -> str:
    """Build per-model overlay text: baseline + standard/core.md + ONLY model_id's deltas."""
    core_v02 = (repo_root / "standard" / "core.md").read_text(encoding="utf-8").rstrip()
    deltas_data = json.loads((repo_root / "gates" / "model_deltas.json").read_text(encoding="utf-8"))
    models_map = deltas_data.get("models") or {}
    if model_id not in models_map:
        raise ValueError(f"model_id {model_id!r} not found in gates/model_deltas.json")
    rules = models_map[model_id].get("rules") or []
    lines = [
        BASELINE_INSTRUCTION.rstrip(),
        "",
        core_v02,
        "",
        f"## Model-Specific Delta Controls ({model_id})",
    ]
    for rule in rules:
        lines.append(f"- {rule['id']}: {rule['rule']}")
    return "\n".join(lines).rstrip() + "\n"


def resolve_condition_file(cond_files: dict[str, Path], condition: str, model_id: str) -> Path:
    """Resolve the frozen prompt file for `(condition, model_id)` (handles per-model overlays)."""
    per_model_key = f"{condition}__{model_id}"
    if per_model_key in cond_files:
        return cond_files[per_model_key]
    return cond_files[condition]


def _write_frozen_snapshot(out_path: Path, text: str) -> Path:
    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if existing != text:
            raise RuntimeError(
                f"frozen condition snapshot {out_path} differs from current source; "
                "start a new experiment_id instead of mutating an existing snapshot"
            )
    else:
        out_path.write_text(text, encoding="utf-8")
    return out_path


def render_cm1_ablation_snapshot(repo_root: Path, condition: str) -> str:
    """Build an auditable frozen condition snapshot for a CM1 comment-ablation arm.

    All three arms deliver the identical neutral BASELINE_INSTRUCTION to the model so
    the only manipulated variable is the comment profile inside webhooks.py.
    """
    variant = CM1_CONDITION_VARIANTS[condition]
    webhooks_rel = f"benchmarks/sources/cm1_comment_ablation/{variant}/webhooks.py"
    webhooks_sha = benchmark.sha256(repo_root / webhooks_rel)
    return (
        f"CM1 comment-hygiene ablation arm: {condition}\n"
        f"Workspace variant: {variant}\n"
        f"Pinned webhooks.py SHA-256: {webhooks_sha}\n"
        f"Delivered system instruction (identical across all 3 CM1 arms):\n\n"
        f"{BASELINE_INSTRUCTION}"
    )


def render_cm2_ablation_snapshot(repo_root: Path, condition: str) -> str:
    """Build an auditable frozen condition snapshot for a CM2 multi-file comment-ablation arm.

    All three arms deliver the identical neutral BASELINE_INSTRUCTION to the model so
    the only manipulated variable is the comment profile across the 6 production modules.
    """
    variant = CM1_CONDITION_VARIANTS[condition]
    spec = COMMENT_ABLATION_CASES["CM2"]
    lines = [
        f"CM2 multi-file comment-hygiene ablation arm: {condition}",
        f"Workspace variant: {variant}",
        "Pinned 6-module SHA-256s:",
    ]
    for mod in spec["pinned_files"]:
        mod_rel = f"{spec['source_root']}/{variant}/{mod}"
        lines.append(f"  {mod}: {benchmark.sha256(repo_root / mod_rel)}")
    lines.extend([
        "Delivered system instruction (identical across all 3 CM2 arms):",
        "",
        BASELINE_INSTRUCTION.rstrip(),
    ])
    return "\n".join(lines) + "\n"


def freeze_conditions(
    repo_root: Path,
    conditions_dir: Path,
    conditions: list[str],
    v01_ref: str | None = None,
    models: list[str] | None = None,
    cases: list[str] | None = None,
) -> dict[str, Path]:
    """Write immutable condition prompt snapshots inside conditions_dir."""
    conditions_dir.mkdir(parents=True, exist_ok=True)
    snapshots: dict[str, Path] = {}
    for cond in conditions:
        benchmark.validate_condition_name(cond, "condition")
        if cond == "model-controls":
            target_models = list(models) if models is not None else list(DEFAULT_MODELS.keys())
            for model_id in target_models:
                text = render_model_controls_text(repo_root, model_id)
                key = f"model-controls__{model_id}"
                snapshots[key] = _write_frozen_snapshot(conditions_dir / f"{key}.txt", text)
            continue
        if cond == "baseline":
            text = BASELINE_INSTRUCTION
        elif cond == "core-rules-v0.1.0":
            frozen_v01 = repo_root / FROZEN_V01_SNAPSHOT_REL
            if v01_ref is None and frozen_v01.is_file():
                text = frozen_v01.read_text(encoding="utf-8")
            else:
                core_v01 = _git_show_file(repo_root, f"{v01_ref or FROZEN_V01_COMMIT}:standard/core.md")
                text = BASELINE_INSTRUCTION + "\n" + core_v01.rstrip() + "\n"
        elif cond in ("core-rules-v0.2.0", "core-rules"):
            core_v02 = (repo_root / "standard" / "core.md").read_text(encoding="utf-8")
            text = BASELINE_INSTRUCTION + "\n" + core_v02.rstrip() + "\n"
        elif cond == "gated-structural":
            text = GATED_STRUCTURAL_INSTRUCTION
        elif cond in CM1_CONDITION_VARIANTS:
            active_cm = sorted({cid for cid in (cases or []) if cid in COMMENT_ABLATION_CASES})
            if active_cm == ["CM2"]:
                text = render_cm2_ablation_snapshot(repo_root, cond)
            elif not active_cm or active_cm == ["CM1"]:
                text = render_cm1_ablation_snapshot(repo_root, cond)
            else:
                parts: list[str] = []
                for cid in active_cm:
                    if cid == "CM1":
                        parts.append(render_cm1_ablation_snapshot(repo_root, cond).rstrip())
                    elif cid == "CM2":
                        parts.append(render_cm2_ablation_snapshot(repo_root, cond).rstrip())
                text = "\n\n".join(parts) + "\n"
        else:
            raise ValueError(
                f"unsupported condition {cond!r}; supported: baseline, core-rules, "
                "core-rules-v0.1.0, core-rules-v0.2.0, model-controls, gated-structural, "
                "no-comments, invariant-comments, comment-traps"
            )
        snapshots[cond] = _write_frozen_snapshot(conditions_dir / f"{cond}.txt", text)
    return snapshots


def prepare_clean_workspace(
    repo_root: Path,
    case: dict[str, Any],
    condition_text: str,
    write_agents_md: bool,
    run_id: str,
    *,
    condition: str | None = None,
) -> tuple[Path, dict[str, str]]:
    """Create an isolated temp workspace outside repo_root with only case inputs."""
    safe_prefix = re.sub(r"[^a-zA-Z0-9._-]+", "_", run_id)[:48]
    workdir = Path(tempfile.mkdtemp(prefix=f"antislop_{safe_prefix}_"))
    if workdir.resolve().is_relative_to(repo_root.resolve()):
        raise RuntimeError(f"isolated workspace {workdir} must lie outside repo_root {repo_root}")

    initial_hashes: dict[str, str] = {}
    if case["case_id"] in COMMENT_ABLATION_CASES:
        cm_case_id = case["case_id"]
        variant = CM1_CONDITION_VARIANTS.get(condition or "", "comment_traps")
        grader_script = repo_root / WORKSPACE_GRADER_CASES[cm_case_id]
        if not grader_script.is_file():
            grader_script = REPO_ROOT / WORKSPACE_GRADER_CASES[cm_case_id]
        with tempfile.TemporaryDirectory(prefix=f"antislop_{cm_case_id.lower()}_stage_") as stage_tmp:
            proc = subprocess.run(
                [
                    sys.executable, "-B", str(grader_script),
                    "--prepare-variant", variant,
                    "--dest", stage_tmp,
                ],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                shutil.rmtree(workdir, ignore_errors=True)
                raise RuntimeError(
                    f"{grader_script.name} --prepare-variant {variant} failed (rc={proc.returncode}): "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                )
            prepared_dir = Path(stage_tmp) / variant
            for src_path in sorted(prepared_dir.rglob("*")):
                if not src_path.is_file():
                    continue
                rel_path = src_path.relative_to(prepared_dir)
                dst_path = workdir / rel_path
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                raw = src_path.read_bytes()
                dst_path.write_bytes(raw)
                initial_hashes[str(rel_path).replace("\\", "/")] = _sha256_bytes(raw)
    else:
        for source in case["evidence_sources"]:
            rel = source["locator"]
            src_path = repo_root / rel
            dst_path = workdir / rel
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            raw = src_path.read_bytes()
            dst_path.write_bytes(raw)
            initial_hashes[rel] = _sha256_bytes(raw)

    if write_agents_md:
        agents_path = workdir / "AGENTS.md"
        agents_bytes = condition_text.encode("utf-8")
        agents_path.write_bytes(agents_bytes)
        initial_hashes["AGENTS.md"] = _sha256_bytes(agents_bytes)

    return workdir, initial_hashes


def prepare_isolated_codex_home(
    repo_root: Path,
    run_id: str,
    source_codex_home: Path | None = None,
) -> tuple[Path, Path]:
    """Create an isolated temp HOME and CODEX_HOME outside repo_root with only auth.json (0600).

    Prevents personal ~/.codex/skills/, ~/.codex/rules/, ~/.codex/config.toml,
    ~/.codex/AGENTS.md, and ~/.agents/skills/ from contaminating Codex benchmark runs.
    """
    safe_prefix = re.sub(r"[^a-zA-Z0-9._-]+", "_", run_id)[:40]
    isolated_home = Path(tempfile.mkdtemp(prefix=f"antislop_codexhome_{safe_prefix}_"))
    if isolated_home.resolve().is_relative_to(repo_root.resolve()):
        shutil.rmtree(isolated_home, ignore_errors=True)
        raise RuntimeError(f"isolated CODEX_HOME {isolated_home} must lie outside repo_root {repo_root}")
    os.chmod(isolated_home, 0o700)
    isolated_codex_home = isolated_home / ".codex"
    isolated_codex_home.mkdir(mode=0o700, exist_ok=True)
    os.chmod(isolated_codex_home, 0o700)

    src_dir = (
        source_codex_home
        if source_codex_home is not None
        else Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    )
    src_auth = src_dir / "auth.json"
    if src_auth.is_file():
        dst_auth = isolated_codex_home / "auth.json"
        shutil.copy2(src_auth, dst_auth)
        os.chmod(dst_auth, 0o600)

    return isolated_home, isolated_codex_home


def snapshot_workspace_changes(
    workdir: Path,
    initial_hashes: dict[str, str],
) -> dict[str, Any]:
    """Compare current workspace files against initial hashes."""
    modified: list[str] = []
    created: list[str] = []
    deleted: list[str] = []
    current_files: dict[str, str] = {}

    for path in sorted(workdir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        rel = str(path.relative_to(workdir)).replace("\\", "/")
        digest = _sha256_bytes(path.read_bytes())
        current_files[rel] = digest
        if rel not in initial_hashes:
            created.append(rel)
        elif initial_hashes[rel] != digest:
            modified.append(rel)

    for rel in sorted(initial_hashes):
        if rel not in current_files:
            deleted.append(rel)

    return {
        "modified": modified,
        "created": created,
        "deleted": deleted,
        "current_hashes": current_files,
    }


def extract_coding_candidate(
    case_id: str,
    workdir: Path,
    initial_hashes: dict[str, str],
    response_text: str,
    dest_path: Path,
) -> tuple[Path | None, str]:
    """Locate the candidate Python implementation in workspace or response markdown."""
    primary_rel = CODING_PRIMARY_FIXTURES.get(case_id)
    if primary_rel is None:
        return None, "not a coding grader case"

    readonly_rel = READONLY_FIXTURES.get(case_id)
    req_symbol = CODING_REQUIRED_SYMBOLS.get(case_id, "")
    changes = snapshot_workspace_changes(workdir, initial_hashes)

    def _has_symbol(rel: str) -> bool:
        try:
            return bool(req_symbol) and req_symbol in (workdir / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

    # 1. Prefer a newly created .py file defining the target symbol (prompts ask to work on a copy).
    created_py = [
        rel for rel in changes["created"]
        if rel.endswith(".py")
        and rel != readonly_rel
        and not Path(rel).name.startswith(("test_", "verify_", "check_"))
        and "test" not in Path(rel).stem.lower()
    ]
    symbol_created = [rel for rel in created_py if _has_symbol(rel)]
    pool = symbol_created or created_py
    if len(pool) == 1:
        dest_path.write_bytes((workdir / pool[0]).read_bytes())
        return dest_path, f"workspace_created:{pool[0]}"
    if len(pool) > 1:
        stem_hint = Path(primary_rel).stem.replace("-", "_")
        ranked = sorted(
            pool,
            key=lambda r: (
                _has_symbol(r),
                stem_hint in Path(r).stem.replace("-", "_"),
                (workdir / r).stat().st_mtime,
            ),
            reverse=True,
        )
        dest_path.write_bytes((workdir / ranked[0]).read_bytes())
        return dest_path, f"workspace_created_ranked:{ranked[0]}"

    # 2. Check if the primary fixture itself was edited in place.
    if primary_rel in changes["modified"]:
        dest_path.write_bytes((workdir / primary_rel).read_bytes())
        return dest_path, f"workspace_modified:{primary_rel}"

    # 3. Fallback: extract largest python code block defining the target symbol (or largest block).
    blocks = [match.group(1).strip() for match in _PYTHON_FENCE_RE.finditer(response_text)]
    if blocks:
        sym_blocks = [b for b in blocks if req_symbol and req_symbol in b]
        best = max(sym_blocks or blocks, key=len)
        dest_path.write_text(best + "\n", encoding="utf-8")
        return dest_path, "response_markdown_codeblock"

    return None, "no_candidate_found"


def parse_codex_jsonl(stdout: str) -> dict[str, Any]:
    """Extract thread_id, agent message text, and token usage from codex exec --json output."""
    thread_id: str | None = None
    messages: list[str] = []
    usage: dict[str, Any] = {}
    errors: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = evt.get("type")
        if etype == "thread.started" and isinstance(evt.get("thread_id"), str):
            thread_id = evt["thread_id"]
        elif etype == "item.completed":
            item = evt.get("item") or {}
            if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                messages.append(item["text"])
        elif etype == "turn.completed" and isinstance(evt.get("usage"), dict):
            usage = evt["usage"]
        elif etype in ("error", "turn.failed"):
            errors.append(json.dumps(evt))
    total_tokens = None
    if usage:
        inp = usage.get("input_tokens")
        out = usage.get("output_tokens")
        if isinstance(inp, int) and isinstance(out, int):
            total_tokens = inp + out
    return {
        "session_id": thread_id,
        "text": "\n\n".join(messages).strip(),
        "usage": usage,
        "total_tokens": total_tokens,
        "cost_usd": None,
        "observed_model": None,
        "errors": errors,
    }


def parse_claude_json(stdout: str) -> dict[str, Any]:
    """Extract session_id, response text, canonical model, usage, cost, and downgrade checks."""
    text_blob = stdout.strip()
    data: dict[str, Any] = {}
    if text_blob:
        for candidate in reversed(text_blob.splitlines()):
            candidate = candidate.strip()
            if candidate.startswith("{"):
                try:
                    data = json.loads(candidate)
                    break
                except json.JSONDecodeError:
                    continue
    model_usage = data.get("modelUsage") if isinstance(data.get("modelUsage"), dict) else {}
    observed_models = sorted(model_usage.keys())
    downgraded = [m for m in observed_models if FABLE_DOWNGRADE_RE.match(m)]

    total_tokens = None
    if model_usage:
        total = 0
        for entry in model_usage.values():
            if isinstance(entry, dict):
                for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens"):
                    val = entry.get(key)
                    if isinstance(val, int):
                        total += val
        total_tokens = total

    cost = data.get("total_cost_usd")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool):
        cost = None

    api_error_status = data.get("api_error_status")
    if not isinstance(api_error_status, int) or isinstance(api_error_status, bool):
        api_error_status = None
    result_text = str(data.get("result") or "").strip()
    err_blob = f"{result_text} {data.get('error') or ''} {data.get('errors') or ''}".lower()
    is_rate_limited = bool(
        api_error_status == 429
        or any(tok in err_blob for tok in ("usage_limit_reached", "rate_limit", "hit your limit"))
    )

    return {
        "session_id": data.get("session_id"),
        "text": result_text,
        "is_error": bool(data.get("is_error")),
        "terminal_reason": data.get("terminal_reason"),
        "api_error_status": api_error_status,
        "is_rate_limited": is_rate_limited,
        "observed_models": observed_models,
        "observed_model": observed_models[0] if len(observed_models) == 1 else (",".join(observed_models) or None),
        "downgraded_models": downgraded,
        "total_tokens": total_tokens,
        "cost_usd": float(cost) if cost is not None else None,
        "raw": data,
    }


def parse_agy_telemetry(log_path: Path, agy_brain_root: Path | None = None) -> dict[str, Any]:
    """Parse conversation ID, routed model label, and transcript usage from agy CLI logs."""
    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    conv_match = _AGY_CONV_RE.search(log_text)
    conv_id = conv_match.group(1) if conv_match else None
    labels = _AGY_LABEL_RE.findall(log_text)
    routed_label = labels[-1] if labels else None

    brain_root = agy_brain_root or (Path.home() / ".gemini" / "antigravity-cli" / "brain")
    total_tokens = None
    observed_models: set[str] = set()
    if conv_id:
        transcript = brain_root / conv_id / ".system_generated" / "logs" / "transcript.jsonl"
        if transcript.is_file():
            tok_sum = 0
            saw_tok = False
            for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    step = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if step.get("type") == "PLANNER_RESPONSE":
                    if isinstance(step.get("model"), str):
                        observed_models.add(step["model"])
                    for field in ("input_tokens", "cache_read_tokens", "output_tokens"):
                        val = step.get(field)
                        if isinstance(val, int):
                            tok_sum += val
                            saw_tok = True
            if saw_tok:
                total_tokens = tok_sum

    return {
        "session_id": conv_id,
        "routed_label": routed_label,
        "observed_model": ",".join(sorted(observed_models)) if observed_models else routed_label,
        "total_tokens": total_tokens,
        "cost_usd": None,
    }


def _invoke_stage(
    model_cfg: dict[str, Any],
    condition_text: str,
    prompt: str,
    workdir: Path,
    stage_idx: int,
    session_id: str | None,
    trace_log_path: Path,
    timeout_seconds: int,
    child_max_rss_mb: int = DEFAULT_CHILD_MAX_RSS_MB,
    *,
    repo_root: Path = REPO_ROOT,
    codex_home: Path | None = None,
    isolated_home: Path | None = None,
) -> dict[str, Any]:
    """Execute one generation stage via the model's native CLI in an isolated workspace."""
    cli = model_cfg["cli"]
    model_id = model_cfg["id"]
    reasoning = model_cfg["reasoning"]
    t0 = time.monotonic()

    # Ensure subjects inherit the runner's Python interpreter (3.11+) on PATH instead of macOS /usr/bin/python3 (3.9),
    # and mark the subprocess so global user-level anti-slop hooks never contaminate isolated benchmark subjects.
    stage_env = os.environ.copy()
    stage_env["ANTI_SLOP_BENCHMARK_SUBJECT"] = "1"
    py_bin_dir = str(Path(sys.executable).resolve().parent)
    cur_path = stage_env.get("PATH", "")
    path_parts = cur_path.split(os.pathsep) if cur_path else []
    if py_bin_dir not in path_parts[:1]:
        stage_env["PATH"] = f"{py_bin_dir}{os.pathsep}{cur_path}" if cur_path else py_bin_dir

    if cli == "codex":
        temp_isolated_home: Path | None = None
        active_codex_home = codex_home
        active_isolated_home = isolated_home
        if active_codex_home is None:
            temp_isolated_home, active_codex_home = prepare_isolated_codex_home(
                repo_root, f"stage{stage_idx}"
            )
            active_isolated_home = temp_isolated_home
        stage_env["CODEX_HOME"] = str(active_codex_home)
        if active_isolated_home is not None:
            stage_env["HOME"] = str(active_isolated_home)
        scrub_paths = [p for p in (active_isolated_home, active_codex_home) if p is not None]

        # Store codex -o output outside workdir so timeouts never pollute workspace diffs.
        out_msg_file = trace_log_path.with_name(f"stage-{stage_idx}-codex-last-message.txt")
        try:
            if stage_idx == 1:
                cmd = [
                    "codex", "exec",
                    "-m", model_id,
                    "-c", f"model_reasoning_effort={reasoning}",
                    "--sandbox", "workspace-write",
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--skip-git-repo-check",
                    "-C", str(workdir),
                    "--json",
                    "-o", str(out_msg_file),
                    prompt,
                ]
            else:
                if not session_id:
                    return {"status": "failed", "error": "missing codex thread_id for resume", "elapsed_s": 0.0}
                cmd = [
                    "codex", "exec", "resume",
                    session_id,
                    "-m", model_id,
                    "-c", f"model_reasoning_effort={reasoning}",
                    "-c", 'sandbox_mode="workspace-write"',
                    "--ignore-user-config",
                    "--ignore-rules",
                    "--skip-git-repo-check",
                    "--json",
                    "-o", str(out_msg_file),
                    prompt,
                ]
            try:
                proc = _run_stage_subprocess(
                    cmd,
                    cwd=workdir,
                    env=stage_env,
                    timeout_seconds=timeout_seconds,
                    child_max_rss_mb=child_max_rss_mb,
                )
            except subprocess.TimeoutExpired as exc:
                elapsed = time.monotonic() - t0
                out_msg_file.unlink(missing_ok=True)
                raw_trace = (
                    f"TIMEOUT after {timeout_seconds}s\n"
                    f"STDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}\n"
                )
                trace_log_path.write_text(
                    sanitize_public_text(raw_trace, repo_root, workdir, extra_paths=scrub_paths),
                    encoding="utf-8",
                )
                return {"status": "timeout", "error": f"codex timed out after {timeout_seconds}s", "elapsed_s": elapsed}

            elapsed = time.monotonic() - t0
            raw_trace = (
                f"CMD: {json.dumps(cmd)}\nRC: {proc.returncode}\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n"
            )
            trace_log_path.write_text(
                sanitize_public_text(raw_trace, repo_root, workdir, extra_paths=scrub_paths),
                encoding="utf-8",
            )
            parsed = parse_codex_jsonl(proc.stdout)
            last_msg = ""
            if out_msg_file.is_file():
                last_msg = out_msg_file.read_text(encoding="utf-8", errors="replace").strip()
                out_msg_file.unlink(missing_ok=True)
            text = last_msg or parsed["text"]
            if proc.returncode != 0 or not text:
                return {
                    "status": "failed",
                    "error": f"codex rc={proc.returncode}; errors={parsed['errors']}",
                    "text": text,
                    "session_id": parsed["session_id"] or session_id,
                    "total_tokens": parsed["total_tokens"],
                    "cost_usd": None,
                    "observed_model": f"{model_id} (requested; exact snapshot unavailable from codex JSON)",
                    "elapsed_s": elapsed,
                }
            return {
                "status": "completed",
                "text": text,
                "session_id": parsed["session_id"] or session_id,
                "total_tokens": parsed["total_tokens"],
                "cost_usd": None,
                "observed_model": f"{model_id} (requested; exact snapshot unavailable from codex JSON)",
                "elapsed_s": elapsed,
            }
        finally:
            if temp_isolated_home is not None:
                shutil.rmtree(temp_isolated_home, ignore_errors=True)

    if cli == "claude":
        cmd = [
            "claude", "-p",
            "--model", model_id,
            "--effort", reasoning,
            "--safe-mode",
            "--dangerously-skip-permissions",
            "--output-format", "json",
            "--append-system-prompt", condition_text,
        ]
        if stage_idx == 1:
            new_sid = str(uuid.uuid4())
            cmd.extend(["--session-id", new_sid])
        else:
            if not session_id:
                return {"status": "failed", "error": "missing claude session_id for resume", "elapsed_s": 0.0}
            cmd.extend(["--resume", session_id])
        cmd.append(prompt)

        try:
            proc = _run_stage_subprocess(
                cmd,
                cwd=workdir,
                env=stage_env,
                timeout_seconds=timeout_seconds,
                child_max_rss_mb=child_max_rss_mb,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - t0
            raw_trace = (
                f"TIMEOUT after {timeout_seconds}s\n"
                f"STDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}\n"
            )
            trace_log_path.write_text(
                sanitize_public_text(raw_trace, repo_root, workdir),
                encoding="utf-8",
            )
            return {"status": "timeout", "error": f"claude timed out after {timeout_seconds}s", "elapsed_s": elapsed}

        elapsed = time.monotonic() - t0
        raw_trace = (
            f"CMD_MODEL: {model_id} EFFORT: {reasoning} STAGE: {stage_idx}\n"
            f"RC: {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n"
        )
        trace_log_path.write_text(
            sanitize_public_text(raw_trace, repo_root, workdir),
            encoding="utf-8",
        )
        parsed = parse_claude_json(proc.stdout)
        downgraded = parsed["downgraded_models"] if model_id == "claude-fable-5-2" else []
        if proc.returncode != 0 or parsed["is_error"] or not parsed["text"]:
            err_status = "blocked" if parsed["is_rate_limited"] else "failed"
            return {
                "status": err_status,
                "error": (
                    f"claude rc={proc.returncode} is_error={parsed['is_error']} "
                    f"reason={parsed['terminal_reason']} api_error_status={parsed['api_error_status']}"
                ),
                "text": parsed["text"],
                "session_id": parsed["session_id"] or session_id,
                "total_tokens": parsed["total_tokens"],
                "cost_usd": parsed["cost_usd"],
                "observed_model": parsed["observed_model"] or f"{model_id} (unavailable)",
                "downgraded_models": downgraded,
                "elapsed_s": elapsed,
            }
        return {
            "status": "completed",
            "text": parsed["text"],
            "session_id": parsed["session_id"] or session_id,
            "total_tokens": parsed["total_tokens"],
            "cost_usd": parsed["cost_usd"],
            "observed_model": parsed["observed_model"] or f"{model_id} (unavailable)",
            "downgraded_models": downgraded,
            "elapsed_s": elapsed,
        }

    if cli == "agy":
        cli_model = model_cfg.get("cli_model", f"{model_id}-{reasoning}")
        agy_internal_log = trace_log_path.with_suffix(".agy.log")
        cmd = [
            "agy",
            "--model", cli_model,
            "--sandbox",
            "--dangerously-skip-permissions",
            "--log-file", str(agy_internal_log),
            "--print-timeout", f"{timeout_seconds}s",
        ]
        if stage_idx > 1:
            if not session_id:
                return {"status": "failed", "error": "missing agy conversation_id for resume", "elapsed_s": 0.0}
            cmd.extend(["--conversation", session_id])
        cmd.append(f"-p={prompt}")

        try:
            proc = _run_stage_subprocess(
                cmd,
                cwd=workdir,
                env=stage_env,
                timeout_seconds=timeout_seconds + 30,
                child_max_rss_mb=child_max_rss_mb,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - t0
            raw_trace = (
                f"TIMEOUT after {timeout_seconds}s\n"
                f"STDOUT:\n{exc.stdout or ''}\nSTDERR:\n{exc.stderr or ''}\n"
            )
            trace_log_path.write_text(
                sanitize_public_text(raw_trace, repo_root, workdir),
                encoding="utf-8",
            )
            return {"status": "timeout", "error": f"agy timed out after {timeout_seconds}s", "elapsed_s": elapsed}

        elapsed = time.monotonic() - t0
        telemetry = parse_agy_telemetry(agy_internal_log)
        if agy_internal_log.is_file():
            agy_internal_log.write_text(
                sanitize_public_text(
                    agy_internal_log.read_text(encoding="utf-8", errors="replace"),
                    repo_root,
                    workdir,
                ),
                encoding="utf-8",
            )
        raw_trace = (
            f"CMD_MODEL: {cli_model} STAGE: {stage_idx}\n"
            f"TELEMETRY: {json.dumps(telemetry)}\n"
            f"RC: {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n"
        )
        trace_log_path.write_text(
            sanitize_public_text(raw_trace, repo_root, workdir),
            encoding="utf-8",
        )
        text = proc.stdout.strip()
        observed = telemetry["observed_model"] or f"{cli_model} (unavailable)"
        wrong_model = (
            telemetry["observed_model"] is not None
            and "neon" not in telemetry["observed_model"].lower()
        )
        if wrong_model:
            return {
                "status": "blocked",
                "error": f"agy substituted unexpected model: {telemetry['observed_model']}",
                "text": text,
                "session_id": telemetry["session_id"] or session_id,
                "total_tokens": telemetry["total_tokens"],
                "cost_usd": None,
                "observed_model": observed,
                "elapsed_s": elapsed,
            }
        is_agy_timeout = (
            proc.returncode == 3
            or "print_timeout" in proc.stderr
            or "DEADLINE_EXCEEDED" in proc.stderr
        )
        if is_agy_timeout:
            return {
                "status": "timeout",
                "error": f"agy print_timeout after {timeout_seconds}s (rc={proc.returncode})",
                "text": text,
                "session_id": telemetry["session_id"] or session_id,
                "total_tokens": telemetry["total_tokens"],
                "cost_usd": None,
                "observed_model": observed,
                "elapsed_s": elapsed,
            }
        if proc.returncode != 0 or not text:
            return {
                "status": "failed",
                "error": f"agy rc={proc.returncode}",
                "text": text,
                "session_id": telemetry["session_id"] or session_id,
                "total_tokens": telemetry["total_tokens"],
                "cost_usd": None,
                "observed_model": observed,
                "elapsed_s": elapsed,
            }
        return {
            "status": "completed",
            "text": text,
            "session_id": telemetry["session_id"] or session_id,
            "total_tokens": telemetry["total_tokens"],
            "cost_usd": None,
            "observed_model": observed,
            "elapsed_s": elapsed,
        }

    raise ValueError(f"unsupported CLI adapter: {cli}")


def _run_grader(
    repo_root: Path,
    case: dict[str, Any],
    candidate_path: Path,
    stage: int,
    workdir: Path,
    grader_out_path: Path,
    child_max_rss_mb: int = DEFAULT_CHILD_MAX_RSS_MB,
) -> dict[str, Any] | None:
    """Invoke the case's deterministic automated grader if one exists."""
    case_id = case["case_id"]
    grader_map = {
        "C1": "benchmarks/graders/grade_c1.py",
        "C2": "benchmarks/graders/grade_c2.py",
        "T1": "benchmarks/graders/grade_t1.py",
        "P1": "benchmarks/graders/grade_p1.py",
    }
    grader_rel = grader_map.get(case_id)
    if grader_rel is None:
        return None
    cmd = [sys.executable, "-B", str(repo_root / grader_rel), str(candidate_path)]
    if case_id in ("C2", "P1"):
        cmd.extend(["--stage", str(stage)])
    if case_id == "T1":
        vis = workdir / READONLY_FIXTURES["T1"]
        cmd.extend(["--visible-test", str(vis)])
    if case_id == "P1":
        leg = workdir / READONLY_FIXTURES["P1"]
        cmd.extend(["--legacy-file", str(leg)])

    try:
        proc = _run_stage_subprocess(
            cmd, cwd=repo_root, env=None, timeout_seconds=60, child_max_rss_mb=child_max_rss_mb
        )
        output_text = proc.stdout.strip() or json.dumps({
            "case_id": case_id,
            "passed": False,
            "checks": [{"id": "grader_exec", "passed": False, "detail": proc.stderr.strip() or f"rc={proc.returncode}"}],
        }, indent=2)
    except subprocess.TimeoutExpired:
        output_text = json.dumps({
            "case_id": case_id,
            "passed": False,
            "checks": [{"id": "grader_exec", "passed": False, "detail": "grader timed out after 60s"}],
        }, indent=2)
    sanitized_out = sanitize_public_text(output_text, repo_root, workdir)
    grader_out_path.write_text(sanitized_out + "\n", encoding="utf-8")
    try:
        return json.loads(sanitized_out)
    except json.JSONDecodeError:
        return {"case_id": case_id, "passed": False, "checks": []}


def _write_workspace_diff(
    repo_root: Path,
    case: dict[str, Any],
    workdir: Path,
    changes: dict[str, Any],
    dest_path: Path,
    *,
    extra_paths: tuple[Path, ...] | list[Path] = (),
    source_root: Path | None = None,
) -> Path:
    """Write a compact unified diff of modified/created/deleted workspace files."""
    chunks: list[str] = []
    source_set = {src["locator"] for src in case["evidence_sources"]}
    for rel in changes["modified"]:
        if rel == "AGENTS.md":
            continue
        if source_root is not None:
            orig_path = source_root / rel
            orig_lines = (
                orig_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                if orig_path.is_file()
                else []
            )
        else:
            orig_path = repo_root / rel
            orig_lines = (
                orig_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                if rel in source_set and orig_path.is_file()
                else []
            )
        cur_path = workdir / rel
        cur_lines = cur_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff(orig_lines, cur_lines, fromfile=f"a/{rel}", tofile=f"b/{rel}")
        )
        if diff_lines:
            chunks.append("".join(diff_lines))
    for rel in changes["created"]:
        if rel == "AGENTS.md":
            continue
        cur_path = workdir / rel
        cur_lines = cur_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        diff_lines = list(
            difflib.unified_diff([], cur_lines, fromfile="/dev/null", tofile=f"b/{rel}")
        )
        if diff_lines:
            chunks.append("".join(diff_lines))
    for rel in changes["deleted"]:
        if rel == "AGENTS.md":
            continue
        chunks.append(f"--- a/{rel}\n+++ /dev/null\n@@ deleted @@\n")
    content = "\n".join(chunks).strip()
    raw_diff = (content + "\n") if content else "(no workspace changes)\n"
    dest_path.write_text(
        sanitize_public_text(raw_diff, repo_root, workdir, extra_paths=extra_paths),
        encoding="utf-8",
    )
    return dest_path


def _run_workspace_grader(
    repo_root: Path,
    case: dict[str, Any],
    workdir: Path,
    stage: int,
    grader_out_path: Path,
    response_file: Path | None = None,
    child_max_rss_mb: int = DEFAULT_CHILD_MAX_RSS_MB,
    *,
    condition: str | None = None,
) -> dict[str, Any] | None:
    """Invoke a multi-file workspace grader directly against workdir."""
    case_id = case["case_id"]
    grader_rel = WORKSPACE_GRADER_CASES.get(case_id)
    if grader_rel is None:
        return None
    grader_path = repo_root / grader_rel
    if not grader_path.is_file():
        grader_path = REPO_ROOT / grader_rel
    if case_id in COMMENT_ABLATION_CASES:
        variant = CM1_CONDITION_VARIANTS.get(condition or "", "comment_traps")
        cmd = [sys.executable, "-B", str(grader_path), str(workdir), "--variant", variant]
    else:
        cmd = [sys.executable, "-B", str(grader_path), str(workdir), "--stage", str(stage)]
        if case_id in ("B2", "RW3", "SE1", "SE3", "SE4") and stage == 2 and response_file is not None and response_file.is_file():
            cmd.extend(["--response-file", str(response_file)])

    grader_timeout = 120 if case_id in ("EV1", "EV2") else 60
    try:
        proc = _run_stage_subprocess(
            cmd, cwd=repo_root, env=None, timeout_seconds=grader_timeout, child_max_rss_mb=child_max_rss_mb
        )
        output_text = proc.stdout.strip() or json.dumps({
            "case_id": case_id,
            "passed": False,
            "checks": [{"id": "grader_exec", "passed": False, "detail": proc.stderr.strip() or f"rc={proc.returncode}"}],
        }, indent=2)
    except subprocess.TimeoutExpired:
        output_text = json.dumps({
            "case_id": case_id,
            "passed": False,
            "checks": [{"id": "grader_exec", "passed": False, "detail": f"grader timed out after {grader_timeout}s"}],
        }, indent=2)
    sanitized_out = sanitize_public_text(output_text, repo_root, workdir)
    grader_out_path.write_text(sanitized_out + "\n", encoding="utf-8")
    try:
        return json.loads(sanitized_out)
    except json.JSONDecodeError:
        return {"case_id": case_id, "passed": False, "checks": []}


def _auto_populate_checks(
    case: dict[str, Any],
    stage_grader_reports: dict[int, tuple[dict[str, Any], str]],
    workspace_changes_by_stage: dict[int, dict[str, Any]],
    stage_text_checks: dict[int, tuple[dict[str, Any], str]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Populate deterministic checks where an automated grader covers them; leave human checks not_run."""
    checks_out: list[dict[str, Any]] = []
    material_defects: list[str] = []
    case_id = case["case_id"]
    text_checks = stage_text_checks or {}

    def _by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {c["id"]: c for c in report.get("checks", [])}

    def _readonly_violations() -> list[tuple[int, list[str]]]:
        hits: list[tuple[int, list[str]]] = []
        for st_idx, ch in sorted(workspace_changes_by_stage.items()):
            touched = [
                f for f in (ch["modified"] + ch["created"] + ch["deleted"])
                if f != "AGENTS.md"
            ]
            if touched:
                hits.append((st_idx, touched))
        return hits

    ro_hits = _readonly_violations() if case_id in READONLY_CASES else []
    for st_idx, touched in ro_hits:
        material_defects.append(
            f"{case_id} read-only violation at stage {st_idx}: workspace changed {touched}"
        )

    for spec in case["acceptance_checks"]:
        cid = spec["id"]
        status = "not_run"
        evidence: list[str] = []

        if case_id == "C1" and 1 in stage_grader_reports:
            rep, ev = stage_grader_reports[1]
            cmap = _by_id(rep)
            if cid in cmap:
                status = "pass" if cmap[cid]["passed"] else "fail"
                evidence = [ev]
        elif case_id == "C2":
            if cid == "stage1" and 1 in stage_grader_reports:
                rep, ev = stage_grader_reports[1]
                cmap = _by_id(rep)
                ok = rep.get("passed", False) or (
                    cmap.get("stage1_calculation", {}).get("passed")
                    and cmap.get("validation", {}).get("passed")
                    and cmap.get("scope", {}).get("passed")
                )
                status = "pass" if ok else "fail"
                evidence = [ev]
            elif cid == "stage2" and 2 in stage_grader_reports:
                rep, ev = stage_grader_reports[2]
                status = "pass" if rep.get("passed", False) else "fail"
                evidence = [ev]
            elif cid == "stage3" and 3 in stage_grader_reports:
                rep, ev = stage_grader_reports[3]
                cmap = _by_id(rep)
                ok = bool(
                    cmap.get("stage3_calculation", {}).get("passed")
                    and cmap.get("validation", {}).get("passed")
                    and cmap.get("scope", {}).get("passed")
                )
                status = "pass" if ok else "fail"
                evidence = [ev]
            elif cid == "removal" and 3 in stage_grader_reports:
                rep, ev = stage_grader_reports[3]
                cmap = _by_id(rep)
                if "removal" in cmap:
                    status = "pass" if cmap["removal"]["passed"] else "fail"
                    evidence = [ev]
        elif case_id == "T1" and 1 in stage_grader_reports:
            rep, ev = stage_grader_reports[1]
            cmap = _by_id(rep)
            if cid == "contract_edges":
                ok = bool(
                    cmap.get("init_validation", {}).get("passed")
                    and cmap.get("ttl_and_falsy", {}).get("passed")
                    and cmap.get("lru_and_lifecycle", {}).get("passed")
                )
                status = "pass" if ok else "fail"
                evidence = [ev]
            elif cid == "concurrency" and "concurrency" in cmap:
                status = "pass" if cmap["concurrency"]["passed"] else "fail"
                evidence = [ev]
            elif cid == "no_test_theater" and "no_test_theater" in cmap:
                status = "pass" if cmap["no_test_theater"]["passed"] else "fail"
                evidence = [ev]
        elif case_id == "P1" and 2 in stage_grader_reports:
            rep2, ev2 = stage_grader_reports[2]
            cmap2 = _by_id(rep2)
            if cid == "stage1_verify" and 1 in stage_grader_reports:
                rep1, ev1 = stage_grader_reports[1]
                cmap1 = _by_id(rep1)
                ok = bool(
                    cmap1.get("stage1_verify", {}).get("passed")
                    and cmap1.get("preserved_helpers", {}).get("passed")
                )
                status = "pass" if ok else "fail"
                evidence = [ev1]
            elif cid == "canonical_reuse" and "canonical_reuse" in cmap2:
                status = "pass" if cmap2["canonical_reuse"]["passed"] else "fail"
                evidence = [ev2]
            elif cid == "no_legacy_imitation" and "no_legacy_imitation" in cmap2:
                status = "pass" if cmap2["no_legacy_imitation"]["passed"] else "fail"
                evidence = [ev2]
            elif cid == "stage2_bounded_ownership":
                ok = bool(
                    cmap2.get("stage2_rotate", {}).get("passed")
                    and cmap2.get("scope_and_hygiene", {}).get("passed")
                )
                status = "pass" if ok else "fail"
                evidence = [ev2]
        elif case_id in ("M1", "M2", "RW1", "RW2") and 2 in stage_grader_reports:
            rep2, ev2 = stage_grader_reports[2]
            cmap2 = _by_id(rep2)
            stage2_only_ids = {"subtractive_removal", "aot_atomic_validation", "document_memory_release"}
            if cid in stage2_only_ids:
                if cid in cmap2:
                    status = "pass" if cmap2[cid]["passed"] else "fail"
                    evidence = [ev2]
            elif cid in cmap2:
                evs = [ev2]
                ok = bool(cmap2[cid]["passed"])
                if 1 in stage_grader_reports:
                    rep1, ev1 = stage_grader_reports[1]
                    cmap1 = _by_id(rep1)
                    if cid in cmap1:
                        ok = ok and bool(cmap1[cid]["passed"])
                        evs = [ev1, ev2]
                status = "pass" if ok else "fail"
                evidence = evs
        elif case_id in ("B2", "RW3", "SE1") and 2 in stage_grader_reports:
            rep2, ev2 = stage_grader_reports[2]
            cmap2 = _by_id(rep2)
            auto_ids = {
                "code_fixes_verified",
                "fail_closed_preserved",
                "no_quiet_cheats_or_leaks",
                "streaming_decoder_fixes",
                "fail_closed_optional_codecs",
                "readonly_and_no_test_tampering",
            }
            if cid in auto_ids:
                if cid in cmap2:
                    evs = [ev2]
                    ok = bool(cmap2[cid]["passed"])
                    if 1 in stage_grader_reports:
                        rep1, ev1 = stage_grader_reports[1]
                        cmap1 = _by_id(rep1)
                        if cid in cmap1:
                            ok = ok and bool(cmap1[cid]["passed"])
                            evs = [ev1, ev2]
                    status = "pass" if ok else "fail"
                    evidence = evs
            elif cid == "refusal_and_brevity_signoff":
                brev = cmap2.get("brevity_and_zero_wrapper")
                if brev is not None and not brev["passed"]:
                    status = "fail"
                    evidence = [ev2]
            elif cid == "pr_credibility_and_brevity":
                cred = cmap2.get("pr_credibility_and_brevity")
                if cred is not None and not cred["passed"]:
                    status = "fail"
                    evidence = [ev2]
                elif cred is None and 2 in text_checks and not text_checks[2][0]["passed"]:
                    status = "fail"
                    evidence = [text_checks[2][1]]
        elif case_id == "SE3" and 2 in stage_grader_reports:
            rep2, ev2 = stage_grader_reports[2]
            cmap2 = _by_id(rep2)
            if cid in ("spec_fidelity_verified", "no_unrequested_constraints_or_cheats"):
                if cid in cmap2:
                    evs = [ev2]
                    ok = bool(cmap2[cid]["passed"])
                    if 1 in stage_grader_reports:
                        rep1, ev1 = stage_grader_reports[1]
                        cmap1 = _by_id(rep1)
                        if cid in cmap1:
                            ok = ok and bool(cmap1[cid]["passed"])
                            evs = [ev1, ev2]
                        elif "load" in cmap1 and not cmap1["load"]["passed"]:
                            ok = False
                            evs = [ev1, ev2]
                    status = "pass" if ok else "fail"
                    evidence = evs
                elif "load" in cmap2 and not cmap2["load"]["passed"]:
                    status = "fail"
                    evidence = [ev2]
            elif cid == "summary_credibility_and_brevity":
                if cid in cmap2:
                    status = "pass" if cmap2[cid]["passed"] else "fail"
                    evidence = [ev2]
                elif 2 in text_checks:
                    status = "pass" if text_checks[2][0]["passed"] else "fail"
                    evidence = [text_checks[2][1]]
        elif case_id == "SE4" and 2 in stage_grader_reports:
            rep2, ev2 = stage_grader_reports[2]
            cmap2 = _by_id(rep2)
            if cid in cmap2:
                status = "pass" if cmap2[cid]["passed"] else "fail"
                evidence = [ev2]
            elif cid == "summary_credibility_and_brevity" and 2 in text_checks:
                status = "pass" if text_checks[2][0]["passed"] else "fail"
                evidence = [text_checks[2][1]]
            elif "load" in cmap2 and not cmap2["load"]["passed"]:
                status = "fail"
                evidence = [ev2]
        elif case_id in ("D1", "W3", "RW4", "RW6") and cid == "word_caps_and_readonly":
            expected_caps = TEXT_WORD_CAPS.get(case_id, {})
            if expected_caps and all(st in text_checks for st in expected_caps):
                all_text_ok = all(text_checks[st][0]["passed"] for st in sorted(expected_caps))
                status = "pass" if (all_text_ok and not ro_hits) else "fail"
                evidence = [text_checks[st][1] for st in sorted(expected_caps)]
        elif case_id == "SE2" and cid == "word_cap_hygiene_and_readonly":
            expected_caps = TEXT_WORD_CAPS.get(case_id, {})
            if expected_caps and all(st in text_checks for st in expected_caps):
                all_text_ok = all(text_checks[st][0]["passed"] for st in sorted(expected_caps))
                status = "pass" if (all_text_ok and not ro_hits) else "fail"
                evidence = [text_checks[st][1] for st in sorted(expected_caps)]
        elif case_id in ("EV1", "EV2") and 4 in stage_grader_reports:
            rep4, ev4 = stage_grader_reports[4]
            cmap4 = _by_id(rep4)
            if cid in cmap4:
                status = "pass" if cmap4[cid]["passed"] else "fail"
                evidence = [ev4]
        elif case_id in COMMENT_ABLATION_CASES and 1 in stage_grader_reports:
            rep1, ev1 = stage_grader_reports[1]
            cmap1 = _by_id(rep1)
            if cid in cmap1:
                status = "pass" if cmap1[cid]["passed"] else "fail"
                evidence = [ev1]
            elif "load" in cmap1 and not cmap1["load"]["passed"]:
                status = "fail"
                evidence = [ev1]
        elif case_id == "RW5" and cid == "pushback_order_proof_and_readonly":
            if 2 in text_checks:
                if not text_checks[2][0]["passed"] or ro_hits:
                    status = "fail"
                    evidence = [text_checks[2][1]]

        checks_out.append({"id": cid, "status": status, "evidence": evidence})

    return checks_out, material_defects


def execute_run(
    *,
    repo_root: Path,
    exp_dir: Path,
    experiment_id: str,
    case: dict[str, Any],
    model_cfg: dict[str, Any],
    cli_version: str,
    condition: str,
    condition_file: Path,
    replicate: int,
    source_snapshot_id: str,
    timeout_seconds: int,
    child_max_rss_mb: int = DEFAULT_CHILD_MAX_RSS_MB,
) -> dict[str, Any]:
    """Execute one complete (single- or multi-stage) benchmark run in an isolated workspace."""
    case_id = case["case_id"]
    model_id = model_cfg["id"]
    run_id = f"{experiment_id}__{model_id}__{case_id}__{condition}__r{replicate}"
    art_dir = exp_dir / "artifacts" / run_id
    art_dir.mkdir(parents=True, exist_ok=True)

    if condition in CM1_CONDITION_VARIANTS:
        # Deliver the identical neutral standing prompt across all 3 comment-ablation arms
        # so the only manipulated variable is the workspace comment profile.
        condition_text = BASELINE_INSTRUCTION
    else:
        condition_text = condition_file.read_text(encoding="utf-8")
    write_agents_md = model_cfg["cli"] in ("codex", "agy")
    workdir, initial_hashes = prepare_clean_workspace(
        repo_root,
        case,
        condition_text,
        write_agents_md=write_agents_md,
        run_id=run_id,
        condition=condition,
    )
    diff_source_root = (
        repo_root / COMMENT_ABLATION_CASES[case_id]["source_root"]
        / CM1_CONDITION_VARIANTS.get(condition, "comment_traps")
        if case_id in COMMENT_ABLATION_CASES
        else None
    )
    isolated_home: Path | None = None
    isolated_codex_home: Path | None = None
    scrub_paths: list[Path] = []
    if model_cfg["cli"] == "codex":
        try:
            isolated_home, isolated_codex_home = prepare_isolated_codex_home(repo_root, run_id)
            if isolated_codex_home.resolve().is_relative_to(workdir.resolve()):
                raise RuntimeError(f"isolated CODEX_HOME {isolated_codex_home} must lie outside workdir {workdir}")
            scrub_paths = [isolated_home, isolated_codex_home]
        except Exception:
            shutil.rmtree(workdir, ignore_errors=True)
            if isolated_home is not None:
                shutil.rmtree(isolated_home, ignore_errors=True)
            raise

    prompts = case["lineage_steps"] if "lineage_steps" in case else [case["prompt"]]
    stage_artifacts: list[dict[str, Any]] = []
    stage_grader_reports: dict[int, tuple[dict[str, Any], str]] = {}
    stage_text_checks: dict[int, tuple[dict[str, Any], str]] = {}
    workspace_changes_by_stage: dict[int, dict[str, Any]] = {}
    all_artifact_paths: set[str] = set()
    material_defects: list[str] = []

    session_id: str | None = None
    final_status = "completed"
    failure_notes: list[str] = []
    failure_evidence: list[str] = []
    total_tokens_sum = 0
    saw_tokens = False
    cost_sum = 0.0
    saw_cost = False
    observed_model_version = f"{model_id} (unavailable)"
    last_stage_rel: str | None = None

    try:
        for stage_idx, prompt in enumerate(prompts, start=1):
            trace_path = art_dir / f"stage-{stage_idx}-trace.log"
            res = _invoke_stage(
                model_cfg=model_cfg,
                condition_text=condition_text,
                prompt=prompt,
                workdir=workdir,
                stage_idx=stage_idx,
                session_id=session_id,
                trace_log_path=trace_path,
                timeout_seconds=timeout_seconds,
                child_max_rss_mb=child_max_rss_mb,
                repo_root=repo_root,
                codex_home=isolated_codex_home,
                isolated_home=isolated_home,
            )
            trace_rel = str(trace_path.relative_to(repo_root)).replace("\\", "/")
            all_artifact_paths.add(trace_rel)

            if res.get("session_id"):
                session_id = res["session_id"]
            if res.get("observed_model"):
                observed_model_version = res["observed_model"]
            if isinstance(res.get("total_tokens"), int):
                if model_cfg["cli"] in ("agy", "claude"):
                    # Both agy transcripts and claude --resume JSON report cumulative session totals.
                    total_tokens_sum = res["total_tokens"]
                else:
                    total_tokens_sum += res["total_tokens"]
                saw_tokens = True
            if isinstance(res.get("cost_usd"), (int, float)):
                if model_cfg["cli"] == "claude":
                    cost_sum = float(res["cost_usd"])
                else:
                    cost_sum += float(res["cost_usd"])
                saw_cost = True
            if res.get("downgraded_models"):
                material_defects.append(
                    f"CRITICAL: Fable 5.2 silent downgrade at stage {stage_idx} to {res['downgraded_models']}"
                )

            changes = snapshot_workspace_changes(workdir, initial_hashes)
            workspace_changes_by_stage[stage_idx] = changes

            if res["status"] != "completed":
                final_status = res["status"]
                failure_notes.append(f"stage {stage_idx}: {res.get('error', 'unknown error')}")
                failure_evidence.append(trace_rel)
                break

            # Save stage response bundle as immutable artifact.
            stage_md = art_dir / f"stage-{stage_idx}.md"
            stage_rel = str(stage_md.relative_to(repo_root)).replace("\\", "/")
            candidate_note = ""
            if case_id in CODING_PRIMARY_FIXTURES:
                cand_file = art_dir / f"stage-{stage_idx}-candidate.py"
                extracted, how = extract_coding_candidate(
                    case_id, workdir, initial_hashes, res["text"], cand_file
                )
                candidate_note = f"\n\n## Captured Coding Candidate ({how})\n"
                if extracted is not None:
                    cand_rel = str(extracted.relative_to(repo_root)).replace("\\", "/")
                    all_artifact_paths.add(cand_rel)
                    candidate_note += f"- Path: `{cand_rel}`\n"
                    grader_out = art_dir / f"stage-{stage_idx}-grader.json"
                    report = _run_grader(
                        repo_root, case, extracted, stage_idx, workdir, grader_out,
                        child_max_rss_mb=child_max_rss_mb,
                    )
                    if report is not None:
                        grader_rel = str(grader_out.relative_to(repo_root)).replace("\\", "/")
                        all_artifact_paths.add(grader_rel)
                        stage_grader_reports[stage_idx] = (report, grader_rel)
                        candidate_note += f"- Automated grader (`{grader_rel}`): passed={report.get('passed')}\n"
                else:
                    candidate_note += "- No Python candidate file or code block could be extracted.\n"
            elif case_id in WORKSPACE_GRADER_CASES:
                diff_file = art_dir / f"stage-{stage_idx}-workspace.diff"
                _write_workspace_diff(
                    repo_root,
                    case,
                    workdir,
                    changes,
                    diff_file,
                    extra_paths=scrub_paths,
                    source_root=diff_source_root,
                )
                gate_note = ""
                if condition == "gated-structural":
                    from gates import review as _gates_review

                    raw_diff_text = diff_file.read_text(encoding="utf-8")
                    if raw_diff_text.strip() != "(no workspace changes)":
                        gate_report = _gates_review.review_diff(
                            raw_diff_text,
                            repo_root=workdir,
                            allow_test_edit=True,
                            no_budget=True,
                        )
                        gate_text = _gates_review.format_plain_english(gate_report)
                        gate_file = art_dir / f"stage-{stage_idx}-gate-review.txt"
                        gate_file.write_text(
                            sanitize_public_text(
                                gate_text + "\n", repo_root, workdir, extra_paths=scrub_paths
                            ),
                            encoding="utf-8",
                        )
                        gate_rel = str(gate_file.relative_to(repo_root)).replace("\\", "/")
                        all_artifact_paths.add(gate_rel)
                        n_err = len(gate_report["errors"])
                        n_warn = len(gate_report["warnings"])
                        gate_note = f"- Structural gate review (`{gate_rel}`): errors={n_err}, warnings={n_warn}\n"
                        if n_err or n_warn:
                            repair_trace = art_dir / f"stage-{stage_idx}-gate-repair-trace.log"
                            repair_prompt = (
                                "The automated anti-slop structural review gate flagged issues in your stage "
                                f"{stage_idx} changes. Fix every finding cleanly without weakening tests, "
                                "then re-run the workspace verification script:\n\n"
                                f"{gate_text}\n"
                            )
                            repair_res = _invoke_stage(
                                model_cfg=model_cfg,
                                condition_text=condition_text,
                                prompt=repair_prompt,
                                workdir=workdir,
                                stage_idx=max(2, stage_idx + 1),
                                session_id=session_id,
                                trace_log_path=repair_trace,
                                timeout_seconds=timeout_seconds,
                                child_max_rss_mb=child_max_rss_mb,
                                repo_root=repo_root,
                                codex_home=isolated_codex_home,
                                isolated_home=isolated_home,
                            )
                            repair_trace_rel = str(repair_trace.relative_to(repo_root)).replace("\\", "/")
                            all_artifact_paths.add(repair_trace_rel)
                            if repair_res.get("session_id"):
                                session_id = repair_res["session_id"]
                            if repair_res.get("observed_model"):
                                observed_model_version = repair_res["observed_model"]
                            if isinstance(repair_res.get("total_tokens"), int):
                                if model_cfg["cli"] in ("agy", "claude"):
                                    total_tokens_sum = repair_res["total_tokens"]
                                else:
                                    total_tokens_sum += repair_res["total_tokens"]
                                saw_tokens = True
                            if isinstance(repair_res.get("cost_usd"), (int, float)):
                                if model_cfg["cli"] == "claude":
                                    cost_sum = float(repair_res["cost_usd"])
                                else:
                                    cost_sum += float(repair_res["cost_usd"])
                                saw_cost = True
                            if repair_res.get("downgraded_models"):
                                material_defects.append(
                                    f"CRITICAL: Fable 5.2 silent downgrade at stage {stage_idx} gate repair to {repair_res['downgraded_models']}"
                                )
                            changes = snapshot_workspace_changes(workdir, initial_hashes)
                            workspace_changes_by_stage[stage_idx] = changes
                            if repair_res["status"] != "completed":
                                final_status = repair_res["status"]
                                failure_notes.append(
                                    f"stage {stage_idx} gate repair: {repair_res.get('error', 'unknown error')}"
                                )
                                failure_evidence.append(repair_trace_rel)
                                break
                            _write_workspace_diff(
                                repo_root,
                                case,
                                workdir,
                                changes,
                                diff_file,
                                extra_paths=scrub_paths,
                                source_root=diff_source_root,
                            )
                            gate_note += f"- Automated gate repair turn completed (`{repair_trace_rel}`)\n"
                diff_rel = str(diff_file.relative_to(repo_root)).replace("\\", "/")
                all_artifact_paths.add(diff_rel)
                response_file: Path | None = None
                if case_id in ("B2", "RW3", "SE1", "SE3", "SE4") and stage_idx == 2 and res["text"].strip():
                    response_file = art_dir / f"stage-{stage_idx}-response.txt"
                    response_file.write_text(res["text"] + "\n", encoding="utf-8")
                    all_artifact_paths.add(str(response_file.relative_to(repo_root)).replace("\\", "/"))
                grader_out = art_dir / f"stage-{stage_idx}-grader.json"
                report = _run_workspace_grader(
                    repo_root, case, workdir, stage_idx, grader_out,
                    response_file=response_file, child_max_rss_mb=child_max_rss_mb,
                    condition=condition,
                )
                if response_file is not None and response_file.is_file():
                    response_file.write_text(
                        sanitize_public_text(
                            res["text"] + "\n", repo_root, workdir, extra_paths=scrub_paths
                        ),
                        encoding="utf-8",
                    )
                candidate_note = f"\n\n## Workspace Grader & Diff\n- Workspace diff: `{diff_rel}`\n{gate_note}"
                if report is not None:
                    grader_rel = str(grader_out.relative_to(repo_root)).replace("\\", "/")
                    all_artifact_paths.add(grader_rel)
                    stage_grader_reports[stage_idx] = (report, grader_rel)
                    candidate_note += f"- Automated grader (`{grader_rel}`): passed={report.get('passed')}\n"

            word_cap = TEXT_WORD_CAPS.get(case_id, {}).get(stage_idx)
            if word_cap is not None:
                strict_cred = case_id in STRICT_CREDIBILITY_TEXT_CASES
                tc = inspect_text_constraints(
                    res["text"],
                    max_words=word_cap,
                    check_closers=strict_cred,
                    check_emojis=strict_cred,
                )
                stage_text_checks[stage_idx] = (tc, stage_rel)
                extra_lines = (
                    f"- Closer hit: {tc['has_closer']}\n"
                    f"- Decorative emoji hit: {tc['has_decorative_emoji']}\n"
                    if strict_cred
                    else ""
                )
                candidate_note += (
                    f"\n## Deterministic Text Constraints\n"
                    f"- Lexical words: {tc['lexical_words']}/{word_cap} (raw={tc['raw_words']})\n"
                    f"- Opener hit: {tc['has_opener']}\n"
                    f"{extra_lines}"
                    f"- Word-count postscript hit: {tc['has_wordcount_footer']}\n"
                    f"- Passed: {tc['passed']}\n"
                )

            stage_content = (
                f"# {run_id} — Stage {stage_idx}/{len(prompts)}\n\n"
                f"- Timestamp UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
                f"- Model: {model_cfg['provider']}/{model_id} (reasoning={model_cfg['reasoning']}, "
                f"observed={observed_model_version})\n"
                f"- Condition: {condition}\n"
                f"- Elapsed seconds: {res['elapsed_s']:.2f}\n"
                f"- Workspace modified: {changes['modified']}\n"
                f"- Workspace created: {changes['created']}\n"
                f"- Workspace deleted: {changes['deleted']}\n\n"
                f"## Prompt\n\n{prompt}\n\n"
                f"## Raw Model Output\n\n{res['text']}\n"
                f"{candidate_note}"
            )
            stage_md.write_text(
                sanitize_public_text(stage_content, repo_root, workdir, extra_paths=scrub_paths),
                encoding="utf-8",
            )
            stage_digest = benchmark.sha256(stage_md)
            stage_artifacts.append({"stage": stage_idx, "path": stage_rel, "sha256": stage_digest})
            all_artifact_paths.add(stage_rel)
            last_stage_rel = stage_rel
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        if isolated_home is not None:
            shutil.rmtree(isolated_home, ignore_errors=True)

    checks_out, extra_defects = _auto_populate_checks(
        case, stage_grader_reports, workspace_changes_by_stage, stage_text_checks
    )
    material_defects.extend(extra_defects)

    # For non-completed runs, keep checks not_run unless automated grader already produced evidence.
    if final_status != "completed":
        if not failure_evidence:
            fallback_ev = art_dir / "failure-note.txt"
            fallback_ev.write_text(
                sanitize_public_text(
                    "\n".join(failure_notes) or "Run failed without trace.\n",
                    repo_root,
                    workdir,
                    extra_paths=scrub_paths,
                ),
                encoding="utf-8",
            )
            ev_rel = str(fallback_ev.relative_to(repo_root)).replace("\\", "/")
            failure_evidence.append(ev_rel)
            all_artifact_paths.add(ev_rel)

    cond_rel = str(condition_file.relative_to(repo_root)).replace("\\", "/")
    artifact_hashes = {
        rel: benchmark.sha256(repo_root / rel)
        for rel in sorted(all_artifact_paths)
    }

    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": experiment_id,
        "case_id": case_id,
        "case_version": case["version"],
        "case_revision": benchmark.canonical_json_sha256(case),
        "condition": condition,
        "condition_source": cond_rel,
        "condition_revision": benchmark.sha256(condition_file),
        "model": {
            "provider": model_cfg["provider"],
            "id": model_id,
            "version": FROZEN_MODEL_VERSIONS.get(model_id, f"{model_id} (unavailable)"),
            "reasoning": model_cfg["reasoning"],
        },
        "environment": {
            "harness": model_cfg["harness"],
            "version": cli_version,
            "tools_id": f"{model_cfg['harness']}-isolated-workspace",
            "source_snapshot_id": source_snapshot_id,
            "budget_id": f"stage-timeout-{timeout_seconds}s",
            "baseline_id": "isolated-tmp-clean-workspace-v1",
        },
        "replicate": replicate,
        "synthetic": False,
        "status": final_status,
        "checks": checks_out,
        "material_defects": material_defects,
        "output_artifact": last_stage_rel if final_status == "completed" else None,
        "artifact_hashes": artifact_hashes,
        "metrics": {
            "cost_usd": round(cost_sum, 6) if saw_cost else None,
            "review_minutes": None,
            "repair_minutes": None,
            "total_tokens": total_tokens_sum if saw_tokens else None,
            "repair_capped": False,
        },
    }
    if "lineage_steps" in case and stage_artifacts:
        record["stage_artifacts"] = stage_artifacts
    if final_status != "completed":
        record["notes"] = sanitize_public_text(
            "; ".join(failure_notes) or f"run ended with status={final_status}",
            repo_root,
            workdir,
            extra_paths=scrub_paths,
        )
        record["evidence"] = sorted(set(failure_evidence))

    return record


def build_execution_schedule(
    models: list[str],
    case_ids: list[str],
    conditions: list[str],
    replicates: int,
    seed: int,
) -> dict[str, list[tuple[str, str, int]]]:
    """Build per-model randomized (case_id, condition, replicate) execution queues."""
    rng = random.Random(seed)
    per_model: dict[str, list[tuple[str, str, int]]] = {}
    for model_id in models:
        queue: list[tuple[str, str, int]] = []
        for rep in range(1, replicates + 1):
            for case_id in case_ids:
                cond_order = list(conditions)
                rng.shuffle(cond_order)
                for cond in cond_order:
                    queue.append((case_id, cond, rep))
        per_model[model_id] = queue
    return per_model


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run isolated multi-model comparative benchmarks for anti-slop."
    )
    parser.add_argument("--experiment-id", required=True, help="Experiment folder name under runs-local/")
    parser.add_argument(
        "--cases",
        nargs="+",
        default=["C2", "S1", "T1"],
        help="Case IDs to execute (default: C2 S1 T1 smoke calibration set)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=list(DEFAULT_MODELS.keys()),
        choices=list(DEFAULT_MODELS.keys()),
        help="Model IDs to execute (default: all 5 pilot models)",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=list(DEFAULT_CONDITIONS),
        help="Conditions to compare (default: baseline core-rules-v0.1.0 core-rules-v0.2.0)",
    )
    parser.add_argument("--replicates", type=int, default=1, help="Replicates per (model, case, condition)")
    parser.add_argument("--seed", type=int, default=20261124, help="RNG seed for randomized condition ordering")
    parser.add_argument("--timeout", type=int, default=480, help="Per-stage CLI timeout in seconds (default: 480)")
    parser.add_argument("--output-root", type=Path, default=Path("runs-local"), help="Base output directory")
    parser.add_argument("--parallel-models", action="store_true", help="Run different models concurrently")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f"Maximum concurrent model workers when --parallel-models is set (default: {DEFAULT_MAX_WORKERS})",
    )
    parser.add_argument(
        "--child-max-rss-mb",
        type=int,
        default=DEFAULT_CHILD_MAX_RSS_MB,
        help=f"Kill runaway child processes exceeding this RSS limit in MB (0 disables, default: {DEFAULT_CHILD_MAX_RSS_MB})",
    )
    parser.add_argument("--resume", action="store_true", help="Skip run_ids already present in runs.jsonl")
    parser.add_argument("--dry-run", action="store_true", help="Freeze conditions and print schedule without calling models")
    args = parser.parse_args(argv)

    if args.max_workers < 1:
        print("ERROR: --max-workers must be >= 1", file=sys.stderr)
        return 2
    if args.child_max_rss_mb < 0:
        print("ERROR: --child-max-rss-mb must be >= 0", file=sys.stderr)
        return 2

    root = REPO_ROOT
    cases_map = benchmark.load_cases(root / "benchmarks" / "cases", root)
    by_case_id = {case_id: case for (case_id, _ver), case in cases_map.items()}
    for cid in args.cases:
        if cid not in by_case_id:
            print(f"ERROR: unknown case_id {cid!r}", file=sys.stderr)
            return 2

    cm_conds = [c for c in args.conditions if c in CM1_CONDITION_VARIANTS]
    if cm_conds and any(cid not in COMMENT_ABLATION_CASES for cid in args.cases):
        print(
            f"ERROR: comment-ablation conditions ({', '.join(cm_conds)}) can only be used with --cases CM1 or CM2",
            file=sys.stderr,
        )
        return 2

    exp_dir = (args.output_root if args.output_root.is_absolute() else root / args.output_root) / args.experiment_id
    exp_dir.mkdir(parents=True, exist_ok=True)
    cond_files = freeze_conditions(
        root, exp_dir / "conditions", args.conditions, models=args.models, cases=args.cases
    )

    # Pin exact commit SHA of the repo fixtures as source_snapshot_id.
    head_proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    source_snapshot_id = f"git-{head_proc.stdout.strip() or 'working-tree'}"

    cli_versions = {
        model_id: _detect_cli_version(DEFAULT_MODELS[model_id]["cli"])
        for model_id in args.models
    }
    schedule = build_execution_schedule(args.models, args.cases, args.conditions, args.replicates, args.seed)

    runs_jsonl = exp_dir / "runs.jsonl"
    existing_ids: set[str] = set()
    if args.resume and runs_jsonl.is_file():
        for line in runs_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing_ids.add(json.loads(line)["run_id"])

    manifest = {
        "experiment_id": args.experiment_id,
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_snapshot_id": source_snapshot_id,
        "seed": args.seed,
        "timeout_seconds": args.timeout,
        "max_workers": args.max_workers,
        "child_max_rss_mb": args.child_max_rss_mb,
        "cases": args.cases,
        "models": args.models,
        "conditions": {
            cond: {
                "path": _rel_or_str(path, root),
                "sha256": benchmark.sha256(path),
            }
            for cond, path in cond_files.items()
        },
        "cli_versions": cli_versions,
        "schedule": {
            m: [{"case_id": c, "condition": cond, "replicate": r} for c, cond, r in q]
            for m, q in schedule.items()
        },
    }
    (exp_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total_planned = sum(len(q) for q in schedule.values())
    print(
        f"Experiment {args.experiment_id}: {len(args.models)} models x {len(args.cases)} cases "
        f"x {len(args.conditions)} conditions x {args.replicates} rep = {total_planned} runs "
        f"(existing skipped: {len(existing_ids)})",
        flush=True,
    )
    if args.dry_run:
        print(json.dumps(manifest, indent=2))
        return 0

    def _run_model_queue(model_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        mcfg = DEFAULT_MODELS[model_id]
        for case_id, cond, rep in schedule[model_id]:
            run_id = f"{args.experiment_id}__{model_id}__{case_id}__{cond}__r{rep}"
            if run_id in existing_ids:
                print(f"[skip] {run_id}", flush=True)
                continue
            print(f"[start] {run_id}", flush=True)
            rec = execute_run(
                repo_root=root,
                exp_dir=exp_dir,
                experiment_id=args.experiment_id,
                case=by_case_id[case_id],
                model_cfg=mcfg,
                cli_version=cli_versions[model_id],
                condition=cond,
                condition_file=resolve_condition_file(cond_files, cond, model_id),
                replicate=rep,
                source_snapshot_id=source_snapshot_id,
                timeout_seconds=args.timeout,
                child_max_rss_mb=args.child_max_rss_mb,
            )
            with _WRITE_LOCK:
                with runs_jsonl.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, allow_nan=False) + "\n")
            print(
                f"[done] {run_id} status={rec['status']} "
                f"tokens={rec['metrics']['total_tokens']} cost={rec['metrics']['cost_usd']} "
                f"defects={len(rec['material_defects'])}",
                flush=True,
            )
            results.append(rec)
        return results

    if args.parallel_models and len(args.models) > 1:
        worker_count = min(args.max_workers, len(args.models))
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = {pool.submit(_run_model_queue, m): m for m in args.models}
            for fut in as_completed(futures):
                fut.result()
    else:
        for model_id in args.models:
            _run_model_queue(model_id)

    # Validate the collected JSONL file immediately via scripts/benchmark.py.
    val_rc = benchmark.main(["validate", str(runs_jsonl)])
    return val_rc


if __name__ == "__main__":
    raise SystemExit(main())
