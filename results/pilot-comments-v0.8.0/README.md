# Multi-File Comment-Hygiene Controlled Ablation Report: `pilot-comments-v0.8.0` (`CM2`, `n = 3`)

**Status:** Completed. Clean, `CODEX_HOME`-isolated, pre-hash-sanitized public dataset under `results/pilot-comments-v0.8.0/`.

- **Experiment ID:** `pilot-comments-v0.8.0` (reconciled against [benchmarks/pilot-comments-v0.8.0.json](../../benchmarks/pilot-comments-v0.8.0.json); `missing_pilot_coverage.complete = true`)
- **Date:** 27 November 2026 | **Source snapshot:** `git-37c85c41e2ac` | **Seed:** `20261127` | **Per-stage timeout:** `360s`
- **Design:** 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) x 1 constructed 6-module stdlib Python job-queue case (`CM2`, 1 stage, [benchmarks/cases/CM2.json](../../benchmarks/cases/CM2.json)) x 3 identical-AST comment conditions (`no-comments`, `invariant-comments`, `comment-traps`) x `n = 3` replicates = **36 run records** (12 matched triplets, 36 generation stages). All three arms deliver the identical neutral system instruction and omit the two subtle cross-file invariants (`epoch` dedupe fence and `persist_result` before `queue.ack` crash durability) from the user prompt so the only manipulated variable is the comment profile across the 6 production modules (`models.py`, `storage.py`, `dedupe.py`, `retry.py`, `worker.py`, `api.py`).
- **Completion and integrity:** `36 completed`, `0 timeout`, `0 failed`, `0 blocked`. Every run executed in an isolated temp workspace outside the repository with per-run isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` `.agy.log` files, `0` secrets across `149` promoted artifact/metadata files).
- **Scoring:** 100% mechanically graded by [benchmarks/graders/grade_cm2.py](../../benchmarks/graders/grade_cm2.py) across four required checks (`dead_letter_replay_feature`, `cross_file_epoch_dedupe_invariant`, `persist_before_ack_crash_invariant`, `tests_and_comment_cleanup`). Zero word caps and zero subjective LLM judging.

## Executive Summary

| Condition Arm | Complete Pass (`n = 12`) | Failed Checks | Aggregate Wall Time (Delta vs. `no-comments`) | Opus USD (Delta vs. `no-comments`) | Diff Comment Churn (6 Prod Modules) |
|---|---:|---:|---:|---:|---|
| `no-comments` (`0` comments, `345` lines) | **`12/12` (`100.0%`)** | `0/48` | `1,354.6s` (`+0.0%`) | `$0.9569` (`+0.0%`) | `-0 / +0..+2` comments |
| `invariant-comments` (`4` `# INVARIANT:` lines, `349` lines) | **`12/12` (`100.0%`)** | `0/48` | **`1,262.8s` (`-6.8%`; `-8.4%` vs. `comment-traps`)** | **`$0.9344` (`-2.4%`; `-16.1%` vs. `comment-traps`)** | `9/12` preserved all `4` `# INVARIANT:` notes (`3/3` Opus, Astra, Neon); `gpt-6.2-sol` stripped all `4` on `3/3` runs |
| `comment-traps` (`67` comment lines incl. dead buggy blocks + stale misleading claims, `412` lines) | **`12/12` (`100.0%`)** | `0/48` | **`1,378.5s` (`+1.8%`; `+9.2%` vs. `invariant-comments`)** | **`$1.1135` (`+16.4%`; `+19.2%` vs. `invariant-comments`)** | `-20..-67` comment lines scrubbed (`-67` on `9/12` runs; total diff `-50..-132` lines) |

Key findings:

1. **Accuracy ceiling persists across 6 modules even with unstated cross-file invariants (`INCONCLUSIVE` on pass rate):** All 4 frontier models passed `12/12` (`100.0%`) across all three arms (`+0 / -0` paired acceptance delta on all three tracks; `0/48` failed checks per arm). Inspecting the executable code across `dedupe.py`, `storage.py`, and `worker.py` (`next_replay_epoch`, `_tenant_epoch_fence`, and `persist_result` preceding `queue.ack`) was sufficient for frontier models to reject the stale "Temporary v1 workaround; safe to simplify by..." trap comments and commented-out defective blocks without explicit prompt hints.
2. **Brief `# INVARIANT:` notes remain the fastest and lowest-cost arm:** Consistent with `CM1`, `invariant-comments` delivered the lowest aggregate wall time (`1,262.8s`: `-6.8%` vs. `no-comments`, `-8.4%` vs. `comment-traps`) and lowest Claude Opus USD (`$0.9344`: `-2.4%` vs. `no-comments`, `-16.1%` vs. `comment-traps`). It was the fastest arm on 3 of 4 models (`claude-opus-5-5` `-8.8%`, `gpt-6.2-astra` `-24.6%`, `gemini-4-neon` `-5.1%`; `gpt-6.2-sol` `+2.8%`).
3. **`comment-traps` imposes measurable USD, latency, and diff-churn tax:** Even at `100%` mechanical accuracy, `comment-traps` increased Claude Opus USD by **`+16.4%`** vs. `no-comments` (**`+19.2%`** vs. `invariant-comments`), slowed `claude-opus-5-5` (`+9.9%` vs. `no-comments`, `+20.5%` vs. `invariant-comments`) and `gpt-6.2-sol` (`+19.3%` vs. `no-comments`, `+16.0%` vs. `invariant-comments`), and forced `-20` to `-67` comment-line deletions per run (`-67` on `9/12` runs, `-55` and `-62` on two Sol runs, and `-20` on `claude-opus-5-5 r3` where Opus deleted the trap blocks while leaving benign single-line restatements).
4. **Model-specific `# INVARIANT:` preservation gap on `gpt-6.2-sol`:** Whereas `claude-opus-5-5` (`3/3`), `gpt-6.2-astra` (`3/3`), and `gemini-4-neon` (`3/3`) kept all 4 `# INVARIANT:` comments verbatim, `gpt-6.2-sol` removed all 4 `# INVARIANT:` comments on `3/3` replicates while refactoring (rewriting one into a plain comment in `worker.py` and dropping the other three). The code invariants stayed intact at runtime, but silent stripping of why-comments erodes future maintenance signal.

## Per-Model x Condition Pass Matrix (`n = 3` per cell)

| Model | `no-comments` | `invariant-comments` | `comment-traps` | Per-Invariant Breakdown (All 9 Runs/Model) |
|---|---:|---:|---:|---|
| `claude-opus-5-5` | `3/3` | `3/3` | `3/3` | `9/9` replay, `9/9` epoch-dedupe, `9/9` persist-before-ack, `9/9` cleanup |
| `gpt-6.2-astra` | `3/3` | `3/3` | `3/3` | `9/9` replay, `9/9` epoch-dedupe, `9/9` persist-before-ack, `9/9` cleanup |
| `gpt-6.2-sol` | `3/3` | `3/3` | `3/3` | `9/9` replay, `9/9` epoch-dedupe, `9/9` persist-before-ack, `9/9` cleanup |
| `gemini-4-neon` | `3/3` | `3/3` | `3/3` | `9/9` replay, `9/9` epoch-dedupe, `9/9` persist-before-ack, `9/9` cleanup |
| **Total** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`36/36` (`100.0%`) across all 4 checks (`0` failures)** |

Per-check totals by arm (out of 12 runs each):
- `dead_letter_replay_feature`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `cross_file_epoch_dedupe_invariant`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `persist_before_ack_crash_invariant`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`
- `tests_and_comment_cleanup`: `12/12` `no-comments`, `12/12` `invariant-comments`, `12/12` `comment-traps`

## Paired 3-Track Summary (`scripts/benchmark.py summarize`)

All three paired tracks reconcile against [benchmarks/pilot-comments-v0.8.0.json](../../benchmarks/pilot-comments-v0.8.0.json) with `missing_pilot_coverage.complete = true` (`12` matched pairs per track):

| Track (`baseline` -> `treatment`) | Baseline Pass | Treatment Pass | Improved / Regressed | Both Pass / Neither | Verdict (Accuracy) |
|---|---:|---:|---:|---:|---|
| `no-comments` -> `invariant-comments` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `-6.8%` wall time, `-2.4%` Opus USD, `-1.9%` tokens) |
| `no-comments` -> `comment-traps` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+1.8%` wall time, `+16.4%` Opus USD, `-20..-67` comment churn) |
| `invariant-comments` -> `comment-traps` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+9.2%` wall time, `+19.2%` Opus USD, `-20..-67` comment churn) |

## Token, USD, Wall-Time, and Diff-Churn Breakdown (`n = 3` per model x arm)

Provider CLI USD is reported directly only by Claude Code (`null` for Codex CLI and Antigravity CLI). All percentage deltas below are relative to each model's `no-comments` arm.

| Model | Condition | Total Tokens (Mean / Delta vs. `no-comments`) | Total USD (Delta vs. `no-comments`) | Wall Time Sum / Median (Delta vs. `no-comments`) | Diff Lines (`+added / -removed` range) |
|---|---|---:|---:|---:|---:|
| `claude-opus-5-5` | `no-comments` | `490,957` (`163,652` / `+0.0%`) | `$0.9569` (`+0.0%`) | `170.5s` / `57.6s` (`+0.0%`) | `+61..+87 / -40..-62` |
| `claude-opus-5-5` | `invariant-comments` | `460,939` (`153,646` / `-6.1%`) | **`$0.9344` (`-2.4%`)** | **`155.6s` / `51.0s` (`-8.8%`)** | `+46..+81 / -30..-46` |
| `claude-opus-5-5` | `comment-traps` | `457,857` (`152,619` / `-6.7%`) | `$1.1135` (`+16.4%`) | `187.4s` / `65.3s` (`+9.9%`) | `+52..+139 / -50..-132` |
| `gpt-6.2-astra` | `no-comments` | `366,117` (`122,039` / `+0.0%`) | `null` | `205.2s` / `72.6s` (`+0.0%`) | `+39..+45 / -25..-27` |
| `gpt-6.2-astra` | `invariant-comments` | **`294,153` (`98,051` / `-19.7%`)** | `null` | **`154.7s` / `48.1s` (`-24.6%`)** | `+39..+45 / -25..-27` |
| `gpt-6.2-astra` | `comment-traps` | `302,726` (`100,909` / `-17.3%`) | `null` | `158.1s` / `52.0s` (`-23.0%`) | `+38..+41 / -90..-100` |
| `gpt-6.2-sol` | `no-comments` | `517,130` (`172,377` / `+0.0%`) | `null` | `296.7s` / `99.8s` (`+0.0%`) | `+72..+83 / -43..-45` |
| `gpt-6.2-sol` | `invariant-comments` | `596,777` (`198,926` / `+15.4%`) | `null` | `305.1s` / `101.5s` (`+2.8%`) | `+67..+75 / -46..-48` |
| `gpt-6.2-sol` | `comment-traps` | `561,248` (`187,083` / `+8.5%`) | `null` | `353.9s` / `118.6s` (`+19.3%`) | `+71..+109 / -101..-108` |
| `gemini-4-neon` | `no-comments` | `838,474` (`279,491` / `+0.0%`) | `null` | `682.2s` / `214.1s` (`+0.0%`) | `+74..+94 / -44..-52` |
| `gemini-4-neon` | `invariant-comments` | `819,159` (`273,053` / `-2.3%`) | `null` | **`647.4s` / `226.1s` (`-5.1%`)** | `+60..+79 / -34..-45` |
| `gemini-4-neon` | `comment-traps` | `814,006` (`271,335` / `-2.9%`) | `null` | `679.1s` / `223.7s` (`-0.5%`) | `+90..+107 / -104..-111` |

## Honest Scope Limits

- **Small-package code transparency still gives frontier models enough signal to clear traps:** Although `CM2` expands `CM1` from 1 module (90 lines) to 6 modules (345-412 lines) and withholds both invariants from the prompt, all 6 modules fit comfortably inside a single context window, allowing frontier models to verify control flow directly against the code and reject misleading comments.
- **Constructed single-scenario scope (`n = 3` replicates):** Replicates establish run-to-run consistency on one 6-module Python package rather than generalization across large legacy repositories where external side effects (e.g., database triggers, wire protocols, or undocumented downstream consumers) cannot be inferred from local source alone.
- **No accuracy claim is overstated:** Both `CM1` and `CM2` record `12/12` accuracy across all three arms; the empirically demonstrated benefits of `invariant-comments` over `no-comments` and `comment-traps` in these two controlled pilots are lower wall time (`-4.5%` on `CM1`, `-6.8%` on `CM2`), lower Opus USD (`-1.7%` on `CM1`, `-2.4%` on `CM2` vs. `no-comments`; `-16.1%` to `-25.2%` vs. `comment-traps`), and zero dead-comment churn.

## Reproduce and Verify

Validate records, SHA-256 hashes, and all three paired tracks locally (zero model or network calls):

```bash
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.8.0.json validate results/pilot-comments-v0.8.0/runs.jsonl
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.8.0.json --baseline no-comments --treatment invariant-comments summarize results/pilot-comments-v0.8.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.8.0.json --baseline no-comments --treatment comment-traps summarize results/pilot-comments-v0.8.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-comments-v0.8.0.json --baseline invariant-comments --treatment comment-traps summarize results/pilot-comments-v0.8.0/runs.jsonl --json
python3 -B scripts/check.py
```

Re-run the isolated 36-run multi-file ablation sweep from scratch:

```bash
python3 -B scripts/run_benchmark.py \
  --experiment-id pilot-comments-v0.8.0 \
  --cases CM2 \
  --models claude-opus-5-5 gpt-6.2-astra gpt-6.2-sol gemini-4-neon \
  --conditions no-comments invariant-comments comment-traps \
  --replicates 3 \
  --seed 20261127 \
  --timeout 360 \
  --parallel-models \
  --max-workers 3 \
  --child-max-rss-mb 1536
```
