#!/usr/bin/env python3
"""Live E2E and real-artifact verification CLI (`anti-slop verify` / `anti-slop-verify`).

Closes the gap where coding agents claim completion from mocked unit tests
without running the actual application, API server, or CLI:
  - Recipe mode: boots optional background services with `start_new_session=True`,
    polls readiness (`ready_url`, `ready_port`, or `ready_stdout`), runs observable
    `http`, `cli`, and `file` checks, and tears down every service process group
    (`SIGTERM` -> 2s -> `SIGKILL`) inside `try/finally`.
  - One-shot ad-hoc CLI mode: `--cmd` and/or `--start` + `--http-get` with no
    recipe file required.
  - Tamper-evident verification receipt (`.anti-slop/last-verify.json`) bound to
    `git_head`, `working_tree_sha256`, and a `receipt_sha256` integrity digest,
    verifiable via `--check-receipt`.

Zero third-party dependencies (Python 3.11+ stdlib only; compatible with 3.9+).
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import urllib.error
import urllib.parse
import urllib.request


RECEIPT_SCHEMA_VERSION = 1
VERIFICATION_TIER = "tier1_live_e2e"
DEFAULT_RECIPE_REL = ".anti-slop/verify.json"
DEFAULT_RECEIPT_REL = ".anti-slop/last-verify.json"
TELEMETRY_REL = ".anti-slop/telemetry.jsonl"

DEFAULT_SERVICE_READY_TIMEOUT_S = 20.0
DEFAULT_HTTP_TIMEOUT_S = 10.0
DEFAULT_CLI_TIMEOUT_S = 30.0
TEARDOWN_GRACE_S = 2.0

MAX_SNIPPET_CHARS = 400
MAX_TABLE_CELL_CHARS = 120
MAX_SERVICE_LOG_CHARS = 8000

NON_GIT_IGNORE_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
})


class VerifyConfigError(ValueError):
    """Raised when recipe JSON, CLI flags, or check specs are invalid."""


class ServiceStartupError(RuntimeError):
    """Raised when a background service fails to start or become ready."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_rel_posix(raw: str) -> str:
    cleaned = raw.replace("\\", "/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _truncate(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 3)].rstrip() + "..."


def _sanitize_text(text: str, repo_root: Path) -> str:
    """Strip local workstation paths (repo root and home dir) from snippets."""
    if not text:
        return text
    replacements: List[Tuple[str, str]] = []
    for candidate in (str(repo_root.resolve()), str(repo_root)):
        if candidate and candidate not in ("/", "."):
            replacements.append((candidate, "."))
    try:
        for h in (str(Path.home().resolve()), str(Path.home())):
            if h and h not in ("/", "~"):
                replacements.append((h, "~"))
    except (OSError, RuntimeError):
        pass

    seen: Set[str] = set()
    out = text
    for prefix, token in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if prefix not in seen:
            seen.add(prefix)
            out = out.replace(prefix, token)
    return out


def _relativize_path(path: Path, repo_root: Path) -> str:
    """Return a repo-relative POSIX path, or a safe non-workstation label if external."""
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        return f"<external>/{path.name}"


def _relativize_if_inside(path: Path, repo_root: Path) -> Optional[str]:
    try:
        rel = path.resolve().relative_to(repo_root.resolve())
        return str(rel).replace("\\", "/")
    except ValueError:
        return None


def _resolve_git_toplevel(path: Path) -> Optional[Path]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(path),
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


def _is_positive_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool) and val > 0


def _is_strict_int(val: Any) -> bool:
    return isinstance(val, int) and not isinstance(val, bool)


def _validate_str_list(val: Any, field: str) -> List[str]:
    if val is None:
        return []
    if not isinstance(val, list) or not all(isinstance(item, str) for item in val):
        raise VerifyConfigError(f"'{field}' must be a list of strings.")
    return list(val)


def _validate_str_dict(val: Any, field: str) -> Dict[str, str]:
    if val is None:
        return {}
    if not isinstance(val, dict):
        raise VerifyConfigError(f"'{field}' must be a JSON object of string keys and values.")
    out: Dict[str, str] = {}
    for k, v in val.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise VerifyConfigError(f"'{field}' must map strings to strings.")
        out[k] = v
    return out


def _validate_command(val: Any, field: str) -> Any:
    if isinstance(val, str) and val.strip():
        return val
    if isinstance(val, list) and val and all(isinstance(item, str) and item != "" for item in val):
        return list(val)
    raise VerifyConfigError(f"'{field}' must be a non-empty command string or list of strings.")


def _opt_http_url(val: Any, field: str) -> Optional[str]:
    if val is None:
        return None
    if not isinstance(val, str) or not val.startswith(("http://", "https://")):
        raise VerifyConfigError(f"{field} must be an http:// or https:// URL.")
    return val


def _opt_int_range(val: Any, lo: int, hi: int, field: str) -> Optional[int]:
    if val is None:
        return None
    if not _is_strict_int(val) or not (lo <= val <= hi):
        raise VerifyConfigError(f"{field} must be an integer between {lo} and {hi}.")
    return val


def _validate_service_readiness(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    prefix = f"services[{idx}]"
    ready_url = _opt_http_url(raw.get("ready_url"), f"{prefix}.ready_url")
    ready_port = _opt_int_range(raw.get("ready_port"), 1, 65535, f"{prefix}.ready_port")
    ready_status = _opt_int_range(raw.get("ready_status"), 100, 599, f"{prefix}.ready_status")

    ready_host = raw.get("ready_host", "127.0.0.1")
    if not isinstance(ready_host, str) or not ready_host.strip():
        raise VerifyConfigError(f"{prefix}.ready_host must be a non-empty string.")

    ready_stdout = raw.get("ready_stdout")
    if ready_stdout is not None and (not isinstance(ready_stdout, str) or not ready_stdout):
        raise VerifyConfigError(f"{prefix}.ready_stdout must be a non-empty string.")

    timeout_s = raw.get("ready_timeout_s", DEFAULT_SERVICE_READY_TIMEOUT_S)
    if not _is_positive_number(timeout_s):
        raise VerifyConfigError(f"{prefix}.ready_timeout_s must be a positive number.")

    return {
        "ready_url": ready_url,
        "ready_port": ready_port,
        "ready_host": ready_host.strip(),
        "ready_stdout": ready_stdout,
        "ready_status": ready_status,
        "ready_timeout_s": float(timeout_s),
    }


def _validate_service(raw: Any, idx: int, seen_names: Set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise VerifyConfigError(f"services[{idx}] must be a JSON object.")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise VerifyConfigError(f"services[{idx}].name must be a non-empty string.")
    if name in seen_names:
        raise VerifyConfigError(f"Duplicate service name '{name}'.")
    seen_names.add(name)

    cmd = _validate_command(raw.get("command"), f"services[{idx}].command")
    cwd = raw.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
        raise VerifyConfigError(f"services[{idx}].cwd must be a non-empty string.")
    env = _validate_str_dict(raw.get("env"), f"services[{idx}].env")
    readiness = _validate_service_readiness(raw, idx)
    return {"name": name.strip(), "command": cmd, "cwd": cwd, "env": env, **readiness}


def _validate_http_status_list(val: Any, cid: str, idx: int) -> List[int]:
    if _is_strict_int(val):
        return [val]
    if isinstance(val, list) and val and all(_is_strict_int(s) for s in val):
        return list(val)
    raise VerifyConfigError(f"checks[{idx}] ('{cid}'): expect_status must be an integer or list of integers.")


def _validate_http_body(raw: Dict[str, Any], cid: str, idx: int) -> Tuple[Optional[str], bool, Any]:
    body = raw.get("body")
    has_json_body = "json_body" in raw and raw["json_body"] is not None
    if body is not None and has_json_body:
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): specify 'body' or 'json_body', not both.")
    if body is not None and not isinstance(body, str):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): body must be a string.")
    return body, has_json_body, raw.get("json_body")


def _validate_http_check(raw: Dict[str, Any], cid: str, idx: int) -> Dict[str, Any]:
    url = raw.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): url must be an http:// or https:// URL.")
    method = raw.get("method", "GET")
    if not isinstance(method, str) or not method.strip():
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): method must be a non-empty string.")
    timeout_s = raw.get("timeout_s", DEFAULT_HTTP_TIMEOUT_S)
    if not _is_positive_number(timeout_s):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): timeout_s must be a positive number.")

    body, has_json_body, json_body = _validate_http_body(raw, cid, idx)
    statuses = _validate_http_status_list(raw.get("expect_status", 200), cid, idx)
    return {
        "id": cid,
        "kind": "http",
        "url": url,
        "method": method.strip().upper(),
        "headers": _validate_str_dict(raw.get("headers"), f"checks[{idx}].headers"),
        "body": body,
        "has_json_body": has_json_body,
        "json_body": json_body,
        "timeout_s": float(timeout_s),
        "expect_status": statuses,
        "has_expect_json": "expect_json" in raw and raw["expect_json"] is not None,
        "expect_json": raw.get("expect_json"),
        "expect_body_contains": _validate_str_list(raw.get("expect_body_contains"), f"checks[{idx}].expect_body_contains"),
        "expect_body_not_contains": _validate_str_list(
            raw.get("expect_body_not_contains"), f"checks[{idx}].expect_body_not_contains"
        ),
    }


def _validate_cli_check(raw: Dict[str, Any], cid: str, idx: int) -> Dict[str, Any]:
    cmd = _validate_command(raw.get("command"), f"checks[{idx}].command")
    cwd = raw.get("cwd")
    if cwd is not None and (not isinstance(cwd, str) or not cwd.strip()):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): cwd must be a non-empty string.")
    timeout_s = raw.get("timeout_s", DEFAULT_CLI_TIMEOUT_S)
    if not _is_positive_number(timeout_s):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): timeout_s must be a positive number.")
    expect_exit = raw.get("expect_exit", 0)
    if not _is_strict_int(expect_exit):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): expect_exit must be an integer.")
    return {
        "id": cid,
        "kind": "cli",
        "command": cmd,
        "cwd": cwd,
        "env": _validate_str_dict(raw.get("env"), f"checks[{idx}].env"),
        "timeout_s": float(timeout_s),
        "expect_exit": expect_exit,
        "expect_stdout_contains": _validate_str_list(
            raw.get("expect_stdout_contains"), f"checks[{idx}].expect_stdout_contains"
        ),
        "expect_stdout_not_contains": _validate_str_list(
            raw.get("expect_stdout_not_contains"), f"checks[{idx}].expect_stdout_not_contains"
        ),
        "expect_stderr_contains": _validate_str_list(
            raw.get("expect_stderr_contains"), f"checks[{idx}].expect_stderr_contains"
        ),
        "expect_stderr_not_contains": _validate_str_list(
            raw.get("expect_stderr_not_contains"), f"checks[{idx}].expect_stderr_not_contains"
        ),
    }


def _validate_file_check(raw: Dict[str, Any], cid: str, idx: int) -> Dict[str, Any]:
    path_val = raw.get("path")
    if not isinstance(path_val, str) or not path_val.strip():
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): path must be a non-empty string.")
    must_exist = raw.get("must_exist", True)
    non_empty = raw.get("non_empty", True)
    if not isinstance(must_exist, bool):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): must_exist must be a boolean.")
    if not isinstance(non_empty, bool):
        raise VerifyConfigError(f"checks[{idx}] ('{cid}'): non_empty must be a boolean.")
    return {
        "id": cid,
        "kind": "file",
        "path": path_val.strip(),
        "must_exist": must_exist,
        "non_empty": non_empty,
        "contains": _validate_str_list(raw.get("contains"), f"checks[{idx}].contains"),
        "not_contains": _validate_str_list(raw.get("not_contains"), f"checks[{idx}].not_contains"),
    }


def _validate_check(raw: Any, idx: int, seen_ids: Set[str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise VerifyConfigError(f"checks[{idx}] must be a JSON object.")
    cid = raw.get("id")
    if not isinstance(cid, str) or not cid.strip():
        raise VerifyConfigError(f"checks[{idx}].id must be a non-empty string.")
    cid = cid.strip()
    if cid in seen_ids:
        raise VerifyConfigError(f"Duplicate check id '{cid}'.")
    seen_ids.add(cid)

    kind = raw.get("kind")
    if kind == "http":
        return _validate_http_check(raw, cid, idx)
    if kind == "cli":
        return _validate_cli_check(raw, cid, idx)
    if kind == "file":
        return _validate_file_check(raw, cid, idx)
    raise VerifyConfigError(
        f"checks[{idx}] ('{cid}'): kind must be 'http', 'cli', or 'file' (got {kind!r})."
    )


def validate_recipe(data: Any) -> Dict[str, Any]:
    """Validate and normalize a verify recipe dictionary."""
    if not isinstance(data, dict):
        raise VerifyConfigError("Verify recipe root must be a JSON object.")
    raw_services = data.get("services", [])
    if not isinstance(raw_services, list):
        raise VerifyConfigError("'services' must be a JSON array.")
    raw_checks = data.get("checks")
    if not isinstance(raw_checks, list) or not raw_checks:
        raise VerifyConfigError("'checks' must be a non-empty JSON array.")

    seen_services: Set[str] = set()
    services = [_validate_service(svc, i, seen_services) for i, svc in enumerate(raw_services)]
    seen_ids: Set[str] = set()
    checks = [_validate_check(chk, i, seen_ids) for i, chk in enumerate(raw_checks)]
    return {"services": services, "checks": checks}


def load_recipe(path: Path | str) -> Dict[str, Any]:
    """Read and validate a verify.json recipe from disk."""
    recipe_path = Path(path)
    if not recipe_path.is_file():
        raise VerifyConfigError(f"Verify recipe file not found: {recipe_path}")
    try:
        raw = json.loads(recipe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerifyConfigError(f"Failed to parse verify recipe {recipe_path}: {exc}") from exc
    return validate_recipe(raw)


def example_recipe() -> Dict[str, Any]:
    """Return a clean starter .anti-slop/verify.json recipe."""
    return {
        "services": [
            {
                "name": "app-server",
                "command": ["python3", "-m", "http.server", "18080", "--bind", "127.0.0.1"],
                "ready_url": "http://127.0.0.1:18080/",
                "ready_timeout_s": 15,
            }
        ],
        "checks": [
            {
                "id": "home-http",
                "kind": "http",
                "url": "http://127.0.0.1:18080/",
                "method": "GET",
                "timeout_s": 10,
                "expect_status": 200,
                "expect_body_contains": ["Directory listing"],
            },
            {
                "id": "cli-version",
                "kind": "cli",
                "command": ["python3", "--version"],
                "expect_exit": 0,
                "expect_stdout_contains": ["Python"],
                "expect_stderr_not_contains": ["Traceback"],
            },
            {
                "id": "readme-present",
                "kind": "file",
                "path": "README.md",
                "must_exist": True,
                "non_empty": True,
            },
        ],
    }


def _json_dict_subset(expected: Dict[str, Any], actual: Any, path: str) -> Optional[str]:
    if not isinstance(actual, dict):
        return f"at {path}: expected JSON object, got {type(actual).__name__}"
    for key, exp_val in expected.items():
        if key not in actual:
            return f"at {path}.{key}: missing expected key"
        mismatch = json_subset_match(exp_val, actual[key], f"{path}.{key}")
        if mismatch is not None:
            return mismatch
    return None


def _json_list_subset(expected: List[Any], actual: Any, path: str) -> Optional[str]:
    if not isinstance(actual, list):
        return f"at {path}: expected JSON array, got {type(actual).__name__}"
    if len(expected) != len(actual):
        return f"at {path}: expected array of length {len(expected)}, got {len(actual)}"
    for idx, (exp_item, act_item) in enumerate(zip(expected, actual)):
        mismatch = json_subset_match(exp_item, act_item, f"{path}[{idx}]")
        if mismatch is not None:
            return mismatch
    return None


def json_subset_match(expected: Any, actual: Any, path: str = "$") -> Optional[str]:
    """Check whether `expected` is a recursive subset of `actual`. Returns None on match."""
    if isinstance(expected, dict):
        return _json_dict_subset(expected, actual, path)
    if isinstance(expected, list):
        return _json_list_subset(expected, actual, path)
    if isinstance(expected, bool) or isinstance(actual, bool):
        if type(expected) is not type(actual) or expected != actual:
            return f"at {path}: expected {expected!r}, got {actual!r}"
        return None
    if expected != actual:
        return f"at {path}: expected {expected!r}, got {actual!r}"
    return None


class _OutputBuffer:
    """Thread-safe bounded output collector with optional readiness substring flag."""

    def __init__(self, needle: Optional[str] = None) -> None:
        self._lock = threading.Lock()
        self._chunks: List[str] = []
        self._size = 0
        self._needle = needle
        self._matched = False

    def append(self, text: str) -> None:
        with self._lock:
            self._chunks.append(text)
            self._size += len(text)
            if self._size > MAX_SERVICE_LOG_CHARS * 2:
                joined = "".join(self._chunks)[-MAX_SERVICE_LOG_CHARS:]
                self._chunks = [joined]
                self._size = len(joined)
            if self._needle is not None and not self._matched and self._needle in "".join(self._chunks):
                self._matched = True

    def matched(self) -> bool:
        with self._lock:
            return self._matched

    def tail(self, limit: int = MAX_SNIPPET_CHARS) -> str:
        with self._lock:
            return _truncate("".join(self._chunks)[-max(limit * 2, 1024):], limit)


class _RunningService:
    """Tracks a background service process group and its output reader thread."""

    def __init__(
        self,
        name: str,
        proc: subprocess.Popen,
        pgid: int,
        output: _OutputBuffer,
        reader: threading.Thread,
    ) -> None:
        self.name = name
        self.proc = proc
        self.pgid = pgid
        self.output = output
        self.reader = reader
        self.ready = False
        self.elapsed_s = 0.0


def _drain_stream(stream: Any, buf: _OutputBuffer) -> None:
    read_fn = getattr(stream, "read1", None)
    try:
        while True:
            chunk = read_fn(4096) if callable(read_fn) else stream.readline()
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
            buf.append(text)
    except (OSError, ValueError):
        return


def _pgid_alive(pgid: int) -> bool:
    if pgid <= 0:
        return False
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _is_group_gone(proc: subprocess.Popen, pgid: int, can_signal_pg: bool) -> bool:
    return proc.poll() is not None and (not can_signal_pg or not _pgid_alive(pgid))


def _signal_group(proc: subprocess.Popen, pgid: int, sig: int, can_signal_pg: bool) -> None:
    if can_signal_pg:
        try:
            os.killpg(pgid, sig)
        except ProcessLookupError:
            return
    elif proc.poll() is None:
        proc.kill() if sig == signal.SIGKILL else proc.terminate()


def _wait_group_exit(proc: subprocess.Popen, pgid: int, timeout_s: float, can_signal_pg: bool) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is None:
            rem = max(0.01, min(0.05, deadline - time.monotonic()))
            try:
                proc.wait(timeout=rem)
            except subprocess.TimeoutExpired:
                pass
        if _is_group_gone(proc, pgid, can_signal_pg):
            return True
        time.sleep(0.05)
    return _is_group_gone(proc, pgid, can_signal_pg)


def _kill_process_group(proc: subprocess.Popen, pgid: int, grace_s: float = TEARDOWN_GRACE_S) -> bool:
    """Tear down an entire POSIX process group: SIGTERM -> grace wait -> SIGKILL."""
    try:
        own_pgid = os.getpgid(0)
    except OSError:
        own_pgid = -1

    can_signal_pg = pgid > 0 and pgid != own_pgid
    if _is_group_gone(proc, pgid, can_signal_pg):
        return True

    _signal_group(proc, pgid, signal.SIGTERM, can_signal_pg)
    if _wait_group_exit(proc, pgid, grace_s, can_signal_pg):
        return True

    _signal_group(proc, pgid, signal.SIGKILL, can_signal_pg)
    return _wait_group_exit(proc, pgid, 2.0, can_signal_pg)


def _stop_service(svc: _RunningService) -> bool:
    clean = _kill_process_group(svc.proc, svc.pgid, grace_s=TEARDOWN_GRACE_S)
    if svc.proc.stdout is not None:
        try:
            svc.proc.stdout.close()
        except OSError:
            pass
    svc.reader.join(timeout=1.0)
    return clean


def _build_url_opener(url: str) -> urllib.request.OpenerDirector:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host in ("127.0.0.1", "localhost", "::1"):
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def _probe_tcp_port(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _probe_http_url(url: str, expected_status: Optional[int] = None) -> bool:
    opener = _build_url_opener(url)
    req = urllib.request.Request(url, method="GET")
    try:
        with opener.open(req, timeout=1.0) as resp:
            code = int(resp.getcode() or 0)
            resp.read(256)
            return (code == expected_status) if expected_status is not None else (200 <= code < 400)
    except urllib.error.HTTPError as exc:
        return expected_status is not None and int(exc.code) == expected_status
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _resolve_work_dir(raw_cwd: Optional[str], repo_root: Path) -> Path:
    if raw_cwd is None:
        return repo_root
    p = Path(raw_cwd)
    return p if p.is_absolute() else (repo_root / p)


def _start_service(spec: Dict[str, Any], repo_root: Path) -> _RunningService:
    name = spec["name"]
    cwd = _resolve_work_dir(spec.get("cwd"), repo_root)
    if not cwd.is_dir():
        raise ServiceStartupError(
            f"Service '{name}' working directory does not exist: {_relativize_path(cwd, repo_root)}"
        )

    env = os.environ.copy()
    env.update(spec.get("env") or {})
    cmd = spec["command"]
    started_at = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            shell=isinstance(cmd, str),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        raise ServiceStartupError(f"Failed to launch service '{name}': {exc}") from exc

    buf = _OutputBuffer(needle=spec.get("ready_stdout"))
    reader = threading.Thread(target=_drain_stream, args=(proc.stdout, buf), daemon=True)
    reader.start()
    svc = _RunningService(name=name, proc=proc, pgid=proc.pid, output=buf, reader=reader)

    try:
        _wait_for_service_ready(svc, spec, started_at, repo_root)
    except ServiceStartupError:
        _stop_service(svc)
        raise
    svc.ready = True
    svc.elapsed_s = round(time.monotonic() - started_at, 3)
    return svc


def _wait_for_service_ready(
    svc: _RunningService,
    spec: Dict[str, Any],
    started_at: float,
    repo_root: Path,
) -> None:
    has_probe = any(spec.get(k) is not None for k in ("ready_url", "ready_port", "ready_stdout"))
    timeout_s = float(spec["ready_timeout_s"])
    deadline = started_at + timeout_s

    if not has_probe:
        time.sleep(min(0.2, timeout_s))
        rc = svc.proc.poll()
        if rc is not None:
            tail = _sanitize_text(svc.output.tail(), repo_root)
            raise ServiceStartupError(f"Service '{svc.name}' exited immediately with code {rc}. Output: {tail}")
        return

    while True:
        rc = svc.proc.poll()
        if rc is not None:
            tail = _sanitize_text(svc.output.tail(), repo_root)
            raise ServiceStartupError(
                f"Service '{svc.name}' exited before becoming ready (exit {rc}). Output: {tail}"
            )
        stdout_ok = spec["ready_stdout"] is None or svc.output.matched()
        port_ok = spec["ready_port"] is None or _probe_tcp_port(spec["ready_host"], spec["ready_port"])
        url_ok = spec["ready_url"] is None or _probe_http_url(spec["ready_url"], spec.get("ready_status"))
        if stdout_ok and port_ok and url_ok:
            return
        if time.monotonic() >= deadline:
            tail = _sanitize_text(svc.output.tail(), repo_root)
            raise ServiceStartupError(
                f"Service '{svc.name}' timed out after {timeout_s:g}s waiting for readiness. Output: {tail}"
            )
        time.sleep(0.05)


def _prepare_http_request(spec: Dict[str, Any]) -> urllib.request.Request:
    headers = dict(spec["headers"])
    data: Optional[bytes] = None
    if spec["has_json_body"]:
        data = json.dumps(spec["json_body"]).encode("utf-8")
        if not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"
    elif spec["body"] is not None:
        data = spec["body"].encode("utf-8")
    return urllib.request.Request(spec["url"], data=data, headers=headers, method=spec["method"])


def _evaluate_http_assertions(spec: Dict[str, Any], http_status: int, body_text: str) -> List[str]:
    failures: List[str] = []
    expected_statuses = spec["expect_status"]
    if http_status not in expected_statuses:
        exp_label = str(expected_statuses[0]) if len(expected_statuses) == 1 else str(expected_statuses)
        failures.append(f"expected HTTP status {exp_label}, got {http_status}")

    if spec["has_expect_json"]:
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError as exc:
            failures.append(f"expected valid JSON response for expect_json, decode error: {exc}")
        else:
            mismatch = json_subset_match(spec["expect_json"], parsed)
            if mismatch is not None:
                failures.append(f"expect_json mismatch {mismatch}")

    for needle in spec["expect_body_contains"]:
        if needle not in body_text:
            failures.append(f"response body missing expected substring {needle!r}")
    for forbidden in spec["expect_body_not_contains"]:
        if forbidden in body_text:
            failures.append(f"response body contained forbidden substring {forbidden!r}")
    return failures


def _run_http_check(spec: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    started_at = time.monotonic()
    target = f"{spec['method']} {spec['url']}"
    req = _prepare_http_request(spec)
    opener = _build_url_opener(spec["url"])

    http_status: Optional[int] = None
    body_text = ""
    failures: List[str] = []
    try:
        with opener.open(req, timeout=spec["timeout_s"]) as resp:
            http_status = int(resp.getcode() or 0)
            body_text = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        http_status = int(exc.code)
        try:
            body_text = exc.read().decode("utf-8", errors="replace")
        except OSError:
            body_text = str(exc.reason)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        failures.append(f"HTTP request error: {_sanitize_text(str(exc), repo_root)}")

    if http_status is not None:
        failures.extend(_evaluate_http_assertions(spec, http_status, body_text))

    elapsed_s = round(time.monotonic() - started_at, 3)
    snippet = _truncate(_sanitize_text(body_text, repo_root))
    status_label = f"HTTP {http_status}" if http_status is not None else "connection error"
    return {
        "id": spec["id"],
        "kind": "http",
        "ok": len(failures) == 0,
        "elapsed_s": elapsed_s,
        "target": target,
        "status": status_label,
        "http_status": http_status,
        "body_snippet": snippet,
        "observed": snippet if snippet else (failures[0] if failures else status_label),
        "failures": failures,
    }


def _format_command_label(cmd: Any, repo_root: Path) -> str:
    raw = cmd if isinstance(cmd, str) else " ".join(str(tok) for tok in cmd)
    return _truncate(_sanitize_text(raw, repo_root), 180)


def _exec_cli_process(
    spec: Dict[str, Any],
    cwd: Path,
    repo_root: Path,
) -> Tuple[Optional[int], str, str, List[str]]:
    env = os.environ.copy()
    env.update(spec.get("env") or {})
    try:
        proc = subprocess.Popen(
            spec["command"],
            shell=isinstance(spec["command"], str),
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
        )
    except OSError as exc:
        return None, "", "", [f"failed to execute command: {_sanitize_text(str(exc), repo_root)}"]

    try:
        out, err = proc.communicate(timeout=spec["timeout_s"])
        return int(proc.returncode), out, err, []
    except subprocess.TimeoutExpired:
        _kill_process_group(proc, proc.pid, grace_s=1.0)
        try:
            out, err = proc.communicate(timeout=1.0)
        except (subprocess.TimeoutExpired, OSError):
            out, err = "", ""
        return None, out, err, [f"command timed out after {spec['timeout_s']:g}s"]


def _evaluate_cli_assertions(
    spec: Dict[str, Any],
    exit_code: int,
    stdout_text: str,
    stderr_text: str,
) -> List[str]:
    failures: List[str] = []
    if exit_code != spec["expect_exit"]:
        failures.append(f"expected exit code {spec['expect_exit']}, got {exit_code}")
    for needle in spec["expect_stdout_contains"]:
        if needle not in stdout_text:
            failures.append(f"stdout missing expected substring {needle!r}")
    for forbidden in spec["expect_stdout_not_contains"]:
        if forbidden in stdout_text:
            failures.append(f"stdout contained forbidden substring {forbidden!r}")
    for needle in spec["expect_stderr_contains"]:
        if needle not in stderr_text:
            failures.append(f"stderr missing expected substring {needle!r}")
    for forbidden in spec["expect_stderr_not_contains"]:
        if forbidden in stderr_text:
            failures.append(f"stderr contained forbidden substring {forbidden!r}")
    return failures


def _run_cli_check(spec: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    started_at = time.monotonic()
    target = _format_command_label(spec["command"], repo_root)
    cwd = _resolve_work_dir(spec.get("cwd"), repo_root)
    if not cwd.is_dir():
        msg = f"working directory does not exist: {_relativize_path(cwd, repo_root)}"
        return {
            "id": spec["id"], "kind": "cli", "ok": False,
            "elapsed_s": round(time.monotonic() - started_at, 3),
            "target": target, "status": "cwd error", "exit_code": None,
            "stdout_snippet": "", "stderr_snippet": "", "observed": msg, "failures": [msg],
        }

    exit_code, stdout_text, stderr_text, failures = _exec_cli_process(spec, cwd, repo_root)
    if exit_code is not None:
        failures.extend(_evaluate_cli_assertions(spec, exit_code, stdout_text, stderr_text))

    out_snip = _truncate(_sanitize_text(stdout_text, repo_root))
    err_snip = _truncate(_sanitize_text(stderr_text, repo_root))
    status_label = f"exit {exit_code}" if exit_code is not None else "exec error"
    return {
        "id": spec["id"],
        "kind": "cli",
        "ok": len(failures) == 0,
        "elapsed_s": round(time.monotonic() - started_at, 3),
        "target": target,
        "status": status_label,
        "exit_code": exit_code,
        "stdout_snippet": out_snip,
        "stderr_snippet": err_snip,
        "observed": out_snip or err_snip or (failures[0] if failures else status_label),
        "failures": failures,
    }


def _file_status_label(exists: bool, is_file: bool, size_bytes: int) -> str:
    if not exists:
        return "missing"
    if not is_file:
        return "not a file"
    return "empty (0B)" if size_bytes == 0 else f"exists ({size_bytes}B)"


def _evaluate_file_contents(
    spec: Dict[str, Any],
    full_path: Path,
    rel_label: str,
    size_bytes: int,
    repo_root: Path,
) -> Tuple[str, List[str]]:
    failures: List[str] = []
    if spec["non_empty"] and size_bytes <= 0:
        failures.append(f"expected non-empty file: {rel_label}")
    content = full_path.read_text(encoding="utf-8", errors="replace")
    snippet = _truncate(_sanitize_text(content, repo_root), 300)
    for needle in spec["contains"]:
        if needle not in content:
            failures.append(f"file missing expected substring {needle!r}")
    for forbidden in spec["not_contains"]:
        if forbidden in content:
            failures.append(f"file contained forbidden substring {forbidden!r}")
    return snippet, failures


def _run_file_check(spec: Dict[str, Any], repo_root: Path) -> Dict[str, Any]:
    started_at = time.monotonic()
    raw_path = Path(spec["path"])
    full_path = raw_path if raw_path.is_absolute() else (repo_root / raw_path)
    rel_label = _relativize_path(full_path, repo_root)
    exists = full_path.exists()
    is_file = full_path.is_file()
    size_bytes = full_path.stat().st_size if is_file else 0
    failures: List[str] = []
    snippet = ""

    if spec["must_exist"]:
        if not exists:
            failures.append(f"expected file to exist: {rel_label}")
        elif not is_file:
            failures.append(f"path exists but is not a regular file: {rel_label}")
        else:
            snippet, failures = _evaluate_file_contents(spec, full_path, rel_label, size_bytes, repo_root)
    elif exists:
        failures.append(f"expected file to be absent, but found: {rel_label}")

    status_label = _file_status_label(exists, is_file, size_bytes)
    return {
        "id": spec["id"],
        "kind": "file",
        "ok": len(failures) == 0,
        "elapsed_s": round(time.monotonic() - started_at, 3),
        "target": rel_label,
        "status": status_label,
        "exists": exists,
        "size_bytes": size_bytes,
        "observed": snippet or f"{rel_label}: {status_label}",
        "failures": failures,
    }


def _hash_file_chunks(hasher: "hashlib._Hash", path: Path) -> None:
    if path.is_symlink():
        hasher.update(b"SYMLINK:")
        hasher.update(os.readlink(path).encode("utf-8", errors="replace"))
        return
    if not path.is_file():
        return
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            hasher.update(chunk)


def _compute_non_git_tree_hash(repo_root: Path, excluded: Set[str]) -> str:
    hasher = hashlib.sha256()
    hasher.update(b"non-git-tree-v1\n")
    for root, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = sorted(d for d in dirnames if d not in NON_GIT_IGNORE_DIRS)
        base = Path(root)
        for fname in sorted(filenames):
            full = base / fname
            rel = str(full.relative_to(repo_root)).replace("\\", "/")
            if rel in excluded:
                continue
            hasher.update(f"FILE:{rel}\0".encode("utf-8"))
            _hash_file_chunks(hasher, full)
            hasher.update(b"\0")
    return hasher.hexdigest()


def _parse_porcelain_z(raw_bytes: bytes, excluded: Set[str]) -> Tuple[List[str], List[str]]:
    """Parse `git status --porcelain=v1 -uall -z`, filtering excluded paths."""
    parts = raw_bytes.split(b"\x00")
    kept_lines: List[str] = []
    untracked_paths: List[str] = []
    idx = 0
    while idx < len(parts):
        entry = parts[idx]
        idx += 1
        if len(entry) < 4:
            continue
        xy = entry[:2].decode("utf-8", errors="replace")
        rel = entry[3:].decode("utf-8", errors="replace")
        orig: Optional[str] = None
        if xy[0] in ("R", "C") or xy[1] in ("R", "C"):
            if idx < len(parts):
                orig = parts[idx].decode("utf-8", errors="replace")
                idx += 1
        if rel in excluded:
            continue
        kept_lines.append(f"{xy} {rel}" if orig is None else f"{xy} {orig} -> {rel}")
        if xy == "??":
            untracked_paths.append(rel)
    return kept_lines, untracked_paths


def _git_diff_bytes(root: Path, git_head: Optional[str], pathspecs: Sequence[str]) -> bytes:
    if git_head is not None:
        proc = subprocess.run(
            ["git", "diff", "HEAD", "--binary", *pathspecs],
            cwd=str(root),
            capture_output=True,
            check=False,
        )
        return proc.stdout
    chunks: List[bytes] = []
    for extra in (["--cached"], []):
        proc = subprocess.run(
            ["git", "diff", *extra, "--binary", *pathspecs],
            cwd=str(root),
            capture_output=True,
            check=False,
        )
        chunks.append(proc.stdout)
    return b"".join(chunks)


def _hash_untracked_files(hasher: "hashlib._Hash", root: Path, untracked: Sequence[str]) -> None:
    hasher.update(b"\n---UNTRACKED---\n")
    for rel in sorted(untracked):
        full = root / rel
        hasher.update(f"UNTRACKED:{rel}\0".encode("utf-8"))
        if full.exists() or full.is_symlink():
            _hash_file_chunks(hasher, full)
        hasher.update(b"\0")


def compute_repo_state(
    repo_root: Path | str,
    *,
    exclude_rel_paths: Sequence[str] = (),
) -> Dict[str, Any]:
    """Compute git HEAD and tamper-sensitive working_tree_sha256 for repo_root."""
    root = Path(repo_root).resolve()
    excluded = {_normalize_rel_posix(p) for p in exclude_rel_paths if p}
    excluded.add(TELEMETRY_REL)

    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        inside = None

    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return {
            "is_git_repo": False,
            "git_head": None,
            "working_tree_sha256": _compute_non_git_tree_hash(root, excluded),
        }

    head_proc = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    git_head: Optional[str] = head_proc.stdout.strip() if head_proc.returncode == 0 else None

    status_proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall", "-z"],
        cwd=str(root),
        capture_output=True,
        check=False,
    )
    status_lines, untracked = _parse_porcelain_z(status_proc.stdout, excluded)
    pathspecs = ["--", "."] + [f":(exclude){p}" for p in sorted(excluded)]

    hasher = hashlib.sha256()
    hasher.update(b"git-working-tree-v1\n")
    for line in status_lines:
        hasher.update(line.encode("utf-8"))
        hasher.update(b"\n")
    hasher.update(b"\n---DIFF---\n")
    hasher.update(_git_diff_bytes(root, git_head, pathspecs))
    _hash_untracked_files(hasher, root, untracked)

    return {
        "is_git_repo": True,
        "git_head": git_head,
        "working_tree_sha256": hasher.hexdigest(),
    }


def compute_receipt_digest(receipt: Dict[str, Any]) -> str:
    """Compute canonical SHA-256 digest over a receipt dict excluding `receipt_sha256`."""
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_receipt_path(repo_root: Path, receipt_path: Optional[Path | str]) -> Path:
    if receipt_path is None:
        return repo_root / DEFAULT_RECEIPT_REL
    p = Path(receipt_path)
    return p if p.is_absolute() else (repo_root / p)


def _execute_recipe_checks(
    recipe: Dict[str, Any],
    repo_root: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    started_services: List[_RunningService] = []
    service_reports: List[Dict[str, Any]] = []
    check_results: List[Dict[str, Any]] = []
    startup_error: Optional[str] = None

    try:
        for svc_spec in recipe["services"]:
            try:
                svc = _start_service(svc_spec, repo_root)
            except ServiceStartupError as exc:
                startup_error = str(exc)
                service_reports.append({
                    "name": svc_spec["name"], "ready": False, "elapsed_s": 0.0,
                    "clean_teardown": True, "error": _sanitize_text(str(exc), repo_root),
                })
                break
            started_services.append(svc)
            service_reports.append({
                "name": svc.name, "ready": True, "elapsed_s": svc.elapsed_s,
                "clean_teardown": None, "error": None,
            })

        if startup_error is None:
            for check_spec in recipe["checks"]:
                kind = check_spec["kind"]
                if kind == "http":
                    check_results.append(_run_http_check(check_spec, repo_root))
                elif kind == "cli":
                    check_results.append(_run_cli_check(check_spec, repo_root))
                else:
                    check_results.append(_run_file_check(check_spec, repo_root))
    finally:
        for svc in reversed(started_services):
            clean = _stop_service(svc)
            for item in service_reports:
                if item["name"] == svc.name and item["ready"]:
                    item["clean_teardown"] = clean

    return service_reports, check_results, startup_error


def run_verification(
    recipe: Dict[str, Any],
    *,
    repo_root: Path | str = ".",
    mode: str = "recipe",
    recipe_rel_path: Optional[str] = None,
    receipt_path: Optional[Path | str] = None,
    write_receipt: bool = True,
) -> Dict[str, Any]:
    """Run services and E2E checks, tear down cleanly, and optionally write receipt."""
    normalized = validate_recipe(recipe)
    root = Path(repo_root).resolve()
    target_receipt = _resolve_receipt_path(root, receipt_path)
    receipt_rel = _relativize_if_inside(target_receipt, root)
    exclude_paths = [receipt_rel] if receipt_rel is not None else [DEFAULT_RECEIPT_REL]

    run_start = time.monotonic()
    service_reports, check_results, startup_error = _execute_recipe_checks(normalized, root)
    total_elapsed_s = round(time.monotonic() - run_start, 3)

    passed_count = sum(1 for item in check_results if item["ok"])
    failed_count = len(check_results) - passed_count
    all_ok = startup_error is None and len(check_results) > 0 and failed_count == 0
    exit_code = 2 if startup_error is not None else (0 if all_ok else 1)

    repo_state = compute_repo_state(root, exclude_rel_paths=exclude_paths)
    receipt_payload: Dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "tier": VERIFICATION_TIER,
        "timestamp_utc": _utc_now_iso(),
        "mode": mode,
        "recipe_path": recipe_rel_path,
        "git_head": repo_state["git_head"],
        "working_tree_sha256": repo_state["working_tree_sha256"],
        "ok": all_ok,
        "summary": {
            "total": len(check_results),
            "passed": passed_count,
            "failed": failed_count,
            "services_started": sum(1 for s in service_reports if s["ready"]),
            "elapsed_s": total_elapsed_s,
        },
        "services": service_reports,
        "checks": check_results,
    }
    if startup_error is not None:
        receipt_payload["error"] = _sanitize_text(startup_error, root)

    receipt_payload["receipt_sha256"] = compute_receipt_digest(receipt_payload)

    written_label: Optional[str] = None
    if write_receipt:
        target_receipt.parent.mkdir(parents=True, exist_ok=True)
        target_receipt.write_text(json.dumps(receipt_payload, indent=2) + "\n", encoding="utf-8")
        written_label = _relativize_path(target_receipt, root)

    report = dict(receipt_payload)
    report["exit_code"] = exit_code
    report["receipt_written"] = write_receipt
    report["receipt_path"] = written_label
    return report


def _load_verified_receipt_json(target: Path, label: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not target.is_file():
        return None, f"verification receipt not found: {label}"
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"verification receipt is unreadable or invalid JSON: {exc}"
    if not isinstance(data, dict):
        return None, "verification receipt root must be a JSON object"
    if data.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        return None, f"unsupported receipt schema_version: {data.get('schema_version')!r}"
    recorded = data.get("receipt_sha256")
    if not isinstance(recorded, str) or len(recorded) != 64:
        return None, "receipt integrity check failed: missing or malformed receipt_sha256"
    if not hmac.compare_digest(recorded, compute_receipt_digest(data)):
        return None, "receipt integrity check failed: receipt_sha256 mismatch (file may have been tampered with)"
    return data, None


def check_receipt(
    *,
    repo_root: Path | str = ".",
    receipt_path: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Validate receipt existence, integrity hash, pass verdict, and current repo state."""
    root = Path(repo_root).resolve()
    target = _resolve_receipt_path(root, receipt_path)
    label = _relativize_path(target, root)
    receipt_rel = _relativize_if_inside(target, root)
    exclude_paths = [receipt_rel] if receipt_rel is not None else [DEFAULT_RECEIPT_REL]

    data, load_err = _load_verified_receipt_json(target, label)
    if load_err is not None or data is None:
        return {"ok": False, "exit_code": 1, "receipt_path": label, "reason": load_err}

    if data.get("ok") is not True:
        return {
            "ok": False, "exit_code": 1, "receipt_path": label,
            "reason": "last verification did not pass (ok: false)",
            "timestamp_utc": data.get("timestamp_utc"),
            "receipt_sha256": data.get("receipt_sha256"),
        }

    current = compute_repo_state(root, exclude_rel_paths=exclude_paths)
    if data.get("git_head") != current["git_head"]:
        return {
            "ok": False, "exit_code": 1, "receipt_path": label,
            "reason": f"stale receipt: git HEAD changed since verification ({data.get('git_head')} -> {current['git_head']})",
            "recorded_git_head": data.get("git_head"),
            "current_git_head": current["git_head"],
        }

    if data.get("working_tree_sha256") != current["working_tree_sha256"]:
        return {
            "ok": False, "exit_code": 1, "receipt_path": label,
            "reason": "stale receipt: working tree changed since last verification (re-run anti-slop verify)",
            "recorded_working_tree_sha256": data.get("working_tree_sha256"),
            "current_working_tree_sha256": current["working_tree_sha256"],
        }

    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "ok": True,
        "exit_code": 0,
        "receipt_path": label,
        "reason": "receipt is valid, passing, and matches current repository state",
        "tier": data.get("tier"),
        "timestamp_utc": data.get("timestamp_utc"),
        "git_head": current["git_head"],
        "working_tree_sha256": current["working_tree_sha256"],
        "receipt_sha256": data["receipt_sha256"],
        "checks_passed": summary.get("passed"),
        "checks_total": summary.get("total"),
    }


def _md_cell(text: str) -> str:
    flat = " ".join(" ".join(str(text).splitlines()).split())
    return _truncate(flat, MAX_TABLE_CELL_CHARS).replace("|", "\\|").replace("`", "'")


def _format_markdown_table(checks: Sequence[Dict[str, Any]]) -> List[str]:
    if not checks:
        return []
    lines = [
        "",
        "| Check | Kind | Result | Status | Elapsed | Observed Output |",
        "|---|---|---|---|---|---|",
    ]
    for chk in checks:
        res_lbl = "PASS" if chk["ok"] else "FAIL"
        obs = _md_cell(chk.get("observed") or "")
        lines.append(
            f"| `{chk['id']}` | `{chk['kind']}` | {res_lbl} | {_md_cell(chk['status'])} | {chk['elapsed_s']:.2f}s | `{obs}` |"
        )
    return lines


def _format_markdown_failures(checks: Sequence[Dict[str, Any]]) -> List[str]:
    failed_checks = [c for c in checks if not c["ok"]]
    if not failed_checks:
        return []
    lines = ["", "### Failures", ""]
    for chk in failed_checks:
        for reason in chk["failures"]:
            lines.append(f"- `{chk['id']}`: {reason}")
    return lines


def _format_markdown_report(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = "PASS" if report["ok"] else ("ERROR" if report["exit_code"] == 2 else "FAIL")
    mode_desc = f"`{report['mode']}`" + (f" (`{report['recipe_path']}`)" if report.get("recipe_path") else "")
    lines = [
        "## Live Verification Evidence (Tier 1 E2E)",
        "",
        f"- **Status:** {verdict} ({summary['passed']}/{summary['total']} checks passed in {summary['elapsed_s']:.2f}s)",
        f"- **Mode:** {mode_desc}",
    ]
    if report.get("git_head"):
        lines.append(f"- **Git HEAD:** `{report['git_head'][:12]}`")
    if report.get("receipt_path"):
        lines.append(f"- **Receipt:** `{report['receipt_path']}` (`sha256: {report['receipt_sha256'][:12]}`)")
    if report.get("error"):
        lines.extend(["", f"**Startup error:** {report['error']}"])
    lines.extend(_format_markdown_table(report["checks"]))
    lines.extend(_format_markdown_failures(report["checks"]))
    return "\n".join(lines).rstrip()


def _format_plain_services(services: Sequence[Dict[str, Any]]) -> Optional[str]:
    if not services:
        return None
    parts: List[str] = []
    for svc in services:
        if svc["ready"]:
            td = "stopped cleanly" if svc["clean_teardown"] else "teardown warning"
            parts.append(f"{svc['name']} (ready in {svc['elapsed_s']:.2f}s, {td})")
        else:
            parts.append(f"{svc['name']} (startup failed)")
    return "Services: " + ", ".join(parts)


def _format_plain_checks(checks: Sequence[Dict[str, Any]]) -> List[str]:
    if not checks:
        return []
    lines = ["", "Checks", "------"]
    for chk in checks:
        tag = "PASS" if chk["ok"] else "FAIL"
        lines.append(f"[{tag}] {chk['id']} ({chk['kind']}, {chk['elapsed_s']:.2f}s): {chk['target']} -> {chk['status']}")
        for reason in chk["failures"]:
            lines.append(f"       Failure: {reason}")
        if chk.get("observed"):
            obs_flat = " ".join(str(chk["observed"]).splitlines())
            lines.append(f"       Observed: {_truncate(obs_flat, 240)}")
    return lines


def _format_plain_report(report: Dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = "PASS" if report["ok"] else ("ERROR" if report["exit_code"] == 2 else "FAIL")
    mode_desc = report["mode"] + (f" ({report['recipe_path']})" if report.get("recipe_path") else "")
    lines = [
        "Anti-Slop Live Verification (Tier 1 E2E)",
        "========================================",
        f"Result: {verdict} ({summary['passed']}/{summary['total']} checks passed in {summary['elapsed_s']:.2f}s)",
        f"Mode: {mode_desc}",
    ]
    svc_line = _format_plain_services(report["services"])
    if svc_line is not None:
        lines.append(svc_line)
    if report.get("receipt_path"):
        lines.append(f"Receipt: {report['receipt_path']} (sha256: {report['receipt_sha256'][:16]})")
    if report.get("error"):
        lines.extend(["", f"Startup error: {report['error']}"])
    lines.extend(_format_plain_checks(report["checks"]))
    return "\n".join(lines).rstrip()


def format_report(report: Dict[str, Any], *, markdown: bool = False) -> str:
    """Format a live verification report as plain English or PR-ready Markdown."""
    return _format_markdown_report(report) if markdown else _format_plain_report(report)


def format_receipt_check(result: Dict[str, Any], *, markdown: bool = False) -> str:
    """Format `--check-receipt` result as plain English or Markdown."""
    status = "VALID" if result["ok"] else "INVALID"
    if markdown:
        lines = [
            f"## Verification Receipt Check: {status}",
            "",
            f"- **Receipt:** `{result['receipt_path']}`",
            f"- **Reason:** {result['reason']}",
        ]
        if result["ok"]:
            lines.extend([
                f"- **Checks:** {result['checks_passed']}/{result['checks_total']} passed",
                f"- **Timestamp:** `{result['timestamp_utc']}`",
                f"- **Digest:** `{result['receipt_sha256'][:16]}`",
            ])
        return "\n".join(lines)

    lines = [f"Verification receipt: {status} ({result['receipt_path']})", f"Reason: {result['reason']}"]
    if result["ok"]:
        lines.append(
            f"Verified: {result['checks_passed']}/{result['checks_total']} checks passed at "
            f"{result['timestamp_utc']} (sha256: {result['receipt_sha256'][:16]})"
        )
    return "\n".join(lines)


def _derive_port_from_url(url: str) -> Tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    if parsed.port is not None:
        return host, int(parsed.port)
    return host, (443 if parsed.scheme == "https" else 80)


def _build_adhoc_services(args: argparse.Namespace) -> List[Dict[str, Any]]:
    if args.start is None:
        return []
    svc: Dict[str, Any] = {
        "name": "service",
        "command": args.start,
        "ready_timeout_s": args.ready_timeout,
    }
    if args.ready_url:
        svc["ready_url"] = args.ready_url
    if args.ready_port is not None:
        svc["ready_port"] = args.ready_port
    if args.ready_stdout:
        svc["ready_stdout"] = args.ready_stdout
    if not any((args.ready_url, args.ready_port, args.ready_stdout)) and args.http_get:
        host, port = _derive_port_from_url(args.http_get[0])
        svc["ready_host"] = host
        svc["ready_port"] = port
    return [svc]


def _build_adhoc_http_checks(args: argparse.Namespace) -> List[Dict[str, Any]]:
    expect_json_obj: Any = None
    has_expect_json = args.expect_json is not None
    if has_expect_json:
        try:
            expect_json_obj = json.loads(args.expect_json)
        except json.JSONDecodeError as exc:
            raise VerifyConfigError(f"Invalid JSON passed to --expect-json: {exc}") from exc

    checks: List[Dict[str, Any]] = []
    for idx, url in enumerate(args.http_get or [], start=1):
        chk: Dict[str, Any] = {
            "id": f"http-{idx}",
            "kind": "http",
            "url": url,
            "method": args.http_method,
            "timeout_s": args.http_timeout,
            "expect_status": args.expect_status,
            "expect_body_contains": list(args.expect_contains or []),
            "expect_body_not_contains": list(args.expect_not_contains or []),
        }
        if has_expect_json:
            chk["expect_json"] = expect_json_obj
        checks.append(chk)
    return checks


def _build_adhoc_recipe(args: argparse.Namespace) -> Dict[str, Any]:
    services = _build_adhoc_services(args)
    checks = _build_adhoc_http_checks(args)
    for idx, cmd in enumerate(args.cmd or [], start=1):
        checks.append({
            "id": f"cli-{idx}",
            "kind": "cli",
            "command": cmd,
            "timeout_s": args.cmd_timeout,
            "expect_exit": args.expect_exit,
            "expect_stdout_contains": list(args.expect_stdout or []),
            "expect_stdout_not_contains": list(args.expect_stdout_not or []),
            "expect_stderr_not_contains": list(args.expect_stderr_not or []),
        })
    for idx, fpath in enumerate(args.file_checks or [], start=1):
        checks.append({"id": f"file-{idx}", "kind": "file", "path": fpath, "must_exist": True, "non_empty": True})

    if not checks:
        raise VerifyConfigError("Ad-hoc mode requires at least one check (--cmd, --http-get, or --file).")
    return validate_recipe({"services": services, "checks": checks})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run live end-to-end and real-artifact verification checks (HTTP, CLI, files) "
            "with guaranteed service process-group teardown and tamper-evident receipts."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root directory (default: '.').")
    parser.add_argument("--recipe", default=None, help=f"Path to verify JSON recipe (default: {DEFAULT_RECIPE_REL}).")
    parser.add_argument("--receipt", default=None, help=f"Path to verification receipt (default: {DEFAULT_RECEIPT_REL}).")
    parser.add_argument("--no-receipt", action="store_true", help="Skip writing the verification receipt file.")
    parser.add_argument(
        "--check-receipt",
        action="store_true",
        help="Verify that the receipt exists, is untampered, passed, and matches current git/working-tree state.",
    )
    parser.add_argument("--init-example", action="store_true", help="Print a starter .anti-slop/verify.json recipe and exit.")

    adhoc = parser.add_argument_group("one-shot ad-hoc mode (no recipe file required)")
    adhoc.add_argument("--cmd", action="append", default=None, help="Run a one-shot CLI check command (repeatable).")
    adhoc.add_argument("--expect-exit", type=int, default=0, help="Expected exit code for --cmd (default: 0).")
    adhoc.add_argument("--expect-stdout", action="append", default=None, help="Expected stdout substring for --cmd (repeatable).")
    adhoc.add_argument("--expect-stdout-not", action="append", default=None, help="Forbidden stdout substring for --cmd (repeatable).")
    adhoc.add_argument("--expect-stderr-not", action="append", default=None, help="Forbidden stderr substring for --cmd (repeatable).")
    adhoc.add_argument("--cmd-timeout", type=float, default=DEFAULT_CLI_TIMEOUT_S, help="Timeout seconds for --cmd (default: 30).")

    adhoc.add_argument("--start", default=None, help="Background server command to boot and tear down cleanly.")
    adhoc.add_argument("--ready-url", default=None, help="Readiness HTTP URL to poll after --start.")
    adhoc.add_argument("--ready-port", type=int, default=None, help="Readiness TCP port to poll after --start.")
    adhoc.add_argument("--ready-stdout", default=None, help="Readiness stdout substring to wait for after --start.")
    adhoc.add_argument("--ready-timeout", type=float, default=DEFAULT_SERVICE_READY_TIMEOUT_S, help="Readiness timeout seconds (default: 20).")

    adhoc.add_argument("--http-get", action="append", default=None, help="HTTP URL to request and assert against (repeatable).")
    adhoc.add_argument("--http-method", default="GET", help="HTTP method for --http-get checks (default: GET).")
    adhoc.add_argument("--http-timeout", type=float, default=DEFAULT_HTTP_TIMEOUT_S, help="Timeout seconds for --http-get (default: 10).")
    adhoc.add_argument("--expect-status", type=int, default=200, help="Expected HTTP status code for --http-get (default: 200).")
    adhoc.add_argument("--expect-contains", action="append", default=None, help="Expected response body substring for --http-get (repeatable).")
    adhoc.add_argument("--expect-not-contains", action="append", default=None, help="Forbidden response body substring for --http-get (repeatable).")
    adhoc.add_argument("--expect-json", default=None, help="JSON object/value subset expected in --http-get JSON response.")
    adhoc.add_argument("--file", dest="file_checks", action="append", default=None, help="Verify a file exists and is non-empty (repeatable).")

    parser.add_argument("--markdown", action="store_true", help="Format output as a PR-ready Markdown evidence table.")
    parser.add_argument("--json", action="store_true", dest="emit_json", help="Emit structured JSON output.")
    return parser


def _resolve_repo_root(raw_repo_root: str) -> Path:
    raw = Path(raw_repo_root).resolve()
    if raw_repo_root == ".":
        top = _resolve_git_toplevel(raw)
        if top is not None:
            return top
    return raw


def _emit_error(exc: Exception, *, emit_json: bool) -> int:
    if emit_json:
        print(json.dumps({"ok": False, "exit_code": 2, "error": str(exc)}, indent=2))
    else:
        print(f"error: {exc}", file=sys.stderr)
    return 2


def _resolve_execution_recipe(args: argparse.Namespace, root: Path) -> Tuple[Dict[str, Any], str, Optional[str]]:
    has_adhoc = any((args.cmd, args.start, args.http_get, args.file_checks))
    if has_adhoc and args.recipe is not None:
        raise VerifyConfigError("Cannot combine --recipe with ad-hoc flags (--cmd, --start, --http-get, --file).")
    if has_adhoc:
        return _build_adhoc_recipe(args), "adhoc", None

    recipe_path = Path(args.recipe) if args.recipe is not None else (root / DEFAULT_RECIPE_REL)
    if not recipe_path.is_absolute():
        recipe_path = root / recipe_path
    if not recipe_path.is_file():
        raise VerifyConfigError(
            f"No verify recipe found at {_relativize_path(recipe_path, root)}. "
            "Run with --init-example to generate a starter recipe, or pass ad-hoc flags (--cmd / --start / --http-get)."
        )
    return load_recipe(recipe_path), "recipe", _relativize_path(recipe_path, root)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.init_example:
        print(json.dumps(example_recipe(), indent=2))
        return 0

    root = _resolve_repo_root(args.repo_root)
    if args.check_receipt:
        result = check_receipt(repo_root=root, receipt_path=args.receipt)
        output = json.dumps(result, indent=2) if args.emit_json else format_receipt_check(result, markdown=args.markdown)
        print(output)
        return int(result["exit_code"])

    try:
        recipe, mode, recipe_rel = _resolve_execution_recipe(args, root)
    except (VerifyConfigError, OSError) as exc:
        return _emit_error(exc, emit_json=args.emit_json)

    report = run_verification(
        recipe,
        repo_root=root,
        mode=mode,
        recipe_rel_path=recipe_rel,
        receipt_path=args.receipt,
        write_receipt=not args.no_receipt,
    )
    output = json.dumps(report, indent=2) if args.emit_json else format_report(report, markdown=args.markdown)
    print(output)
    return int(report["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
