# Multi-Turn Compounding Software Quality Report: `pilot-evolution-v0.7.0` (`EV1`, `n = 3`)

**Status:** Completed. Clean, `CODEX_HOME`-isolated, pre-hash-sanitized public dataset under `results/pilot-evolution-v0.7.0/`.

- **Experiment ID:** `pilot-evolution-v0.7.0` (reconciled against [benchmarks/pilot-evolution-v0.7.0.json](../../benchmarks/pilot-evolution-v0.7.0.json); `missing_pilot_coverage.complete = true`)
- **Date:** 27 November 2026 | **Source snapshot:** `git-2f06ef584068` | **Seed:** `20261127` | **Per-stage timeout:** `720s`
- **Design:** 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) x 1 constructed 4-turn Python evolution case (`EV1`, [benchmarks/cases/EV1.json](../../benchmarks/cases/EV1.json): Turn 1 prorated plan upgrades + idempotency -> Turn 2 shared promo codes -> Turn 3 penny-conserving partial refunds + credit notes -> Turn 4 subtractive `legacy_flat_fee` removal + fail-closed `audit_sink`) x 3 conditions (`baseline`, `core-rules-v0.2.0`, `gated-structural`) x `n = 3` replicates = **36 run records** (12 matched triplets, `144` base generation stages + `15` automated gate-repair turns on `gated-structural`).
- **Completion and integrity:** `36 completed`, `0 timeout`, `0 failed`, `0 blocked`. `144/144` stage functional checks passed. Every run ran in an isolated temp workspace outside the repository with per-run isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` `.agy.log` files, `0` secrets across `644` promoted files).
- **Scoring:** 100% mechanically graded by [benchmarks/graders/grade_ev1.py](../../benchmarks/graders/grade_ev1.py) across six required checks (`functional_all_turns`, `mutation_test_strength` >= 65% AST mutant kill rate + 0 test theater, `no_duplicate_code_growth`, `no_dead_or_legacy_code`, `no_sprawl_or_god_functions`, `no_silent_failures_or_shortcuts`). Zero word caps, zero prose constraints, and zero subjective LLM judging.

## Executive Summary

| Condition Arm | Overall Pass (`n = 12`) | Functional Pass (`4` turns) | Mutation Kill Rate Mean / Median | Total Slop Defects (Avg / Run) | God Functions | Silent / Shortcut Findings | Test Theater | Automated Repair Turns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | **`6/12` (`50.0%`)** | `12/12` (`100.0%`) | `70.56%` / `66.67%` | `75` (`6.25`) | `3` | `71` | `1` | `0` |
| `core-rules-v0.2.0` | **`5/12` (`41.7%`)** | `12/12` (`100.0%`) | `67.22%` / `63.33%` | `45` (`3.75`) | `3` | `42` | `0` | `0` |
| `gated-structural` | **`11/12` (`91.7%`)** | `12/12` (`100.0%`) | **`74.72%` / `73.33%`** | **`0` (`0.00`)** | **`0`** | **`0`** | **`0`** | `15` |

Three clear empirical findings emerged across `n = 3` replicates:

1. **Mechanical gating decisively beats standing prose rules on multi-turn software quality (`11/12` vs. `5/12` and `6/12`):** Standing prose instructions (`core-rules-v0.2.0`) alone slightly **regressed** overall pass rate (`6/12 -> 5/12`, `+1/-2`) and weakened mean AST mutation kill rate (`70.56% -> 67.22%`), triggering `DROP` verdicts on both `claude-opus-5-5` and `gpt-6.2-sol`. In contrast, `gated-structural` (zero standing rule bloat, mechanical diff + structural review after each stage with targeted repair when findings fire) lifted overall pass rate to **`11/12` (`91.7%`)** (`+6/-1` vs. `baseline`, `+6/-0` zero-regression vs. `core-rules-v0.2.0`), eliminated **100% (`75 -> 0`)** of structural and shortcut defects, and raised AST mutation kill rate to **`74.72%`** mean / **`73.33%`** median (`+4.2 pp` vs. `baseline`, **`+7.5 pp`** vs. `core-rules-v0.2.0`).
2. **Real structural and test-quality fixes caught mid-evolution:** On `gemini-4-neon`, every `baseline` (`3/3`) and `core-rules-v0.2.0` (`3/3`) run grew a god function in `api.py` (`68L-75L`, exceeding the `65L` grader limit); `gated-structural` flagged `upgrade_subscription` (`69L-70L`) at Stage 2 on all 3 replicates, prompting Neon to refactor into smaller helpers (`47L-49L` final max), eliminating `3 -> 0` god functions and lifting Neon's mutation kill rate from `71.1%` (`baseline`) / `68.9%` (`core-rules-v0.2.0`) to **`82.2%`** (`3/3` pass). On `claude-opus-5-5`, `gated-structural` caught an assertion-free smoke test (`STRUCT-TEST-THEATER`, `test_percent_bounds_are_inclusive` with zero assertions) at Stage 2 on `r3`, preventing the test-theater defect seen in `baseline r3` (`1 -> 0`) and lifting Opus from `1/3` (`baseline`) and `0/3` (`core-rules-v0.2.0`) to **`3/3`**.
3. **Transparent composition of `silent_failures_and_shortcuts` and token overhead:** All `113/113` `silent_failures_and_shortcuts` findings in `baseline` (`71`) and `core-rules-v0.2.0` (`42`) were `DIFF-SUPPRESSION` violations for bare `# type: ignore[...]` comments without a trailing justification (split across test files and production `pricing.py`); zero runs across all 36 introduced broad silent `except` catches, skipped tests, or stub bodies. Automated gate repairs on `gated-structural` (`15` repair turns across `12` runs, `10` triggered by `STRUCT-DEAD-COMPAT` keeping `legacy_flat_fee` from leaking into newly added Stage-2 helpers) increased total tokens by `+18.7%` to `+43.8%` (`+11.3%` Opus USD) while keeping aggregate wall time nearly flat (`+1.7%`: `5,415.0s` -> `5,506.8s`).

## Objective `benchmarks/evolution.py compare` Verdicts (`KEEP` / `DROP` / `INCONCLUSIVE`)

Computed directly from Stage-4 [benchmarks/graders/grade_ev1.py](../../benchmarks/graders/grade_ev1.py) metric JSONs via [benchmarks/evolution.py](../../benchmarks/evolution.py) `compare`:

| Comparison Pair (`baseline` -> `treatment`) | Scope | Decision | Functional Delta | Mutation Kill Delta | Slop Defects Delta (`/run`) | Reason |
|---|---|---|---:|---:|---:|---|
| `baseline` -> `core-rules-v0.2.0` | **Aggregate (`12` vs `12`)** | **`KEEP`*** | `+0.0%` | `-3.3%` (`70.6% -> 67.2%`) | `-2.50` (`6.25 -> 3.75`) | Driven solely by Neon `# type: ignore` drop (`64 -> 37`); overall pass fell `6/12 -> 5/12` |
| `baseline` -> `core-rules-v0.2.0` | `claude-opus-5-5` (`3` vs `3`) | **`DROP`** | `+0.0%` | `-6.7%` (`66.7% -> 60.0%`) | `-1.00` (`2.67 -> 1.67`) | Weakened test mutation kill rate > 5 pp (`1/3 -> 0/3` pass) |
| `baseline` -> `core-rules-v0.2.0` | `gpt-6.2-astra` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `+4.4%` (`66.7% -> 71.1%`) | `+0.00` (`0.00 -> 0.00`) | No decisive gain (`3/3 -> 3/3`, `0` slop) |
| `baseline` -> `core-rules-v0.2.0` | `gpt-6.2-sol` (`3` vs `3`) | **`DROP`** | `+0.0%` | `-8.9%` (`77.8% -> 68.9%`) | `+0.00` (`0.00 -> 0.00`) | Weakened test mutation kill rate > 5 pp |
| `baseline` -> `core-rules-v0.2.0` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | `-2.2%` (`71.1% -> 68.9%`) | `-9.00` (`22.33 -> 13.33`) | Reduced `# type: ignore` count, but `0/3 -> 0/3` pass and `3/3` god functions remained |
| `baseline` -> `gated-structural` | **Aggregate (`12` vs `12`)** | **`KEEP`** | `+0.0%` | **`+4.2%`** (`70.6% -> 74.7%`) | **`-6.25`** (`6.25 -> 0.00`) | Zero slop defects across all 12 runs, `+4.2 pp` mutation kill, `6/12 -> 11/12` pass |
| `baseline` -> `gated-structural` | `claude-opus-5-5` (`3` vs `3`) | **`KEEP`** | `+0.0%` | `+0.0%` (`66.7% -> 66.7%`) | `-2.67` (`2.67 -> 0.00`) | Eliminated all suppressions and test theater (`1/3 -> 3/3` pass) |
| `baseline` -> `gated-structural` | `gpt-6.2-astra` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+6.7%`** (`66.7% -> 73.3%`) | `+0.00` (`0.00 -> 0.00`) | Improved mutation kill rate >= +5 pp (`3/3 -> 3/3`) |
| `baseline` -> `gated-structural` | `gpt-6.2-sol` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `-1.1%` (`77.8% -> 76.7%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `2/3` pass with `0` slop (`r1` mutation `60.0%`) |
| `baseline` -> `gated-structural` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+11.1%`** (`71.1% -> 82.2%`) | **`-22.33`** (`22.33 -> 0.00`) | Eliminated `3 -> 0` god functions and `64 -> 0` suppressions (`0/3 -> 3/3` pass) |
| `core-rules-v0.2.0` -> `gated-structural` | **Aggregate (`12` vs `12`)** | **`KEEP`** | `+0.0%` | **`+7.5%`** (`67.2% -> 74.7%`) | **`-3.75`** (`3.75 -> 0.00`) | Beats standing prose rules on mutation kill (`+7.5 pp`), slop (`-3.75/run`), and pass (`5/12 -> 11/12`) |
| `core-rules-v0.2.0` -> `gated-structural` | `claude-opus-5-5` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+6.7%`** (`60.0% -> 66.7%`) | `-1.67` (`1.67 -> 0.00`) | `0/3 -> 3/3` pass, zero slop |
| `core-rules-v0.2.0` -> `gated-structural` | `gpt-6.2-astra` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `+2.2%` (`71.1% -> 73.3%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop |
| `core-rules-v0.2.0` -> `gated-structural` | `gpt-6.2-sol` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+7.8%`** (`68.9% -> 76.7%`) | `+0.00` (`0.00 -> 0.00`) | Recovered mutation strength lost under standing prose rules |
| `core-rules-v0.2.0` -> `gated-structural` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+13.3%`** (`68.9% -> 82.2%`) | **`-13.33`** (`13.33 -> 0.00`) | `0/3 -> 3/3` pass, `3 -> 0` god functions, `+13.3 pp` mutation kill |

*\*Note on aggregate `baseline -> core-rules-v0.2.0`: `compare_evolution_arms` flags `KEEP` at aggregate level strictly because average slop defects fell `-2.50/run` while aggregate mutation drop (`-3.34 pp`) stayed above the `-5.0 pp` auto-drop threshold. Per-model inspection exposes that `core-rules-v0.2.0` scored `DROP` on 2 of 4 models (`claude-opus-5-5`, `gpt-6.2-sol`), `INCONCLUSIVE` on `gpt-6.2-astra`, and left `gemini-4-neon` at `0/3` pass.*

## Per-Model x Condition Structural & Mutation Matrix (`n = 3` per cell)

All 36 runs scored `0` duplicate blocks (`dup=0`), `0` dead/legacy compat findings at Stage 4 (`dead=0`), `0` god files (`god_f=0`), and `12/12` functional correctness (`func=3/3` per model x arm).

| Model | Condition | Pass | Mut Kill Mean (Med) | God Fns | Silent/Shortcuts | Test Theater | Max Func (`L`/`br`) | Avg Prod LOC | Gate Repairs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `claude-opus-5-5` | `baseline` | `1/3` | `66.7%` (`66.7%`) | `0` | `7` | `1` | `61L / 9br` | `620` | `0` |
| `claude-opus-5-5` | `core-rules-v0.2.0` | `0/3` | `60.0%` (`60.0%`) | `0` | `5` | `0` | `54L / 7br` | `572` | `0` |
| `claude-opus-5-5` | `gated-structural` | **`3/3`** | `66.7%` (`66.7%`) | `0` | **`0`** | **`0`** | `60L / 6br` | `589` | `4` |
| `gpt-6.2-astra` | `baseline` | `3/3` | `66.7%` (`66.7%`) | `0` | `0` | `0` | `44L / 9br` | `466` | `0` |
| `gpt-6.2-astra` | `core-rules-v0.2.0` | `3/3` | `71.1%` (`73.3%`) | `0` | `0` | `0` | `47L / 9br` | `461` | `0` |
| `gpt-6.2-astra` | `gated-structural` | **`3/3`** | **`73.3%`** (`66.7%`) | `0` | `0` | `0` | `43L / 9br` | `458` | `3` |
| `gpt-6.2-sol` | `baseline` | `2/3` | `77.8%` (`86.7%`) | `0` | `0` | `0` | `53L / 7br` | `562` | `0` |
| `gpt-6.2-sol` | `core-rules-v0.2.0` | `2/3` | `68.9%` (`66.7%`) | `0` | `0` | `0` | `46L / 7br` | `539` | `0` |
| `gpt-6.2-sol` | `gated-structural` | `2/3` | `76.7%` (`83.3%`) | `0` | `0` | `0` | `49L / 7br` | `560` | `2` |
| `gemini-4-neon` | `baseline` | `0/3` | `71.1%` (`66.7%`) | `3` | `64` | `0` | `75L / 10br` | `661` | `0` |
| `gemini-4-neon` | `core-rules-v0.2.0` | `0/3` | `68.9%` (`60.0%`) | `3` | `37` | `0` | `71L / 9br` | `656` | `0` |
| `gemini-4-neon` | `gated-structural` | **`3/3`** | **`82.2%` (`80.0%`)** | **`0`** | **`0`** | `0` | **`49L / 8br`** | `686` | `6` |

Per-check pass rates across all 12 runs/arm:
- `functional_all_turns`: `12/12` `baseline`, `12/12` `core-rules-v0.2.0`, `12/12` `gated-structural`
- `mutation_test_strength` (>= 65% kill rate, 0 test theater): `9/12` (`75.0%`) `baseline`, `6/12` (`50.0%`) `core-rules-v0.2.0`, **`11/12` (`91.7%`)** `gated-structural`
- `no_duplicate_code_growth`: `12/12` across all three arms
- `no_dead_or_legacy_code`: `12/12` across all three arms
- `no_sprawl_or_god_functions`: `9/12` (`75.0%`) `baseline`, `9/12` (`75.0%`) `core-rules-v0.2.0`, **`12/12` (`100.0%`)** `gated-structural`
- `no_silent_failures_or_shortcuts`: `7/12` (`58.3%`) `baseline`, `8/12` (`66.7%`) `core-rules-v0.2.0`, **`12/12` (`100.0%`)** `gated-structural`

## Paired 3-Track Summary (`scripts/benchmark.py summarize`)

All three tracks validate against [benchmarks/pilot-evolution-v0.7.0.json](../../benchmarks/pilot-evolution-v0.7.0.json) with `missing_pilot_coverage.complete = true` (`12` matched pairs per track):

| Track (`baseline` -> `treatment`) | Baseline Pass | Treatment Pass | Improved / Regressed | Both Pass / Neither | Per-Model (`B -> T`) |
|---|---:|---:|---:|---:|---|
| `baseline` -> `core-rules-v0.2.0` | `6/12` (`50.0%`) | `5/12` (`41.7%`) | `+1 / -2` (net `-1`) | `4 / 5` | Opus `1/3 -> 0/3`, Astra `3/3 -> 3/3`, Sol `2/3 -> 2/3`, Neon `0/3 -> 0/3` |
| `baseline` -> `gated-structural` | `6/12` (`50.0%`) | **`11/12` (`91.7%`)** | **`+6 / -1` (net `+5`)** | `5 / 0` | Opus `1/3 -> 3/3`, Astra `3/3 -> 3/3`, Sol `2/3 -> 2/3`, Neon `0/3 -> 3/3` |
| `core-rules-v0.2.0` -> `gated-structural` | `5/12` (`41.7%`) | **`11/12` (`91.7%`)** | **`+6 / -0` (net `+6`)** | `5 / 1` | Opus `0/3 -> 3/3`, Astra `3/3 -> 3/3`, Sol `2/3 -> 2/3`, Neon `0/3 -> 3/3` |

## Token, USD, and Wall-Time Overhead (`n = 3` per model x arm)

Provider CLI USD is reported directly only by Claude Code (`null` for Codex CLI and Antigravity CLI). Wall time sums Stage 1 through Stage 4 generation elapsed seconds (gate-repair turns are reflected in cumulative session tokens/USD; stage markdown elapsed headers capture primary stage turns).

| Model | Condition | Total Tokens (Delta vs. `baseline`) | Total USD (Delta vs. `baseline`) | Stage 1-4 Wall Time Sum / Median (Delta vs. `baseline`) |
|---|---|---:|---:|---:|
| `claude-opus-5-5` | `baseline` | `4,189,068` (`+0.0%`) | `$5.3410` (`+0.0%`) | `1,176.5s` / `365.8s` (`+0.0%`) |
| `claude-opus-5-5` | `core-rules-v0.2.0` | `4,205,889` (`+0.4%`) | `$5.1390` (`-3.8%`) | `1,142.5s` / `371.6s` (`-2.9%`) |
| `claude-opus-5-5` | `gated-structural` | `5,845,630` (`+39.5%`) | `$5.9470` (`+11.3%`) | `1,171.7s` / `393.5s` (`-0.4%`) |
| `gpt-6.2-astra` | `baseline` | `4,552,806` (`+0.0%`) | `null` | `801.7s` / `251.1s` (`+0.0%`) |
| `gpt-6.2-astra` | `core-rules-v0.2.0` | `4,354,338` (`-4.4%`) | `null` | `804.5s` / `265.2s` (`+0.3%`) |
| `gpt-6.2-astra` | `gated-structural` | `6,544,838` (`+43.8%`) | `null` | `874.7s` / `281.2s` (`+9.1%`) |
| `gpt-6.2-sol` | `baseline` | `9,082,272` (`+0.0%`) | `null` | `1,494.1s` / `500.9s` (`+0.0%`) |
| `gpt-6.2-sol` | `core-rules-v0.2.0` | `7,787,478` (`-14.3%`) | `null` | `1,401.6s` / `471.0s` (`-6.2%`) |
| `gpt-6.2-sol` | `gated-structural` | `11,359,962` (`+25.1%`) | `null` | `1,460.8s` / `484.8s` (`-2.2%`) |
| `gemini-4-neon` | `baseline` | `720,348` (`+0.0%`) | `null` | `1,942.7s` / `643.5s` (`+0.0%`) |
| `gemini-4-neon` | `core-rules-v0.2.0` | `832,200` (`+15.5%`) | `null` | `1,812.4s` / `590.4s` (`-6.7%`) |
| `gemini-4-neon` | `gated-structural` | `855,381` (`+18.7%`) | `null` | `1,999.5s` / `697.7s` (`+2.9%`) |

## Complete List of Non-Passing Runs (`14 / 36`: `6` `baseline`, `7` `core-rules-v0.2.0`, `1` `gated-structural`)

### `baseline` (`6` failing runs)

1. `pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r2`: `mutation_test_strength` (`9/15 = 60.0% < 65%`) + `no_silent_failures_or_shortcuts` (`4` bare `# type: ignore[...]` comments in `pricing.py` and candidate `test_refunds.py`).
2. `pilot-evolution-v0.7.0__claude-opus-5-5__EV1__baseline__r3`: `mutation_test_strength` (`11/15 = 73.3%`, failed due to `test_theater = 1`) + `no_silent_failures_or_shortcuts` (`3` bare `# type: ignore[...]` comments in tests).
3. `pilot-evolution-v0.7.0__gpt-6.2-sol__EV1__baseline__r2`: `mutation_test_strength` (`9/15 = 60.0% < 65%`; `0` structural defects).
4. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r1`: `no_sprawl_or_god_functions` (`max_func = 73L / 10br`, `god_fns = 1`) + `no_silent_failures_or_shortcuts` (`25` bare `# type: ignore[...]` comments).
5. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r2`: `no_sprawl_or_god_functions` (`max_func = 75L / 9br`, `god_fns = 1`) + `no_silent_failures_or_shortcuts` (`17` bare `# type: ignore[...]` comments).
6. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r3`: `no_sprawl_or_god_functions` (`max_func = 68L / 9br`, `god_fns = 1`) + `no_silent_failures_or_shortcuts` (`22` bare `# type: ignore[...]` comments, including production `pricing.py:82,83,86`).

### `core-rules-v0.2.0` (`7` failing runs)

7. `pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r1`: `mutation_test_strength` (`9/15 = 60.0% < 65%`).
8. `pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r2`: `mutation_test_strength` (`9/15 = 60.0% < 65%`) + `no_silent_failures_or_shortcuts` (`2` bare `# type: ignore[...]` comments in tests).
9. `pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3`: `mutation_test_strength` (`9/15 = 60.0% < 65%`) + `no_silent_failures_or_shortcuts` (`3` bare `# type: ignore[...]` comments in tests).
10. `pilot-evolution-v0.7.0__gpt-6.2-sol__EV1__core-rules-v0.2.0__r1`: `mutation_test_strength` (`8/15 = 53.3% < 65%`; `0` structural defects).
11. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r1`: `no_sprawl_or_god_functions` (`max_func = 71L / 9br`, `god_fns = 1`).
12. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2`: `mutation_test_strength` (`9/15 = 60.0% < 65%`) + `no_sprawl_or_god_functions` (`max_func = 71L / 8br`, `god_fns = 1`) + `no_silent_failures_or_shortcuts` (`18` bare `# type: ignore[...]` comments).
13. `pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r3`: `mutation_test_strength` (`9/15 = 60.0% < 65%`) + `no_sprawl_or_god_functions` (`max_func = 68L / 9br`, `god_fns = 1`) + `no_silent_failures_or_shortcuts` (`19` bare `# type: ignore[...]` comments, including `pricing.py:82,83,86`).

### `gated-structural` (`1` failing run)

14. `pilot-evolution-v0.7.0__gpt-6.2-sol__EV1__gated-structural__r1`: `mutation_test_strength` (`9/15 = 60.0% < 65%`; `0` structural defects, `0` silent/shortcut findings).

## Honest Scope Limits and Calibration Notes

- **Constructed single-scenario scope (`EV1`):** `EV1` is a 4-turn stdlib Python billing/ledger evolution scenario (`n = 3` replicates per cell). Replicates verify consistency on this chain, not generalization across arbitrary multi-language production codebases.
- **Gate-repair trigger profile (`15` turns total on `gated-structural`):** Pre-repair findings caught by `gates/review.py` comprised `15` `DIFF-SUPPRESSION` findings, `10` `STRUCT-DEAD-COMPAT` findings, `5` `STRUCT-GOD-FUNCTION` findings, and `1` `STRUCT-TEST-THEATER` finding. Ten of the 15 repair turns triggered at Stage 2 when models propagated `legacy_flat_fee` into newly introduced Turn-2 pricing helpers before Turn 4 deprecated it; fixing those kept `legacy_flat_fee` isolated to legacy entry points without breaking Stage 2 tests (`144/144` stage functional pass), while contributing to the `+18.7%` to `+43.8%` token overhead on `gated-structural`.
- **Mutation testing is not yet part of the Stage 1-4 gate loop:** The only remaining `gated-structural` failure (`gpt-6.2-sol r1`, `9/15 = 60.0%`) missed the `65%` mutation kill bar while passing all static structural checks cleanly. Integrating fast AST mutation checks (`anti-slop-mutate`) into the optional gate loop is a natural next experiment.

## Reproduce and Verify

Validate records, SHA-256 hashes, and all three paired tracks locally (zero model or network calls):

```bash
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-evolution-v0.7.0.json validate results/pilot-evolution-v0.7.0/runs.jsonl
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-evolution-v0.7.0.json --baseline baseline --treatment core-rules-v0.2.0 summarize results/pilot-evolution-v0.7.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-evolution-v0.7.0.json --baseline baseline --treatment gated-structural summarize results/pilot-evolution-v0.7.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-evolution-v0.7.0.json --baseline core-rules-v0.2.0 --treatment gated-structural summarize results/pilot-evolution-v0.7.0/runs.jsonl --json
python3 -B scripts/check.py
```

Re-run the isolated 36-run 4-turn evolution sweep from scratch:

```bash
python3 -B scripts/run_benchmark.py \
  --experiment-id pilot-evolution-v0.7.0 \
  --cases EV1 \
  --models claude-opus-5-5 gpt-6.2-astra gpt-6.2-sol gemini-4-neon \
  --conditions baseline core-rules-v0.2.0 gated-structural \
  --replicates 3 \
  --seed 20261127 \
  --timeout 720 \
  --parallel-models \
  --max-workers 3 \
  --child-max-rss-mb 1536
```
