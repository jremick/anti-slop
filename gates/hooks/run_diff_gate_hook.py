#!/usr/bin/env python3
"""Thin CLI hook adapter wrapping gates/diff_check.py for agent lifecycles.

Works both per-repository and as a global user hook across Claude Code,
Antigravity, and Codex CLI with zero external dependencies (stdlib Python only):

  1. PreToolUse (`--stdin-tool-json`): reads a Claude Code, Codex, or
     Antigravity JSON tool-invocation payload on stdin and blocks unauthorized
     edits under `tests/` unless `--allow-test-edit` or
     `ANTI_SLOP_ALLOW_TEST_EDIT=1` is set.
  2. Stop / post-edit diff gate (default): resolves the git repository root
     from `--repo-root` or stdin JSON (`cwd` / `workspacePaths[0]`), collects
     staged + unstaged `git diff`, and runs `gates/diff_check.py`.

Harness output contracts (`--harness {auto,claude,codex,antigravity}`):
  - Claude Code / Codex: exit 0 on pass; exit 2 + concise remediation on stderr
    on policy violation (exit 1 is reserved for non-blocking hook errors).
  - Antigravity (explicit `--harness antigravity` or auto-detected via
    camelCase stdin keys `hookEventName` / `toolCall` / `continuationActive` /
    `terminationReason` / `workspacePaths`): JSON on stdout with exit 0:
      * PreToolUse: `{"decision": "allow"}` or `{"decision": "deny", "reason": "..."}`
      * Stop: `{"decision": "allow"}` or `{"decision": "continue", "reason": "..."}`

Built-in global-safety guards:
  - Benchmark isolation: immediate no-op when `ANTI_SLOP_BENCHMARK_SUBJECT=1`
    or when the target directory lies under an `antislop_*` temp workspace.
  - Non-git graceful no-op: in diff-gate mode, non-git directories pass cleanly.
  - Anti-loop Stop guard: immediately allows stop when `stop_hook_active` is
    true (Claude/Codex), `continuationActive` is true (Antigravity), or
    `terminationReason` is present and not `"NO_TOOL_CALL"`.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


HARNESS_CHOICES = ("auto", "claude", "codex", "antigravity")
INSTALL_CHOICES = ("claude", "antigravity", "codex")

CLAUDE_PRETOOL_MATCHER = "Edit|Write|MultiEdit|NotebookEdit"
ANTIGRAVITY_PRETOOL_MATCHER = (
    "edit_file|write_file|write_to_file|replace_file_content|multi_replace_file_content"
)
CODEX_EDIT_MATCHER = "apply_patch|edit_file|write_file|Edit|Write"

ANTIGRAVITY_SCHEMA_KEYS = frozenset({
    "hookEventName",
    "toolCall",
    "continuationActive",
    "terminationReason",
    "workspacePaths",
})

READ_ONLY_TOOLS = frozenset({
    "read",
    "read_file",
    "view_file",
    "view_file_outline",
    "view_code_item",
    "glob",
    "grep",
    "grep_search",
    "find_by_name",
    "ls",
    "list_dir",
})

PATH_KEYS = (
    "file_path",
    "path",
    "target_file",
    "TargetFile",
    "Path",
    "AbsolutePath",
    "FilePath",
    "TargetPath",
    "DestinationPath",
    "OldPath",
    "NewPath",
    "notebook_path",
    "destination",
    "dest",
    "new_path",
    "old_path",
)

CONTAINER_KEYS = ("tool_input", "input", "arguments", "args", "parameters")

PATCH_PATH_RE = re.compile(
    r"^(?:(?:\+\+\+|---)\s+(?:[ab]/)?|\*\*\*\s+(?:(?:Update|Add|Delete)\s+File|Move\s+to):\s+)(.+?)(?:\t.*)?$"
)


def _extract_patch_paths(patch_text: str, out: List[str]) -> None:
    for line in patch_text.splitlines():
        m = PATCH_PATH_RE.match(line)
        if m:
            candidate = m.group(1).strip()
            if candidate and candidate != "/dev/null":
                out.append(candidate)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _read_stdin_safely(*, always_read: bool = False) -> str:
    try:
        if not always_read and sys.stdin.isatty():
            return ""
        return sys.stdin.read()
    except OSError:
        return ""


def _parse_stdin_json(raw: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not raw.strip():
        return None, None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if isinstance(parsed, dict):
        return parsed, None
    return None, None


def detect_harness(requested: str, payload: Optional[Dict[str, Any]]) -> str:
    """Resolve effective harness contract from `--harness` and stdin schema."""
    if requested in ("claude", "codex", "antigravity"):
        return requested
    if isinstance(payload, dict) and any(k in payload for k in ANTIGRAVITY_SCHEMA_KEYS):
        return "antigravity"
    return "claude"


def _resolve_target_dir(
    repo_root_arg: Optional[str],
    payload: Optional[Dict[str, Any]],
) -> Path:
    """Resolve target directory from explicit `--repo-root` or stdin JSON `cwd`/`workspacePaths[0]`."""
    if repo_root_arg not in (None, "", "."):
        return Path(str(repo_root_arg)).resolve()
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            return Path(cwd.strip()).resolve()
        ws_paths = payload.get("workspacePaths")
        if isinstance(ws_paths, list):
            for item in ws_paths:
                if isinstance(item, str) and item.strip():
                    return Path(item.strip()).resolve()
    return Path(repo_root_arg or ".").resolve()


def _is_benchmark_subject(
    target_dir: Path,
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """Return True when running inside an isolated anti-slop benchmark subject."""
    if _env_truthy("ANTI_SLOP_BENCHMARK_SUBJECT"):
        return True
    candidates: List[Path] = [target_dir]
    if isinstance(payload, dict):
        cwd = payload.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            candidates.append(Path(cwd.strip()))
        ws_paths = payload.get("workspacePaths")
        if isinstance(ws_paths, list):
            for ws in ws_paths:
                if isinstance(ws, str) and ws.strip():
                    candidates.append(Path(ws.strip()))
    for cand in candidates:
        if cand.name.startswith("antislop_") or any(
            part.startswith("antislop_") for part in cand.parts
        ):
            return True
    return False


def _should_allow_stop_immediately(payload: Optional[Dict[str, Any]]) -> bool:
    """Anti-loop Stop guard for Claude Code, Codex, and Antigravity."""
    if not isinstance(payload, dict):
        return False
    if payload.get("stop_hook_active") is True:
        return True
    if payload.get("continuationActive") is True:
        return True
    if "terminationReason" in payload and payload.get("terminationReason") != "NO_TOOL_CALL":
        return True
    return False


def _resolve_git_toplevel(target_dir: Path) -> Optional[Path]:
    """Return resolved git worktree root for target_dir, or None if not in a git repo."""
    if not target_dir.is_dir():
        return None
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=target_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    top = proc.stdout.strip()
    return Path(top).resolve() if top else None


def _normalize_candidate_path(raw: str, repo_root: Path) -> str:
    cleaned = raw.strip().replace("\\", "/")
    if cleaned in ("", "/dev/null"):
        return ""
    candidate = Path(cleaned)
    if candidate.is_absolute():
        try:
            rel = candidate.resolve().relative_to(repo_root.resolve())
            cleaned = str(rel).replace("\\", "/")
        except ValueError:
            cleaned = str(candidate).replace("\\", "/")
    if cleaned.startswith("a/") or cleaned.startswith("b/"):
        cleaned = cleaned[2:]
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _is_test_path(norm_path: str) -> bool:
    if not norm_path:
        return False
    return norm_path == "tests" or norm_path.startswith("tests/") or "/tests/" in norm_path


def _extract_paths_from_obj(obj: Any, out: List[str]) -> None:
    if isinstance(obj, str):
        if obj.strip():
            out.append(obj.strip())
        return
    if isinstance(obj, list):
        for item in obj:
            _extract_paths_from_obj(item, out)
        return
    if not isinstance(obj, dict):
        return

    for key in PATH_KEYS:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            out.append(val.strip())

    for list_key in ("edits", "files", "paths"):
        items = obj.get(list_key)
        if isinstance(items, list):
            _extract_paths_from_obj(items, out)

    for patch_key in ("patch", "diff", "raw_patch", "patch_text"):
        patch_val = obj.get(patch_key)
        if isinstance(patch_val, str):
            _extract_patch_paths(patch_val, out)


def extract_tool_edit_paths(payload: Dict[str, Any]) -> List[str]:
    """Extract target file paths from a PreToolUse JSON payload.

    Supports Claude Code (`tool_name` / `tool_input`), Codex (`tool_name` / `input`),
    and Antigravity (`toolCall.name` / `toolCall.args`). Returns an empty list for
    explicitly read-only tools so read/search calls under `tests/` are never blocked.
    """
    tool_call = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else None
    tool_name = str(
        (tool_call.get("name") if tool_call else None)
        or payload.get("tool_name")
        or payload.get("tool")
        or payload.get("name")
        or ""
    ).strip().lower()
    if tool_name in READ_ONLY_TOOLS:
        return []

    raw_paths: List[str] = []
    sources: List[Dict[str, Any]] = [payload]
    if tool_call is not None:
        sources.append(tool_call)

    for src in sources:
        _extract_paths_from_obj(src, raw_paths)
        for container_key in CONTAINER_KEYS:
            sub = src.get(container_key)
            if isinstance(sub, dict):
                _extract_paths_from_obj(sub, raw_paths)
            elif isinstance(sub, str):
                stripped = sub.strip()
                if stripped.startswith("{"):
                    try:
                        parsed_sub = json.loads(stripped)
                    except json.JSONDecodeError:
                        parsed_sub = None
                    if isinstance(parsed_sub, dict):
                        _extract_paths_from_obj(parsed_sub, raw_paths)
                    else:
                        _extract_patch_paths(sub, raw_paths)
                elif stripped:
                    _extract_patch_paths(sub, raw_paths)

    seen: Set[str] = set()
    unique: List[str] = []
    for item in raw_paths:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def run_pretooluse_check(
    raw_json: str,
    *,
    repo_root: Path,
    allow_test_edit: bool = False,
) -> Tuple[int, str]:
    """Inspect PreToolUse stdin JSON and block unauthorized test edits with code 2."""
    if not raw_json.strip():
        return 0, ""

    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return 1, f"[anti-slop hook] Failed to parse PreToolUse JSON: {exc}"

    if not isinstance(payload, dict):
        return 0, ""

    if allow_test_edit:
        return 0, ""

    blocked: List[str] = []
    for raw_path in extract_tool_edit_paths(payload):
        norm = _normalize_candidate_path(raw_path, repo_root)
        if _is_test_path(norm) and norm not in blocked:
            blocked.append(norm)

    if blocked:
        targets = ", ".join(blocked)
        msg = (
            f"[anti-slop hook] Blocked [DIFF-UNAUTHORIZED-TEST-EDIT]: attempted edit under tests/ ({targets}).\n"
            "Remediation: Fix the production code instead of weakening tests. "
            "Pass --allow-test-edit or set ANTI_SLOP_ALLOW_TEST_EDIT=1 only when test changes are explicitly authorized."
        )
        return 2, msg

    return 0, ""


def _collect_git_diff(repo_root: Path, *, staged_only: bool = False) -> Tuple[int, str, str]:
    """Collect unified git diff (staged + unstaged) from repo_root."""
    if staged_only:
        proc = subprocess.run(
            ["git", "diff", "--cached"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    head_check = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head_check.returncode == 0:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr

    # Unborn branch (no commits yet): combine staged + unstaged diffs.
    staged = subprocess.run(
        ["git", "diff", "--cached"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if staged.returncode != 0:
        return staged.returncode, "", staged.stderr
    unstaged = subprocess.run(
        ["git", "diff"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if unstaged.returncode != 0:
        return unstaged.returncode, "", unstaged.stderr
    chunks = [chunk for chunk in (staged.stdout, unstaged.stdout) if chunk.strip()]
    return 0, "\n".join(chunks), ""


def _format_remediation(payload: Dict[str, Any]) -> str:
    errors = payload.get("errors") or []
    lines = [f"[anti-slop hook] Blocked by gates/diff_check.py ({len(errors)} error(s)):"]
    for item in errors:
        code = item.get("code", "DIFF-ERROR")
        loc = ""
        if "file" in item:
            loc = f"{item['file']}:{item['line']}: " if "line" in item else f"{item['file']}: "
        message = item.get("message", "diff gate violation")
        remediation = item.get("remediation", "Resolve the violation and re-run.")
        lines.append(f"- [{code}] {loc}{message} -> {remediation}")
    return "\n".join(lines)


def run_diff_gate(
    *,
    repo_root: Path,
    diff_text: Optional[str] = None,
    staged_only: bool = False,
    allow_test_edit: bool = False,
    no_budget: bool = False,
    max_net_loc: Optional[int] = None,
    max_files: Optional[int] = None,
    learned_rules: Optional[Path | str] = None,
) -> Tuple[int, str]:
    """Run gates/diff_check.py on git diff and map violations to code 2."""
    toplevel = _resolve_git_toplevel(repo_root)
    if diff_text is None:
        if toplevel is None:
            return 0, ""
        repo_root = toplevel
        rc, collected, git_err = _collect_git_diff(repo_root, staged_only=staged_only)
        if rc != 0:
            detail = git_err.strip() or f"git diff exited {rc}"
            return 1, f"[anti-slop hook] Unable to read git diff in {repo_root}: {detail}"
        diff_text = collected
    elif toplevel is not None:
        repo_root = toplevel

    if not diff_text.strip():
        return 0, ""

    diff_check_script = Path(__file__).resolve().parents[1] / "diff_check.py"
    cmd = [
        sys.executable,
        "-B",
        str(diff_check_script),
        "--diff",
        "-",
        "--repo-root",
        str(repo_root),
        "--json",
    ]
    if allow_test_edit:
        cmd.append("--allow-test-edit")
    if no_budget:
        cmd.append("--no-budget")
    else:
        if max_net_loc is not None:
            cmd.extend(["--max-net-loc", str(max_net_loc)])
        if max_files is not None:
            cmd.extend(["--max-files", str(max_files)])

    effective_learned_rules: Optional[Path] = None
    if learned_rules is not None:
        effective_learned_rules = Path(learned_rules)
    else:
        default_store = repo_root / ".anti-slop" / "learned" / "rules.json"
        if default_store.is_file():
            effective_learned_rules = default_store
    if effective_learned_rules is not None:
        cmd.extend(["--learned-rules", str(effective_learned_rules)])

    proc = subprocess.run(
        cmd,
        input=diff_text,
        capture_output=True,
        text=True,
        check=False,
    )

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        if proc.returncode == 0:
            return 0, ""
        detail = (proc.stderr or proc.stdout).strip() or f"diff_check.py exited {proc.returncode}"
        return 1, f"[anti-slop hook] Diff gate error (non-blocking): {detail}"

    if not isinstance(payload, dict):
        if proc.returncode == 0:
            return 0, ""
        return 1, f"[anti-slop hook] Diff gate error (non-blocking): unexpected JSON payload from diff_check.py"

    if "error" in payload and "errors" not in payload:
        return 1, f"[anti-slop hook] Diff gate error (non-blocking): {payload['error']}"

    if not payload.get("ok") or proc.returncode != 0:
        return 2, _format_remediation(payload)

    warnings = payload.get("warnings") or []
    if warnings:
        warn_lines = [
            f"[anti-slop hook] warning [{w.get('code', 'DIFF-WARN')}]: {w.get('message', '')}"
            for w in warnings
        ]
        return 0, "\n".join(warn_lines)

    return 0, ""


UVX_HOOK_BASE_COMMAND = "uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook"

EPHEMERAL_CACHE_MARKERS = (
    "/.cache/uv/",
    "/caches/uv/",
    "/uv/cache/",
    "/pipx/.cache/",
    "/pipx/shared/",
)


def _is_ephemeral_cache_path(path: Path) -> bool:
    """Return True if path lives in an ephemeral uvx/uv/pipx cache directory."""
    candidates: List[Path] = [path]
    try:
        resolved = path.resolve()
        if resolved != path:
            candidates.append(resolved)
    except OSError:
        pass

    uv_cache_raw = os.environ.get("UV_CACHE_DIR", "").strip()
    uv_cache_dir: Optional[Path] = None
    if uv_cache_raw:
        try:
            uv_cache_dir = Path(uv_cache_raw).resolve()
        except OSError:
            uv_cache_dir = None

    for cand in candidates:
        if any(part == "archive-v0" for part in cand.parts):
            return True
        norm = cand.as_posix().lower()
        if any(marker in norm for marker in EPHEMERAL_CACHE_MARKERS):
            return True
        if uv_cache_dir is not None:
            try:
                cand.resolve().relative_to(uv_cache_dir)
                return True
            except (OSError, ValueError):
                pass
    return False


def _find_permanent_console_script(name: str = "anti-slop-hook") -> Optional[Path]:
    """Find a non-ephemeral executable on PATH (skipping uvx archive-v0 cache bins)."""
    path_env = os.environ.get("PATH", "")
    for raw_dir in path_env.split(os.pathsep):
        if not raw_dir:
            continue
        candidate = Path(raw_dir) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            if not _is_ephemeral_cache_path(candidate):
                return candidate
    return None


def _resolve_portable_hook_base_command() -> str:
    """Prefer permanent `anti-slop-hook` on PATH; fall back to uvx (if ephemeral) or `python3 -B <script>`."""
    if _find_permanent_console_script("anti-slop-hook") is not None:
        return "anti-slop-hook"
    script_path = Path(__file__).resolve()
    if _is_ephemeral_cache_path(script_path) or _is_ephemeral_cache_path(Path(sys.executable)):
        return UVX_HOOK_BASE_COMMAND
    return f"python3 -B {shlex.quote(str(script_path))}"


def _install_target_path(target: str, home: Optional[Path] = None) -> Path:
    base_home = home if home is not None else Path.home()
    if target == "claude":
        return base_home / ".claude" / "settings.json"
    if target == "antigravity":
        return base_home / ".gemini" / "config" / "hooks.json"
    if target == "codex":
        return base_home / ".codex" / "hooks.json"
    raise ValueError(f"Unsupported install target: {target}")


def _is_antislop_hook_command(command: Any) -> bool:
    if not isinstance(command, str):
        return False
    return "anti-slop-hook" in command or "run_diff_gate_hook.py" in command


def _build_install_commands(
    target: str,
    *,
    base_cmd: str,
    allow_test_edit: bool = False,
) -> Tuple[str, str]:
    suffix = " --allow-test-edit" if allow_test_edit else ""
    pre_cmd = f"{base_cmd} --harness {target} --stdin-tool-json{suffix}"
    diff_cmd = f"{base_cmd} --harness {target} --no-budget{suffix}"
    return pre_cmd, diff_cmd


def _upsert_grouped_hook_event(
    existing_entries: List[Any],
    *,
    matcher: Optional[str],
    command: str,
) -> Tuple[List[Any], bool]:
    """Insert or update a single anti-slop hook entry without duplicating or disturbing other hooks."""
    updated: List[Any] = []
    found_existing = False

    for raw_entry in copy.deepcopy(existing_entries):
        if not isinstance(raw_entry, dict):
            updated.append(raw_entry)
            continue
        sub_hooks = raw_entry.get("hooks")
        if isinstance(sub_hooks, list):
            new_sub: List[Any] = []
            had_antislop = False
            for handler in sub_hooks:
                if isinstance(handler, dict) and _is_antislop_hook_command(handler.get("command")):
                    had_antislop = True
                    if not found_existing:
                        found_existing = True
                        patched = copy.deepcopy(handler)
                        patched["type"] = "command"
                        patched["command"] = command
                        new_sub.append(patched)
                    # Drop any accidental duplicate anti-slop handlers.
                else:
                    new_sub.append(handler)
            if had_antislop and not new_sub:
                continue
            raw_entry["hooks"] = new_sub
            updated.append(raw_entry)
        elif _is_antislop_hook_command(raw_entry.get("command")):
            if not found_existing:
                found_existing = True
                raw_entry["type"] = "command"
                raw_entry["command"] = command
                updated.append(raw_entry)
        else:
            updated.append(raw_entry)

    if not found_existing:
        new_entry: Dict[str, Any] = {
            "hooks": [{"type": "command", "command": command}],
        }
        if matcher is not None:
            new_entry = {
                "matcher": matcher,
                "hooks": [{"type": "command", "command": command}],
            }
        updated.append(new_entry)

    return updated, updated != existing_entries


def _antigravity_entry_contains_antislop(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    for event_val in entry.values():
        if not isinstance(event_val, list):
            continue
        for item in event_val:
            if not isinstance(item, dict):
                continue
            if _is_antislop_hook_command(item.get("command")):
                return True
            sub_hooks = item.get("hooks")
            if isinstance(sub_hooks, list):
                for h in sub_hooks:
                    if isinstance(h, dict) and _is_antislop_hook_command(h.get("command")):
                        return True
    return False


def _merge_install_config(
    target: str,
    existing: Dict[str, Any],
    *,
    base_cmd: str,
    allow_test_edit: bool = False,
) -> Tuple[Dict[str, Any], bool]:
    """Return (updated_config, changed) for target CLI without mutating existing."""
    updated: Dict[str, Any] = copy.deepcopy(existing)
    pre_cmd, diff_cmd = _build_install_commands(
        target,
        base_cmd=base_cmd,
        allow_test_edit=allow_test_edit,
    )

    if target in ("claude", "codex"):
        raw_hooks = updated.get("hooks")
        if raw_hooks is None:
            hooks_dict: Dict[str, Any] = {}
            updated["hooks"] = hooks_dict
        elif isinstance(raw_hooks, dict):
            hooks_dict = raw_hooks
        else:
            raise ValueError("Expected top-level 'hooks' field to be a JSON object.")

        if target == "claude":
            events: Tuple[Tuple[str, Optional[str], str], ...] = (
                ("PreToolUse", CLAUDE_PRETOOL_MATCHER, pre_cmd),
                ("Stop", None, diff_cmd),
            )
        else:
            events = (
                ("PreToolUse", CODEX_EDIT_MATCHER, pre_cmd),
                ("PostToolUse", CODEX_EDIT_MATCHER, diff_cmd),
            )

        for event_name, matcher, cmd in events:
            raw_list = hooks_dict.get(event_name)
            if raw_list is None:
                current_list: List[Any] = []
            elif isinstance(raw_list, list):
                current_list = raw_list
            else:
                raise ValueError(f"Expected 'hooks.{event_name}' to be a JSON list.")
            merged_list, _ = _upsert_grouped_hook_event(
                current_list,
                matcher=matcher,
                command=cmd,
            )
            hooks_dict[event_name] = merged_list

        return updated, updated != existing

    if target == "antigravity":
        desired_pre = [
            {
                "matcher": ANTIGRAVITY_PRETOOL_MATCHER,
                "hooks": [
                    {
                        "type": "command",
                        "command": pre_cmd,
                        "timeout": 15,
                    }
                ],
            }
        ]
        desired_stop = [
            {
                "type": "command",
                "command": diff_cmd,
                "timeout": 15,
            }
        ]

        hook_key = "anti-slop-diff-gate"
        if hook_key not in updated:
            for existing_key, existing_val in updated.items():
                if _antigravity_entry_contains_antislop(existing_val):
                    hook_key = existing_key
                    break

        existing_block = updated.get(hook_key)
        if existing_block is None:
            updated[hook_key] = {
                "PreToolUse": desired_pre,
                "Stop": desired_stop,
            }
        elif isinstance(existing_block, dict):
            new_block = copy.deepcopy(existing_block)
            raw_pre = new_block.get("PreToolUse")
            if raw_pre is None:
                new_block["PreToolUse"] = desired_pre
            elif isinstance(raw_pre, list):
                merged_pre, _ = _upsert_grouped_hook_event(
                    raw_pre,
                    matcher=ANTIGRAVITY_PRETOOL_MATCHER,
                    command=pre_cmd,
                )
                for group in merged_pre:
                    if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                        for h in group["hooks"]:
                            if isinstance(h, dict) and h.get("command") == pre_cmd and "timeout" not in h:
                                h["timeout"] = 15
                new_block["PreToolUse"] = merged_pre
            else:
                raise ValueError(f"Expected '{hook_key}.PreToolUse' to be a JSON list.")

            raw_stop = new_block.get("Stop")
            if raw_stop is None:
                new_block["Stop"] = desired_stop
            elif isinstance(raw_stop, list):
                new_stop: List[Any] = []
                found_stop = False
                for handler in raw_stop:
                    if isinstance(handler, dict) and _is_antislop_hook_command(handler.get("command")):
                        if not found_stop:
                            found_stop = True
                            patched = copy.deepcopy(handler)
                            patched["type"] = "command"
                            patched["command"] = diff_cmd
                            patched.setdefault("timeout", 15)
                            new_stop.append(patched)
                    else:
                        new_stop.append(handler)
                if not found_stop:
                    new_stop.append(desired_stop[0])
                new_block["Stop"] = new_stop
            else:
                raise ValueError(f"Expected '{hook_key}.Stop' to be a JSON list.")

            updated[hook_key] = new_block
        else:
            raise ValueError(f"Expected top-level '{hook_key}' entry to be a JSON object.")

        return updated, updated != existing

    raise ValueError(f"Unsupported install target: {target}")


def install_hook(
    target: str,
    *,
    dry_run: bool = False,
    allow_test_edit: bool = False,
    home: Optional[Path] = None,
    base_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """Safely install or update user-level anti-slop hooks for claude, antigravity, or codex."""
    config_path = _install_target_path(target, home=home)
    resolved_cmd = base_cmd or _resolve_portable_hook_base_command()
    existing_data: Dict[str, Any] = {}
    file_exists = config_path.exists()

    if file_exists:
        try:
            raw_text = config_path.read_text(encoding="utf-8")
            if raw_text.strip():
                parsed = json.loads(raw_text)
                if not isinstance(parsed, dict):
                    return {
                        "ok": False,
                        "target": target,
                        "config_path": str(config_path),
                        "backup_path": None,
                        "command": resolved_cmd,
                        "changed": False,
                        "dry_run": dry_run,
                        "config": None,
                        "error": f"Expected JSON object in {config_path}, got {type(parsed).__name__}.",
                    }
                existing_data = parsed
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "target": target,
                "config_path": str(config_path),
                "backup_path": None,
                "command": resolved_cmd,
                "changed": False,
                "dry_run": dry_run,
                "config": None,
                "error": f"Failed to parse existing config {config_path}: {exc}",
            }

    try:
        updated_config, changed = _merge_install_config(
            target,
            existing_data,
            base_cmd=resolved_cmd,
            allow_test_edit=allow_test_edit,
        )
    except ValueError as exc:
        return {
            "ok": False,
            "target": target,
            "config_path": str(config_path),
            "backup_path": None,
            "command": resolved_cmd,
            "changed": False,
            "dry_run": dry_run,
            "config": None,
            "error": f"Unsupported config structure in {config_path}: {exc}",
        }

    backup_path: Optional[Path] = (
        config_path.with_name(config_path.name + ".bak-antislop")
        if (file_exists and changed)
        else None
    )

    if changed and not dry_run:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if backup_path is not None:
            shutil.copy2(config_path, backup_path)
        config_path.write_text(json.dumps(updated_config, indent=2) + "\n", encoding="utf-8")

    return {
        "ok": True,
        "target": target,
        "config_path": str(config_path),
        "backup_path": str(backup_path) if backup_path is not None else None,
        "command": resolved_cmd,
        "changed": changed,
        "dry_run": dry_run,
        "config": updated_config,
        "error": None,
    }


def _run_install_cli(target: str, *, dry_run: bool, allow_test_edit: bool) -> int:
    res = install_hook(
        target,
        dry_run=dry_run,
        allow_test_edit=allow_test_edit,
    )
    if not res["ok"]:
        print(f"[anti-slop hook] {res['error']}", file=sys.stderr)
        return 1

    prefix = "[dry-run] " if dry_run else ""
    if not res["changed"]:
        print(f"{prefix}anti-slop hooks already up to date in {res['config_path']} (no changes).")
    elif dry_run:
        backup_note = f" (backup: {res['backup_path']})" if res["backup_path"] else ""
        print(f"{prefix}Would update {res['config_path']}{backup_note}")
        print(f"{prefix}Wired command: {res['command']}")
    else:
        if res["backup_path"]:
            print(f"Backed up existing config to {res['backup_path']}")
        print(f"Installed anti-slop {target} hooks in {res['config_path']}")
        print(f"Wired command: {res['command']}")

    if dry_run:
        print(json.dumps(res["config"], indent=2))

    if isinstance(res.get("command"), str) and res["command"].startswith("uvx "):
        print(
            "Tip: Run `uv tool install git+https://github.com/jremick/anti-slop` then re-run "
            f"`anti-slop-hook --install {target}` for instant startup without uvx resolution."
        )

    if target == "codex":
        print(
            "Note: Codex blocking Stop-hook parity lags Claude Code/Antigravity; "
            "pair hooks with execpolicy rules and CI diff gates (see gates/hooks/codex-execpolicy.example.md)."
        )

    return 0


def _emit_result(*, harness: str, mode: str, code: int, message: str) -> int:
    """Format output and exit status for the active CLI harness contract."""
    if harness == "antigravity":
        if code == 0:
            print(json.dumps({"decision": "allow"}))
            if message:
                print(message, file=sys.stderr)
            return 0
        if code == 2:
            decision = "deny" if mode == "pretooluse" else "continue"
            print(json.dumps({"decision": decision, "reason": message}))
            return 0
        if message:
            print(message, file=sys.stderr)
        return code

    if message:
        print(message, file=sys.stderr)
    return code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Global-safe CLI hook wrapper around gates/diff_check.py for "
            "Claude Code, Antigravity, and Codex harnesses."
        )
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help=(
            "Repository root for git diff and relative path checks "
            "(default: '.'; falls back to stdin JSON cwd / workspacePaths[0] when '.' or omitted)."
        ),
    )
    parser.add_argument(
        "--harness",
        choices=HARNESS_CHOICES,
        default="auto",
        help="Target CLI hook output contract (default: auto).",
    )
    parser.add_argument(
        "--stdin-tool-json",
        action="store_true",
        help="PreToolUse mode: read tool-invocation JSON from stdin and block unauthorized tests/ edits.",
    )
    parser.add_argument(
        "--diff",
        default=None,
        help="Optional path to a unified diff file instead of running git diff (use '-' for stdin).",
    )
    parser.add_argument(
        "--staged-only",
        action="store_true",
        help="Inspect only staged git changes (`git diff --cached`) instead of staged + unstaged.",
    )
    parser.add_argument(
        "--allow-test-edit",
        action="store_true",
        help="Authorize edits under tests/ (also enabled via ANTI_SLOP_ALLOW_TEST_EDIT=1).",
    )
    parser.add_argument(
        "--no-budget",
        action="store_true",
        help="Disable heuristic --max-net-loc and --max-files diff budgets (block objective defects only).",
    )
    parser.add_argument(
        "--max-net-loc",
        type=int,
        default=None,
        help="Override gates/diff_check.py --max-net-loc budget.",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Override gates/diff_check.py --max-files budget.",
    )
    parser.add_argument(
        "--learned-rules",
        default=None,
        help=(
            "Optional path to an approved anti-slop-learn rules JSON store "
            "(by default, auto-enforces <repo-root>/.anti-slop/learned/rules.json if present)."
        ),
    )
    parser.add_argument(
        "--install",
        choices=INSTALL_CHOICES,
        default=None,
        help=(
            "Install user-level anti-slop hooks for claude (~/.claude/settings.json), "
            "antigravity (~/.gemini/config/hooks.json), or codex (~/.codex/hooks.json) "
            "with automatic *.bak-antislop backup and deduplication."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview --install changes and resulting JSON config without writing to disk.",
    )
    args = parser.parse_args(argv)

    if args.install is not None:
        return _run_install_cli(
            args.install,
            dry_run=args.dry_run,
            allow_test_edit=args.allow_test_edit,
        )

    mode = "pretooluse" if args.stdin_tool_json else "stop"
    raw_stdin = ""
    stdin_payload: Optional[Dict[str, Any]] = None
    if args.stdin_tool_json:
        raw_stdin = _read_stdin_safely(always_read=True)
        stdin_payload, _ = _parse_stdin_json(raw_stdin)
    elif args.diff != "-":
        raw_stdin = _read_stdin_safely(always_read=False)
        stdin_payload, _ = _parse_stdin_json(raw_stdin)

    harness = detect_harness(args.harness, stdin_payload)
    target_dir = _resolve_target_dir(args.repo_root, stdin_payload)

    if _is_benchmark_subject(target_dir, stdin_payload):
        return _emit_result(harness=harness, mode=mode, code=0, message="")

    if mode == "stop" and _should_allow_stop_immediately(stdin_payload):
        return _emit_result(harness=harness, mode=mode, code=0, message="")

    allow_test_edit = args.allow_test_edit or _env_truthy("ANTI_SLOP_ALLOW_TEST_EDIT")

    if args.stdin_tool_json:
        effective_root = _resolve_git_toplevel(target_dir) or target_dir
        code, message = run_pretooluse_check(
            raw_stdin,
            repo_root=effective_root,
            allow_test_edit=allow_test_edit,
        )
    else:
        diff_text: Optional[str] = None
        if args.diff is not None:
            if args.diff == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = Path(args.diff).read_text(encoding="utf-8")
        code, message = run_diff_gate(
            repo_root=target_dir,
            diff_text=diff_text,
            staged_only=args.staged_only,
            allow_test_edit=allow_test_edit,
            no_budget=args.no_budget,
            max_net_loc=args.max_net_loc,
            max_files=args.max_files,
            learned_rules=args.learned_rules,
        )

    return _emit_result(harness=harness, mode=mode, code=code, message=message)


if __name__ == "__main__":
    raise SystemExit(main())
