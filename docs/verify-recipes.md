# Live E2E Verification and Recipes (`anti-slop verify`)

`gates/verify.py` (exposed as `anti-slop verify` and `anti-slop-verify`) runs real observable Tier 1 checks against your actual application, API server, CLI, or generated artifacts and writes a tamper-evident receipt bound to your exact repository state.

Use this tool alongside [the 3-tier verification hierarchy](operating-guide.md#3-tier-verification-hierarchy) so an AI coding agent cannot claim completion from isolated, mocked unit tests without exercising the running system.

## Why Tier 1 Live Verification Matters

Unit tests with heavy mocks routinely pass while the real server crashes on startup, an HTTP route returns the wrong JSON shape, a CLI exits non-zero, or a build artifact is empty. `anti-slop verify` closes that gap with zero third-party dependencies:

1. Boots optional background services in isolated POSIX process groups and waits for real readiness signals.
2. Runs real HTTP requests, CLI invocations, and file artifact checks against the live system.
3. Tears down every started service process group inside `try/finally` (`SIGTERM`, 2 second grace window, then `SIGKILL`) so zero orphan or zombie servers leak.
4. Writes a repo-relative, SHA-256 tamper-evident receipt (`<repo>/.anti-slop/last-verify.json`) that automatically invalidates if any tracked or untracked file changes afterward.

## Quick Start: One-Shot Ad-Hoc Mode

When you want immediate proof without creating a recipe file, pass ad-hoc flags directly.

### Verify a CLI command

```bash
anti-slop verify \
  --cmd "python3 -m myapp --version" \
  --expect-exit 0 \
  --expect-stdout "myapp 1.0"
```

Multiple checks and assertions are repeatable:

```bash
anti-slop verify \
  --cmd "python3 -m myapp export --format json" \
  --expect-exit 0 \
  --expect-stdout '"status": "ok"' \
  --expect-stderr-not "Traceback" \
  --file "build/export.json"
```

### Boot a local server, verify an HTTP endpoint, and tear down cleanly

```bash
anti-slop verify \
  --start "python3 -m myapp.server --port 18080" \
  --ready-url "http://127.0.0.1:18080/health" \
  --http-get "http://127.0.0.1:18080/api/status" \
  --expect-status 200 \
  --expect-contains '"healthy": true'
```

If you pass `--start` and `--http-get` without an explicit `--ready-url`, `--ready-port`, or `--ready-stdout`, `gates/verify.py` automatically waits for the TCP port of the first `--http-get` URL to accept connections before running checks.

Use `--expect-json '{"service": "api", "healthy": true}'` in ad-hoc mode to run recursive JSON subset matching against the response payload.

## Project Recipe Mode (`<repo>/.anti-slop/verify.json`)

For repeatable verification across agent turns and CI, store a recipe at `<repo>/.anti-slop/verify.json` (or pass `--recipe <path>`). Generate a starter template with:

```bash
anti-slop verify --init-example > .anti-slop/verify.json
```

Run the default recipe from anywhere inside the repository:

```bash
anti-slop verify
anti-slop verify --markdown
anti-slop verify --json
```

### Complete Recipe Example

```json
{
  "services": [
    {
      "name": "api",
      "command": ["python3", "-m", "myapp.server", "--host", "127.0.0.1", "--port", "18080"],
      "cwd": ".",
      "env": {
        "APP_ENV": "test"
      },
      "ready_url": "http://127.0.0.1:18080/health",
      "ready_timeout_s": 20
    }
  ],
  "checks": [
    {
      "id": "health-json",
      "kind": "http",
      "url": "http://127.0.0.1:18080/health",
      "method": "GET",
      "timeout_s": 10,
      "expect_status": 200,
      "expect_json": {
        "status": "ok",
        "dependencies": {
          "db": "up"
        }
      },
      "expect_body_not_contains": ["error"]
    },
    {
      "id": "create-item",
      "kind": "http",
      "url": "http://127.0.0.1:18080/api/items",
      "method": "POST",
      "headers": {
        "X-Request-Source": "verify"
      },
      "json_body": {
        "name": "smoke-item"
      },
      "expect_status": 201,
      "expect_json": {
        "name": "smoke-item"
      }
    },
    {
      "id": "cli-smoke",
      "kind": "cli",
      "command": ["python3", "-m", "myapp.cli", "check"],
      "timeout_s": 30,
      "expect_exit": 0,
      "expect_stdout_contains": ["OK"],
      "expect_stdout_not_contains": ["WARN"],
      "expect_stderr_not_contains": ["Traceback"]
    },
    {
      "id": "dist-artifact",
      "kind": "file",
      "path": "build/report.json",
      "must_exist": true,
      "non_empty": true,
      "contains": ["\"ok\": true"]
    }
  ]
}
```

### Recipe Schema Reference

#### `services` (optional array)

Each entry boots one background service before checks run and tears down its entire process group in reverse startup order inside `try/finally`.

| Field | Required | Default | Description |
|---|---|---|---|
| `name` | Yes | | Unique service label used in reports and logs. |
| `command` | Yes | | List of argv strings (`shell=False`) or a shell command string (`shell=True`). |
| `cwd` | No | repo root | Working directory, resolved relative to the repository root. |
| `env` | No | `{}` | Extra string environment variables merged with the current environment. |
| `ready_url` | No | `null` | HTTP URL polled until it returns `2xx`/`3xx` (or `ready_status` if set). |
| `ready_port` | No | `null` | TCP port polled on `ready_host` (default `127.0.0.1`) until it accepts connections. |
| `ready_stdout` | No | `null` | Substring waited for in the service's combined stdout and stderr stream. |
| `ready_status` | No | `null` | Exact HTTP status required by `ready_url` (overrides default `200..399`). |
| `ready_timeout_s` | No | `20` | Seconds to wait for readiness before failing startup with exit code `2`. |

If a service exits before becoming ready, `gates/verify.py` aborts immediately instead of waiting for the full timeout, tears down any previously started services, and exits `2` with the captured log tail.

#### `checks` (required non-empty array)

Every check requires a unique `id` and a `kind` of `"http"`, `"cli"`, or `"file"`.

**`http` check fields:**

| Field | Default | Description |
|---|---|---|
| `url` | required | Target `http://` or `https://` URL. Localhost requests bypass system proxies. |
| `method` | `"GET"` | HTTP verb (case-insensitive). |
| `headers` | `{}` | Optional HTTP request headers. |
| `body` | `null` | Raw UTF-8 request body string (mutually exclusive with `json_body`). |
| `json_body` | `null` | JSON payload serialized automatically with `Content-Type: application/json`. |
| `timeout_s` | `10` | Request timeout in seconds. |
| `expect_status` | `200` | Expected HTTP status integer or list of accepted integers. |
| `expect_json` | `null` | Recursive JSON subset match against the parsed JSON response (strict `bool` vs `int`). |
| `expect_body_contains` | `[]` | Substrings that must appear in the response body. |
| `expect_body_not_contains` | `[]` | Substrings forbidden in the response body. |

**`cli` check fields:**

| Field | Default | Description |
|---|---|---|
| `command` | required | List of argv strings or shell command string. |
| `cwd` | repo root | Working directory relative to repo root. |
| `env` | `{}` | Extra string environment variables. |
| `timeout_s` | `30` | Execution timeout in seconds (timed-out process groups are killed cleanly). |
| `expect_exit` | `0` | Expected integer exit code. |
| `expect_stdout_contains` | `[]` | Substrings required in stdout. |
| `expect_stdout_not_contains` | `[]` | Substrings forbidden in stdout. |
| `expect_stderr_contains` | `[]` | Substrings required in stderr. |
| `expect_stderr_not_contains` | `[]` | Substrings forbidden in stderr. |

**`file` check fields:**

| Field | Default | Description |
|---|---|---|
| `path` | required | File path resolved relative to the repository root. |
| `must_exist` | `true` | When `true`, file must exist as a regular file; when `false`, path must not exist. |
| `non_empty` | `true` | When `must_exist` is `true`, fail if file size is `0` bytes. |
| `contains` | `[]` | Substrings required in the file's UTF-8 text. |
| `not_contains` | `[]` | Substrings forbidden in the file's UTF-8 text. |

## Tamper-Evident Receipts and `--check-receipt`

By default, every verification run writes `<repo>/.anti-slop/last-verify.json` (override with `--receipt <path>`, or skip with `--no-receipt`). The receipt records:

- `schema_version`: `1`
- `tier`: `"tier1_live_e2e"`
- `timestamp_utc`: UTC ISO-8601 timestamp
- `git_head`: current commit SHA (or `null` outside git / before first commit)
- `working_tree_sha256`: SHA-256 digest of `git status --porcelain=v1 -uall`, `git diff HEAD`, and untracked file contents (excluding the receipt path itself so writing the receipt does not invalidate itself)
- `ok`: boolean pass verdict
- `services` and `checks`: per-service readiness/teardown status and per-check statuses, timings, and truncated observable snippets (all paths kept repo-relative with local workstation paths redacted)
- `receipt_sha256`: canonical SHA-256 digest over all other fields in the receipt

### Catching Unverified Edits or Tampering

Before opening a PR, merging, or claiming a task is done, run:

```bash
anti-slop verify --check-receipt
```

`--check-receipt` exits `0` only when all five conditions hold:

1. The receipt file exists and parses as schema version `1`.
2. Recomputing `receipt_sha256` matches the recorded digest (catches manual edits to `ok`, snippets, or hashes).
3. `ok` is `true` (a failed verification run never passes `--check-receipt`).
4. `git_head` matches the current repository `HEAD`.
5. `working_tree_sha256` matches the current working tree (any subsequent edit to a tracked or untracked file immediately invalidates the receipt and exits `1`).

## Outputs and Exit Codes

| Flag | Output |
|---|---|
| (default) | Plain-English summary with service readiness, check pass/fail details, and observed snippets. |
| `--markdown` | PR-ready Markdown evidence table with status, timings, observed outputs, and failure bullets. |
| `--json` | Full structured JSON report (or structured receipt check status with `--check-receipt --json`). |

| Exit Code | Meaning |
|---|---|
| `0` | All checks passed, `--init-example` succeeded, or `--check-receipt` is fresh and valid. |
| `1` | One or more checks failed, or `--check-receipt` detected a missing, failed, stale, or tampered receipt. |
| `2` | Invalid recipe JSON/schema, invalid CLI flags, missing recipe file, or background service failed to start. |

## Agent Workflow Pattern

1. Implement the change and run unit or mutation tests (`gates/mutate.py`).
2. Run `anti-slop verify --markdown` (via recipe or ad-hoc `--start` / `--http-get` / `--cmd`) to prove the real artifact works end to end.
3. Paste the Markdown evidence table into the PR or handoff summary.
4. Before finishing, run `anti-slop verify --check-receipt` to confirm no post-verification edits slipped in unverified.
