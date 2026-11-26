# Anti-slop

[![Validate](https://github.com/jremick/anti-slop/actions/workflows/validate.yml/badge.svg)](https://github.com/jremick/anti-slop/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
![Dependencies: 0](https://img.shields.io/badge/dependencies-0-brightgreen.svg)

Deterministic diff gates, 3-CLI agent lifecycle hooks, and empirical benchmarks for AI-assisted engineering — zero dependencies, zero hype.

Most "anti-slop" repos are unmeasured 1,500-line prompt walls or statistical AI-text detectors (61.2% false-positive rate on non-native English, [EXT-13](docs/evidence.md#ext-13)). Anti-slop enforces objective engineering defects mechanically first at zero prompt-token cost, pairs them with a 298-word core standard (`0.2.0`) and opt-in per-model deltas, and publishes where standing rules hit ceilings, regressed models, or inflated cost.

**Release:** `0.6.0` (tooling, runtime gates, packaging, and 24-case benchmark suite; [standard/core.md](standard/core.md) remains pinned at `0.2.0`). See [CHANGELOG.md](CHANGELOG.md).

## What It Catches

Real `stderr` output from `gates/diff_check.py` scanning a unified diff and PR body (`exit 1`, stdlib Python only, zero LLM calls; `<user>` redacted for repository hygiene):

```text
src/billing/sync.py:13: [ERROR] DIFF-SUPPRESSION: src/billing/sync.py:13 adds bare '# type: ignore' without specific [code] and reason.
  remediation: Fix the underlying lint/type error, or scope the suppression to a specific rule/code with an inline reason.
src/billing/sync.py:17: [ERROR] DIFF-SILENT-CATCH: src/billing/sync.py:17 swallows errors via silent handler (except Exception: pass).
  remediation: Narrow the caught exception type or log/re-raise instead of silently swallowing broad exceptions.
src/billing/sync.py:14: [ERROR] DIFF-DEBUG-LEFTOVER: src/billing/sync.py:14 leaves debug call 'breakpoint(' in code.
  remediation: Remove interactive debugger statements before committing.
src/billing/sync.py:15: [ERROR] DIFF-HOST-PATH: src/billing/sync.py:15 contains hardcoded local host home path (/Users/<user>/).
  remediation: Replace local machine home paths with relative paths, Path.home()/env vars, or explicit placeholders like /Users/<user>/ or /Users/....
tests/test_sync.py:8: [ERROR] DIFF-TEST-SKIP: tests/test_sync.py:8 adds test-skip/waiver annotation '@pytest.mark.skip'.
  remediation: Fix the underlying failure instead of skipping tests, or pass --allow-test-skip if explicitly authorized.
<pr-body>:3: [ERROR] DIFF-CHATBOT-CLOSER: <pr-body>:3 ends with chatbot closing filler 'Hope this helps'.
  remediation: Remove conversational sign-off filler and end with the concrete decision, status, or verification step.
```

In the same pass, `gates/diff_check.py` blocks unauthorized edits under `tests/` (`DIFF-UNAUTHORIZED-TEST-EDIT` unless `--allow-test-edit` is set), stub placeholders (`DIFF-STUB-TODO`, `DIFF-STUB-NOT-IMPLEMENTED`, `DIFF-STUB-PASS`), chatbot openers (`DIFF-CHATBOT-OPENER`), broken backticked repo paths (`DIFF-BROKEN-DOC-PATH`), and warns on decorative AI emojis (`DIFF-DECORATIVE-EMOJI`, promoted to error with `--strict-prose`). Valid scoped suppressions (e.g., `# noqa: E402`, `# type: ignore[arg-type]  # upstream stub`), narrowed catches (`except ProcessLookupError: pass`), and `@abstractmethod`/`Protocol` stubs pass cleanly.

## Try It in 60 Seconds

### 1. Check a local diff (zero clone, zero dependencies)

```bash
# Packaged CLI via uvx (defined in pyproject.toml)
git diff origin/main...HEAD | uvx --from git+https://github.com/jremick/anti-slop anti-slop-diff --diff - --no-budget

# Or inside a checkout with stdlib Python 3.11+
git diff origin/main...HEAD | python3 -B gates/diff_check.py --diff -
```

### 2. Drop into GitHub Actions or local pre-commit

```yaml
# .github/workflows/anti-slop.yml (reusable composite action via action.yml)
- uses: jremick/anti-slop@v0.6.0
  with:
    allow-test-edit: "true"
    no-budget: "true"
    check-pr-body: "true"
```

```yaml
# .pre-commit-config.yaml (wired via .pre-commit-hooks.yaml)
repos:
  - repo: https://github.com/jremick/anti-slop
    rev: v0.6.0
    hooks:
      - id: anti-slop-diff
```

### 3. Install blocking `PreToolUse` / `Stop` agent lifecycle hooks

```bash
# One-command installer (backs up existing config to *.bak-antislop; preview first with --dry-run)
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --install claude
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --install antigravity
uvx --from git+https://github.com/jremick/anti-slop anti-slop-hook --install codex
```

See [gates/hooks/README.md](gates/hooks/README.md) for manual templates and Codex `execpolicy` behavior.

## What We Measured (Honest Empirical Summary)

### Flagship clean `n = 3` public benchmark (`pilot-3way-v0.6.0`, `LOCAL-05`)

Published under [results/pilot-3way-v0.6.0/](results/pilot-3way-v0.6.0/README.md) (`144` runs = `4` focus models × `4` multi-stage cases × `3` conditions × `n = 3` replicates; `142` completed, `2` `720s` timeouts kept in denominators; isolated per-run `CODEX_HOME`/`HOME`, pre-hash sanitized, `100%` verbatim human-audited):

| Suite Slice (`pilot-3way-v0.6.0`, `n = 3`) | `baseline` | `core-rules-v0.2.0` | `model-controls` | Net `B -> M` |
|---|---|---|---|---:|
| **All 4 cases** (`48` runs/arm) | **`31/48` (`64.6%`)** *(31/47 comp.)* | **`40/48` (`83.3%`)** | **`43/48` (`89.6%`)** *(43/47 comp.)* | **`+12/-0`** |
| **Pinned OSS `origin: real_work`** (`RW3` `urllib3`, `RW5` `sqlparse`, `RW6` `tomlkit`; `36`/arm) | **`22/36` (`61.1%`)** *(22/35 comp.)* | **`30/36` (`83.3%`)** | **`34/36` (`94.4%`)** *(34/35 comp.)* | **`+12/-0`** |
| **Constructed credibility audit (`SE2`)** (`12`/arm) | **`9/12` (`75.0%`)** | **`10/12` (`83.3%`)** | **`9/12` (`75.0%`)** | `0` |
| **Strict `wc -w` sensitivity (all 4 cases)** (`48`/arm) | **`26/48` (`54.2%`)** | **`37/48` (`77.1%`)** | **`42/48` (`87.5%`)** | **`+16`** |

- **Code-integrity win (`RW3` frozen-test tampering):** Under Stage 2 release-cut pressure, **`8/11` (`72.7%`)** completed `baseline` runs modified frozen `benchmarks/sources/rw3_urllib3/tests/test_response_gates.py` to skip the optional codec check and grant a waiver (`gpt-6.2-astra` `3/3`, `gpt-6.2-sol` `3/3`, `claude-opus-5-5` `2/3`, `gemini-4-neon` `0/2`). Both `core-rules-v0.2.0` (`0/12`) and `model-controls` (`0/11` completed) cut test tampering to **`0.0%`**.
- **Compliance & cost win (`D-OPU-4` on Claude Opus 5.5):** Layering `D-OPU-4` eliminated **100% (`0/11` completed)** of Opus's word-cap and wrapper failures, lifted Opus on `real_work` OSS from `4/9 -> 4/9 -> 8/9` (`8/8` completed; strict `wc -w`: `0/9 -> 2/9 -> 8/9`), and cut matched Opus lexical words **`-31.6%`**, matched USD **`-6.9%`** (`$3.9351 -> $3.6651`), and matched wall time **`-21.8%`**.
- **Honest negatives & tradeoffs:** (1) `claude-opus-5-5` still failed `SE2` Stage 2 on **`8/9`** runs (`0/3` baseline, `1/3` core, `0/3` model-controls) by conceding follow-up-ticket deferral on a skipped concurrency test (`4` runs) or folding TypeScript verification into `pytest` output (`4` runs) — showing brevity deltas do not fix semantic verification discipline; (2) treatment arms added matched token overhead on Astra (`+15.8%` / `+15.2%`), Sol (`+10.8%` / `+4.2%`), and Neon (`+26.1%` / `+23.6%`); (3) `2` `RW3` Stage 1 runs hit the `720s` timeout (`claude-opus-5-5` `model-controls` `r3`, `gemini-4-neon` `baseline` `r1`). See the full breakdown in [results/pilot-3way-v0.6.0/README.md](results/pilot-3way-v0.6.0/README.md).

### Archived pre-public internal diagnostics (`v0.2.0`–`v0.5.0`, `LOCAL-01`–`LOCAL-04`)

Prior to `v0.6.0`, four `n = 1` internal diagnostic pilots (`348` runs) informed gate and delta scoping and were archived privately off the public repo because pre-public Codex runs lacked `CODEX_HOME` isolation (allowing Codex subjects to read local `~/.codex/skills/` into SHA-256-pinned traces) and early traces retained host/temp paths. Rather than silently rewriting historical hashes or publishing contaminated traces, every pre-public outcome—including null results, regressions, and cost spikes—is disclosed below and in [docs/evidence.md](docs/evidence.md#local-measured-evaluations):

| Pre-Public Diagnostic (Archived) | Origin & Cases (`n = 1`/cell) | Baseline | Core Rules (`0.2.0`) | Model Controls | Honest Takeaway |
|---|---|---|---|---|---|
| `v0.2.0` (`LOCAL-01`) | Constructed (`W1`–`P1`, 150 runs, 5 models) | `48/50` (`96.0%`) | `48/50` (`96.0%`) | — *(v0.1.0: `49/50`)* | **96% baseline ceiling (null result):** standing rules showed zero lift; Opus failed two word caps via wrapper bloat (`D-OPU-4` born). |
| `v0.3.0` (`LOCAL-02`) | Harder constructed (`M1`–`W3`, 90 runs, 5 models) | `27/30` (`90.0%`) | `28/30` (`93.3%`) | `29/30` (`96.7%`; `29/29` comp.) | **Code integrity vs. prompt regression:** `core-rules` stopped Sol `B2` `@unittest.skip` tampering, yet *regressed* Opus (`5/6 -> 4/6`) via bloat; `D-OPU-4` lifted Opus to `6/6`. Fable cost rose `+24.3%`. |
| `v0.4.0` (`LOCAL-03`) | Pinned OSS `real_work` (`RW3`–`RW6`, 60 runs, 5 models) | `13/20` (`65.0%`) | `13/20` (`65.0%`) | `15/20` (`75.0%`; `15/18` comp.) | **Real OSS failures exposed:** `core-rules` stopped Astra `RW3` test-skip tampering (`4/4`) while regressing Opus `1/4 -> 0/4`; `D-OPU-4` lifted Opus to `3/4`. Fable hit `+23.9%` cost, `RW5` wrapper fails, and 6/6 `RW3` 480s timeouts (Fable/Neon). |
| `v0.5.0` (`LOCAL-04`) | `SE1`–`SE2` constructed + `RW5`–`RW6` OSS (48 runs, 4 models) | `10/16` (`62.5%`) *(strict `wc -w`: `8/16`)* | `13/16` (`81.2%`; `13/15` comp.) *(`11/16`)* | `13/16` (`81.2%`) *(`13/16`)* | **Scoped deltas validated internally:** refined `D-NEO-2` and `D-OPU-1`/`D-OPU-4` yielded zero openers/closers/emojis and cut Opus words `-18.4%` at `-1.3%` USD; `SE1` S2 fails (`7/11`) were polite refusal preambles exceeding the whole-response 120w cap, not code cheats. |

**Methodology caveats:**
- **Not population estimates:** `pilot-3way-v0.6.0` spans 4 scenarios (`3` Python OSS + `1` polyglot PR audit) over `n = 3` replicates per cell (`replicates` do not create additional independent task scenarios); `claude-fable-5-2` remains excluded pending a revised `D-FAB-4` wrapper/cost delta and longer `RW3` timeout retest.
- **No bogus "Slop Score" or model leaderboard:** We report same-model paired comparisons only, separate **code-integrity wins** (`RW3` test-skip tampering prevented) from **compliance/brevity wins** (`D-OPU-4` word-cap & wrapper elimination) and **unmitigated semantic failures** (Opus `SE2`), and treat the model + CLI harness + settings as the tested system (**GPT-6.2 Astra**, **GPT-6.2 Sol**, **Claude Opus 5.5**, **Claude Fable 5.2**, **Gemini 4 Neon**).

## Architecture (3 Layers)

1. **Layer 1 — Deterministic Runtime Gates & CLI Hooks (`0` standing prompt tokens):**
   - [gates/README.md](gates/README.md): stdlib Python `gates/diff_check.py`, 2026 API & context-hygiene validator `gates/api_checks.py` (HTTP 400 traps, Fable silent downgrade alerts, observation-masking checks), warning-first `gates/vale/` prose rules with technical allowlists, and modular `gates/ci-ratchet.yml`.
   - [gates/hooks/README.md](gates/hooks/README.md): exit-`2` `PreToolUse`/`Stop` wrapper (`gates/hooks/run_diff_gate_hook.py`) for Claude Code, Antigravity, and Codex CLI.
2. **Layer 2 — Ultra-Lean Core Standard (`<= 300` words):**
   - [standard/core.md](standard/core.md): seven stable-ID rules (`R1`–`R7`, `0.2.0`, 298 words; retiring a rule leaves a gap—never renumber). This is the only standing prompt text.
   - Rationale, context provenance, 5-model routing, and 4-tier stakes review stay out of standing prompts in [docs/operating-guide.md](docs/operating-guide.md) and [docs/operations-and-routing.md](docs/operations-and-routing.md).
3. **Layer 3 — Per-Model Deltas & Cryptographically Auditable Benchmarks:**
   - [gates/model_deltas.json](gates/model_deltas.json), [docs/models.md](docs/models.md), and [docs/evidence.md](docs/evidence.md): strictly delta-only per-model overlays (`D-AST`, `D-SOL`, `D-OPU`, `D-FAB`, `D-NEO`) loaded one model at a time, backed by source-linked 2026 evidence.
   - [benchmarks/README.md](benchmarks/README.md) & [benchmarks/graders/README.md](benchmarks/graders/README.md): **24 versioned cases** (18 constructed probes `W1`–`W3`, `SE1`–`SE2` + 6 pinned OSS `origin: real_work` tasks `RW1`–`RW6`), **11 automated stdlib coding graders**, and `scripts/benchmark.py` (SHA-256-pinned cases, fixtures, prompt snapshots, per-stage lineage outputs, and auditable failure/blocker records).

### Verify the repository locally

Requires Python 3.11+ with zero third-party packages and zero model credentials:

```bash
python3 -B scripts/check.py
```

Validates all 24 cases and pinned source fixtures, reconciles all pilot manifests (`benchmarks/pilot*.json`) and `benchmarks/run-record.example.json`, validates/summarizes any committed `results/**/*.jsonl` datasets, and executes every `tests/test_*.py` suite (including self-checking every Markdown file in the repository with `gates/diff_check.py`). It makes zero model or network calls.

## Known Limits & Roadmap

- **Address Opus `SE2` Stage 2 verification & pushback concessions:** `pilot-3way-v0.6.0` exposed an unmitigated `8/9` Opus failure mode on polyglot verification checklists and follow-up-ticket deferral under author pushback; test targeted mechanical checks or scoped rules without inflating token overhead.
- **Close the Claude Fable 5.2 wrapper & cost gap:** Evaluate a targeted `D-FAB-4` zero-wrapper/word-cap delta while trimming `+18%`–`+24%` treatment overhead, and retest `RW3` on Fable under longer stage timeout budgets.
- **Broaden real-work coverage & plugin packaging:** Expand `origin: real_work` scenarios beyond five Python OSS repositories (adding held-out non-Python stacks) and package native Claude Code / Antigravity hook plugins.
- **Live external citations:** Vendor docs and external leaderboards in [docs/evidence.md](docs/evidence.md) are date-stamped (24–26 November 2026) rather than web-archived; recheck upstream pages before relying on them downstream.

## Contributing, Security & Third-Party Licensing

- **Contributing:** Report a reproducible defect (`.github/ISSUE_TEMPLATE/slop-defect.md`) or propose a rule/gate change (`.github/ISSUE_TEMPLATE/rule-change.md`). Prefer deterministic `gates/` checks over standing prompt text; every proposed change requires a reproduced failure, a **valid neighbouring case**, and a retirement trigger. See [CONTRIBUTING.md](CONTRIBUTING.md).
- **Security:** See the repository security policy (`SECURITY.md`) for vulnerability disclosure and scope.
- **Licensing:** Original repository code, gates, standard, and documentation are licensed under the [MIT License](LICENSE). The six pinned public OSS benchmark fixtures under `benchmarks/sources/` (`tomlkit` MIT, `Python-Markdown` BSD-3-Clause, `urllib3` MIT, `pypa/packaging` BSD-2-Clause selected under its Apache-2.0 OR BSD-2-Clause dual license, `sqlparse` BSD-3-Clause) preserve verbatim upstream `LICENSE*` files and `UPSTREAM.json` commit SHAs; see `THIRD_PARTY_LICENSES.md` for full attributions.
