# Comment-Hygiene Controlled Ablation Report: `pilot-comments-v0.7.0` (`CM1`, `n = 3`)

**Status:** Completed. Clean, `CODEX_HOME`-isolated, pre-hash-sanitized public dataset under `results/pilot-comments-v0.7.0/`.

- **Experiment ID:** `pilot-comments-v0.7.0` (reconciled against [benchmarks/pilot-comments-v0.7.0.json](../../benchmarks/pilot-comments-v0.7.0.json); `missing_pilot_coverage.complete = true`)
- **Date:** 27 November 2026 | **Source snapshot:** `git-2f06ef584068` | **Seed:** `20261127` | **Per-stage timeout:** `360s`
- **Design:** 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) x 1 constructed stdlib Python webhook case (`CM1`, 1 stage, [benchmarks/cases/CM1.json](../../benchmarks/cases/CM1.json)) x 3 identical-AST comment conditions (`no-comments`, `invariant-comments`, `comment-traps`) x `n = 3` replicates = **36 run records** (12 matched triplets, 36 generation stages). All three arms deliver the identical neutral system instruction so the only manipulated variable is the comment profile inside `webhooks.py`.
- **Completion and integrity:** `36 completed`, `0 timeout`, `0 failed`, `0 blocked`. Every run ran in an isolated temp workspace outside the repository with per-run isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` `.agy.log` files, `0` secrets across `149` promoted files).
- **Scoring:** 100% mechanically graded by [benchmarks/graders/grade_cm1.py](../../benchmarks/graders/grade_cm1.py) across four required checks (`feature_and_idempotency_verified`, `out_of_order_invariant_preserved`, `integer_cent_precision_preserved`, `commented_code_cleaned_and_readonly_intact`). Zero word caps and zero subjective LLM judging.

## Executive Summary

| Condition Arm | Complete Pass (`n = 12`) | Failed Checks | Aggregate Wall Time (Delta vs. `no-comments`) | Opus USD (Delta vs. `no-comments`) | Diff Comment Churn (`webhooks.py`) |
|---|---:|---:|---:|---:|---|
| `no-comments` (`0` comments, `90` lines) | **`12/12` (`100.0%`)** | `0/48` | `413.0s` (`+0.0%`) | `$0.4022` (`+0.0%`) | `+0 / -0` on `12/12` runs |
| `invariant-comments` (`3` `# INVARIANT:` lines, `93` lines) | **`12/12` (`100.0%`)** | `0/48` | **`394.3s` (`-4.5%`)** | **`$0.3953` (`-1.7%`)** | `+0 / -0` on `12/12` runs (all 3 preserved verbatim) |
| `comment-traps` (`28` comment lines incl. dead float blocks + stale ordering claim, `119` lines) | **`12/12` (`100.0%`)** | `0/48` | **`523.5s` (`+26.8%`; `+32.8%` vs. `invariant-comments`)** | **`$0.5288` (`+31.5%`; `+33.8%` vs. `invariant-comments`)** | `-28` comment lines scrubbed on `12/12` runs |

Key findings:

1. **Accuracy ceiling on explicit-invariant single-file prompt (`INCONCLUSIVE` on pass rate):** All 4 frontier models passed `12/12` (`100.0%`) across all three arms (`+0 / -0` paired acceptance delta on all three tracks). Because `CM1`'s prompt explicitly asks models to preserve event ordering and integer-cent math (`compute_fee_cents`) while deleting dead commented-out code blocks on a single 90-line module, frontier models rejected both the commented-out float traps and the misleading staleness prose comment.
2. **Consistent latency, cost, and churn tax from `comment-traps`:** Even at `100%` mechanical pass rate, `comment-traps` was the slowest arm on **4/4 models**, adding **`+26.8%`** aggregate wall time over `no-comments` (`+32.8%` over `invariant-comments`), **`+31.5%`** USD (`$0.4022 -> $0.5288`) and **`+27.5%`** tokens on `claude-opus-5-5`, and forcing `-28` comment-line deletions (total diff churn `+20..+36` / `-52..-74` lines) on every single run.
3. **Zero penalty from brief invariant comments:** The 3 single-line `# INVARIANT:` comments were preserved intact on `12/12` runs (`0` accidental removals), produced `-4.5%` lower aggregate wall time than `no-comments` (`-16.5%` wall time and `-9.3%` tokens on `gemini-4-neon`), and cost `-1.7%` less USD on `claude-opus-5-5`.

## Per-Model x Condition Pass Matrix (`n = 3` per cell)

| Model | `no-comments` | `invariant-comments` | `comment-traps` | All 4 Mechanical Checks |
|---|---:|---:|---:|---|
| `claude-opus-5-5` | `3/3` | `3/3` | `3/3` | `9/9` pass on all 4 checks |
| `gpt-6.2-astra` | `3/3` | `3/3` | `3/3` | `9/9` pass on all 4 checks |
| `gpt-6.2-sol` | `3/3` | `3/3` | `3/3` | `9/9` pass on all 4 checks |
| `gemini-4-neon` | `3/3` | `3/3` | `3/3` | `9/9` pass on all 4 checks |
| **Total** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`36/36` (`100.0%`)** |

Per-check totals by arm (out of 12 runs each):
- `feature_and_idempotency_verified`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `out_of_order_invariant_preserved`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `integer_cent_precision_preserved`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `commented_code_cleaned_and_readonly_intact`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`

## Paired 3-Track Summary (`scripts/benchmark.py summarize`)

All three paired tracks reconcile against [benchmarks/pilot-comments-v0.7.0.json](../../benchmarks/pilot-comments-v0.7.0.json) with `missing_pilot_coverage.complete = true` (`12` matched pairs per track):

| Track (`baseline` -> `treatment`) | Baseline Pass | Treatment Pass | Improved / Regressed | Both Pass / Neither | Verdict (Accuracy) |
|---|---:|---:|---:|---:|---|
| `no-comments` -> `invariant-comments` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `-4.5%` wall time, `-1.7%` Opus USD) |
| `no-comments` -> `comment-traps` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+26.8%` wall time, `+31.5%` Opus USD) |
| `invariant-comments` -> `comment-traps` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+32.8%` wall time, `+33.8%` Opus USD) |

## Token, USD, Wall-Time, and Diff-Churn Breakdown (`n = 3` per model x arm)

Provider CLI USD is reported directly only by Claude Code (`null` for Codex CLI and Antigravity CLI). All percentage deltas below are relative to each model's `no-comments` arm.

| Model | Condition | Total Tokens (Mean / Delta vs. `no-comments`) | Total USD (Delta vs. `no-comments`) | Wall Time Sum / Median (Delta vs. `no-comments`) | Diff Lines (`+added / -removed` range) |
|---|---|---:|---:|---:|---:|
| `claude-opus-5-5` | `no-comments` | `210,288` (`70,096` / `+0.0%`) | `$0.4022` (`+0.0%`) | `53.1s` / `17.1s` (`+0.0%`) | `+17..+26 / -0..-39` |
| `claude-opus-5-5` | `invariant-comments` | `232,288` (`77,429` / `+10.5%`) | `$0.3953` (`-1.7%`) | `53.2s` / `17.5s` (`+0.2%`) | `+17 / -0` (`3/3`) |
| `claude-opus-5-5` | `comment-traps` | `268,151` (`89,384` / `+27.5%`) | `$0.5288` (`+31.5%`) | `81.8s` / `26.8s` (`+54.0%`) | `+27 / -61` (`3/3`) |
| `gpt-6.2-astra` | `no-comments` | `242,497` (`80,832` / `+0.0%`) | `null` | `78.8s` / `26.1s` (`+0.0%`) | `+20 / -23` (`3/3`) |
| `gpt-6.2-astra` | `invariant-comments` | `222,747` (`74,249` / `-8.1%`) | `null` | `84.6s` / `31.9s` (`+7.4%`) | `+20 / -23` (`3/3`) |
| `gpt-6.2-astra` | `comment-traps` | `225,860` (`75,287` / `-6.9%`) | `null` | `88.4s` / `32.2s` (`+12.2%`) | `+30 / -74` (`3/3`) |
| `gpt-6.2-sol` | `no-comments` | `296,493` (`98,831` / `+0.0%`) | `null` | `120.3s` / `40.2s` (`+0.0%`) | `+20 / -23` (`3/3`) |
| `gpt-6.2-sol` | `invariant-comments` | `316,349` (`105,450` / `+6.7%`) | `null` | `122.2s` / `41.1s` (`+1.6%`) | `+20 / -23` (`3/3`) |
| `gpt-6.2-sol` | `comment-traps` | `278,802` (`92,934` / `-6.0%`) | `null` | `137.7s` / `45.7s` (`+14.5%`) | `+20..+21 / -52` |
| `gemini-4-neon` | `no-comments` | `338,388` (`112,796` / `+0.0%`) | `null` | `160.8s` / `55.7s` (`+0.0%`) | `+17 / -0` (`3/3`) |
| `gemini-4-neon` | `invariant-comments` | `306,765` (`102,255` / `-9.3%`) | `null` | `134.3s` / `45.3s` (`-16.5%`) | `+17 / -0` (`3/3`) |
| `gemini-4-neon` | `comment-traps` | `339,977` (`113,326` / `+0.5%`) | `null` | `215.6s` / `70.6s` (`+34.1%`) | `+33..+36 / -61` |

## Honest Scope Limits and Next-Iteration Guidance

- **Ceiling compression from explicit prompt guidance:** `CM1` is a single 90-line constructed stdlib Python module whose prompt explicitly mentions event ordering, exact cent math, and deleting commented-out code blocks. This result does not claim comment traps never cause correctness regressions; rather, it measures that frontier models clear explicit single-file comment traps at `100%` accuracy while still paying a `+26.8%` wall-time and `+31.5%` Opus USD cleanup tax.
- **Single scenario (`n = 3` replicates):** Replicates measure consistency across runs on one scenario, not independent task diversity.
- **Recommended `CM2` design:** Future comment-ablation cases should hide domain invariants across multiple interacting files without naming those invariants in the user prompt, testing whether brief `# INVARIANT:` comments prevent silent invariant regression and whether stale prose traps break accuracy when the model cannot rely on explicit prompt hints.

## Reproduce and Verify

Validate records, SHA-256 hashes, and all three paired tracks locally (zero model or network calls):

```bash
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.7.0.json validate results/pilot-comments-v0.7.0/runs.jsonl
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.7.0.json --baseline no-comments --treatment invariant-comments summarize results/pilot-comments-v0.7.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.7.0.json --baseline no-comments --treatment comment-traps summarize results/pilot-comments-v0.7.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.7.0.json --baseline invariant-comments --treatment comment-traps summarize results/pilot-comments-v0.7.0/runs.jsonl --json
python3 -B scripts/check.py
```

Re-run the isolated 36-run ablation sweep from scratch:

```bash
python3 -B scripts/run_benchmark.py \
  --experiment-id pilot-comments-v0.7.0 \
  --cases CM1 \
  --models claude-opus-5-5 gpt-6.2-astra gpt-6.2-sol gemini-4-neon \
  --conditions no-comments invariant-comments comment-traps \
  --replicates 3 \
  --seed 20261127 \
  --timeout 360 \
  --parallel-models \
  --max-workers 3 \
  --child-max-rss-mb 1536
```
