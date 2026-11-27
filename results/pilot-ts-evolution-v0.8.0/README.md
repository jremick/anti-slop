# Multi-Turn TypeScript Compounding Quality Report: `pilot-ts-evolution-v0.8.0` (`EV2`, `n = 3`)

**Status:** Completed. Clean, `CODEX_HOME`-isolated, pre-hash-sanitized public dataset under `results/pilot-ts-evolution-v0.8.0/`.

- **Experiment ID:** `pilot-ts-evolution-v0.8.0` (reconciled against [benchmarks/pilot-ts-evolution-v0.8.0.json](../../benchmarks/pilot-ts-evolution-v0.8.0.json); `missing_pilot_coverage.complete = true`)
- **Date:** 27 November 2026 | **Source snapshot:** `git-37c85c41e2ac` | **Seed:** `20261127` | **Per-stage timeout:** `720s`
- **Design:** 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) x 1 constructed 4-turn erasable TypeScript evolution case (`EV2`, [benchmarks/cases/EV2.json](../../benchmarks/cases/EV2.json): Turn 1 half-up fractional-hour pricing, slot overlap, holds/expiration -> Turn 2 multi-room atomic group bookings + shared `applyDiscountAndTax` -> Turn 3 tiered cancellation refunds + centralized fail-closed `BOOKING_CANCEL_FEE_TIERS_JSON` -> Turn 4 complete removal of `legacyDepositMode`/`calculateLegacyDeposit`/`LEGACY_DEPOSIT_BPS`/`depositCents` + fail-closed atomic `notifyHook`) x 3 conditions (`baseline`, `core-rules-v0.2.0`, `gated-structural`) x `n = 3` replicates = **36 run records** (12 matched triplets, `144` base generation stages + `4` automated gate-repair turns on `gated-structural`).
- **Completion and integrity:** `36 completed`, `0 timeout`, `0 failed`, `0 blocked`. `144/144` stage functional checks passed via native Node.js TS execution (`node v26.12.1`). Every run executed in an isolated temp workspace outside the repository with per-run isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` `.agy.log` files, `0` secrets across `633` promoted artifact/metadata files).
- **Scoring:** 100% mechanically graded by [benchmarks/graders/grade_ev2.py](../../benchmarks/graders/grade_ev2.py) across six required checks (`functional_all_turns`, `mutation_test_strength` >= 65% JS/TS mutant kill rate via [gates/mutate.py](../../gates/mutate.py) + 0 test theater, `no_duplicate_code_growth`, `no_dead_or_legacy_code`, `no_sprawl_or_god_functions`, `no_silent_failures_or_shortcuts`). Zero word caps, zero prose constraints, and zero subjective LLM judging.

## Executive Summary

| Condition Arm | Overall Pass (`n = 12`) | Functional Pass (`4` turns) | TS Mutation Kill Rate Mean / Median | Total Slop Defects (Avg / Run) | Duplicate Blocks | God Functions | Dead / Circular / Silent / Theater | Automated Repair Turns |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | **`7/12` (`58.3%`)** | `12/12` (`100.0%`) | `74.17%` / `80.00%` | `10` (`0.83`) | `6` | `4` | `0 / 0 / 0 / 0` | `0` |
| `core-rules-v0.2.0` | **`8/12` (`66.7%`)** | `12/12` (`100.0%`) | `75.00%` / `75.00%` | `5` (`0.42`) | `2` | `3` | `0 / 0 / 0 / 0` | `0` |
| `gated-structural` | **`12/12` (`100.0%`)** | `12/12` (`100.0%`) | **`79.17%` / `77.50%`** | **`0` (`0.00`)** | **`0`** | **`0`** | **`0 / 0 / 0 / 0`** | `4` |

Four clear empirical findings emerged across `n = 3` replicates:

1. **Mechanical gating achieves `12/12` (`100.0%`) pass with aggregate `KEEP`, beating standing prose rules (`8/12`, `INCONCLUSIVE`) at lower cost:** Standing prose instructions (`core-rules-v0.2.0`) lifted pass rate by only 1 run (`7/12 -> 8/12`, `+1/-0`), scored **`INCONCLUSIVE`** at aggregate level under `benchmarks/evolution.py compare` (`+0.83 pp` mutation kill, `-0.42` slop/run), and left `gemini-4-neon` at `0/3` pass. In contrast, `gated-structural` reached **`12/12` (`100.0%`)** (`+5/-0` zero-regression vs. `baseline`, `+4/-0` zero-regression vs. `core-rules-v0.2.0`), eliminated **100% (`10 -> 0`)** of structural slop defects, raised JS/TS mutation kill rate to **`79.17%`** (**`+5.00 pp`** vs. `baseline`, earning aggregate **`KEEP`**), and cost **less** than `core-rules-v0.2.0` on tokens (`-10.4%`), Opus USD (`-8.5%`), and Stage 1-4 wall time (`-6.8%`).
2. **100% real structural compounding defects, zero suppression noise:** Unlike Python `EV1` (where bare `# type: ignore[...]` comments accounted for `113/113` `silent_failures_and_shortcuts` findings), all 36 `EV2` runs had **`0`** `DIFF-*` shortcut/suppression findings, **`0`** `dead_compat`, **`0`** `circular_imports`, and **`0`** `test_theater`. Every single structural failure across `baseline` (`10` defects) and `core-rules-v0.2.0` (`5` defects) was a genuine TypeScript compounding defect: **`STRUCT-DUPLICATE-BLOCK`** (`6 -> 2 -> 0`, copy-pasted 6-statement booking logic across `bookings.ts` and `corporate.ts`) and **`STRUCT-GOD-FUNCTION`** (`4 -> 3 -> 0`, oversized functions exceeding the `65L` limit).
3. **Direct mid-evolution structural + test-strength rescue on `gemini-4-neon`:** On `gemini-4-neon`, every `baseline` (`3/3`) and `core-rules-v0.2.0` (`3/3`) run failed with god functions (`3/3`) plus duplicate blocks (`4` in `baseline`, `1` in `core-rules-v0.2.0`) and weak JS/TS mutation kills (`58.3%` `baseline`, `63.3%` `core-rules-v0.2.0`). Under `gated-structural`, `gates/review.py` fired on `3/3` Neon replicates (`4` repair turns total: `3` `STRUCT-GOD-FUNCTION` on `corporate.ts:createGroupBooking` at `72L-77L` in Stage 2 and `3` `STRUCT-DUPLICATE-BLOCK` between `bookings.ts` and `corporate.ts` in Stage 2-3). Resolving those findings mid-evolution eliminated `4 -> 0` duplicate blocks and `3 -> 0` god functions, lifted Neon's JS/TS mutation kill rate to **`80.0%`** (**`+21.67 pp`** vs. `baseline`, **`+16.67 pp`** vs. `core-rules-v0.2.0`), moved Neon from `0/3` to **`3/3`** (`KEEP` vs. both `baseline` and `core-rules-v0.2.0`), and used **`-10.9%`** fewer tokens than `baseline`.
4. **Transparent attribution on `claude-opus-5-5`:** `claude-opus-5-5` also improved from `1/3` (`baseline`: `2` duplicate blocks + `1` god function) and `2/3` (`core-rules-v0.2.0`: `1` duplicate block) to **`3/3`** (`gated-structural`: `0` defects, `85.0%` mutation kill, `KEEP` vs. `baseline`), with **`0`** post-stage repair turns triggered. Because no post-stage repair fired on Opus, that lift reflects either the lightweight two-sentence gate-awareness prompt avoiding copy-paste/long functions upfront or replicate variance at `n = 3`, rather than post-stage repair intervention.

## Objective `benchmarks/evolution.py compare` Verdicts (`KEEP` / `DROP` / `INCONCLUSIVE`)

Computed directly from Stage-4 [benchmarks/graders/grade_ev2.py](../../benchmarks/graders/grade_ev2.py) metric JSONs via [benchmarks/evolution.py](../../benchmarks/evolution.py) `compare`:

| Comparison Pair (`baseline` -> `treatment`) | Scope | Decision | Functional Delta | Mutation Kill Delta | Slop Defects Delta (`/run`) | Reason |
|---|---|---|---:|---:|---:|---|
| `baseline` -> `core-rules-v0.2.0` | **Aggregate (`12` vs `12`)** | **`INCONCLUSIVE`** | `+0.0%` | `+0.83%` (`74.17% -> 75.00%`) | `-0.42` (`0.83 -> 0.42`) | Below +5 pp mutation and -1.0 slop/run thresholds (`+13.0%` tokens, `+11.6%` Opus USD) |
| `baseline` -> `core-rules-v0.2.0` | `claude-opus-5-5` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `-1.67%` (`85.00% -> 83.33%`) | `-0.67` (`1.00 -> 0.33`) | Cut 2 of 3 slop defects (`1/3 -> 2/3`), but below thresholds at `+33.9%` tokens |
| `baseline` -> `core-rules-v0.2.0` | `gpt-6.2-astra` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `-5.00%` (`80.00% -> 75.00%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop (exact `-5.0%` boundary, not `< -5.0%`) |
| `baseline` -> `core-rules-v0.2.0` | `gpt-6.2-sol` (`3` vs `3`) | **`KEEP`** | `+0.0%` | `+5.00%` (`73.33% -> 78.33%`) | `+0.00` (`0.00 -> 0.00`) | Improved mutation kill rate >= +5 pp (`3/3 -> 3/3`, `0` slop) |
| `baseline` -> `core-rules-v0.2.0` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | `+5.00%` (`58.33% -> 63.33%`) | `-1.00` (`2.33 -> 1.33`) | Reduced duplicates (`4 -> 1`), but `0/3 -> 0/3` pass and `3/3` god functions remained |
| `baseline` -> `gated-structural` | **Aggregate (`12` vs `12`)** | **`KEEP`** | `+0.0%` | **`+5.00%`** (`74.17% -> 79.17%`) | **`-0.83`** (`0.83 -> 0.00`) | **`12/12` (`100%`) pass, `0` slop defects, `+5.0 pp` mutation kill** |
| `baseline` -> `gated-structural` | `claude-opus-5-5` (`3` vs `3`) | **`KEEP`** | `+0.0%` | `+0.00%` (`85.00% -> 85.00%`) | **`-1.00`** (`1.00 -> 0.00`) | Eliminated `2` duplicate blocks + `1` god function (`1/3 -> 3/3` pass) |
| `baseline` -> `gated-structural` | `gpt-6.2-astra` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `-5.00%` (`80.00% -> 75.00%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop (`-7.4%` fewer tokens) |
| `baseline` -> `gated-structural` | `gpt-6.2-sol` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `+3.34%` (`73.33% -> 76.67%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop |
| `baseline` -> `gated-structural` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+21.67%`** (`58.33% -> 80.00%`) | **`-2.33`** (`2.33 -> 0.00`) | Eliminated `4 -> 0` duplicate blocks and `3 -> 0` god functions (`0/3 -> 3/3` pass) |
| `core-rules-v0.2.0` -> `gated-structural` | **Aggregate (`12` vs `12`)** | **`INCONCLUSIVE`*** | `+0.0%` | `+4.17%` (`75.00% -> 79.17%`) | `-0.42` (`0.42 -> 0.00`) | Just below `+5.0 pp` / `-1.0/run` thresholds while lifting pass `8/12 -> 12/12` at `-10.4%` tokens |
| `core-rules-v0.2.0` -> `gated-structural` | `claude-opus-5-5` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `+1.67%` (`83.33% -> 85.00%`) | `-0.33` (`0.33 -> 0.00`) | `2/3 -> 3/3` pass, `0` slop, `-19.5%` fewer tokens and `-8.5%` lower USD |
| `core-rules-v0.2.0` -> `gated-structural` | `gpt-6.2-astra` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `+0.00%` (`75.00% -> 75.00%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop (`-12.1%` fewer tokens) |
| `core-rules-v0.2.0` -> `gated-structural` | `gpt-6.2-sol` (`3` vs `3`) | **`INCONCLUSIVE`** | `+0.0%` | `-1.66%` (`78.33% -> 76.67%`) | `+0.00` (`0.00 -> 0.00`) | Both arms `3/3` pass with `0` slop (`-3.1%` fewer tokens) |
| `core-rules-v0.2.0` -> `gated-structural` | `gemini-4-neon` (`3` vs `3`) | **`KEEP`** | `+0.0%` | **`+16.67%`** (`63.33% -> 80.00%`) | **`-1.33`** (`1.33 -> 0.00`) | `0/3 -> 3/3` pass, `3 -> 0` god functions, `1 -> 0` duplicates, `+16.7 pp` mutation kill |

*\*Note on `core-rules-v0.2.0 -> gated-structural`: `compare_evolution_arms` requires `>= +5.0 pp` mutation gain or `<= -1.0` slop/run for aggregate `KEEP`; here `gated-structural` recorded `+4.17 pp` mutation kill and `-0.42` slop/run (eliminating all `5` remaining `core-rules-v0.2.0` defects and moving overall pass from `8/12` to `12/12` with `+4/-0` zero regressions) while cutting aggregate tokens `-10.4%`, Opus USD `-8.5%`, and Stage 1-4 wall time `-6.8%`.*

## Per-Model x Condition Structural & Mutation Matrix (`n = 3` per cell)

All 36 runs scored `12/12` functional correctness (`func = 3/3` per model x arm), `6` production TS files (`<= 8` cap), `0` dead/legacy compat paths at Stage 4, `0` god files, `0` circular imports, `0` test theater, and `0` `DIFF-*`/silent-fallback/config-scatter findings.

| Model | Condition | Pass | Mut Kill Mean (Med) | Per-Replicate Kill (`r1, r2, r3`) | Duplicate Blocks | God Functions | Gate Repairs |
|---|---|---:|---:|---|---:|---:|---:|
| `claude-opus-5-5` | `baseline` | `1/3` | `85.0%` (`85.0%`) | `80%, 85%, 90%` | `2` | `1` | `0` |
| `claude-opus-5-5` | `core-rules-v0.2.0` | `2/3` | `83.3%` (`85.0%`) | `90%, 85%, 75%` | `1` | `0` | `0` |
| `claude-opus-5-5` | `gated-structural` | **`3/3`** | `85.0%` (`85.0%`) | `85%, 80%, 90%` | **`0`** | **`0`** | `0` |
| `gpt-6.2-astra` | `baseline` | `3/3` | `80.0%` (`80.0%`) | `80%, 80%, 80%` | `0` | `0` | `0` |
| `gpt-6.2-astra` | `core-rules-v0.2.0` | `3/3` | `75.0%` (`75.0%`) | `75%, 75%, 75%` | `0` | `0` | `0` |
| `gpt-6.2-astra` | `gated-structural` | **`3/3`** | `75.0%` (`75.0%`) | `75%, 75%, 75%` | `0` | `0` | `0` |
| `gpt-6.2-sol` | `baseline` | `3/3` | `73.3%` (`70.0%`) | `80%, 70%, 70%` | `0` | `0` | `0` |
| `gpt-6.2-sol` | `core-rules-v0.2.0` | `3/3` | `78.3%` (`80.0%`) | `80%, 80%, 75%` | `0` | `0` | `0` |
| `gpt-6.2-sol` | `gated-structural` | **`3/3`** | `76.7%` (`75.0%`) | `80%, 75%, 75%` | `0` | `0` | `0` |
| `gemini-4-neon` | `baseline` | `0/3` | `58.3%` (`60.0%`) | `60%, 65%, 50%` | `4` | `3` | `0` |
| `gemini-4-neon` | `core-rules-v0.2.0` | `0/3` | `63.3%` (`65.0%`) | `65%, 60%, 65%` | `1` | `3` | `0` |
| `gemini-4-neon` | `gated-structural` | **`3/3`** | **`80.0%` (`80.0%`)** | **`80%, 90%, 70%`** | **`0`** | **`0`** | `4` |

Per-check pass rates across all 12 runs/arm:
- `functional_all_turns`: `12/12` `baseline`, `12/12` `core-rules-v0.2.0`, `12/12` `gated-structural`
- `mutation_test_strength` (>= 65% kill rate, 0 test theater): `10/12` (`83.3%`) `baseline`, `11/12` (`91.7%`) `core-rules-v0.2.0`, **`12/12` (`100.0%`)** `gated-structural`
- `no_duplicate_code_growth`: `7/12` (`58.3%`) `baseline`, `10/12` (`83.3%`) `core-rules-v0.2.0`, **`12/12` (`100.0%`)** `gated-structural`
- `no_dead_or_legacy_code`: `12/12` across all three arms
- `no_sprawl_or_god_functions`: `8/12` (`66.7%`) `baseline`, `9/12` (`75.0%`) `core-rules-v0.2.0`, **`12/12` (`100.0%`)** `gated-structural`
- `no_silent_failures_or_shortcuts`: `12/12` across all three arms

## Paired 3-Track Summary (`scripts/benchmark.py summarize`)

All three tracks validate against [benchmarks/pilot-ts-evolution-v0.8.0.json](../../benchmarks/pilot-ts-evolution-v0.8.0.json) with `missing_pilot_coverage.complete = true` (`12` matched pairs per track):

| Track (`baseline` -> `treatment`) | Baseline Pass | Treatment Pass | Improved / Regressed | Both Pass / Neither | Per-Model (`B -> T`) |
|---|---:|---:|---:|---:|---|
| `baseline` -> `core-rules-v0.2.0` | `7/12` (`58.3%`) | `8/12` (`66.7%`) | `+1 / -0` (net `+1`) | `7 / 4` | Opus `1/3 -> 2/3`, Astra `3/3 -> 3/3`, Sol `3/3 -> 3/3`, Neon `0/3 -> 0/3` |
| `baseline` -> `gated-structural` | `7/12` (`58.3%`) | **`12/12` (`100.0%`)** | **`+5 / -0` (net `+5`)** | `7 / 0` | Opus `1/3 -> 3/3`, Astra `3/3 -> 3/3`, Sol `3/3 -> 3/3`, Neon `0/3 -> 3/3` |
| `core-rules-v0.2.0` -> `gated-structural` | `8/12` (`66.7%`) | **`12/12` (`100.0%`)** | **`+4 / -0` (net `+4`)** | `8 / 0` | Opus `2/3 -> 3/3`, Astra `3/3 -> 3/3`, Sol `3/3 -> 3/3`, Neon `0/3 -> 3/3` |

## Token, USD, and Wall-Time Overhead (`n = 3` per model x arm)

Provider CLI USD is reported directly only by Claude Code (`null` for Codex CLI and Antigravity CLI). Wall time sums Stage 1 through Stage 4 generation elapsed seconds (gate-repair turns are included in cumulative session tokens/USD).

| Model | Condition | Total Tokens (Delta vs. `baseline`) | Total USD (Delta vs. `baseline`) | Stage 1-4 Wall Time Sum / Median (Delta vs. `baseline`) |
|---|---|---:|---:|---:|
| `claude-opus-5-5` | `baseline` | `3,969,281` (`+0.0%`) | `$5.4059` (`+0.0%`) | `1,196.9s` / `404.7s` (`+0.0%`) |
| `claude-opus-5-5` | `core-rules-v0.2.0` | `5,313,807` (`+33.9%`) | `$6.0341` (`+11.6%`) | `1,377.6s` / `478.5s` (`+15.1%`) |
| `claude-opus-5-5` | `gated-structural` | `4,279,974` (`+7.8%`) | `$5.5231` (`+2.2%`) | `1,217.8s` / `408.2s` (`+1.7%`) |
| `gpt-6.2-astra` | `baseline` | `4,926,717` (`+0.0%`) | `null` | `930.0s` / `291.9s` (`+0.0%`) |
| `gpt-6.2-astra` | `core-rules-v0.2.0` | `5,186,935` (`+5.3%`) | `null` | `988.2s` / `333.2s` (`+6.3%`) |
| `gpt-6.2-astra` | `gated-structural` | **`4,560,962` (`-7.4%`)** | `null` | **`913.7s` / `311.6s` (`-1.7%`)** |
| `gpt-6.2-sol` | `baseline` | `7,395,689` (`+0.0%`) | `null` | `1,362.2s` / `446.5s` (`+0.0%`) |
| `gpt-6.2-sol` | `core-rules-v0.2.0` | `8,021,047` (`+8.5%`) | `null` | `1,369.0s` / `447.6s` (`+0.5%`) |
| `gpt-6.2-sol` | `gated-structural` | `7,773,173` (`+5.1%`) | `null` | `1,416.8s` / `455.5s` (`+4.0%`) |
| `gemini-4-neon` | `baseline` | `993,713` (`+0.0%`) | `null` | `1,912.8s` / `631.0s` (`+0.0%`) |
| `gemini-4-neon` | `core-rules-v0.2.0` | `1,009,397` (`+1.6%`) | `null` | `2,186.1s` / `698.6s` (`+14.3%`) |
| `gemini-4-neon` | `gated-structural` | **`885,471` (`-10.9%`)** | `null` | `1,968.8s` / `653.0s` (`+2.9%`) |
| **Aggregate (4 models)** | `baseline` | `17,285,400` (`+0.0%`) | `$5.4059` (`+0.0%`) | `5,401.8s` (`+0.0%`) |
| **Aggregate (4 models)** | `core-rules-v0.2.0` | `19,531,186` (`+13.0%`) | `$6.0341` (`+11.6%`) | `5,920.9s` (`+9.6%`) |
| **Aggregate (4 models)** | `gated-structural` | **`17,499,580` (`+1.2%`)** | **`$5.5231` (`+2.2%`)** | **`5,517.2s` (`+2.1%`)** |

## Complete List of Non-Passing Runs (`9 / 36`: `5` `baseline`, `4` `core-rules-v0.2.0`, `0` `gated-structural`)

### `baseline` (`5` failing runs)

1. `pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1`: `no_duplicate_code_growth` (`bookings.ts:182` duplicates 6-statement block at `corporate.ts:37`) + `no_sprawl_or_god_functions` (`god_fns = 1`).
2. `pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r2`: `no_duplicate_code_growth` (`bookings.ts:187` duplicates 6-statement block at `corporate.ts:44`).
3. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__baseline__r1`: `mutation_test_strength` (`12/20 = 60.0% < 65%`) + `no_duplicate_code_growth` (`2` blocks: `bookings.ts:135` vs `corporate.ts:29`, `bookings.ts:240` vs `bookings.ts:274`) + `no_sprawl_or_god_functions` (`god_fns = 1`).
4. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__baseline__r2`: `no_duplicate_code_growth` (`bookings.ts:112` duplicates `corporate.ts:33`) + `no_sprawl_or_god_functions` (`god_fns = 1`).
5. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__baseline__r3`: `mutation_test_strength` (`10/20 = 50.0% < 65%`) + `no_duplicate_code_growth` (`bookings.ts:140` duplicates `corporate.ts:29`) + `no_sprawl_or_god_functions` (`god_fns = 1`).

### `core-rules-v0.2.0` (`4` failing runs)

6. `pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1`: `no_duplicate_code_growth` (`bookings.ts:206` duplicates `corporate.ts:47`).
7. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__core-rules-v0.2.0__r1`: `no_duplicate_code_growth` (`bookings.ts:143` duplicates `corporate.ts:55`) + `no_sprawl_or_god_functions` (`god_fns = 1`).
8. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__core-rules-v0.2.0__r2`: `mutation_test_strength` (`12/20 = 60.0% < 65%`) + `no_sprawl_or_god_functions` (`god_fns = 1`).
9. `pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__core-rules-v0.2.0__r3`: `no_sprawl_or_god_functions` (`god_fns = 1`).

### `gated-structural` (`0` failing runs)

All `12/12` runs passed all `6` mechanical checks.

## Gate-Repair Trigger Profile (`gated-structural`)

Across `48` base stages (`12` runs x `4` turns), `gates/review.py` triggered **`4`** automated repair turns (all on `gemini-4-neon`), catching **`6`** pre-repair findings with **`0`** false positives:
- **`STRUCT-GOD-FUNCTION` (`3` findings, all Stage 2):** `corporate.ts:createGroupBooking` flagged at `77L` (`r1`), `72L` (`r2`), and `74L` (`r3`) against the `60L` gate heuristic.
- **`STRUCT-DUPLICATE-BLOCK` (`3` findings, `2` at Stage 2 + `1` at Stage 3):** 6-statement duplicated logic blocks between `bookings.ts` and `corporate.ts` (`r1` Stage 3, `r2` Stage 2, `r3` Stage 2).
- **`ARCH-*` (`0` findings)** and **`DIFF-*` (`0` findings):** Zero circular imports, zero boundary scatter, zero test skips, zero suppressions, and zero silent catch fallbacks triggered across all 48 stages.

## Honest Scope Limits

- **Constructed single-scenario erasable TypeScript scope (`EV2`):** `EV2` uses zero-dependency erasable TypeScript executed natively via `node --test` (`n = 3` replicates per cell). Replicates verify consistency on this 4-turn booking evolution chain, not generalization across arbitrary bundled frontend/backend TypeScript monorepos.
- **Model-dependent headroom:** `gpt-6.2-astra` and `gpt-6.2-sol` already passed `3/3` at `baseline` with `0` structural defects on `EV2`, so the aggregate pass-rate gain (`7/12 -> 12/12`) came from `gemini-4-neon` (`0/3 -> 3/3`, directly driven by 4 mid-evolution gate repairs) and `claude-opus-5-5` (`1/3 -> 3/3`, with `0` repair turns).
- **Zero-regression cost profile:** Unlike `EV1` (where `10/15` repairs fired on Python `legacy_flat_fee` propagation before Turn 4, adding `+18.7%` to `+43.8%` tokens), `EV2` triggered only `4` genuine mid-evolution repairs, keeping `gated-structural` token (`+1.2%`), wall-time (`+2.1%`), and Opus USD (`+2.2%`) overhead near baseline and below `core-rules-v0.2.0` on every resource axis.

## Reproduce and Verify

Validate records, SHA-256 hashes, and all three paired tracks locally (zero model or network calls):

```bash
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-ts-evolution-v0.8.0.json validate results/pilot-ts-evolution-v0.8.0/runs.jsonl
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-ts-evolution-v0.8.0.json --baseline baseline --treatment core-rules-v0.2.0 summarize results/pilot-ts-evolution-v0.8.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-ts-evolution-v0.8.0.json --baseline baseline --treatment gated-structural summarize results/pilot-ts-evolution-v0.8.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-ts-evolution-v0.8.0.json --baseline core-rules-v0.2.0 --treatment gated-structural summarize results/pilot-ts-evolution-v0.8.0/runs.jsonl --json
python3 -B scripts/check.py
```

Re-run the isolated 36-run 4-turn TypeScript evolution sweep from scratch:

```bash
python3 -B scripts/run_benchmark.py \
  --experiment-id pilot-ts-evolution-v0.8.0 \
  --cases EV2 \
  --models claude-opus-5-5 gpt-6.2-astra gpt-6.2-sol gemini-4-neon \
  --conditions baseline core-rules-v0.2.0 gated-structural \
  --replicates 3 \
  --seed 20261127 \
  --timeout 720 \
  --parallel-models \
  --max-workers 3 \
  --child-max-rss-mb 1536
```
