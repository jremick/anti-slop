---
name: anti-slop
description: Run plain-English AI slop reviews, live E2E verification, diff-scoped Python and JS/TS mutation tests, human-approved self-learning rules, and continuous hygiene mining with the anti-slop CLI while keeping humans in charge of engineering judgment.
---

# anti-slop Agent Workflow

Operate `anti-slop` on the human's behalf so they never have to memorize CLI flags. Fix objective shortcuts automatically, run mechanical verification before making proposals, and reserve human attention for architecture tradeoffs and rule approvals.

## Workflow 1: Plain-English Change Review

Trigger: Before declaring work ready, or when asked to review changes for AI slop.

1. Run `anti-slop review --json` against the current git diff (or pass `--base origin/main` for a branch review). It checks surface shortcuts (`DIFF-*`), structural risks (`STRUCT-*`), architectural compounding slop (`ARCH-*`: circular imports, single-implementation wrappers, env-var boundary scatter), and approved learned rules (`LEARNED-*`).
2. For Python or JS/TS logic changes, also run `anti-slop mutate --test-cmd "<repo test command>" --json` to check whether tests catch real bugs injected on your changed lines.
3. Fix blocking errors automatically (`DIFF-*` shortcuts such as stubs, test skips, unjustified suppressions, silent catches, debug leftovers, hardcoded host paths, broken doc paths, or approved `LEARNED-*` errors), then re-run `anti-slop review --json` to confirm `ok: true`.
4. Summarize non-blocking structural and architectural risks (`STRUCT-*` and `ARCH-*` warnings) and any survived mutants in plain English for the human: state what changed, why it can compound across future sessions, and concrete fix options with tradeoffs. Never dump raw JSON or unexplained error codes.

## Workflow 2: Conversational Self-Learning

Trigger: The human points out a recurring AI slop pattern that slipped past existing checks.

Lifecycle: `capture -> propose -> verify -> human approve`.

1. Check the curated optional library first so you do not reinvent an existing guard:
   - Run `anti-slop learn library list` and `anti-slop learn library show <pack-or-rule-id>`.
   - If a matching optional rule exists, preview it with `anti-slop learn library enable <id> --by preview --dry-run` and stop for human approval before enabling.
2. Otherwise, choose the narrowest prevention layer (escalation ladder):
   - First: `deterministic_check` (zero standing prompt tokens; regex scoped by `--file-glob`).
   - Second: `codebase_example` (point to one canonical file with `--canonical-path`).
   - Last resort: `prompt_rule` (`<= 45` words, with `--why-not-deterministic` explaining why static checks cannot catch it).
3. Draft both the concrete bad example and a valid look-alike neighbouring case that must pass cleanly, then run:
   - `anti-slop learn capture --title "..." --bad-code "..." --valid-code "..." --desired "..." --file-glob "*.py"`
   - `anti-slop learn propose <ID> --layer ... --remediation "..." --retirement-trigger "..."`
   - `anti-slop learn verify <ID>`
4. If `verify` fails (misses the bad case, flags the valid look-alike, or produces false positives in the repo), tighten the pattern and re-verify, or discard the draft.
5. **Mandatory human approval gate:** Present the verified rule summary (layer, bad vs. valid case, repo scan hits, remediation, and retirement trigger) to the human. Always pause for explicit human approval before running `anti-slop learn approve <ID> --by <human>` (or `anti-slop learn library enable <id> --by <human>`). Never self-approve and never substitute an agent name for `--by`.

## Workflow 3: Continuous Monitoring and Hygiene Mining

Trigger: Periodic maintenance, end-of-sprint hygiene, or when asked to audit recurring slop and rule health.

1. Run `anti-slop learn mine --json` (read-only). It inspects opt-in local hook telemetry (when enabled) and recent git commits to surface:
   - recurring slop codes,
   - candidate optional library packs not yet enabled,
   - stale approved rules with zero recent hits that may be ready to retire.
2. Auto-verify every candidate before involving the human:
   - For candidate optional packs or rules, run `anti-slop learn library enable <id> --by preview --dry-run`.
   - For custom draft rules, run `anti-slop learn verify <ID>`.
   - Silently discard any candidate that fails verification or triggers false positives on the repo.
3. Present only the verified shortlist to the human for a yes/no decision:
   - verified new guards or optional packs worth enabling,
   - stale approved rules recommended for retirement via `anti-slop learn retire <ID> --reason "..."`.
4. Execute `approve`, `library enable`, or `retire` only after the human confirms each item.

## Workflow 4: Verification Hierarchy

Before reporting a bug fix or feature complete, verify behavior at the highest feasible tier:

1. **Tier 1 (Preferred): Live end-to-end or real-artifact proof.** Run `anti-slop verify` (using a project verify recipe from `anti-slop verify --init-example`, or ad-hoc `--cmd` / `--start` + `--http-get` flags) to execute the real CLI, server, API endpoint, or artifact flow and record a tamper-evident receipt. Confirm receipt freshness before sign-off with `anti-slop verify --check-receipt`.
2. **Tier 2: Behavioral and mutation-checked tests.** Run tests against real inputs and outputs, and confirm diff-scoped bug detection across Python or JS/TS changes with `anti-slop mutate --test-cmd "<test cmd>"`.
3. **Tier 3 (Weakest): Isolated mocked unit tests.** Restrict mocks to external network or clock boundaries; never rely on mock-only assertions as sole proof that an application works.

## Command Quick Reference

- `anti-slop review --json` (or `--base origin/main`, `--markdown`)
- `anti-slop verify --json` (or `--cmd "..."`, `--start "..." --http-get ...`, `--check-receipt`, `--markdown`)
- `anti-slop diff --diff - --no-budget`
- `anti-slop mutate --test-cmd "pytest -q" --json` (supports Python and JS/TS, e.g. `node --test`)
- `anti-slop learn library list` / `show <id>` / `enable <id> --by <human> --dry-run`
- `anti-slop learn capture|propose|verify|approve|retire|list|mine`
- `anti-slop hook --install claude|antigravity|codex --dry-run`
- `anti-slop skill show` / `anti-slop skill install claude|antigravity|codex --dry-run`
- `anti-slop api <config.json>`
