# Layer-1 Deterministic Gates (`gates/`)

Opt-in runtime and CI checks that enforce mechanical anti-slop invariants outside `standard/core.md` at zero standing-prompt token cost.

Every Python gate uses stdlib Python only (no third-party packages), exits `0` silently on pass, and emits structured findings with remediation guidance on failure (`exit 1`).

## Contents

- [cli.py](cli.py): Unified top-level agent-friendly CLI (`anti-slop <review|audit|diff|learn|mutate|verify|hook|api|skill>` and `--version`), dispatching to the underlying stdlib modules and bundling skill inspection/installation (`anti-slop skill show`, `anti-slop skill install claude|antigravity|codex`, backed by [skills/anti-slop/SKILL.md](../skills/anti-slop/SKILL.md)). All 8 direct `anti-slop-*` console scripts remain installed alongside `anti-slop` (`9` console scripts total in `pyproject.toml`).
- [audit.py](audit.py): Clean-room cross-family spec-fidelity diff auditor (`anti-slop audit` / `anti-slop-audit`). Enforces `auditor_provider != author_provider` (detecting `Co-authored-by` trailers automatically), builds a neutral third-person clean-room prompt over `(spec + diff + optional summary)`, parses structured `SPEC-DROPPED-REQ`, `SPEC-UNREQUESTED-CONSTRAINT`, `SPEC-INVENTED-POLICY`, and `SPEC-SUMMARY-MISMATCH` findings, and supports `--print-prompt`, `--from-response`, `--auditor-cmd`, and SHA-256 receipts (`--write-receipt`).
- [api_checks.py](api_checks.py): Validates 2026 model API and harness configurations (`anti-slop api` / `anti-slop-api`) for `gpt-6.2-astra`, `gpt-6.2-sol`, `claude-opus-5-5`, `claude-fable-5-2`, and `gemini-4-neon`, including cross-family audit enforcement (`HARNESS-SAME-FAMILY-AUDIT`) and Claude ML R&D routing warnings (`CLAUDE-ML-RD-CAP-WARNING`).
- [diff_check.py](diff_check.py): Validates unified diffs, modified file lists, and PR bodies (`anti-slop diff` / `anti-slop-diff`) for objective defects (`DIFF-*`), protected spec/decision/invariant locks (`DIFF-PROTECTED-PATH` via `--protect-path` and `<repo>/.anti-slop/protected-paths.json`), optional net-LOC/file budgets (`--no-budget`), repeatable `**`-aware path exclusions (`--exclude <glob>`, mirrored as `exclude:` in `action.yml`), optional AI-era structural and architectural checks (`--structural` / `--strict-structural`), plain-English explanations (`--explain`), and approved learned rules (`--learned-rules`).
- [structural.py](structural.py): Measurable detectors for compounding AI-era slop (`STRUCT-TEST-THEATER`, `STRUCT-SILENT-FALLBACK`, `STRUCT-DUPLICATE-BLOCK`, `STRUCT-DEAD-COMPAT`, `STRUCT-COMMENTED-CODE`, `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, `STRUCT-SCOPE-SPRAWL`) plus wired architectural checks from [architecture.py](architecture.py) (`11` Layer B checks total), warning-first by default.
- [architecture.py](architecture.py): Static Python and JS/TS architectural compounding-slop detectors (`ARCH-CIRCULAR-IMPORT`, `ARCH-SINGLE-IMPL-WRAPPER`, `ARCH-BOUNDARY-SCATTER`), wired automatically into `structural.py`, `diff_check.py --structural`/`--strict-structural`, and `review.py` (`warning` by default, `error` under `--strict-structural`; `0` FPs across 150 OSS commits + `7/7` TP runtime cycles in `hono` HEAD).
- [review.py](review.py): Plain-English review CLI (`anti-slop review` / `anti-slop-review`) combining `diff_check.py`, `structural.py` (including `architecture.py`), and approved learned rules to explain why experienced engineers flag each issue, how it compounds across future AI turns, what fix prompt to give your AI, and inline evidence references (`--markdown`, `--json`, `--fail-on-warning`), including 3-tier Verification Hierarchy guidance on `STRUCT-TEST-THEATER`.
- [verify.py](verify.py): Tier 1 live end-to-end and real-artifact verification CLI (`anti-slop verify` / `anti-slop-verify`; full guide in [docs/verify-recipes.md](../docs/verify-recipes.md)). Boots optional background services in isolated POSIX process groups, waits for HTTP/TCP/stdout readiness, runs real `http`, `cli`, and `file` checks, tears down process groups inside `try/finally`, and writes SHA-256 tamper-evident receipts (`.anti-slop/last-verify.json`) validated with `--check-receipt`.
- [mutate.py](mutate.py): Diff-scoped mutation testing CLI (`anti-slop mutate` / `anti-slop-mutate`) for **Python and JS/TS** (`.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`), inspired by Google Critique ([arXiv:2102.11378](https://arxiv.org/abs/2102.11378)). Copies the target repo into an isolated temporary directory (never touching your working tree), suppresses arid nodes/lines, mutates only changed executable lines across 7 operator families, and reports every surviving mutant with exact `file:line` diffs (`--test-cmd`, `--max-mutants`, `--min-kill-rate`, `--markdown`, `--json`).
- [learn.py](learn.py): Verified human-gated self-learning loop CLI (`anti-slop learn` / `anti-slop-learn`) implementing `R7` (`capture -> propose -> verify -> approve -> check -> retire`), read-only pattern mining (`anti-slop learn mine [--commits 30] [--stale-days 60] [--json]`, scanning opt-in `<repo>/.anti-slop/telemetry.jsonl` and recent git commits for recurring slop, recommended optional packs, and stale retirement candidates without auto-approving), and curated optional rule library management (`anti-slop learn library list|show|enable`, backed by [library/catalog.json](../library/catalog.json) and [library/README.md](../library/README.md)) with narrowest-layer escalation (`deterministic_check` > `codebase_example` > `prompt_rule`), 3-way automated verification (bad case, valid neighbouring case, existing repo scan), SHA-256-bound human approval, and non-reusable stable IDs (`L-001`, `L-002`, ...).
- [hooks/](hooks/README.md): Portable 3-CLI lifecycle hooks (`anti-slop hook` / `anti-slop-hook`, including `--install claude|antigravity|codex --dry-run` and strictly opt-in zero-code/zero-secret local telemetry to `<repo>/.anti-slop/telemetry.jsonl`) wrapping `gates/diff_check.py` outside the model context window.
- [model_deltas.json](model_deltas.json): Strictly delta-only per-model harness overlays (`D-AST`, `D-SOL`, `D-OPU`, `D-FAB`, `D-NEO`) with stable IDs, falsification checks, valid neighbouring cases, and effort routing. Keep outside `standard/core.md`.
- [vale/.vale.ini](vale/.vale.ini): Warning-first Vale configuration implementing the deterministic subset of Cursor `unslop` across [Openers.yml](vale/styles/AntiSlop/Openers.yml), [Closers.yml](vale/styles/AntiSlop/Closers.yml), [ADRStructure.yml](vale/styles/AntiSlop/ADRStructure.yml), [Vocab.yml](vale/styles/AntiSlop/Vocab.yml), and [Phrasing.yml](vale/styles/AntiSlop/Phrasing.yml).
- [ci-ratchet.yml](ci-ratchet.yml): Opt-in GitHub Actions workflow template showcasing the reusable composite action (`action.yml` / `uses: jremick/anti-slop@v0.9.0`), `uvx`, and vendored script execution across four independent modular jobs (`diff-gate`, `api-config-gate`, `code-hygiene-ratchet`, `prose-vale-ratchet`).

## Quick Usage

### 1. Run in Any External Repository (Unified CLI, Zero-Clone `uvx`, Action, or `pre-commit`)

`pyproject.toml` exposes the unified `anti-slop` CLI (`review`, `audit`, `diff`, `learn`, `mutate`, `verify`, `hook`, `api`, `skill`) alongside the eight direct console scripts (`anti-slop-diff`, `anti-slop-review`, `anti-slop-audit`, `anti-slop-learn`, `anti-slop-mutate`, `anti-slop-verify`, `anti-slop-hook`, `anti-slop-api`), while root `action.yml` and `.pre-commit-hooks.yaml` enable drop-in CI and local hooks without copying `gates/`:

```bash
# Plain-English review of current git changes (shortcuts + structural/architectural slop + learned rules)
uvx --from git+https://github.com/jremick/anti-slop anti-slop review

# Clean-room cross-family spec-fidelity diff audit (enforces auditor_provider != author_provider)
uvx --from git+https://github.com/jremick/anti-slop anti-slop audit --spec-file spec.md --summary-file pr.md --markdown

# Tier-1 live E2E verification with SHA-256 tamper-evident receipt (recipe or ad-hoc)
uvx --from git+https://github.com/jremick/anti-slop anti-slop verify --cmd "python3 -m myapp --version" --expect-exit 0 --markdown
uvx --from git+https://github.com/jremick/anti-slop anti-slop verify --check-receipt

# Run fast diff gate on your current git diff (with protected-path locks and repeatable --exclude)
git diff HEAD | uvx --from git+https://github.com/jremick/anti-slop anti-slop diff --diff - --no-budget --protect-path "docs/decisions/**" --exclude "results/*/artifacts/**"

# Run diff-scoped mutation testing on your changed Python or JS/TS lines (isolated temp copy)
uvx --from git+https://github.com/jremick/anti-slop anti-slop mutate --test-cmd "pytest -q"
uvx --from git+https://github.com/jremick/anti-slop anti-slop mutate --test-cmd "node --test"

# Mine recent commits and opt-in local hook telemetry read-only, or browse/enable optional packs
uvx --from git+https://github.com/jremick/anti-slop anti-slop learn mine --commits 30
uvx --from git+https://github.com/jremick/anti-slop anti-slop learn library list
uvx --from git+https://github.com/jremick/anti-slop anti-slop learn library show network-timeouts
uvx --from git+https://github.com/jremick/anti-slop anti-slop learn library enable network-timeouts --by <your-name> --dry-run

# Validate a model/harness JSON config
uvx --from git+https://github.com/jremick/anti-slop anti-slop api path/to/model-config.json

# Install user-level hooks + conversational workflow skill (preview first with --dry-run)
uvx --from git+https://github.com/jremick/anti-slop anti-slop hook --install claude --dry-run
uvx --from git+https://github.com/jremick/anti-slop anti-slop skill install claude --dry-run
```

GitHub Actions (drop-in via `action.yml`; optional opt-in inputs `structural`, `strict-structural`, `explain`, `learned-rules`, and `exclude` default off for backward compatibility):

```yaml
- uses: jremick/anti-slop@v0.9.0
  with:
    no-budget: 'true'
    # Optional opt-ins:
    # structural: 'true'
    # explain: 'true'
    # learned-rules: '.anti-slop/learned/rules.json'
    # protect-paths: |
    #   docs/decisions/**
    #   tests/invariants/**
    # exclude: |
    #   results/*/artifacts/**
    #   benchmarks/sources/**
```

Local `pre-commit` (via `.pre-commit-hooks.yaml`; also exposes opt-in `anti-slop-review` and `anti-slop-diff-lock-tests`):

```yaml
repos:
  - repo: https://github.com/jremick/anti-slop
    rev: v0.9.0
    hooks:
      - id: anti-slop-diff
      # Or opt in to plain-English review (shortcuts + structural/architectural warnings + learned rules):
      # - id: anti-slop-review
```

### 2. Validate Model API and Harness Configs

```bash
python3 -B gates/api_checks.py path/to/model-config.json
python3 -B gates/api_checks.py --json --strict path/to/neon-config.json
```

Returns `{ok, model, errors, warnings}` in `--json` mode and exits `1` on any `error` or `critical` finding (such as a `claude-fable-5-2` silent downgrade via `model_refusal_fallback` to `claude-opus-4-8` or `claude-opus-5`).

### 3. Validate Diffs, Files, and PR Descriptions

```bash
git diff origin/main...HEAD | python3 -B gates/diff_check.py --diff - --repo-root . --no-budget
git diff origin/main...HEAD | python3 -B gates/diff_check.py --diff - --repo-root . --no-budget --exclude "results/*/artifacts/**" --exclude "benchmarks/sources/**"
python3 -B gates/diff_check.py --files docs/models.md gates/README.md --repo-root .
python3 -B gates/diff_check.py --diff pr.diff --allow-test-edit --max-net-loc 400 --max-files 10 --json
python3 -B gates/diff_check.py --diff pr.diff --allow-test-edit --allow-test-skip --strict-prose --json
```

Starting budgets (`--max-net-loc 400`, `--max-files 10`, PR comment cap `<= 10`, Fable `concurrent_subagents <= 3`, Neon thinking ratio `<= 4:1`, Neon TTFT `<= 45s`) are `[Heuristic]` defaults to calibrate locally against repository telemetry. Pass `--no-budget` on first-time adoption to enforce only zero-FP objective defects without hitting the default LOC/file caps. Pass repeatable `--exclude <glob>` (or `exclude:` in `action.yml`) with `**`-aware glob matching to skip immutable benchmark artifacts or vendored third-party fixtures without weakening checks on authored files.

Engineering-credibility checks in `gates/diff_check.py`:

- `DIFF-PROTECTED-PATH` (`error`): Blocks unauthorized edits, creations, or renames matching `<repo>/.anti-slop/protected-paths.json` or repeatable `--protect-path <glob>` (and automatically self-protects `<repo>/.anti-slop/protected-paths.json` itself), even when `--allow-test-edit` is active; override only with explicit `--allow-protected-edit` (or `ANTI_SLOP_ALLOW_PROTECTED_EDIT=1` in hooks).
- `DIFF-TEST-SKIP` (`error`): Blocks newly added test-skip/waiver annotations (`@unittest.skip`, `@unittest.skipIf`, `@unittest.skipUnless`, `@pytest.mark.skip`, `@pytest.mark.skipif`, `@pytest.mark.xfail`, `self.skipTest(`, `pytest.skip(`, `it.skip(`, `test.skip(`, `describe.skip(`, `xit(`, `xtest(`) even when `--allow-test-edit` is set; override only with explicit `--allow-test-skip`.
- `DIFF-SUPPRESSION` (`error`): Flags newly added unjustified lint/type suppressions (bare `# type: ignore` without `[code]` + reason, bare `# noqa` without specific rule code, `@ts-ignore`, bare `@ts-expect-error` without explanation, bare `eslint-disable`/`eslint-disable-next-line` without specific rule + `-- reason`, bare `// nolint` without linter name + reason). Valid scoped suppressions (e.g., `# noqa: E402`, `# type: ignore[arg-type]  # upstream stub`, `// @ts-expect-error -- legacy CJS interop`, `// eslint-disable-next-line no-console -- CLI output`) pass cleanly.
- `DIFF-SILENT-CATCH` (`error`): Flags newly added Python bare `except:` or broad `except Exception:` / `except BaseException:` handlers whose body only executes `pass`, `...`, or returns `None`/`[]`/`{}`/`False` with no logging or re-raise, plus empty JS/TS `catch (...) {}` blocks. Narrowed exceptions (e.g., `except ProcessLookupError: pass`) and handlers that log or re-raise pass cleanly.
- `DIFF-DEBUG-LEFTOVER` (`error`): Flags newly added `breakpoint()`, `pdb.set_trace()`, `ipdb.set_trace()`, and JS/TS `debugger;` statements outside strings and comments.
- `DIFF-HOST-PATH` (`error`): Flags newly added hardcoded local home paths matching real usernames (`/Users/<user>/`, `/home/<user>/`, `C:\Users\<user>\`) in code or Markdown while allowing explicit placeholders (`/Users/...`, `/Users/<user>/`, `/Users/example/`, `<HOME>`, `<REPO_ROOT>`).
- `DIFF-CHATBOT-CLOSER` (`error`): Flags trailing chatbot closing filler (`Let me know if you'd like...`, `Hope this helps`, `Feel free to reach out`, `Happy to adjust/help if`) in Markdown docs and PR bodies (mirrored in `gates/vale/styles/AntiSlop/Closers.yml`).
- `DIFF-DECORATIVE-EMOJI` (`warning`, or `error` with `--strict-prose`): Flags decorative AI emojis outside fenced code blocks and inline code spans.

Reusable Python helpers exported by `gates/diff_check.py` for graders and tooling include `check_credibility_text(...)`, `check_diff_and_text(...)`, `check_markdown_openers(...)`, `check_markdown_closers(...)`, `check_decorative_emojis(...)`, `check_host_paths(...)`, `check_test_skips_in_source(...)`, `check_suppressions_in_source(...)`, `check_silent_catches_in_source(...)`, and `check_debug_leftovers_in_source(...)`.

### 4. Diff-Scoped Python & JS/TS Mutation Testing (`gates/mutate.py`)

Verify whether your test suite catches real bugs injected strictly on your changed executable **Python or JS/TS** lines (`.py`, `.js`, `.mjs`, `.cjs`, `.ts`, `.mts`, `.cts`):

```bash
# Auto-diff current git changes against HEAD in an isolated temp copy
python3 -B gates/mutate.py --test-cmd "pytest -q"
python3 -B gates/mutate.py --test-cmd "node --test"

# Diff against a base branch or target explicit file/line ranges with custom thresholds
python3 -B gates/mutate.py --base origin/main --test-cmd "pytest -q" --max-mutants 24 --min-kill-rate 0.65
python3 -B gates/mutate.py --files src/bookings.ts:10-45 --test-cmd "node --test" --markdown
```

`gates/mutate.py` never mutates your working tree in place: it copies the repository into a fresh `tempfile.TemporaryDirectory()` (skipping `.git`, `.venv`, `node_modules`, `__pycache__`, `runs-local`, and `results`), sets `PYTHONDONTWRITEBYTECODE=1`, verifies unmutated baseline tests pass first (exiting `2` on baseline failure or timeout), suppresses arid Python nodes (`__main__`, `TYPE_CHECKING`, docstrings, annotations, logging/print calls) and arid JS/TS lines (imports, type/interface declarations, `console`/`logger` calls, regex literals, comments), and samples up to `--max-mutants` (default `24`) across 7 operator families (`condition`, `compare`, `validation`, `return_value`, `arithmetic`, `boolean`, `boundary`). Default `--test-cmd` auto-selects `unittest` for Python targets and `node --test` for JS/TS targets. Exit codes: `0` when kill rate `>= --min-kill-rate` (default `0.65`, or `0` for report-only) or no mutable lines changed; `1` below threshold; `2` baseline test failure or invalid invocation.

### 5. Live E2E Verification & Tamper-Evident Receipts (`gates/verify.py`)

Run Tier 1 live checks against a real running service, HTTP API, CLI, or output artifact and save a SHA-256 receipt bound to the exact repository state (full schema and examples in [docs/verify-recipes.md](../docs/verify-recipes.md)):

```bash
# Generate a starter project recipe (.anti-slop/verify.json) or run an existing recipe
python3 -B gates/verify.py --init-example > .anti-slop/verify.json
python3 -B gates/verify.py --markdown

# One-shot ad-hoc mode (boots service in isolated PGID, waits for readiness, tears down in try/finally)
python3 -B gates/verify.py --start "python3 -m myapp.server --port 18080" --http-get "http://127.0.0.1:18080/health" --expect-status 200

# Confirm the saved receipt (.anti-slop/last-verify.json) is fresh, passed, and untampered
python3 -B gates/verify.py --check-receipt
```

### 6. Benchmark `core-rules` vs. `model-controls`

Load `standard/core.md` alone for the `core-rules` condition. For `model-controls`, load `standard/core.md` plus ONLY the single matching model block from `gates/model_deltas.json`. Never paste model deltas into `standard/core.md`; retire obsolete `D-*` rules by leaving a numeric gap.

## Incremental Adoption

Adopt gates one job at a time rather than enabling a full linter stack on Day 1:

1. **Start with zero-dependency gates:** Enable `diff-gate` (via `uses: jremick/anti-slop@v0.9.0` with `no-budget: 'true'`) and `api-config-gate` from `gates/ci-ratchet.yml`. These require only Python stdlib and catch objective failures (HTTP 400 API traps, silent Fable downgrades, stub placeholders, unauthorized test edits, test-skip waivers, unjustified suppressions, silent broad catches, debug leftovers, hardcoded host paths, chatbot openers/closers, broken local doc paths).
2. **Add warning-first prose checks:** Enable `prose-vale-ratchet` on changed Markdown files. Only `AntiSlop.Openers` and `AntiSlop.Closers` block by default (`level: error`). `AntiSlop.Vocab`, `AntiSlop.Phrasing`, `AntiSlop.ADRStructure`, and `DIFF-DECORATIVE-EMOJI` default to `warning`.
3. **Layer stack-specific code ratchets:** Enable only the `code-hygiene-ratchet` tools matching your stack (`ruff`/`vulture` for Python, `knip` for JS/TS, `jscpd` for duplicate blocks) scoped strictly to changed files so legacy debt does not block active PRs.

## Warning-First Calibration and Anti-Overcorrection

Follow the prose boundaries in [docs/operating-guide.md](../docs/operating-guide.md):

- **Never treat style warnings as proof of factual error.** Reserve hard CI errors for objective defects (broken paths, chatbot openers/closers, API contract traps, unauthorized test edits, test-skip waivers, unjustified suppressions, silent broad catches, debug leftovers, hardcoded host paths, stub code). Keep decorative emoji checks (`DIFF-DECORATIVE-EMOJI`) at `warning` unless `--strict-prose` is explicitly enabled.
- **Preserve domain vocabulary.** `gates/vale/styles/AntiSlop/Vocab.yml` and `gates/vale/styles/AntiSlop/Phrasing.yml` intentionally omit `vector`, `harness`, `primitive`, `surface`, `substrate`, and `features` from their banned `tokens` and guard them in `exceptions` so future edits do not degrade technical documentation into choppy prose (a documented failure mode under rigid style rules on Claude Fable 5.2).
- **Test valid neighbouring cases before tightening any gate.** Before promoting `ADRStructure` from `warning` to `error` or lowering diff budgets, verify the change against both a reproduced defect and a valid neighbouring case (see [CONTRIBUTING.md](../CONTRIBUTING.md) and [tests/test_gates.py](../tests/test_gates.py)).

## Complementary to Ruff, ESLint, and Semgrep

`anti-slop` does not replace language-specific AST linters or security SAST tools: run Ruff, ESLint, and Semgrep for deep single-language analysis, and layer `gates/diff_check.py` as a zero-dependency polyglot diff, prose, and agent-hook gate.

| Capability | Ruff / ESLint | Semgrep | `anti-slop` (`diff_check.py` + hooks) |
| --- | --- | --- | --- |
| Deep language-specific lint, formatting, and type rules | Primary strength (per-stack setup) | Partial (pattern rules) | Out of scope (keep Ruff/ESLint) |
| Security taint / dataflow SAST across codebase | Limited | Primary strength | Out of scope (keep Semgrep) |
| Zero-config polyglot diff gate (Python, JS/TS, Go, Markdown, PR body in one stdlib script) | Separate per-language configs | Requires rulepacks + binary | Native (`--diff - --no-budget`, 0 deps) |
| Block unauthorized edits under `tests/` and newly added test skips (`DIFF-TEST-SKIP`) | Not enforced by default | Custom rules only | Native (explicit `--allow-test-edit` / `--allow-test-skip`) |
| Catch unjustified suppressions, silent broad catches, debug leftovers, and stubs on *added diff lines only* | Overlaps on Python (`BLE001`/`PGH003`/`T100`) or JS (`no-empty`/`no-debugger`) per language | Overlaps with custom rules | Unified diff-scoped gate across Python, JS/TS, and Go |
| Verify backticked local repo paths in Markdown docs and PR bodies (`DIFF-BROKEN-DOC-PATH`) | Not covered | Not covered | Native (respects `.gitignore`, globs, URLs, placeholders) |
| Block hardcoded workstation home paths (`DIFF-HOST-PATH`) and chatbot openers/closers | Not covered | Custom regex only | Native across code, Markdown, and PR bodies |
| Blocking `PreToolUse` / `Stop` exit-2 hooks for Claude Code, Antigravity, and Codex | Not built in | Not built in | Native (`anti-slop-hook --install <cli>`) |

## Real-World OSS Precision Audit

To measure false positives on real production engineering history (not just synthetic unit tests), `gates/diff_check.py` was audited against the last **50 non-merge commits** of three public OSS repositories spanning Python and TypeScript (**150 commits**, **409 file edits**, `+10,442 / -2,936` LOC) using `--diff - --allow-test-edit --no-budget --json`, plus all tracked authored files in this repository.

Every commit was evaluated in both **checkout mode** (`--repo-root` checked out at each commit SHA, matching CI `action.yml` and local `Stop` hooks) and **hunk-only mode** (`repo_root=None`, matching piped diffs without disk files). Every finding was inspected verbatim and classified into one of four buckets: **Parser/Regex FP** (tool bug), **True Positive**, **Debatable / Intentional Pattern** (rule matched real syntax used deliberately upstream), or **Policy-Strict Convention** (upstream style omits an inline reason required by the rule).

### Corpus Summary (Post-Fix)

| Repository | Pinned `HEAD` SHA | Commits | File Edits (`+ / -` LOC) | Clean Commits | Errors / Warnings | Findings by Rule ID |
| --- | --- | ---: | --- | ---: | ---: | --- |
| [urllib3/urllib3](https://github.com/urllib3/urllib3) (Python) | `3db5970fcc56` | 50 | 185 (`+4,779 / -2,214`) | 39 / 50 (78.0%) | 23 E / 0 W | `DIFF-SUPPRESSION`: 19, `DIFF-TEST-SKIP`: 3, `DIFF-STUB-TODO`: 1 |
| [sdispater/tomlkit](https://github.com/sdispater/tomlkit) (Python) | `d2aa305673a0` | 50 | 110 (`+3,621 / -357`) | 48 / 50 (96.0%) | 5 E / 0 W | `DIFF-SUPPRESSION`: 5 |
| [honojs/hono](https://github.com/honojs/hono) (TypeScript) | `717dc17cb80b` | 50 | 114 (`+2,042 / -365`) | 49 / 50 (98.0%) | 1 E / 0 W | `DIFF-SILENT-CATCH`: 1 |
| **OSS Total** | - | **150** | **409 (`+10,442 / -2,936`)** | **136 / 150 (90.7%)** | **29 E / 0 W** | **`DIFF-SUPPRESSION`: 24, `DIFF-TEST-SKIP`: 3, `DIFF-STUB-TODO`: 1, `DIFF-SILENT-CATCH`: 1** |

- **Zero-noise rules across all 150 commits (0 errors, 0 warnings):** `DIFF-DEBUG-LEFTOVER`, `DIFF-HOST-PATH`, `DIFF-STUB-PASS` (post-fix), `DIFF-STUB-NOT-IMPLEMENTED`, `DIFF-BROKEN-DOC-PATH`, `DIFF-CHATBOT-OPENER`, `DIFF-CHATBOT-CLOSER`, and `DIFF-DECORATIVE-EMOJI`.
- **Checkout vs. hunk-only parity (post-fix):** `100%` identical findings across all 150 commits (`29 E / 0 W` in both modes).

### Classification of All 29 OSS Findings (and 2 Bugs Found & Fixed)

1. **Parser / Regex False Positives (`0 / 29` post-fix; `2` real bugs caught during the audit and fixed with regression tests in [tests/test_gates.py](../tests/test_gates.py)):**
   - **Hunk-only `DIFF-STUB-PASS` FP (OSS corpus, `sdispater/tomlkit` commit `7133174ab7`):** `class StringKey(str): pass` passed cleanly in checkout/AST mode (`5 E`) but falsely triggered `DIFF-STUB-PASS` in hunk-only mode (`6 E -> 5 E`, aggregate hunk-only `30 E -> 29 E`) because `_hunk_pass_is_non_function_block` only exempted `Protocol`/`Exception`/`*Error` bases rather than all `class` headers. Fixed for single-line and multi-line `class` headers without relaxing non-abstract `def ...: pass` detection.
   - **Prose-comment `DIFF-STUB-TODO` FP (self-repo audit, `tests/test_gates.py`):** `# 1) Removed TODO lines do not trigger errors.` falsely triggered `DIFF-STUB-TODO` (`9 E -> 8 E` on `tests/`) because `COMMENT_TODO_RE` and `TODO_FIXME_RE` matched `TODO`/`FIXME` anywhere in a comment. Tightened comment matching to require a leading marker (`# TODO`, `// FIXME`, `/* TODO`) or explicit marker punctuation (`TODO:`, `TODO(`, `TODO[`), and wired comment-aware scanning into Python hunk mode and JS/TS/Go stub checks so string literals never false-positive.
2. **True Positives (`1 / 29`):**
   - `DIFF-STUB-TODO` (`1`, `urllib3` commit `01cd60b539`): genuine `# TODO: Add optional support for socket.gethostbyname checking.` line added inside a newly extracted helper function (caveat: the line was moved verbatim from an existing method in the same commit; line-level diff checks do not suppress moved TODOs).
3. **Debatable / Intentional Upstream Patterns (`4 / 29`):**
   - `DIFF-TEST-SKIP` (`3`, `urllib3` commits `a0cab2d084`, `9016d7e8af`, `ea2ad7b21a`): deliberate `@pytest.mark.skipif` (PyPy 8.0.0 bug) and `pytest.skip()` (optional codec availability). Blocked intentionally by default so agents cannot silently waive failing tests; maintainers pass `--allow-test-skip` when an environment skip is authorized.
   - `DIFF-SILENT-CATCH` (`1`, `hono` commit `5704c75137`): deliberate empty `try { decoded = decodeURI(path) } catch {}` immediately followed by an explicit `if (decoded === undefined)` recovery branch. Matches the exact syntax the rule targets, illustrating a real-world intentional empty-catch edge case.
4. **Policy-Strict Upstream Style Conventions (`24 / 29`):**
   - `DIFF-SUPPRESSION` (`24` total: `19` across 8 `urllib3` commits and `5` across 2 `tomlkit` commits): every single hit is a mypy-coded `# type: ignore[arg-type]`, `[assignment]`, `[misc]`, `[union-attr]`, `[comparison-overlap]`, or `[index]` comment that omits a trailing `# <reason>` explanation. `diff_check.py` intentionally requires both `[code]` and a short reason (`# type: ignore[arg-type]  # mock socket`); teams adopting `anti-slop` on mypy-strict repos should expect this rule to require brief inline justifications on new `# type: ignore[...]` additions.

### Structural Gates (`gates/structural.py`) OSS Precision Audit

Using the exact same 150-commit pinned OSS corpus (`urllib3` `3db5970fcc56`, `tomlkit` `d2aa305673a0`, `hono` `717dc17cb80b`), `gates/structural.py` (`check_structural_diff(..., repo_root=...)`, all rules warning-only by default) was audited in checkout mode and every warning was inspected verbatim.

| Repository | Pinned `HEAD` SHA | Commits | Clean (All 8 `STRUCT-*`) | Clean (Non-Size Defect Rules) | Total Warnings (Post-Fix) | Warnings by Rule ID |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| [urllib3/urllib3](https://github.com/urllib3/urllib3) (Python) | `3db5970fcc56` | 50 | 30 / 50 (60.0%) | 48 / 50 (96.0%) | 29 W | `STRUCT-GOD-FILE`: 14, `STRUCT-GOD-FUNCTION`: 12, `STRUCT-TEST-THEATER`: 3 |
| [sdispater/tomlkit](https://github.com/sdispater/tomlkit) (Python) | `d2aa305673a0` | 50 | 29 / 50 (58.0%) | 50 / 50 (100.0%) | 33 W | `STRUCT-GOD-FILE`: 22, `STRUCT-GOD-FUNCTION`: 11 |
| [honojs/hono](https://github.com/honojs/hono) (TypeScript) | `717dc17cb80b` | 50 | 43 / 50 (86.0%) | 47 / 50 (94.0%) | 10 W | `STRUCT-GOD-FILE`: 5, `STRUCT-DUPLICATE-BLOCK`: 4, `STRUCT-GOD-FUNCTION`: 1 |
| **OSS Total** | - | **150** | **102 / 150 (68.0%)** | **145 / 150 (96.7%)** | **72 W** | **`STRUCT-GOD-FILE`: 41, `STRUCT-GOD-FUNCTION`: 24, `STRUCT-DUPLICATE-BLOCK`: 4, `STRUCT-TEST-THEATER`: 3** |

- **Zero-noise structural rules across all 150 commits (0 warnings):** `STRUCT-SILENT-FALLBACK` (`0`), `STRUCT-DEAD-COMPAT` (`0`), `STRUCT-COMMENTED-CODE` (`0`), and `STRUCT-SCOPE-SPRAWL` (`0`). Hunk-only mode (`repo_root=None`) also reported `0` warnings across the 150 pinned commits (and an additional 150 earlier history commits after fixing truncated hunk-only test blocks and Deno `@std/assert` calls below).
- **`STRUCT-COMMENTED-CODE` 150-commit + 551-HEAD OSS audit (`0` false positives):** Audited across the same 150 commits (258 code-file edits, 28 newly added `>= 3`-line comment blocks) and full `HEAD` source trees (551 code files, 331 `>= 3`-line comment groups): `urllib3` (83 code edits / 9 added blocks; 86 HEAD files / 175 groups -> `0` hits), `tomlkit` (73 code edits / 18 added blocks; 29 HEAD files / 103 groups -> `0` hits), `hono` (102 code edits / 1 added block; 436 HEAD files / 53 groups -> `0` hits), plus `0` hits across `anti-slop` itself. Normal prose comments, 1-2 line `# INVARIANT:` notes, license headers, docstrings, JSDoc `@example` blocks, fenced comment examples, URLs, and dividers all pass cleanly.
- **Parser/AST false-positive classes caught during the audit and fixed (`87 W -> 72 W` on the 150 pinned commits, `-15` false warnings, plus `4` additional hunk-only/Deno FPs caught on earlier `urllib3`/`hono` history; regression tests in [tests/test_structural_and_review.py](../tests/test_structural_and_review.py)):**
  1. **Vitest / `expect-type` & Deno `@std/assert` assertions (`hono`, 5/5 pinned + 3/3 `6cbe361b7a` FPs fixed):** `expectTypeOf<...>().toEqualTypeOf<...>()`, `assertType<...>()`, and Deno camelCase assertions (`assertEquals`, `assertThrows`) were not recognized by `JS_ASSERT_RE`. Updated `JS_ASSERT_RE` while keeping tautology and empty-test checks intact.
  2. **AST-verified local, imported, and module-attribute test helpers (`tomlkit`, 9/9 FPs fixed):** `tomlkit`'s `test_items.py` delegated assertions to `from tests.util import elementary_test`. Updated Python test-theater inspection to verify via AST whether same-file, `from tests.* import ...`, `import tests.*` attribute calls, or 1-hop re-exported helpers actually execute real assertions; assertion-free helpers remain flagged.
  3. **Strict stdlib warning-error assertions (`urllib3`, 1/4 FPs fixed):** `warnings.simplefilter("error", FutureWarning)` inside `warnings.catch_warnings()` turns any emitted warning into a test failure (`warnings.simplefilter("ignore", ...)` remains flagged).
  4. **Truncated hunk-only test blocks (`urllib3` `e8a81de5e1` hunk-only FP fixed) & TypeScript function overloads:** Hunk-only mode (`repo_root=None`) now skips `STRUCT-TEST-THEATER` when a Python function reaches the end of a partial diff hunk or a JS/TS test block is unclosed (`depth > 0`), and `STRUCT-GOD-FUNCTION` skips semicolon-terminated / ambient TypeScript overload signatures without bodies.
- **Classification of all 72 post-fix structural warnings:**
  - **True duplicates (`4 / 72`):** All 4 `STRUCT-DUPLICATE-BLOCK` hits in `hono` (`64d4cd2234`, `399e7c9207`, `fb48e2b295`) flagged real verbatim mirrored adapter files (`adapters/<target>/src/` duplicating `src/adapter/<target>/`) where each bugfix had to be applied identically in two places.
  - **Intentional no-assert / string-eval tests (`3 / 72`):** In `urllib3`, `2` hits (`test_assert_hostname_invalid_cn`, `test_timeout_success`) are intentional "does not raise" HTTP smoke tests with zero `assert` statements, and `1` hit (`test_streaming_close`) passes Python assertions inside a string executed by a Pyodide webworker (`run_webworker(worker_code)`).
  - **Pre-existing large files and complex methods (`65 / 72`):** `41` `STRUCT-GOD-FILE` warnings (growing pre-existing 518-to-1,951-line core files such as `urllib3` `response.py`, `tomlkit` `items.py`, and `hono` `render.ts`) and `24` `STRUCT-GOD-FUNCTION` warnings (`urlopen`, `_parse_table`, `item`, `methodOverride`). These findings explain why `STRUCT-*` rules default to `warning` rather than blocking errors unless `--strict-structural` is opted in.

### Architectural Gates (`gates/architecture.py`) OSS Precision Audit

Using the same 150-commit OSS corpus (`urllib3/urllib3`, `sdispater/tomlkit`, `honojs/hono`; 50 non-merge commits each) plus full `HEAD` scans across `316` OSS production files and `anti-slop` itself (`33` HEAD production files + `17` non-merge commits), `gates/architecture.py` (wired via `gates/structural.py`) recorded **`0` false positives**:

| Target | Scope | `ARCH-CIRCULAR-IMPORT` | `ARCH-SINGLE-IMPL-WRAPPER` | `ARCH-BOUNDARY-SCATTER` | Verbatim Audit Classification |
| --- | --- | ---: | ---: | ---: | --- |
| `urllib3/urllib3` (Python) | 50 commits / 45 HEAD prod files | `0` / `0` | `0` / `0` | `0` / `0` | `0` FP (cleanly exempted `EmscriptenHttpResponseWrapper`) |
| `sdispater/tomlkit` (Python) | 50 commits / 13 HEAD prod files | `0` / `0` | `0` / `0` | `0` / `0` | `0` FP (cleanly exempted `Key(ABC)` with multiple subclasses) |
| `honojs/hono` (TypeScript) | 50 commits / 258 HEAD prod files | `0` / `7` | `0` / `0` | `0` / `0` | `0` hits on 50 commits (7 bugfix commits touching pre-existing cyclic files without touching cyclic edges skipped cleanly); **`7/7` TP, `0` FP** on HEAD runtime cycles |
| `anti-slop` (self-scan) | 17 commits / 33 HEAD prod files | `0` / `0` | `0` / `0` | `0` / `0` | `0` FP |

- **All `7/7` verbatim-verified true runtime circular imports in `hono` HEAD:** *src/helper/streaming/index.ts:9 <-> text.ts:4*, *src/jsx/base.ts:10 <-> context.ts:4*, *src/jsx/base.ts:19 <-> intrinsic-element/components.ts:3*, *src/jsx/base.ts:19 -> intrinsic-element/components.ts:7 -> context.ts:4 -> base.ts*, *src/jsx/components.ts:10 <-> streaming.ts:11*, *src/jsx/context.ts:6 <-> dom/context.ts:4*, and *src/jsx/dom/render.ts:13 <-> hooks/index.ts:3*.
- **Five parser/FP bugs caught and fixed during the audit (regression tests in [tests/test_architecture.py](../tests/test_architecture.py)):** (1) fixed 1-line off-by-one in JS/TS `import`/`export` regex newline capture; (2) exempted pure-abstract exported external-runtime type stubs in `types.ts` (such as `hono`'s `FetchEventLike`) with 0 concrete subclasses and 0 concrete methods; (3) added balanced `<...>` generic-constraint stripping (`_strip_angle_generics`) so `<E extends LambdaEvent>` is not misparsed as class inheritance; (4) added JS/TS regex-literal masking so `//` inside URL regexes is not stripped as a comment; and (5) handled Python 3.9+ `ast.Subscript` slice unwrapping for `os.environ["KEY"]`.

### Self-Repository Dogfood Audit

Scanning this repository's own tracked authored files (excluding pinned third-party OSS snapshots under `benchmarks/sources/` and archived raw model transcripts under `results/pilot-3way-v0.6.0/artifacts/`):

- **164 authored Markdown files:** `0` errors, `0` warnings.
- **26 authored non-test Python files (`gates/`, `scripts/`, `benchmarks/graders/`, `benchmarks/evolution.py`):** `1` error (`benchmarks/graders/grade_rw3.py:281`, an intentional `except Exception: pass` negative probe inside a grader), `0` warnings.
- **9 test-suite files (`tests/test_*.py`):** `8` errors post-fix (down from `9` after fixing the prose `TODO` false positive in `tests/test_gates.py`): `6` intentional `DIFF-HOST-PATH` negative-test fixture strings and `2` intentional Python-version `@unittest.skipIf` guards in `tests/test_graders.py`.

### Reproducing the OSS Audit

Add `--structural` to the `gates/diff_check.py` command below (or call `structural.check_structural_diff(...)` directly) to reproduce the structural precision audit on the same pinned SHAs.

```bash
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

for spec in \
  "urllib3 https://github.com/urllib3/urllib3.git 3db5970fcc56666ed5e7d450816ece9cce55589f" \
  "tomlkit https://github.com/sdispater/tomlkit.git d2aa305673a01eafd0edda54ef07ebcb8902f4d4" \
  "hono https://github.com/honojs/hono.git 717dc17cb80bff270ddc557614fe3c3e1b916a1f"
do
  read -r name url pinned <<< "$spec"
  git clone --depth=100 "$url" "$WORKDIR/$name"
  git -C "$WORKDIR/$name" checkout --quiet "$pinned" 2>/dev/null || true
  for sha in $(git -C "$WORKDIR/$name" rev-list --no-merges -n 50 HEAD); do
    git -C "$WORKDIR/$name" checkout --force --quiet "$sha"
    git -C "$WORKDIR/$name" diff --unified=3 "${sha}~1" "$sha" \
      | python3 -B gates/diff_check.py --diff - --repo-root "$WORKDIR/$name" --allow-test-edit --no-budget --json \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print("'"$name"'", "'"${sha:0:10}"'", len(d["errors"]), [e["code"] for e in d["errors"]]) if d["errors"] or d["warnings"] else None'
  done
done
```
