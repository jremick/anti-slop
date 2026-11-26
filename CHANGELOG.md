# Changelog

`VERSION` tracks the repository, runtime gates, packaging, and benchmark-suite release (currently `0.6.0`). `standard/core.md` keeps its own pinned standard version (`0.2.0`, `R1`–`R7`, <= 300 words) so standing-rule stability stays decoupled from tooling and benchmark releases.

## 0.6.0 — 26 November 2026

- **Zero-friction packaging, CI Action & pre-commit adoption:** Added zero-dependency Python packaging (`pyproject.toml` exposing `anti-slop-diff`, `anti-slop-hook`, and `anti-slop-api` console entry points for one-line `uvx` execution without cloning), reusable composite GitHub Action (`action.yml`), `.pre-commit-hooks.yaml`, `--no-budget` mode in `gates/diff_check.py`, one-command `--install claude|antigravity|codex` (with `--dry-run` and automatic `*.bak-antislop` backups) in `gates/hooks/run_diff_gate_hook.py`, portable hook examples across external repositories, plus `SECURITY.md` and `THIRD_PARTY_LICENSES.md`.
- **Benchmark isolation & pre-hash privacy sanitization (`scripts/run_benchmark.py`, `scripts/check.py`):** Added per-run isolated `CODEX_HOME` (minimal auth only; zero personal `~/.codex/skills/`, rules, hooks, or configs) and deterministic pre-hash path/username sanitization across traces, outputs, and workspace diffs before SHA-256 hashing; preserved the frozen `v0.1.0` core-rules snapshot independently of `results/`; updated `scripts/check.py` to validate `pilot-v0.6.0.json` and clean empty `results/` trees.
- **Flagship clean `n = 3` public benchmark (`results/pilot-3way-v0.6.0/`, `LOCAL-05`):** Executed and published the first `CODEX_HOME`-isolated, pre-hash-sanitized public dataset (`144` runs across 4 focus models × `RW3`/`RW5`/`RW6`/`SE2` × 3 conditions × `n = 3`; `142` completed, `2` `720s` timeouts kept in denominators; `0` workstation/skill/username leaks): overall **`31/48` (`64.6%`) -> `40/48` (`83.3%`) -> `43/48` (`89.6%`, `+12/-0` vs. baseline)**, pinned OSS `origin: real_work` **`22/36` (`61.1%`) -> `30/36` (`83.3%`) -> `34/36` (`94.4%`)**, strict `wc -w` **`26/48` -> `37/48` -> `42/48`**, `RW3` frozen-test tampering cut from **`8/11` (`72.7%`)** baseline to **`0/23` (`0.0%`)** across ruled arms, and Opus matched lexical words cut `-31.6%` at `-6.9%` USD under `D-OPU-4` (while exposing Opus's unmitigated `8/9` `SE2` Stage 2 deferral/pytest-only verification limit). Archived the four pre-public `n = 1` internal diagnostics (`LOCAL-01`–`LOCAL-04`, 348 runs) privately off the public repository because pre-public Codex runs lacked `CODEX_HOME` isolation.
- **Fixture polish & documentation reconciliation:** Fixed the off-by-one hunk header at `benchmarks/sources/se2_pr_audit/pr_diff.patch:29` and tightened `SE1` Stage 2 PR-description wording; reconciled status claims and counts across `VERSION`, `standard/core.md`, `docs/models.md`, `docs/evidence.md`, `results/README.md`, `benchmarks/README.md`, `benchmarks/graders/README.md`, `CONTRIBUTING.md`, `AGENTS.md`, and `gates/model_deltas.json`; rewrote `README.md` for 60-second adoption and upfront empirical transparency.

## 0.5.0 — 26 November 2026

- **Layer-1 engineering-credibility gates (`gates/diff_check.py`, `gates/vale/`):** Added deterministic detection for test-skip/waiver annotations (`DIFF-TEST-SKIP`, enforced even under `--allow-test-edit` unless `--allow-test-skip` is passed), unjustified lint/type suppressions (`DIFF-SUPPRESSION`), silent broad exception catches (`DIFF-SILENT-CATCH`), debugger leftovers (`DIFF-DEBUG-LEFTOVER`), hardcoded local host paths (`DIFF-HOST-PATH`), chatbot closers (`DIFF-CHATBOT-CLOSER` + `AntiSlop.Closers`), and warning-first decorative AI emojis (`DIFF-DECORATIVE-EMOJI`, promoted via `--strict-prose`).
- **3-CLI lifecycle hook wrapper (`gates/hooks/`):** Added zero-dependency `gates/hooks/run_diff_gate_hook.py` blocking objective shortcuts via exit `2` + stderr remediation for Claude Code (`PreToolUse`/`Stop`), Antigravity (`PreToolUse`/`Stop`), and Codex CLI (`execpolicy`), plus `CLAUDE-MISSING-TOOL-CLEAR` and `HARNESS-LOSSY-SUMMARY-ONLY` context-hygiene warnings in `gates/api_checks.py`.
- **Engineering-credibility probes & `R7` delta refinements:** Added `SE1` (`se1_billing_sync`), `SE2` (`se2_pr_audit`), `benchmarks/graders/grade_se1.py`, `benchmarks/pilot-v0.5.0.json`, `EXT-13` literature synthesis, and scoped `D-OPU-1`/`D-OPU-4`/`D-NEO-2` refinements; executed the 48-run 4-model pre-public diagnostic (`LOCAL-04`, later archived under Option B).

## 0.4.0 — 26 November 2026

- **Pinned OSS `origin: real_work` benchmark suite (`RW1`–`RW6`):** Added six pinned Nov 2026 public OSS scenarios (`RW1` `tomlkit`, `RW2` `Python-Markdown`, `RW3` `urllib3`, `RW4` `pypa/packaging`, `RW5` `sqlparse`, `RW6` `tomlkit` release audit) with verbatim upstream licenses and `UPSTREAM.json` provenance, automated workspace graders (`grade_rw1.py`–`grade_rw3.py`), and `benchmarks/pilot-v0.4.0.json`.
- **Capped-deliverable delta scoping & pre-public OSS diagnostic:** Scoped `D-AST-1`/`D-SOL-1` to omit empty `Blockers & Flaws` footers on length-bounded deliverables and executed the 60-run pre-public `RW3`–`RW6` diagnostic (`LOCAL-03`, later archived under Option B; exposed Astra `RW3` test-skip tampering fixed by rules, Opus `D-OPU-4` recovery `0/4 -> 3/4`, Fable `+23.9%` cost overhead + `RW5` wrapper gap, and Fable/Neon `RW3` 480s timeouts).

## 0.3.0 — 26 November 2026

- **Harder multi-file/multi-document probes & runner (`M1`, `M2`, `B2`, `D1`, `S2`, `W3`):** Added six harder constructed probes, automated workspace graders (`grade_m1.py`, `grade_m2.py`, `grade_b2.py`), `D-OPU-4` zero-wrapper/word-cap delta for Opus 5.5, `benchmarks/pilot-v0.3.0.json`, and the `scripts/run_benchmark.py` execution harness (`tests/test_runner.py`).
- **Pre-public constructed diagnostics (`LOCAL-01`, `LOCAL-02`):** Recorded the 150-run `v0.2.0` constructed pilot (96% baseline ceiling, leaving standing-rule efficacy unestablished) and the 90-run `v0.3.0` harder-probe pilot (`27/30 -> 28/30 -> 29/30`, Sol `B2` test-skip tampering prevented, Opus regression reversed by `D-OPU-4`; both archived privately off the public repo under Option B).

## 0.2.0 — 24 November 2026

- **Core standard (`standard/core.md`):** Assigned stable rule IDs (`R1`–`R7`) with a no-renumber retirement gap contract; added surgical clauses to verify user premises against evidence before acting (`R2`) and forbid editing or weakening tests to fit broken code (`R4`) while staying under 300 words with zero model-specific bloat.
- **Validator & CI hardening (`scripts/benchmark.py`, `scripts/check.py`):** Unblocked arbitrary condition ablations (`--baseline` / `--treatment`, enabling `v0.1.0` vs. `v0.2.0` and `core-rules` vs. `model-controls`); enforced `lineage_steps[0] == prompt`, per-stage `stage_artifacts` SHA-256 verification, `benchmarks/pilot.json` & `run-record.example.json` reconciliation, mandatory blocker evidence on failed/blocked/timeout runs, `parse_constant` rejection of `NaN`/`Infinity` in `load_runs()`, per-model baseline `condition_revision` scoping, and unified `tests/test_*.py` discovery.
- **Production-realism probes & automated graders (`benchmarks/`):** Kept original `W1`–`C2` cases and fixtures byte-identical for `v0.1.0` vs. `v0.2.0` comparison; added `B1` (blocker deception), `S1` (sycophancy & user-turn injection), `T1` (test-theater & hidden suite), and `P1` (sloppy-neighbor imitation & ownership toggle), plus stdlib Python graders for `C1`, `C2`, `T1`, and `P1` and `tests/test_graders.py`.
- **Opt-in runtime gates (`gates/`):** Added zero-dependency `gates/api_checks.py`, `gates/diff_check.py`, delta-only `gates/model_deltas.json`, warning-first `gates/vale/` rules with technical allowlists, modular `gates/ci-ratchet.yml`, and `tests/test_gates.py`.
- **2026 model intelligence & operational playbooks (`docs/`):** Updated `docs/models.md` and `docs/evidence.md` with verified 2026 findings across all five models (Sol 24.08% Blocker Deception, `effort="none"` HTTP 400, top-level `instructions` caching trap, UK AISI eval awareness & correlated judge failures, CodeRabbit precision/nitpick polarity, Opus 5.5 `SlopCodeBench` erosion inversion, Fable 5.2 `max` cliff & sticky Opus 4.8 cyber fallback, Neon 3× SWE-sweep cliff & `xhigh` diminishing returns); added `docs/operations-and-routing.md` (workload routing, 4-tier stakes review matrix, cross-family verification, safe legacy removal and Golden Eval ablation/pruning).
- **Governance & licensing:** Added MIT `LICENSE` and aligned `CONTRIBUTING.md`, `AGENTS.md`, and GitHub PR/issue templates with stable-ID rule retirement and valid-neighbouring-case validation.

Comparative model evaluation had not been run at `0.2.0` release.

## 0.1.0 — 24 November 2026

- Seeded the seven-rule candidate standard and operating guide.
- Added source-linked profiles for the five requested models.
- Added six constructed diagnostic cases and a 60-record pilot roster.
- Added dependency-free evidence validation and paired-result summaries.
- Added checks against incomplete acceptance, incompatible comparisons, changed evidence and misleading fixture results.
- Added contribution, defect and rule-change workflows.

Comparative model evaluation had not been run at `0.1.0` release.
