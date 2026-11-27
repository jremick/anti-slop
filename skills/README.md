# Bundled Agent Skill (`skills/`)

`anti-slop` is designed for AI coding agents to operate while humans stay in charge of engineering judgment and approvals. The bundled skill in [anti-slop/SKILL.md](anti-slop/SKILL.md) teaches Claude Code, Antigravity, and Codex when and how to invoke `anti-slop` subcommands automatically.

## Inspect or Install the Skill

Using the unified `anti-slop` CLI (installed locally or via `uvx`):

```bash
# Print the bundled SKILL.md content
anti-slop skill show

# Preview installation without writing any files
anti-slop skill install claude --dry-run
anti-slop skill install antigravity --dry-run
anti-slop skill install codex --dry-run

# Install for your agent harness (creates SKILL.md.bak-antislop if an existing file differs)
anti-slop skill install claude
anti-slop skill install antigravity
anti-slop skill install codex

# Install to a custom path or directory
anti-slop skill install claude --dest path/to/custom/skills/anti-slop

# Run zero-clone from GitHub with uvx
uvx --from git+https://github.com/jremick/anti-slop anti-slop skill show
uvx --from git+https://github.com/jremick/anti-slop anti-slop skill install claude --dry-run
```

## Default Install Locations

| Harness | Default destination |
| --- | --- |
| `claude` | `~/.claude/skills/anti-slop/SKILL.md` |
| `antigravity` | `~/.gemini/config/skills/anti-slop/SKILL.md` |
| `codex` | `~/.codex/skills/anti-slop/SKILL.md` |

Install behavior:

- **Safe backup:** If an existing file at the destination differs from the bundled skill, it is backed up to `SKILL.md.bak-antislop` before updating.
- **Idempotent:** Re-running when the file already matches exits `0` with no changes and no backup file.
- **Preview-first:** `--dry-run` prints the target path and planned action without creating directories or writing files.

## What the Skill Teaches Agents

1. **Plain-English Change Review:** Run `anti-slop review --json` (plus `anti-slop mutate` for Python logic changes), fix blocking shortcuts automatically, and summarize structural risks in plain English with tradeoffs.
2. **Conversational Self-Learning:** Check `anti-slop learn library list` first, draft narrow rules (`deterministic_check` > `codebase_example` > `<= 45`-word `prompt_rule`), run 3-way `anti-slop learn verify`, and pause for explicit human approval before `approve --by <human>`.
3. **Continuous Monitoring and Hygiene Mining:** Run `anti-slop learn mine --json`, auto-verify candidates, discard anything that fails or false-positives, and present only the verified shortlist for a human yes/no decision.
4. **Verification Hierarchy:** Prefer Tier 1 live end-to-end or real-artifact proof over Tier 2 behavioral/mutation tests over Tier 3 isolated mocked unit tests.
