# Agent Lifecycle Hook Adapters (`gates/hooks/`)

Zero-dependency CLI hook templates wrapping `gates/diff_check.py` outside the model context window. Moving test-file locks and diff hygiene into external hooks avoids standing-prompt bloat while capturing the environmental hardening and edit-integrity gains documented in `docs/evidence.md` (`EXT-13`).

## One-Command Portable Install

Install the zero-dependency console scripts (`anti-slop-diff`, `anti-slop-hook`, `anti-slop-api`) once, then wire user-level hooks for Claude Code (`~/.claude/settings.json`), Antigravity (`~/.gemini/config/hooks.json`), or Codex CLI (`~/.codex/hooks.json`):

```bash
# Option A: Install console scripts globally with uv or pip
uv tool install git+https://github.com/jremick/anti-slop

# Preview exact config changes without writing
anti-slop-hook --install claude --dry-run
anti-slop-hook --install antigravity --dry-run
anti-slop-hook --install codex --dry-run

# Apply (backs up existing configs to *.bak-antislop; never duplicates entries)
anti-slop-hook --install claude
anti-slop-hook --install antigravity
anti-slop-hook --install codex
```

If `anti-slop-hook` is on `PATH`, `--install` wires portable `anti-slop-hook` commands so hooks work in every external repository without vendoring `gates/`. When run directly from a local checkout (`python3 -B gates/hooks/run_diff_gate_hook.py --install claude`), it wires the resolved `python3 -B <script>` path instead. Re-running `--install` is idempotent and updates existing anti-slop entries in place.

## Harness Blocking Contracts

`gates/hooks/run_diff_gate_hook.py` (console script `anti-slop-hook`) supports both per-repository and global user-level hooks via `--harness {auto,claude,codex,antigravity}` (default `auto`):

- **Claude Code & Codex CLI (exit-2 contract):**
  - **Exit `0`:** Clean pass; tool invocation or agent turn completes normally.
  - **Exit `2`:** Hard block; denies the tool edit or stops the agent from finishing and injects `stderr` back into the session as concise corrective remediation.
  - **Exit `1`:** Non-blocking hook error; never used for policy denials.
- **Antigravity (`--harness antigravity` or auto-detected via camelCase stdin JSON):**
  - Always exits `0` with a JSON object on `stdout`:
  - `PreToolUse`: `{"decision": "allow"}` on pass, or `{"decision": "deny", "reason": "..."}` on unauthorized `tests/` edits (inspecting `toolCall.name` and `toolCall.args`).
  - `Stop`: `{"decision": "allow"}` on pass, or `{"decision": "continue", "reason": "..."}` on diff-gate violations.

## Global-Safe Guards

When installed globally across repositories, `anti-slop-hook` applies five safety defaults:

- **Workspace resolution:** When `--repo-root` is `.` or omitted, reads `cwd` or `workspacePaths[0]` from stdin JSON and resolves `git rev-parse --show-toplevel` (essential because Antigravity runs hook commands from the directory containing hooks.json).
- **Non-git graceful no-op:** In diff-gate (`Stop` / `PostToolUse`) mode, non-git directories cleanly pass (`exit 0`, or `{"decision": "allow"}` for Antigravity).
- **Anti-loop `Stop` guard:** Immediately allows stop when Claude/Codex sets `"stop_hook_active": true`, or Antigravity sets `"continuationActive": true` or a `"terminationReason"` other than `"NO_TOOL_CALL"`.
- **Automatic learned-rule enforcement (fail-safe):** When a target repository contains an approved `<repo>/.anti-slop/learned/rules.json` store (created via `anti-slop-learn`), `Stop` mode automatically enforces approved, SHA-256-intact deterministic rules alongside built-in diff checks. Repos without a learned-rule store no-op cleanly, and unapproved, retired, or tampered entries are ignored.
- **Benchmark isolation & `--no-budget`:** Immediately no-ops when `ANTI_SLOP_BENCHMARK_SUBJECT=1` or the target path lies inside an `antislop_*` temp workspace. Pass `--no-budget` (default in `--install` Stop/PostToolUse hooks) to disable heuristic `--max-net-loc` / `--max-files` caps and block only objective defects (`DIFF-TEST-SKIP`, `DIFF-STUB-*`, `DIFF-SUPPRESSION`, `DIFF-SILENT-CATCH`, `DIFF-DEBUG-LEFTOVER`, `DIFF-HOST-PATH`, `DIFF-CHATBOT-OPENER`, `DIFF-CHATBOT-CLOSER`, `DIFF-BROKEN-DOC-PATH`).

## Contents

- [run_diff_gate_hook.py](run_diff_gate_hook.py): Stdlib-only hook wrapper (`anti-slop-hook`) supporting `--stdin-tool-json` (`PreToolUse` test-file edit lock), default `git diff` mode (`Stop` / `PostToolUse`), `--harness`, `--no-budget`, and `--install {claude,antigravity,codex}` (`--dry-run`).
- [claude-settings.example.json](claude-settings.example.json): Portable Claude Code settings template (copy into .claude/settings.json in any target repo). Uses `anti-slop-hook` when installed, falls back to vendored `gates/hooks/run_diff_gate_hook.py` if present, or runs via `uvx` without cloning.
- [antigravity-hooks.example.json](antigravity-hooks.example.json): Portable Antigravity hooks template (copy into .agents/hooks.json in any target repo) using Antigravity's named-hook schema (`anti-slop-diff-gate`, grouped `PreToolUse`, flat `Stop` array, `--harness antigravity`) with the same `anti-slop-hook` / vendored / `uvx` fallback chain.
- [codex-execpolicy.example.md](codex-execpolicy.example.md): Codex CLI `execpolicy` + portable `PreToolUse` / `PostToolUse` template for `gpt-6.2-astra` / `gpt-6.2-sol`, including the blocking `Stop`-hook parity gap reminder.

## Quick Usage

```bash
# 1. PreToolUse test-file edit lock (exits 2 for Claude/Codex when targeting tests/)
echo '{"tool_name":"Edit","tool_input":{"file_path":"tests/test_app.py"}}' \
  | uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --stdin-tool-json --repo-root .

# 2. Stop / post-edit gate on staged + unstaged git diff (exits 2 on violations, 0 on clean pass)
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --no-budget --repo-root .

# 3. Local checkout / vendored invocation (zero third-party tools needed)
python3 -B gates/hooks/run_diff_gate_hook.py --repo-root .

# 4. Copy portable per-repo examples into any target repository
mkdir -p .claude && cp gates/hooks/claude-settings.example.json .claude/settings.json
mkdir -p .agents && cp gates/hooks/antigravity-hooks.example.json .agents/hooks.json
```

For Codex CLI, pair lifecycle hooks with CI (`action.yml` / `gates/ci-ratchet.yml`) and explicit `Verify Command` checks because blocking `Stop` hook parity still lags Claude Code and Antigravity.
