# Codex CLI `execpolicy` & Lifecycle Hook Template

Opt-in harness template for `gpt-6.2-astra` and `gpt-6.2-sol` in Codex CLI. Combines OS-sandboxed command rules (`execpolicy`), `PreToolUse` test-file edit blocking, and `PostToolUse` exit-code checks outside the model context window.

## 1. `execpolicy` Command Guardrails

Place restrictive rules in your Codex policy file (for example under .codex/rules/ in a target workspace) to block silent test bypasses, hook disabling, and destructive resets:

```python
# Example Codex execpolicy rules (adapt to your repo's test runner)
prefix_rule(
    pattern=["git", "commit", "--no-verify"],
    decision="forbidden",
    justification="Never bypass repository pre-commit or diff gates.",
)

prefix_rule(
    pattern=["git", "push", "--force"],
    decision="prompt",
    justification="Require explicit human approval before force-pushing.",
)

prefix_rule(
    pattern=["rm", "-rf", "tests"],
    decision="forbidden",
    justification="Do not delete test suites to bypass failing checks.",
)
```

Run Codex inside the workspace sandbox so repository git hooks and policy files stay read-only to the agent.

## 2. Portable `PreToolUse` and `PostToolUse` Hook Wiring

The fastest way to wire user-level Codex hooks (`~/.codex/hooks.json`, with automatic backup to `*.bak-antislop` and zero duplicate entries) is the one-command installer:

```bash
# Preview changes without writing
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --install codex --dry-run

# Or install directly after `uv tool install git+https://github.com/jremick/anti-slop`
anti-slop-hook --install codex
```

For per-repository Codex hooks that work in any external repo (without assuming `gates/` is vendored inside the target repo), wire `anti-slop-hook` (or fall back to `uvx`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "apply_patch|edit_file|write_file|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "if command -v anti-slop-hook >/dev/null 2>&1; then anti-slop-hook --harness codex --stdin-tool-json; else uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --harness codex --stdin-tool-json; fi"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "apply_patch|edit_file|write_file|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "if command -v anti-slop-hook >/dev/null 2>&1; then anti-slop-hook --harness codex --no-budget; else uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --harness codex --no-budget; fi"
          }
        ]
      }
    ]
  }
}
```

Pair `PostToolUse` with deterministic tool exit-code logging rather than trusting narrative summaries (raw API GPT-6.2 calls lack Codex's blocker-deception prompt mitigation; see `docs/evidence.md` `OAI-01` and `EXT-13`).

## 3. Mandatory `Stop`-Hook Parity Reminder

Blocking `Stop` hook parity in Codex CLI still lags Claude Code and Antigravity. Do **not** rely on agent-turn hooks alone to catch stub placeholders, diff budget overruns, or unverified completions on GPT-6.2 runs:

1. Require an explicit `Verify Command` in every GPT-6.2 task brief (`D-AST-2` / `D-SOL-2` in `gates/model_deltas.json`).
2. Run `anti-slop-diff` in CI (`action.yml` / `gates/ci-ratchet.yml`) or in your outer harness wrapper after Codex exits:

```bash
# Portable across any repository (no local clone required)
git diff HEAD | uvx --from git+https://github.com/jremick/anti-slop anti-slop-diff --diff - --repo-root .

# Or using a vendored local checkout of gates/diff_check.py
git diff HEAD | python3 -B gates/diff_check.py --diff - --repo-root .
```
