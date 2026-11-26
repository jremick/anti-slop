# Security Policy

## Supported Versions

Security fixes are maintained on the latest `0.6.x` release line and `main`. Earlier pre-public development tags (`< 0.6.0`) are unsupported.

| Version | Supported |
| :--- | :--- |
| `0.6.x` | Yes |
| `< 0.6.0` | No |

## Reporting a Vulnerability

Do **not** open a public GitHub issue for an undisclosed security vulnerability.

Report vulnerabilities privately through GitHub Security Advisories:

- [Open a private security advisory](https://github.com/jremick/anti-slop/security/advisories/new)

Include:

1. Affected file or entry point (for example `gates/diff_check.py`, `gates/hooks/run_diff_gate_hook.py`, `action.yml`, or `scripts/run_benchmark.py`).
2. Minimal reproduction steps or payload demonstrating the flaw.
3. Impact assessment and any suggested fix.

Expect an initial acknowledgment within 72 hours and a triage update within 7 days.

## Scope

### In Scope

- Command injection, shell-escaping flaws, path traversal, or arbitrary file overwrite in `gates/hooks/run_diff_gate_hook.py` (including `--install`), `action.yml`, `gates/diff_check.py`, `gates/api_checks.py`, or `scripts/`.
- Gate bypasses where malformed diffs or payloads evade deterministic security/integrity checks (`DIFF-UNAUTHORIZED-TEST-EDIT`, `DIFF-TEST-SKIP`, `DIFF-HOST-PATH`, `FABLE-SILENT-DOWNGRADE`).
- Credential, environment, or host-path leakage in benchmark isolation or public sanitization helpers (`scripts/run_benchmark.py`).

### Out of Scope

- **Vendored historical OSS benchmark snapshots (`benchmarks/sources/`):** Pinned third-party open-source snapshots used solely as offline benchmark fixtures (never installed as runtime dependencies). Report vulnerabilities in `tomlkit`, `Python-Markdown`, `urllib3`, `pypa/packaging`, or `sqlparse` directly to their upstream maintainers.
- **Model behavior or third-party CLI bugs:** Prompt-injection or refusal behavior in upstream LLM providers or external CLIs (Claude Code, Codex CLI, Antigravity) should be reported to the respective vendor.
- **Heuristic threshold tuning:** False positives/negatives in optional style warnings (`gates/vale/`, `DIFF-DECORATIVE-EMOJI`) or `[Heuristic]` LOC/file budgets are regular bugs—file them via `.github/ISSUE_TEMPLATE/slop-defect.md`.
