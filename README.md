# Anti-slop

[![Validate](https://github.com/jremick/anti-slop/actions/workflows/validate.yml/badge.svg)](https://github.com/jremick/anti-slop/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)

**You do not need to memorize CLI commands.** `anti-slop` is an **Agent-First, Human-Guided** toolkit built for your AI coding agent to run while you stay in charge of engineering judgment and approvals.

**Pre-v1 release (`0.8.0`):** Ready for daily use on Python and TypeScript/JS diffs with zero third-party dependencies, Tier 1 live E2E verification receipts (`anti-slop verify`), architectural slop detectors (`ARCH-*`), Python + JS/TS diff mutation (`anti-slop mutate`), 150-commit OSS precision audits, and `288` clean public runs (`standard/core.md` remains pinned independently at `0.2.0`, `298` words).

AI coding tools often produce code that looks convincing and passes a quick run while quietly accumulating hidden defects: skipped or over-mocked tests that stay green when features break ([Hora & Robbes, arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [EXT-13](docs/evidence.md#ext-13)), silent fallback defaults or bare type suppressions, copy-pasted logic that drifts across files ([GitClear 2025](https://www.gitclear.com/ai_assistant_code_quality_2025_research), [EXT-12](docs/evidence.md#ext-12)), commented-out code traps ([Huang et al., arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [EXT-14](docs/evidence.md#ext-14)), and growing monolithic functions or tight cross-module coupling ([Liu et al., arXiv:2603.28592](https://arxiv.org/abs/2603.28592); [Zhu et al., arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [EXT-15](docs/evidence.md#ext-15)).

Worse, **slop compounds across future AI sessions**. Coding agents imitate whatever patterns already sit in your repository ([Sun et al., ETH Zurich, arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [EXT-12](docs/evidence.md#ext-12)), while piling more prose rules into `AGENTS.md` or `CLAUDE.md` degrades compliance and raises inference cost ([IFScale, arXiv:2507.11538](https://arxiv.org/abs/2507.11538); [Gloaguen et al., arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [EXT-11](docs/evidence.md#ext-11)). Across our two live 4-turn evolution benchmarks below (`72` runs, `288` base stages, zero word caps), mechanical gates outperformed standing prose in both languages: **Python `EV1`: `50.0% -> 41.7%` (prompts) `-> 91.7%` (gated)** and **TypeScript `EV2`: `58.3% -> 66.7%` (prompts) `-> 100.0%` (gated, `0` slop, and `-10.4%` fewer tokens than prompts alone)**.

`anti-slop` runs on Python 3.11+ standard library only around three pillars:

1. **Catch shortcuts, compounding slop, and weak verification:** block objective shortcuts mid-turn or in CI, surface structural and architectural decay (`STRUCT-*` + `ARCH-*`) in plain English (`anti-slop review`), verify running apps/CLIs end-to-end with tamper-evident receipts (`anti-slop verify`), and test suite strength on changed Python and JS/TS lines with `anti-slop mutate`.
2. **Learn continuously with human approval:** when slop slips through, your agent captures a bad example plus a valid look-alike, checks the curated [Optional Rule Library](library/README.md), runs 3-way repo verification, and stops for your approval (`anti-slop learn`), or mines recent commits and opt-in hook logs read-only (`anti-slop learn mine`) to propose verified guards or retire stale ones.
3. **Prove which rules improve real software:** evaluate rules against live multi-turn Python (`EV1`) and TypeScript (`EV2`) evolution (functional bugs, mutation kill rate, duplicate blocks, dead shims, god functions, silent shortcuts; zero word caps) and controlled comment ablations (`CM1`, `CM2`), keeping what works and retiring what new models outgrow ([docs/continuous-evals.md](docs/continuous-evals.md)).

```mermaid
flowchart LR
  A["1. Catch shortcuts, slop & weak verification"] --> B["Plain-English review, live E2E verify & diff mutation"]
  B --> C["2. Capture, mine, or pick optional pack"]
  C --> D["3-way verify & human approve"]
  D --> E["Enforced automatically in hooks, pre-commit, and CI"]
  E --> A
  F["3. Multi-turn EV1/EV2 & CM1/CM2 evals"] -. "Prove, keep, or retire rules" .-> D
```

| What you want to do | Start here |
|---|---|
| Wire blocking hooks + conversational workflow skill into Claude Code, Antigravity, or Codex | [Agent Skill](skills/anti-slop/SKILL.md) + [gates/hooks/README.md](gates/hooks/README.md) |
| Verify a running app, API server, CLI, or artifact end-to-end with a tamper-evident receipt | [Live E2E Verification & Recipes](docs/verify-recipes.md) (`anti-slop verify`) |
| Understand which coding rules earned `KEEP` in `EV1` & `EV2` (and which pre-AI habits hurt) | [AI-Era Coding Rules Guide](docs/ai-era-rules.md) |
| Browse Default Core vs. 6 Opt-In Rule Packs vs. 6 Deliberately Excluded rules | [Optional Rule Library](library/README.md) (`anti-slop learn library list`) |
| Run continuous slop mining, new-model onboarding, and rule retirement | [Continuous Evals & Learning Loop](docs/continuous-evals.md) |
| Inspect diff gates, structural & architectural checks, plain-English review, and Python + JS/TS mutation | [gates/README.md](gates/README.md) (`anti-slop review`, `anti-slop mutate`) |
| Inspect live public datasets (`EV2`, `CM2`, `EV1`, `CM1`, `v0.6.0`), per-model profiles, and core standard | [results/README.md](results/README.md) + [docs/models.md](docs/models.md) + [standard/core.md](standard/core.md) |

---

## Set Up Once, Then Drive It Through Your Agent

Everything runs on Python 3.11+ standard library only (zero third-party installs, zero LLM API calls, zero standing prompt-token cost for mechanical gates).

### Option A: One-line agent onboarding (hooks + workflow skill)

Install once so your AI coding agent gets **both** blocking mid-turn hooks (stopping test skips, stubs, and unauthorized test edits outside the context window) **and** the conversational workflow skill ([skills/anti-slop/SKILL.md](skills/anti-slop/SKILL.md)):

```bash
# Install the unified zero-dependency CLI once
uv tool install git+https://github.com/jremick/anti-slop

# Wire blocking mid-turn hooks + conversational skill (preview first with --dry-run; backs up to *.bak-antislop)
anti-slop hook --install claude --dry-run && anti-slop skill install claude --dry-run
anti-slop hook --install claude && anti-slop skill install claude   # or: antigravity | codex
```

Without a global install, you can run via `uvx` or paste this prompt straight to your agent:

```bash
# Zero-install onboarding via uvx (replace claude with antigravity or codex)
uvx --from git+https://github.com/jremick/anti-slop anti-slop hook --install claude --dry-run
uvx --from git+https://github.com/jremick/anti-slop anti-slop skill install claude --dry-run
```

Once installed, drive `anti-slop` in plain English while you focus on design judgment and final approvals:

| What you ask your agent | What your agent runs and brings back to you |
|---|---|
| *"Review my changes for AI slop"* | Runs `anti-slop review`, fixes blocking shortcuts automatically, and explains structural and architectural risks (`STRUCT-*` + `ARCH-*`) in plain English. |
| *"Verify the running app/CLI end-to-end and save a receipt"* | Runs `anti-slop verify` ([docs/verify-recipes.md](docs/verify-recipes.md)), boots any required local service, executes real HTTP/CLI/file checks, tears down process groups cleanly, and writes a SHA-256 tamper-evident receipt (`.anti-slop/last-verify.json`) validated via `--check-receipt`. |
| *"Check whether our tests actually catch bugs in this diff"* | Runs `anti-slop mutate`, injects bugs strictly on changed Python or JS/TS lines in an isolated temp copy, and surfaces every surviving mutant. |
| *"Capture this slop pattern and propose a guard"* | Checks optional library packs first, drafts a bad example + valid look-alike + narrowest prevention, verifies it (`anti-slop learn`), and **stops for your explicit approval** (never self-approves). |
| *"Mine recent commits and hook logs for recurring slop"* | Runs read-only `anti-slop learn mine`, checks optional packs and stale rules for retirement, and brings a verified shortlist to you. |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/hook-loop-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/hook-loop-light.svg">
  <img alt="Blocking Stop hook loop: agent adds @pytest.mark.skip, anti-slop-hook exits 2 with stderr remediation, agent fixes the real bug and exits 0" src="docs/assets/hook-loop-light.svg">
</picture>

When a repository contains an approved `<repo>/.anti-slop/learned/rules.json` store, the `Stop` hook enforces approved deterministic rules automatically (and no-ops cleanly when no store exists). Opt-in local telemetry (`<repo>/.anti-slop/telemetry.jsonl`, zero code snippets, zero secrets, zero host paths) feeds `anti-slop learn mine` when `<repo>/.anti-slop/` exists or `ANTI_SLOP_TELEMETRY=1` is set. See [gates/hooks/README.md](gates/hooks/README.md) for harness contracts and Codex `execpolicy` templates.

### Option B: Automated repo guardrails (GitHub Actions & `pre-commit`)

GitHub Actions (reusable composite action via [action.yml](action.yml); opt-in `structural`, `strict-structural`, `explain`, `learned-rules`, and `exclude` inputs default off for backward compatibility):

```yaml
- uses: jremick/anti-slop@v0.8.0
  with:
    allow-test-edit: "true"
    no-budget: "true"
    check-pr-body: "true"
    # Optional opt-ins:
    # structural: "true"
    # explain: "true"
    # learned-rules: ".anti-slop/learned/rules.json"
    # exclude: |
    #   results/*/artifacts/**
    #   benchmarks/sources/**
```

Local `pre-commit` (wired via `.pre-commit-hooks.yaml`; choose fast `anti-slop-diff`, strict `anti-slop-diff-lock-tests`, or plain-English `anti-slop-review`):

```yaml
repos:
  - repo: https://github.com/jremick/anti-slop
    rev: v0.8.0
    hooks:
      - id: anti-slop-diff
      # Or opt in to plain-English review (shortcuts + structural/architectural risks + approved learned rules):
      # - id: anti-slop-review
```

### Sample plain-English review (`anti-slop review`)

```text
Anti-Slop Plain-English Review
==============================
Must-fix shortcuts: 1 | Compounding slop risks: 2

Must-Fix Shortcuts (Blocking)
-----------------------------
1. A test was skipped instead of fixing the bug [DIFF-TEST-SKIP] (tests/test_sync.py:8)
   What was found: tests/test_sync.py:8 adds test-skip/waiver annotation '@pytest.mark.skip'.
   Why engineers flag this: Adding a skip marker makes the test suite report green without verifying the broken behavior.
   How it compounds across AI turns: Future AI sessions see skipped tests as normal and keep skipping failing checks.
   Fix / prompt to give your AI: Remove the test skip annotation, fix the underlying code defect, and re-run the test suite.
   Reference: docs/evidence.md#local-05, docs/evidence.md#ext-13, docs/ai-era-rules.md

Compounding Slop Risks (Review Before Merging)
----------------------------------------------
1. Tests that look green without actually proving the code works [STRUCT-TEST-THEATER] (tests/test_sync.py:19)
   What was found: tests/test_sync.py:19 test 'test_sync_runs' contains zero assertions (only checks that code does not crash).
   Why engineers flag this: Tests with zero assertions, tautologies like 'assert True', or heavy mocking stay green even when you introduce an obvious bug.
   How it compounds across AI turns: Future AI turns trust the green test run and ship regressions believing the suite checked behavior that was never tested.
   Fix / prompt to give your AI: Prefer live end-to-end verification, or behavioral tests against real inputs backed by 'anti-slop-mutate', over mock-heavy unit tests.
   Reference: docs/evidence.md#ext-13, docs/ai-era-rules.md
```

### Live E2E verification (`anti-slop verify`), diff mutation (`anti-slop mutate`) & the 3-tier hierarchy

Coding agents edit tests almost twice as often as humans (`23%` vs. `13%`) and add mocks more often (`36%` vs. `26%`; [Hora & Robbes, arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [EXT-13](docs/evidence.md#ext-13)). Vanilla LLM unit tests average ~`53%` mutation kill rate, and even `100%`-coverage suites can score `4%` on mutants ([MutGen, arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [EXT-13](docs/evidence.md#ext-13)). `anti-slop` pairs Tier 1 live end-to-end verification (`anti-slop verify`, [docs/verify-recipes.md](docs/verify-recipes.md)) with Tier 2 diff-scoped mutation testing for **Python and JS/TS** (`anti-slop mutate`, inspired by Google Critique diff-based mutation with arid-node suppression, [Petrović et al., arXiv:2102.11378](https://arxiv.org/abs/2102.11378), [EXT-13](docs/evidence.md#ext-13)):

```bash
# Tier 1: Boot real service, check live HTTP response, tear down cleanly, and save a SHA-256 receipt
anti-slop verify --start "python3 -m myapp.server --port 18080" --http-get "http://127.0.0.1:18080/health" --expect-status 200 --markdown
anti-slop verify --check-receipt   # Fails (exit 1) if any file changed or receipt was edited afterward

# Tier 2: Inject bugs strictly on changed Python or JS/TS lines inside an isolated temp copy
anti-slop mutate --test-cmd "pytest -q"      # Python AST mutation
anti-slop mutate --test-cmd "node --test"    # JS/TS mutation (default for .ts/.js changes)
```

Treat verification evidence in three tiers (see [docs/ai-era-rules.md](docs/ai-era-rules.md#2-tests-and-verification-follow-the-3-tier-ai-era-verification-hierarchy)):

1. **Tier 1 (Strongest for apps, APIs, CLIs, UIs): Live end-to-end / real-artifact proof (`anti-slop verify`)** (run the real process against real inputs, verify observable output/HTTP/file state, and bind a tamper-evident receipt to the exact working tree).
2. **Tier 2 (Strong for logic and libraries): Behavioral integration/property tests + Python & JS/TS diff-scoped mutation (`anti-slop mutate`)** against real code without mocking the system under test.
3. **Tier 3 (Weakest): Same-turn isolated, heavily mocked unit tests** (useful for narrow external I/O boundaries only; weak proof on their own).

### Optional Rule Library ([library/README.md](library/README.md))

Default checks stay small on purpose so teams do not inherit noisy rules or prompt bloat. [library/README.md](library/README.md) ([library/catalog.json](library/catalog.json)) lays out all three buckets cleanly:

- **Default Core:** `15` Layer A `DIFF-*` checks, `11` Layer B `STRUCT-*` + `ARCH-*` checks, and `standard/core.md` (`R1`-`R7`, `298` words).
- **6 Curated Opt-In Packs (`10` `OPT-*` rules):** `network-timeouts`, `security-boundaries`, `comment-hygiene`, `verification-proof`, `build-config-hygiene`, and `architecture-simplicity`.
- **6 Deliberately Excluded Items (`EXCL-*`):** statistical AI-text detectors (`61.22%` non-native English FP), unfiltered SAST as blocking post-edit hooks (`65%`/`61%` ground-truth match), blanket "delete all comments", blanket "be concise" prompts, 100% line-coverage mandates, and heavyweight upfront DI wrappers.

```bash
anti-slop learn library list
anti-slop learn library show network-timeouts
anti-slop learn library enable network-timeouts --by <your-name> --dry-run
anti-slop learn library enable network-timeouts --by <your-name>
```

Every `library enable` call runs the full 3-way `verify_rule()` gate (must catch `bad_example`, `0` hits on `valid_neighbouring_case`, `<= --max-repo-hits` on your existing repo) and leaves `<repo>/.anti-slop/learned/rules.json` untouched if verification fails.

---

## What It Catches

Checks are split into two layers so objective shortcuts block immediately while heuristic structural patterns explain risks clearly without noisy false blocks. For concrete before/after examples, measured verdicts, and pre-AI habits that hurt AI workflows, read [AI-Era Coding Rules](docs/ai-era-rules.md).

### Layer A: Objective Shortcuts (Blocked by default in `anti-slop diff` and hooks)

| Rule ID | Catches | Example trigger | Allowed / escape hatch |
|---|---|---|---|
| `DIFF-TEST-SKIP` | Test-skip or waiver annotations added to test files (enforced even with `--allow-test-edit`) | `@pytest.mark.skip`, `@unittest.skipUnless`, `self.skipTest()`, `it.skip()` | Pass `--allow-test-skip` when a skip is explicitly authorized |
| `DIFF-UNAUTHORIZED-TEST-EDIT` | Any diff modifying files under `tests/` | Agent weakens assertions inside `tests/` during a code fix | Pass `--allow-test-edit` when test edits are in scope |
| `DIFF-SUPPRESSION` | Bare lint or type suppressions missing a rule code or inline reason | `# type: ignore`, `# noqa`, `@ts-ignore`, bare `eslint-disable`, bare `// nolint` | Scoped directives with reason (`# noqa: E402`, `# type: ignore[arg-type]  # upstream stub`, `// @ts-expect-error -- legacy CJS`) |
| `DIFF-SILENT-CATCH` | Bare or broad exception handlers that silently swallow errors | `except Exception: pass`, `except: return None`, empty JS/TS `catch (e) {}` | Narrowed exception types (`except ProcessLookupError: pass`) or handlers that log or re-raise |
| `DIFF-DEBUG-LEFTOVER` | Interactive debugger statements left in source code | `breakpoint()`, `pdb.set_trace()`, `ipdb.set_trace()`, JS/TS `debugger;` | Strings, comments, and object properties named `debugger` |
| `DIFF-HOST-PATH` | Hardcoded local workstation home paths containing a real username | `/Users/<name>/...`, `/home/<name>/...`, `C:\Users\<name>\...` | Explicit placeholders (`/Users/<user>/`, `/Users/...`, `/Users/example/`, `<HOME>`) and web URLs |
| `DIFF-STUB-*` (`TODO`, `NOT-IMPLEMENTED`, `PASS`) | Placeholder comments and unfinished bodies in added code | `# TODO:`, `raise NotImplementedError`, bare `pass` in concrete function | `@abstractmethod`, `@overload`, `Protocol` methods, and empty custom `Exception` subclasses |
| `DIFF-CHATBOT-OPENER` / `DIFF-CHATBOT-CLOSER` | Conversational openers or sign-offs in Markdown docs or PR bodies | `Sure!`, `Here is ...`, `Hope this helps`, `Let me know if you'd like...` | Direct technical opening and concrete closing status; code fences and inline backticks ignored |
| `DIFF-BROKEN-DOC-PATH` | Backticked local repository paths in Markdown that do not exist | Nonexistent relative repo path inside inline backticks | Valid repo paths, URLs, CLI flags, ALL-CAPS placeholders, gitignored paths, and fenced blocks |
| `DIFF-DECORATIVE-EMOJI` | Decorative AI emojis in technical headings, docs, or PR prose (`warning` by default) | Rocket, sparkles, fire, or party emojis outside code spans | Inline backticks and fenced code blocks; promote to hard error with `--strict-prose` |
| `DIFF-MAX-NET-LOC`, `DIFF-MAX-FILES` *(optional budgets)* | Oversized diffs exceeding defaults (`> 400` net LOC or `> 10` files) | Single diff adding 650 net LOC across 14 files | Disable with `--no-budget`, exclude globs with `--exclude`, or tune `--max-net-loc` / `--max-files` |

### Layer B: Compounding Structural & Architectural Slop (`11` checks in `anti-slop review` and `anti-slop diff --structural`)

Default `warning` (promote to blocking errors with `--strict-structural`):

| Rule ID | Plain-English meaning | What it detects | Valid neighbouring case (allowed) |
|---|---|---|---|
| `STRUCT-TEST-THEATER` | Tests that stay green even when code breaks | Python/JS/TS tests with zero assertions, tautologies (`assert True`, `assert x == x`, `expect(true).toBe(true)`), or `>= 3` mocks with zero real value/state assertions | Normal assertions, `pytest.raises`, `warnings.simplefilter("error", ...)`, `expectTypeOf`/`assertType`, AST-verified test helpers, or `<= 2` mocks with real output assertions |
| `STRUCT-SILENT-FALLBACK` | Made-up defaults hiding broken logic or missing secrets | Broad `except Exception:` returning a silent literal (`0`, `"unknown"`, `""`) without logging/re-raising; JS/TS `catch (e) { return 0; }`; hardcoded fallback strings on sensitive env vars (`*SECRET*`, `*API_KEY*`, `*TOKEN*`, `*PASSWORD*`) | Narrowed catches (`except KeyError: return 0`), logged broad catches, non-secret env defaults (`LOG_LEVEL`) |
| `STRUCT-DUPLICATE-BLOCK` | Copy-pasted logic that will drift out of sync (`EV2: KEEP`, `6 -> 0`) | Alpha-normalized Python AST clones (`>= 6` statements with real control flow/ops, catching variable-renamed copy-paste) and normalized JS/TS/Go blocks duplicated across production files or functions | Short helpers, flat constant blocks, test setup fixtures |
| `STRUCT-DEAD-COMPAT` | Dead branches and abandoned "legacy" shims (`EV1: KEEP`) | Unreachable `if False:` / `if 0:` branches, unreferenced `*_legacy`/`*_compat`/`*_deprecated` symbols, `allow_legacy_*` flags, and orphaned private module helpers never called anywhere | Live private helpers called in-module, decorated handlers, active adapters with callers |
| `STRUCT-COMMENTED-CODE` | Commented-out code traps poisoning future AI turns (`0` FPs across 150 OSS commits + 551 HEAD files; [Huang et al., arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [EXT-14](docs/evidence.md#ext-14)) | Newly added `>= 3`-line consecutive executable-looking commented-out code blocks in Python (AST-verified), JS/TS, and Go | Short 1-2 line `# INVARIANT:` / "why" notes ([Vitale et al., arXiv:2601.23059](https://arxiv.org/abs/2601.23059)), docstrings, JSDoc `@example`, fenced comment examples, license headers, URLs, and dividers |
| `STRUCT-GOD-FUNCTION` / `STRUCT-GOD-FILE` | Growing monolithic functions or files (`EV1 & EV2: KEEP`) | Functions exceeding `60` code lines or `12` branches `[Heuristic]`; production files growing above `400` code lines `[Heuristic]` | Focused helpers, or refactoring diffs that **shrink** an existing large file |
| `STRUCT-SCOPE-SPRAWL` | Unrequested edits scattered across unrelated modules | Single diff editing `> 3` distinct production module directories `[Heuristic]` | Focused feature touching one production module plus `tests/` and `docs/` |
| `ARCH-CIRCULAR-IMPORT` | Modules importing each other in a runtime cycle (`0` FPs / 150 OSS commits, `7/7` TP `hono` cycles) | Static runtime import cycles across changed Python or JS/TS production modules (`a.py -> b.py -> a.py`) | `if TYPE_CHECKING:` blocks, deferred function-local imports, JS/TS `import type` / `export type`, and tests |
| `ARCH-SINGLE-IMPL-WRAPPER` | Speculative indirection with only one real implementation (`0` FPs / 150 OSS commits) | Python `ABC`/`Protocol` with `<= 1` concrete impl, trivial pass-through `*Factory`/`*Wrapper`/`*Impl`, and JS/TS method-bearing single-impl `abstract class`/service wrappers | `__all__` public interfaces, `>= 2` concrete implementations, dataclasses/NamedTuples/TypedDicts, plain TS data DTO `interface` types |
| `ARCH-BOUNDARY-SCATTER` | Raw environment reads scattered across production modules (`0` FPs / 150 OSS commits) | Diffs reading the same raw `os.environ`/`os.getenv` or `process.env` key across `>= 3` distinct production modules instead of centralizing config validation | Single config module reading env vars, universal runtime keys (`PATH`, `HOME`, `CI`, `NODE_ENV`, `TZ`, `DEBUG`), and tests |

---

## Verified Self-Learning Loop (`R7` in Practice)

Standing prompt rules bloat quickly if every one-off mistake becomes another line in `AGENTS.md` or `CLAUDE.md` ([IFScale, arXiv:2507.11538](https://arxiv.org/abs/2507.11538); [Gloaguen et al., arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [EXT-11](docs/evidence.md#ext-11)). `anti-slop learn` (`gates/learn.py`) implements `R7` as an auditable, human-approved workflow that your agent drives on your behalf:

1. **Catch, Capture, or Mine:** Record a slipped mistake plus a **valid neighbouring case** (`capture`, assigning permanent ID `L-001`, `L-002`, ...), browse curated packs ([library/README.md](library/README.md)), or run read-only `anti-slop learn mine` to scan opt-in hook telemetry (`<repo>/.anti-slop/telemetry.jsonl`) and recent commits for recurring patterns and stale rules.
2. **Smallest Prevention Ladder:** `suggest` and `propose` enforce narrowest-scope-first:
   - `deterministic_check` (first choice: regex/pattern check at zero prompt tokens),
   - `codebase_example` (second choice: point to a canonical repo helper/file),
   - `prompt_rule` (last resort: capped at `<= 45` words, requires explicit `--why-not-deterministic` justification and a `--retirement-trigger`).
3. **3-Way Automated Verification (`verify`):** Verifies (a) the bad example is caught, (b) the valid neighbouring case has `0` hits, and (c) scanning your existing repository produces `<= --max-repo-hits` (default `0`) false positives.
4. **Human Approval Gate (`approve`):** Only rules with `status == "verified"` can be approved, bound to a SHA-256 hash of the verified proposal. Editing the rules store after approval invalidates the hash and fails closed (rule is ignored until re-verified and re-approved).
5. **Clean Retirement (`retire`):** Stops enforcing obsolete rules while preserving captured regression examples and leaving the stable ID permanently unused (never renumbered or reused).

```bash
# Direct CLI flow (usually executed by your agent via the anti-slop skill; human approves step 4)
anti-slop learn capture \
  --title "Float math on money amounts" \
  --bad-code "total = float(cents) / 100.0" \
  --desired "Keep currency math in integer cents or Decimal." \
  --valid-code "seconds = float(elapsed_ms) / 1000.0"

anti-slop learn propose L-001 \
  --layer deterministic_check --severity error \
  --pattern '\bfloat\s*\(\s*\w*(?:cent|dollar|price|amount)\w*\s*\)' \
  --remediation "Use integer cents or Decimal for currency math." \
  --retirement-trigger "Retire once static NewType(Cents) enforces integer-only math."

anti-slop learn verify L-001
anti-slop learn approve L-001 --by maintainer   # human approval required
anti-slop learn mine --commits 30               # read-only telemetry + git pattern scan
```

Approved deterministic rules are enforced automatically by `anti-slop review`, the live `Stop` hook (`anti-slop hook`), `anti-slop diff --learned-rules <store>`, and opt-in `learned-rules` in `action.yml`.

---

## Empirical Evidence: Live Cross-Language Evolution, Comment Ablations, and `v0.6.0`

All five public datasets under [results/](results/README.md) (`288` total runs across 4 frontier models, `n = 3` replicates per cell) executed in isolated temp workspaces outside this repository with per-run isolated `CODEX_HOME`/`HOME` and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` secrets).

### 1. Multi-Turn Compounding Software Quality: TypeScript `EV2` & Python `EV1` (72 runs, 288 base stages, 0 word caps)

Across both languages, mechanical gating beat standing prose prompts cleanly: **Python `EV1`: `50.0% -> 41.7%` (prompts) `-> 91.7%` (gated)** and **TypeScript `EV2`: `58.3% -> 66.7%` (prompts) `-> 100.0%` (gated, `0` slop, `-10.4%` fewer tokens than prompts)**.

#### TypeScript `EV2` (`pilot-ts-evolution-v0.8.0`, 36 runs, 144 base stages)

Full report and raw artifacts: [results/pilot-ts-evolution-v0.8.0/README.md](results/pilot-ts-evolution-v0.8.0/README.md) ([LOCAL-09](docs/evidence.md#local-09)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pilot-v0.8.0-ts-evolution-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/pilot-v0.8.0-ts-evolution-light.svg">
  <img alt="Live EV2 TypeScript multi-turn code quality benchmark across 36 runs and 144 stages: baseline 58.3% (7/12), standing core-rules 66.7% (8/12, INCONCLUSIVE), gated-structural 100.0% (12/12, KEEP, 0 slop defects, 79.2% JS/TS mutation kill rate, -10.4% tokens vs prompts)" src="docs/assets/pilot-v0.8.0-ts-evolution-light.svg">
</picture>

Across 4 sequential turns on an evolving zero-dependency erasable TypeScript booking service ([benchmarks/cases/EV2.json](benchmarks/cases/EV2.json); `36/36` completed, `144/144` stage functional passes on native Node.js TS, 100% mechanically graded by [benchmarks/graders/grade_ev2.py](benchmarks/graders/grade_ev2.py)):

| Condition Arm (`12` runs/arm) | Overall Pass | TS Mutation Kill Mean / Med | Total Slop (`/run`) | Duplicate Blocks | God Fns | Suppression / Other | Total Tokens (vs. base) | Opus USD (vs. base) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | **`7/12` (`58.3%`)** | `74.17%` / `80.00%` | `10` (`0.83`) | `6` | `4` | `0` | `17,285,400` (`+0.0%`) | `$5.4059` (`+0.0%`) |
| `core-rules-v0.2.0` (prompts alone) | **`8/12` (`66.7%`)** | `75.00%` / `75.00%` | `5` (`0.42`) | `2` | `3` | `0` | `19,531,186` (`+13.0%`) | `$6.0341` (`+11.6%`) |
| `gated-structural` (mechanical gates) | **`12/12` (`100.0%`)** | **`79.17%` / `77.50%`** | **`0` (`0.00`)** | **`0`** | **`0`** | **`0`** | **`17,499,580` (`+1.2%`)** | **`$5.5231` (`+2.2%`)** |

Key measured findings and tradeoffs (`EV2`):

1. **`100.0%` (`12/12`) pass with aggregate `KEEP`, cheaper and faster than standing prompts:** Standing prose (`core-rules-v0.2.0`) lifted pass rate by only 1 run (`7/12 -> 8/12`, `INCONCLUSIVE`) while adding `+13.0%` tokens, `+11.6%` Opus USD, and `+9.6%` Stage 1-4 wall time. Mechanical gating (`gated-structural`) reached **`12/12` (`100.0%`)** (`+5/-0` vs. baseline, `+4/-0` vs. prompts, aggregate **`KEEP`** vs. baseline at `+5.00pp` TS mutation kill), cut slop **`10 -> 0`**, and used **`-10.4%`** fewer tokens, **`-8.5%`** lower Opus USD, and **`-6.8%`** less wall time than standing prompts (`+1.2%` tokens / `+2.2%` Opus USD / `+2.1%` wall vs. baseline).
2. **Zero suppression noise, 100% real structural compounding defects:** All 36 `EV2` runs had **`0`** `DIFF-*` shortcut/suppression hits, `0` dead compat, `0` circular imports, and `0` test theater. Every single defect in `baseline` (`10`) and `core-rules-v0.2.0` (`5`) was a real TypeScript compounding defect: `STRUCT-DUPLICATE-BLOCK` (`6 -> 2 -> 0`, copy-pasted booking logic between `bookings.ts` and `corporate.ts`) and `STRUCT-GOD-FUNCTION` (`4 -> 3 -> 0`, functions over `65L`).
3. **Model split and attribution:** `gpt-6.2-astra` and `gpt-6.2-sol` already passed `3/3` at baseline (`0` slop). On `gemini-4-neon`, `gates/review.py` fired `4` mid-evolution repair turns (`3` `STRUCT-GOD-FUNCTION` on `createGroupBooking` at `72L-77L` + `3` `STRUCT-DUPLICATE-BLOCK`), lifting Neon from **`0/3` (`baseline` & `core-rules`) to `3/3`** (`+21.7pp` TS mutation kill, `58.3% -> 80.0%`) while spending **`-10.9%`** fewer tokens than baseline. `claude-opus-5-5` moved `1/3 -> 2/3 -> 3/3` (`2` baseline duplicates + `1` god function -> `0`) with **`0`** post-stage repair turns triggered, so its lift reflects upfront gate-awareness or `n = 3` variance rather than post-stage repair.

#### Python `EV1` (`pilot-evolution-v0.7.0`, 36 runs, 144 base stages)

Full report and raw artifacts: [results/pilot-evolution-v0.7.0/README.md](results/pilot-evolution-v0.7.0/README.md) ([LOCAL-07](docs/evidence.md#local-07)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pilot-v0.7.0-evolution-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/pilot-v0.7.0-evolution-light.svg">
  <img alt="Live EV1 multi-turn code quality benchmark across 36 runs and 144 stages: baseline 50.0% (6/12), standing core-rules 41.7% (5/12, DROP on Opus and Sol), gated-structural 91.7% (11/12, 0 slop defects, 74.7% AST mutation kill rate)" src="docs/assets/pilot-v0.7.0-evolution-light.svg">
</picture>

Across 4 sequential turns on the same evolving Python billing/ledger codebase ([benchmarks/cases/EV1.json](benchmarks/cases/EV1.json); `36/36` completed, `144/144` base stages functional pass, 100% mechanically graded by [benchmarks/graders/grade_ev1.py](benchmarks/graders/grade_ev1.py)):

| Condition Arm (`12` runs/arm) | Overall Pass | Functional (`4` turns) | AST Mutation Kill Mean / Med | Total Slop Defects (`/run`) | God Fns | Silent / Shortcuts | Test Theater | Stage 1-4 Wall Time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | **`6/12` (`50.0%`)** | `12/12` | `70.56%` / `66.67%` | `75` (`6.25`) | `3` | `71` | `1` | `5,415.0s` (`+0.0%`) |
| `core-rules-v0.2.0` (prompts alone) | **`5/12` (`41.7%`)** | `12/12` | `67.22%` / `63.33%` | `45` (`3.75`) | `3` | `42` | `0` | `5,161.0s` (`-4.7%`) |
| `gated-structural` (mechanical gates) | **`11/12` (`91.7%`)** | `12/12` | **`74.72%` / `73.33%`** | **`0` (`0.00`)** | **`0`** | **`0`** | **`0`** | `5,506.8s` (`+1.7%`) |

Key measured findings and tradeoffs (`EV1`):

1. **Mechanical gates outperformed standing prompts alone (`91.7%` vs. `41.7%`):** Standing prose instructions (`core-rules-v0.2.0`) **regressed** overall pass rate (`6/12 -> 5/12`, `+1/-2`) and weakened mean mutation kill rate (`70.6% -> 67.2%`), scoring **`DROP`** on both `claude-opus-5-5` (`1/3 -> 0/3`, `66.7% -> 60.0%` mut) and `gpt-6.2-sol` (`77.8% -> 68.9%` mut). Mechanical gating (`gated-structural`) jumped pass rate to **`11/12` (`91.7%`)** (`+6/-1` vs. baseline, `+6/-0` vs. prompts), cut slop **`75 -> 0`**, and lifted AST mutation kill rate **`+7.5pp`** vs. prompts (`KEEP` aggregate and on 3/4 models: Opus `1/3 -> 3/3`, Astra `3/3` [`+6.7pp`], Neon `0/3 -> 3/3`).
2. **Mid-evolution structural and test-theater catches:** On `gemini-4-neon`, `gated-structural` cut god functions **`3/3 -> 0/3`** (`maxFnL 75L -> 49L`) and lifted mutation kill rate to **`82.2%`**. On `claude-opus-5-5`, it caught an assertion-free smoke test (`STRUCT-TEST-THEATER`, `1 -> 0`) at Stage 2 `r3`. Pre-repair catches across `15` repair turns comprised `15` `DIFF-SUPPRESSION`, `10` `STRUCT-DEAD-COMPAT`, `5` `STRUCT-GOD-FUNCTION`, and `1` `STRUCT-TEST-THEATER`.
3. **Defect composition, token overhead, and lone miss:** All `113/113` `silent_failures_and_shortcuts` defects in `baseline` (`71`) and `core-rules-v0.2.0` (`42`) were bare `# type: ignore[...]` comments lacking inline reasons (`0` broad silent `except`, `0` skips, `0` stubs). The `15` repair turns kept Stage 1-4 wall time nearly flat (`+1.7%`) while adding **`+18.7%` to `+43.8%` total tokens** (`+11.3%` Opus USD, `$5.34 -> $5.95`), and `gpt-6.2-sol r1` (`60.0% < 65%` mut kill, `0` slop) remained the sole gated miss because `anti-slop mutate` was not yet wired into the Stage 1-4 gate loop.

### 2. Controlled Comment-Hygiene Ablations (`CM1` + `CM2`, 72 runs total)

Full reports: [results/pilot-comments-v0.7.0/README.md](results/pilot-comments-v0.7.0/README.md) (`CM1`, [LOCAL-06](docs/evidence.md#local-06)) and [results/pilot-comments-v0.8.0/README.md](results/pilot-comments-v0.8.0/README.md) (`CM2`, [LOCAL-08](docs/evidence.md#local-08)).

Testing identical-AST Python codebases across 4 models x 3 arms x `n = 3` in both a single 90-line webhook file (`CM1`, explicit prompt invariants) and a 6-module 345-line job-queue package (`CM2`, both cross-file invariants omitted from the prompt; `72/72` completed, 100% mechanically graded by [grade_cm1.py](benchmarks/graders/grade_cm1.py) and [grade_cm2.py](benchmarks/graders/grade_cm2.py); motivated by [EXT-14](docs/evidence.md#ext-14)):

| Suite & Condition Arm (`12` runs/arm) | Pass (`4` checks) | Aggregate Wall Time (vs. `no-comments`) | Opus USD (vs. `no-comments`) | Comment Diff Churn |
|---|---:|---:|---:|---|
| `CM1` (1 file, `90L`): `no-comments` (`0` cmts) | `12/12` (`100.0%`) | `413.0s` (`+0.0%`) | `$0.4022` (`+0.0%`) | `+0 / -0` on `12/12` |
| `CM1`: `invariant-comments` (`3` `# INVARIANT:`) | `12/12` (`100.0%`) | **`394.3s` (`-4.5%`)** | **`$0.3953` (`-1.7%`)** | All `3` preserved verbatim on `12/12` |
| `CM1`: `comment-traps` (`28` trap cmts) | `12/12` (`100.0%`) | **`523.5s` (`+26.8%`; `+32.8%` vs. inv)** | **`$0.5288` (`+31.5%`)** | `-28` comment lines scrubbed on `12/12` |
| `CM2` (6 modules, `345L`): `no-comments` (`0` cmts) | `12/12` (`100.0%`) | `1,354.6s` (`+0.0%`) | `$0.9569` (`+0.0%`) | `-0 / +0..+2` comments |
| `CM2`: `invariant-comments` (`4` `# INVARIANT:`) | `12/12` (`100.0%`) | **`1,262.8s` (`-6.8%`; `-8.4%` vs. traps)** | **`$0.9344` (`-2.4%`; `-16.1%` vs. traps)** | `9/12` kept all `4` (`gpt-6.2-sol` stripped all `4` on `3/3`) |
| `CM2`: `comment-traps` (`67` trap cmts) | `12/12` (`100.0%`) | `1,378.5s` (`+1.8%`; `+9.2%` vs. inv) | **`$1.1135` (`+16.4%`; `+19.2%` vs. inv)** | `-20..-67` comment lines scrubbed (`-67` on `9/12`) |

Across all 72 runs, all 4 frontier models hit a **`24/24` accuracy ceiling** (`INCONCLUSIVE` on pass rate) because 1-to-6 stdlib modules still fit comfortably in one context window for direct control-flow verification. Even at `100%` accuracy, short `# INVARIANT:` notes were consistently the **fastest and lowest-cost arm** (`-4.5%` / `-6.8%` wall time, `-1.7%` / `-2.4%` Opus USD vs. `no-comments`), whereas `comment-traps` inflated Opus USD **`+31.5%` / `+16.4%`** and forced `-28` / `-20..-67` deleted comment lines per run. `CM2` also revealed a model-specific preservation gap: `gpt-6.2-sol` silently stripped all 4 `# INVARIANT:` comments while refactoring on `3/3` runs.

### 3. Frozen-Test Integrity & Per-Model Overlays (`pilot-3way-v0.6.0`, 144 runs)

Full report and per-run verbatim reviews: [results/pilot-3way-v0.6.0/README.md](results/pilot-3way-v0.6.0/README.md) ([LOCAL-05](docs/evidence.md#local-05)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/pilot-v0.6.0-results-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/pilot-v0.6.0-results-light.svg">
  <img alt="Empirical results from pilot-3way-v0.6.0 across 144 runs showing core rules cutting frozen-test tampering from 72.7% to 0%, core matching model-controls on 3 of 4 models, Opus D-OPU-4 brevity and cost gains, and Opus SE2 unresolved failures" src="docs/assets/pilot-v0.6.0-results-light.svg">
</picture>

Across 4 frontier models, 4 real-world OSS and PR-audit tasks, and `n = 3` runs per cell (`144` runs total, `142` completed + `2` `720s` timeouts kept in denominators):

1. **Core rules stopped test-skip cheating (`RW3`, `urllib3`):** Under release pressure, **`8/11` (`72.7%`)** completed baseline runs quietly modified a frozen test file (`@unittest.skip*`, `self.skipTest`) to waive a failing check (`Astra` `3/3`, `Sol` `3/3`, `Opus` `2/3`, `Neon` `0/2`). Standing `core-rules-v0.2.0` cut tampering to **`0/12` (`0%`)**, and `model-controls` stayed at **`0/11` (`0%`)**.
2. **`model-controls` tied `core-rules` on 3 of 4 models:** On `GPT-6.2 Astra` (`12/12` vs `12/12`), `GPT-6.2 Sol` (`11/12` vs `11/12`), and `Gemini 4 Neon` (`12/12` vs `12/12`), per-model overlays did not raise pass rate above `core-rules-v0.2.0` while adding matched token overhead (`+15.8%`/`+15.2%` Astra, `+10.8%`/`+4.2%` Sol, `+26.1%`/`+23.6%` Neon). Per-model overlays only moved pass rate on **`Claude Opus 5.5`** (`5/12 -> 8/12`; `8/8` completed OSS) via `D-OPU-4`, eliminating word-cap/wrapper overruns (`0/11`) while cutting matched lexical words **`-31.6%`**, USD **`-6.9%`** (`$3.94 -> $3.67`), and wall time **`-21.8%`**.
3. **Why `v0.6.0` motivated shifting to `EV1` & `EV2`:** Prompt rules still failed `8/9` Opus `SE2` Stage 2 runs (deferral concessions or `pytest`-only TS verification), and outside `RW3` test tampering and Opus `SE2`, the remaining `12` completed-run failures were word-cap/wrapper misses rather than multi-turn structural code decay. That gap motivated building and running `EV1` and `EV2` above.

| Benchmark Slice (`48` runs/arm total) | `baseline` | `core-rules-v0.2.0` | `model-controls` | Net `B -> M` |
|---|---|---|---|---:|
| **All 4 scenarios** (`RW3`, `RW5`, `RW6`, `SE2`; `48`/arm) | **`31/48` (`64.6%`)** *(31/47 comp.)* | **`40/48` (`83.3%`)** | **`43/48` (`89.6%`)** *(43/47 comp.)* | **`+12/-0`** |
| **Pinned Python OSS tasks** (`urllib3` `RW3`, `sqlparse` `RW5`, `tomlkit` `RW6`; `36`/arm) | **`22/36` (`61.1%`)** *(22/35 comp.)* | **`30/36` (`83.3%`)** | **`34/36` (`94.4%`)** *(34/35 comp.)* | **`+12/-0`** |
| **Polyglot TS+Python PR audit** (`SE2`; `12`/arm) | **`9/12` (`75.0%`)** | **`10/12` (`83.3%`)** | **`9/12` (`75.0%`)** | `0` |
| **Strict `wc -w` sensitivity (all 4 scenarios)** (`48`/arm) | **`26/48` (`54.2%`)** | **`37/48` (`77.1%`)** | **`42/48` (`87.5%`)** | **`+16`** |

<details>
<summary>Audit methodology &amp; isolation details (<code>LOCAL-05</code> through <code>LOCAL-09</code>)</summary>

- **Isolation &amp; privacy:** All five published datasets (`288` total runs) executed under per-run isolated `CODEX_HOME`/`HOME` with deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` personal skills, `0` `.agy.log` files across all published files under `results/`).
- **Scoring split:** `LOCAL-06` (`CM1`, `grade_cm1.py`), `LOCAL-07` (`EV1`, `grade_ev1.py`), `LOCAL-08` (`CM2`, `grade_cm2.py`), and `LOCAL-09` (`EV2`, `grade_ev2.py`) are **100% mechanically graded** with zero LLM judging and zero word caps. In `LOCAL-05` (`pilot-3way-v0.6.0`), deterministic checks (`benchmarks/graders/grade_rw3.py`, frozen-test `git diff`, read-only checks, lexical/`wc -w` counts) were mechanically verified, while semantic rubric checks were scored via isolated per-case verbatim audit passes committed under `results/pilot-3way-v0.6.0/reviews/`.

</details>

---

## Continuous Improvement & Roadmap Toward v1.0

`0.8.0` is an active pre-v1 release designed to evolve with each new model generation instead of accumulating permanent rule debt. See [docs/continuous-evals.md](docs/continuous-evals.md) for the full runbook covering:

- **Continuous project monitoring (`anti-slop learn mine`):** Read-only mining of opt-in local hook telemetry (`<repo>/.anti-slop/telemetry.jsonl`) and recent git commits to recommend optional rule packs, flag recurring slop, and identify stale rules ready for retirement, always gated by 3-way verification and human approval.
- **Repeatable new-model onboarding ([scripts/eval_cycle.py](scripts/eval_cycle.py)):** Generates longitudinal scorecards across all five committed datasets under `results/` (`288` runs, including a rule-retirement watch whenever baseline reaches `100%` across all models) and exact isolated `scripts/run_benchmark.py` onboarding commands across all five suites (`evolution`, `ts-evolution`, `comments`, `comments-multifile`, `integrity`).

### Shipped in `0.8.0`

- **Tier 1 live E2E verification (`anti-slop verify`):** Boot background services, run real HTTP/CLI/file checks, tear down process groups cleanly, and emit SHA-256 tamper-evident receipts ([docs/verify-recipes.md](docs/verify-recipes.md)).
- **Architectural slop detectors (`ARCH-*`):** `ARCH-CIRCULAR-IMPORT`, `ARCH-SINGLE-IMPL-WRAPPER`, and `ARCH-BOUNDARY-SCATTER` in `gates/architecture.py` (`0` FPs across 150 OSS commits + `7/7` TP `hono` runtime cycles).
- **JS/TS diff-scoped mutation testing (`anti-slop mutate`) & Node 24 CI:** Extends isolated diff mutation to `.js`/`.ts` modules alongside Python.
- **Live `n = 3` TypeScript evolution (`EV2`) & 6-module comment ablation (`CM2`):** `72` new clean isolated runs published under `results/`.

### Next frontier toward `v1.0`

1. **Playwright / browser visual verification adapter:** Extend `anti-slop verify` with headless browser flow checks, DOM/console assertions, and visual artifact verification for frontend UIs.
2. **Deeper architectural coupling & data-model drift checks:** Detect cross-module fan-in/fan-out spikes, schema/DTO drift across service boundaries, and leaky abstraction layers.
3. **Broader language & scale evals:** Go and Rust multi-turn evolution suites (`EV3+`), plus 1,000+ line cross-repo context-rot comment evals testing external invariants that cannot be inferred from local source alone.
4. **PyPI publication & scheduled cross-model re-evaluations:** Publish `anti-slop` to PyPI (`pip install anti-slop` / `uvx anti-slop`) and run recurring `eval_cycle.py` onboarding and rule-retirement passes as new frontier models release.

### Known limits in `0.8.0`

- **Single-scenario constructed scope in `EV1`, `EV2`, `CM1`, and `CM2`:** These `n = 3` datasets establish run-to-run consistency on stdlib Python and erasable TypeScript scenarios, not generalization across arbitrary bundled multi-service monorepos.
- **Untriggered rules stay labeled as candidates:** `STRUCT-SILENT-FALLBACK` (`0` triggers in `EV1` & `EV2`) and `ARCH-*` (`0` FPs across 150 OSS commits and `7/7` TP `hono` cycles, but `0` triggers in `EV2`) remain labeled `Candidate` / `Practitioner hypothesis` for causal `EV` lift in [docs/ai-era-rules.md](docs/ai-era-rules.md).
- **Opus `EV2` repair attribution:** `claude-opus-5-5` improved `1/3 -> 3/3` in `EV2` with `0` post-stage repair turns triggered, so its lift reflects upfront gate-awareness or `n = 3` variance rather than post-stage repair intervention.
- **Heuristic structural thresholds stay warning-only by default:** The 150-commit OSS audit confirmed `96.7%` clean pass rate on non-size defect rules and `0` FPs on `ARCH-*`, while `STRUCT-GOD-FILE` / `STRUCT-GOD-FUNCTION` frequently fire on pre-existing large OSS modules (keep `--strict-structural` opt-in for greenfield or refactored modules).
- **Opus `SE2` Stage 2 verification gap & Fable 5.2 exclusion:** Documented in [results/pilot-3way-v0.6.0/README.md](results/pilot-3way-v0.6.0/README.md) and [docs/models.md](docs/models.md).
- **Live external citations:** External sources in [docs/evidence.md](docs/evidence.md) are date-stamped (24-27 November 2026, live-verified via arXiv Atom API, Crossref/OpenAlex, and HTTP checks) rather than web-archived; recheck upstream pages before relying on them downstream.

---

## Technical Reference

### Unified CLI reference (`anti-slop`)

All commands dispatch from one top-level entry point (all 7 legacy `anti-slop-*` console scripts remain installed in `pyproject.toml` for backward compatibility, `8` scripts total):

```bash
anti-slop review [--markdown|--json] [--fail-on-warning]             # Plain-English diff + structural/architectural + learned review
anti-slop verify [--recipe .anti-slop/verify.json|--check-receipt]   # Live Tier-1 E2E checks + SHA-256 tamper-evident receipts
anti-slop diff --diff - --no-budget [--exclude <glob>]               # Fast blocking Layer-A diff/prose gate
anti-slop mutate --test-cmd "pytest -q" [--base origin/main]         # Isolated diff-scoped Python & JS/TS mutation testing
anti-slop learn <capture|propose|verify|approve|retire|library|mine> # Verified self-learning, packs, and pattern mining
anti-slop hook --install <claude|antigravity|codex> [--dry-run]      # Mid-turn PreToolUse/Stop hook adapter & installer
anti-slop skill <show|install <claude|antigravity|codex>>            # Inspect or install the bundled agent workflow skill
anti-slop api <path/to/model-config.json>                            # Validate 2026 model API & harness configs
```

### How This Complements Ruff, ESLint, and Semgrep

Keep language-specific AST linters (`ruff`, `eslint`, `mypy`, `tsc`) for deep single-language rules and SAST tools (`Semgrep`, `CodeQL`) for security taint analysis. `anti-slop` sits beside them as a zero-config, zero-dependency polyglot diff, structural/architectural review, live E2E verification, mutation, learning, and agent-hook layer:

| Capability | Ruff / ESLint / mypy | Semgrep / CodeQL | `anti-slop` |
|---|---|---|---|
| Deep single-language AST lint and type checking | Primary tool | Partial | Not a replacement (keep existing linters) |
| Security vulnerability and taint SAST | Limited | Primary tool | Not a replacement (avoid raw SAST as blocking hooks; see [EXT-13](docs/evidence.md#ext-13)) |
| Zero-config polyglot diff gate + blocking `PreToolUse`/`Stop` agent hooks | Per-stack config / manual glue | Rulepacks / too slow for hooks | Built-in (`anti-slop diff`, `anti-slop hook --install`, `anti-slop skill install`) |
| Catch test-skip waivers, test theater, silent fallbacks, duplicate clones, dead shims, comment traps, circular imports, single-impl wrappers, and config scatter in plain English | Partial per-language only | Custom rules only | Built-in (`anti-slop review`, `gates/structural.py`, `gates/architecture.py`) |
| Tier-1 live E2E service/HTTP/CLI/artifact verification with SHA-256 receipts | Not built in | Not built in | Built-in (`anti-slop verify`, [docs/verify-recipes.md](docs/verify-recipes.md)) |
| Diff-scoped Python & JS/TS mutation testing on changed lines | Not built in | Not built in | Built-in (`anti-slop mutate`, isolated temp copy) |
| Human-gated, repo-verified self-learning loop, continuous mining, and curated optional library | Manual rule authoring | Manual rule authoring | Built-in (`anti-slop learn`, `anti-slop learn mine`, `library/catalog.json`) |

**Real-world OSS precision audits (150 commits across `urllib3/urllib3`, `sdispater/tomlkit`, and `honojs/hono`):**

- **Layer A (`gates/diff_check.py`, `--allow-test-edit --no-budget`):** `136/150` (`90.7%`) commits passed clean with `0/29` parser or regex false positives post-fix (`24/29` mypy `# type: ignore[<code>]` comments missing an inline `# <reason>`, `4/29` intentional upstream skips or catches, and `1/29` moved `TODO`).
- **Layer B Structural (`gates/structural.py`, warning-only default):** `145/150` (`96.7%`) commits passed clean on non-size structural defect rules (`STRUCT-SILENT-FALLBACK`: `0`, `STRUCT-DEAD-COMPAT`: `0`, `STRUCT-COMMENTED-CODE`: `0`, `STRUCT-SCOPE-SPRAWL`: `0`, `STRUCT-DUPLICATE-BLOCK`: `4` true mirrored-adapter duplicates in `hono`, `STRUCT-TEST-THEATER`: `3` no-assert/string-eval tests in `urllib3`), plus `0` false positives for `STRUCT-COMMENTED-CODE` across `551` OSS HEAD files. `65/72` total structural warnings came from growing pre-existing 518-to-1,951-line OSS files/methods.
- **Layer B Architectural (`gates/architecture.py`, warning-only default):** **`0` false positives across all 150 OSS commits** (`0` hits in `urllib3`, `tomlkit`, and `hono`), **`7/7` verbatim-verified true runtime circular imports** across `316` OSS HEAD production files (all in `hono` JSX/streaming, `0` `ARCH-SINGLE-IMPL-WRAPPER`, `0` `ARCH-BOUNDARY-SCATTER`), and `0` hits across `anti-slop` itself (`33` prod files + `17` commits). Full SHAs and reproduction steps are in [gates/README.md](gates/README.md#real-world-oss-precision-audit).

### Architecture

1. **Unified CLI, Deterministic Gates, Plain-English Review, Live Verification, Diff Mutation, Self-Learning, Hooks & Skill (`0` standing prompt tokens):**
   - Eight console scripts in `pyproject.toml`: unified `anti-slop` plus legacy `anti-slop-diff` (`gates/diff_check.py`), `anti-slop-review` (`gates/review.py`), `anti-slop-verify` (`gates/verify.py`), `anti-slop-learn` (`gates/learn.py`), `anti-slop-mutate` (`gates/mutate.py`), `anti-slop-hook` (`gates/hooks/run_diff_gate_hook.py`), and `anti-slop-api` (`gates/api_checks.py`), alongside `gates/structural.py`, `gates/architecture.py`, warning-first `gates/vale/`, `gates/ci-ratchet.yml`, [skills/anti-slop/SKILL.md](skills/anti-slop/SKILL.md), and [library/README.md](library/README.md) (`library/catalog.json`). See [gates/README.md](gates/README.md).
2. **Lean Core Standard (`<= 300` words) & AI-Era Guidance:**
   - [standard/core.md](standard/core.md): seven stable-ID rules (`R1`-`R7`, `298` words, independently pinned at `0.2.0`; retiring a rule leaves a gap rather than renumbering). Rationale, measured AI-era rules vs. pre-AI anti-patterns, live E2E recipes, continuous eval runbooks, and operating workflows stay out of standing prompts in [docs/ai-era-rules.md](docs/ai-era-rules.md), [docs/verify-recipes.md](docs/verify-recipes.md), [docs/continuous-evals.md](docs/continuous-evals.md), [docs/operating-guide.md](docs/operating-guide.md), and [docs/operations-and-routing.md](docs/operations-and-routing.md).
3. **Per-Model Deltas & Auditable Benchmarks:**
   - [gates/model_deltas.json](gates/model_deltas.json), [docs/models.md](docs/models.md), [docs/evidence.md](docs/evidence.md): opt-in per-model overlays (`D-AST`, `D-SOL`, `D-OPU`, `D-FAB`, `D-NEO`) loaded one model at a time.
   - [benchmarks/README.md](benchmarks/README.md) & [benchmarks/graders/README.md](benchmarks/graders/README.md): **28 versioned cases** (`22` constructed including 4-turn Python `EV1`, 4-turn TypeScript `EV2`, `CM1`, and `CM2` + `6` pinned OSS `origin: real_work` tasks `RW1`-`RW6`), **15 automated stdlib graders**, **9 pilot manifests**, `benchmarks/evolution.py`, `scripts/benchmark.py`, [scripts/eval_cycle.py](scripts/eval_cycle.py), and **5 clean public datasets** (`288` total runs under [results/](results/README.md)).

### Verify the repository locally

Requires Python 3.11+ (plus Node 24+ for JS/TS mutation & `EV2` tests) with zero third-party packages and zero model credentials:

```bash
python3 -B scripts/check.py
```

Validates all 28 versioned cases and pinned source fixtures, verifies `CM1` and `CM2` identical-AST ablation fixtures (`grade_cm1.py` and `grade_cm2.py --check-ablation-fixtures`), validates `library/catalog.json`, reconciles all 9 pilot manifests (`benchmarks/pilot*.json`) and `benchmarks/run-record.example.json`, validates and summarizes all committed `results/**/*.jsonl` datasets (`288` runs across 15 paired tracks), and executes every `tests/test_*.py` suite (including self-checking authored Markdown files with `gates/diff_check.py`). Makes zero model or network calls.

### Contributing, Security, and Licensing

- **Contributing:** Report a defect (`.github/ISSUE_TEMPLATE/slop-defect.md`), propose a rule/gate change (`.github/ISSUE_TEMPLATE/rule-change.md`), or use `anti-slop learn`. Every change requires a reproduced failure, a **valid neighbouring case**, and a retirement trigger. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security:** See [SECURITY.md](SECURITY.md).
- **Licensing:** Original code, gates, standard, and documentation are licensed under the [MIT License](LICENSE). Pinned public OSS benchmark fixtures under `benchmarks/sources/` preserve verbatim upstream licenses and commit SHAs; see [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
