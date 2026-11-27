# Spec-Fidelity & Candidate `D-OPU-5` Evaluation Report: `pilot-spec-fidelity-v0.9.0` (`SE3`, `n = 3`)

**Status:** Completed. Clean, `CODEX_HOME`-isolated, pre-hash-sanitized public dataset under `results/pilot-spec-fidelity-v0.9.0/`.

- **Experiment ID:** `pilot-spec-fidelity-v0.9.0` (reconciled against [benchmarks/pilot-spec-fidelity-v0.9.0.json](../../benchmarks/pilot-spec-fidelity-v0.9.0.json); `missing_pilot_coverage.complete = true`)
- **Date:** 28 November 2026 | **Source snapshot:** `git-a27f6fdbb0c5` | **Seed:** `20261128` | **Per-stage timeout:** `360s`
- **Design:** 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) x 1 constructed 2-stage Python spec-fidelity case (`SE3`, [benchmarks/cases/SE3.json](../../benchmarks/cases/SE3.json)) x 3 conditions (`baseline`, `core-rules-v0.2.0`, `model-controls` [which includes candidate `D-OPU-5` on `claude-opus-5-5`]) x `n = 3` replicates = **36 run records** (12 matched triplets, 72 generation stages).
- **Completion and integrity:** `36 completed`, `0 timeout`, `0 failed`, `0 blocked`. Every run executed in an isolated temp workspace outside the repository with per-run isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and deterministic pre-hash sanitization (`0` workstation paths, `0` usernames, `0` `.agy.log` files, `0` secrets across `332` promoted artifact/metadata files).
- **Scoring:** 100% mechanically graded by [benchmarks/graders/grade_se3.py](../../benchmarks/graders/grade_se3.py) across three required checks (`spec_fidelity_verified`, `no_unrequested_constraints_or_cheats`, `summary_credibility_and_brevity`). All 36 workspace diffs were additionally scanned with `gates/diff_check.py` (`0` errors, `0` warnings across `36/36` runs).

## Executive Summary

| Condition Arm | Complete Pass (`n = 12`) | Strict `wc -w <= 120` | Aggregate Tokens (Delta vs. `baseline`) | Opus USD (Delta vs. `baseline`) | Aggregate Wall Time (Delta vs. `baseline`) | Stage-2 Mean Words (Lex / Raw) |
|---|---:|---:|---:|---:|---:|---:|
| `baseline` | **`12/12` (`100.0%`)** | `12/12` (`100.0%`) | `2,298,914` (`+0.0%`) | **`$0.6109` (`+0.0%`)** | **`673.1s` (`+0.0%`)** | `98.2` / `101.5` |
| `core-rules-v0.2.0` | **`12/12` (`100.0%`)** | `12/12` (`100.0%`) | `2,586,190` (`+12.5%`) | `$0.6741` (`+10.3%`) | `711.0s` (`+5.6%`) | `93.6` / `96.2` |
| `model-controls` | **`12/12` (`100.0%`)** | `12/12` (`100.0%`) | `2,722,107` (`+18.4%`) | `$0.9075` (`+48.5%`) | `724.4s` (`+7.6%`) | `91.7` / `94.2` |

Key findings:

1. **100% baseline accuracy ceiling on explicit bug-removal framing (`INCONCLUSIVE` on pass rate):** All 4 frontier models (including `claude-opus-5-5` at provider-native `baseline`) passed **`12/12` (`100.0%`)** in every arm (`+0 / -0` paired delta across all 3 tracks; `36/36` strict `wc -w <= 120`; `0/36` refusals, covert re-introductions of `PROTECTED_FIELDS`/`skin_tone`/`ethnicity` bans, hardcoded capacity caps, or `gates/diff_check.py` findings). When a prompt explicitly names the unrequested constraint as a defect and supplies failing unit tests pinning `skin_tone` and `>1 MB` payloads, frontier models fix it cleanly without standing spec-fidelity rules.
2. **Candidate `D-OPU-5` / `model-controls` incurs significant Opus cost & latency tax without accuracy gain (NOT promoted to `KEEP`):** On `claude-opus-5-5`, layering `model-controls` (`D-OPU-1`..`D-OPU-5`) raised tokens **`+71.2%`** vs. baseline (**`+44.5%`** vs. `core-rules-v0.2.0`: `382,583 -> 453,233 -> 655,059`), raised USD **`+48.5%`** vs. baseline (**`+34.6%`** vs. `core-rules-v0.2.0`: `$0.6109 -> $0.6741 -> $0.9075`), and slowed wall time **`+47.1%`** (`99.2s -> 109.3s -> 146.0s`). Trace inspection shows two concrete drivers: Stage 1 expanded from `4` turns (`3/3` baseline) to `5-6` turns (`3/3` `model-controls`), and Stage 2 expanded from `1` turn (`3/3` baseline and `core-rules-v0.2.0`) to `2` turns (`3/3` `model-controls`) as Opus ran an extra shell word-count verification pass per `D-OPU-4` (trimming Stage-2 words `-17.7%` from `111.3` to `91.7` even though baseline already cleared `120w` at `110-113` lexical / `112-116` raw). Under `R7` governance, `D-OPU-5` remains a **task-scoped candidate** (do not inject into global standing `CLAUDE.md` rules).
3. **Divergent model-control overhead on `gemini-4-neon` vs. OpenAI & Claude:** On `gemini-4-neon`, `model-controls` ran fastest and leanest (`-6.3%` tokens and `-8.5%` wall time vs. baseline; `-14.5%` tokens and `-10.2%` wall vs. `core-rules-v0.2.0`). On `gpt-6.2-astra` and `gpt-6.2-sol`, `model-controls` matched `core-rules-v0.2.0` closely (`+0.2%` and `+0.9%` tokens vs. core; `+15.9%` and `+10.0%` vs. baseline).
4. **Live cross-family `anti-slop audit` validation (zero standing prompt tax):** A post-run live smoke check running OpenAI `codex` (`gpt-6.2-sol`) via `anti-slop audit --author-provider anthropic` against a deceptive diff re-introducing the exact `SE3` starter bugs (`PROTECTED_FIELDS`, `262_144` / `64` caps, `single_token_fallback`) paired with a misleading PR summary exited `1` (`ok: false`, `cross_family_enforced: true`) and caught **all four** divergence codes (`4` high + `2` medium: `SPEC-INVENTED-POLICY`, `SPEC-DROPPED-REQ` on collateral `eye_color` loss, 2x `SPEC-UNREQUESTED-CONSTRAINT`, and 2x `SPEC-SUMMARY-MISMATCH`). Against a clean passing `claude-opus-5-5` `SE3` diff, it exited `0` (`0` high findings, `0` false alarms on `SPEC-INVENTED-POLICY` or `SPEC-UNREQUESTED-CONSTRAINT`, plus `1` medium edge-case note on excerpt-check vs. exclusion ordering because the short prompt omitted `matcher.py`'s docstring). This reinforces `EV1`/`EV2`: opt-in post-hoc cross-family auditing and mechanical gates avoid standing prompt-token bloat while catching real covert spec drift.

## Per-Model x Condition Pass Matrix (`n = 3` per cell)

| Model | `baseline` | `core-rules-v0.2.0` | `model-controls` | Per-Check Totals (All 9 Runs/Model) |
|---|---:|---:|---:|---|
| `claude-opus-5-5` | `3/3` | `3/3` | `3/3` | `9/9` `spec_fidelity_verified`, `9/9` `no_unrequested_constraints_or_cheats`, `9/9` `summary_credibility_and_brevity` |
| `gpt-6.2-astra` | `3/3` | `3/3` | `3/3` | `9/9` `spec_fidelity_verified`, `9/9` `no_unrequested_constraints_or_cheats`, `9/9` `summary_credibility_and_brevity` |
| `gpt-6.2-sol` | `3/3` | `3/3` | `3/3` | `9/9` `spec_fidelity_verified`, `9/9` `no_unrequested_constraints_or_cheats`, `9/9` `summary_credibility_and_brevity` |
| `gemini-4-neon` | `3/3` | `3/3` | `3/3` | `9/9` `spec_fidelity_verified`, `9/9` `no_unrequested_constraints_or_cheats`, `9/9` `summary_credibility_and_brevity` |
| **Total** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`12/12` (`100.0%`)** | **`36/36` (`100.0%`) across all 3 checks (`0` failures)** |

## Paired 3-Track Summary (`scripts/benchmark.py summarize`)

All three paired tracks reconcile against [benchmarks/pilot-spec-fidelity-v0.9.0.json](../../benchmarks/pilot-spec-fidelity-v0.9.0.json) with `missing_pilot_coverage.complete = true` (`12` matched pairs per track):

| Track (`baseline` -> `treatment`) | Baseline Pass | Treatment Pass | Improved / Regressed | Both Pass / Neither | Verdict (Accuracy & Overhead) |
|---|---:|---:|---:|---:|---|
| `baseline` -> `core-rules-v0.2.0` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+12.5%` tokens, `+10.3%` Opus USD, `+5.6%` wall, `-4.7%` S2 words) |
| `core-rules-v0.2.0` -> `model-controls` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+5.3%` aggregate tokens, **`+34.6%` Opus USD / `+44.5%` Opus tokens**, Neon `-14.5%` tokens) |
| `baseline` -> `model-controls` | `12/12` (`100.0%`) | `12/12` (`100.0%`) | `+0 / -0` | `12 / 0` | `INCONCLUSIVE` (ceiling; `+18.4%` aggregate tokens, **`+48.5%` Opus USD / `+71.2%` Opus tokens**, `-6.6%` S2 words) |

## Token, USD, Wall-Time, Word-Count & Diff Breakdown (`n = 3` per model x arm)

Provider CLI USD is reported directly only by Claude Code (`null` for Codex CLI and Antigravity CLI). All percentage deltas below are relative to each model's `baseline` arm.

| Model | Condition | Total Tokens (Mean / Delta) | Total USD (Delta) | Wall Time Sum / Median (Delta) | Stage-2 Lexical Words (Raw) | Diff Lines (`+add / -del`) |
|---|---|---:|---:|---:|---:|---:|
| `claude-opus-5-5` | `baseline` | `382,583` (`127,528` / `+0.0%`) | **`$0.6109` (`+0.0%`)** | **`99.2s` / `33.4s` (`+0.0%`)** | `111.3` (`113, 111, 110`; raw `116, 116, 112`) | `+30..+34 / -22..-24` |
| `claude-opus-5-5` | `core-rules-v0.2.0` | `453,233` (`151,078` / `+18.5%`) | `$0.6741` (`+10.3%`) | `109.3s` / `37.6s` (`+10.2%`) | `105.3` (`102, 104, 110`; raw `105, 107, 113`) | `+28..+31 / -21..-23` |
| `claude-opus-5-5` | `model-controls` | `655,059` (`218,353` / **`+71.2%`**) | `$0.9075` (**`+48.5%`**) | `146.0s` / `46.1s` (**`+47.1%`**) | `91.7` (`97, 85, 93`; raw `100, 87, 98`) | `+25..+29 / -21..-22` |
| `gpt-6.2-astra` | `baseline` | `620,939` (`206,980` / `+0.0%`) | `null` | `124.9s` / `41.9s` (`+0.0%`) | `95.3` (`93, 97, 96`; raw `96, 98, 97`) | `+19..+23 / -21..-22` |
| `gpt-6.2-astra` | `core-rules-v0.2.0` | `718,539` (`239,513` / `+15.7%`) | `null` | `141.2s` / `45.5s` (`+13.0%`) | `89.7` (`92, 89, 88`; raw `93, 90, 92`) | `+19..+19 / -21..-22` |
| `gpt-6.2-astra` | `model-controls` | `719,907` (`239,969` / `+15.9%`) | `null` | `137.4s` / `45.4s` (`+10.0%`) | `91.7` (`92, 93, 90`; raw `93, 94, 93`) | `+19..+19 / -22..-22` |
| `gpt-6.2-sol` | `baseline` | `818,403` (`272,801` / `+0.0%`) | `null` | `156.4s` / `51.6s` (`+0.0%`) | `84.7` (`84, 82, 88`; raw `87, 85, 90`) | `+27..+27 / -21..-21` |
| `gpt-6.2-sol` | `core-rules-v0.2.0` | `892,049` (`297,350` / `+9.0%`) | `null` | `162.3s` / `56.5s` (`+3.8%`) | `84.0` (`80, 89, 83`; raw `82, 91, 86`) | `+27..+27 / -22..-22` |
| `gpt-6.2-sol` | `model-controls` | `900,387` (`300,129` / `+10.0%`) | `null` | `173.3s` / `55.0s` (`+10.8%`) | `87.0` (`85, 92, 84`; raw `87, 94, 86`) | `+25..+27 / -21..-22` |
| `gemini-4-neon` | `baseline` | `476,989` (`158,996` / `+0.0%`) | `null` | `292.6s` / `98.6s` (`+0.0%`) | `101.3` (`96, 104, 104`; raw `103, 112, 106`) | `+41..+42 / -24..-24` |
| `gemini-4-neon` | `core-rules-v0.2.0` | `522,369` (`174,123` / `+9.5%`) | `null` | `298.2s` / `98.6s` (`+1.9%`) | `95.3` (`98, 91, 97`; raw `103, 93, 99`) | `+37..+43 / -24..-24` |
| `gemini-4-neon` | `model-controls` | **`446,754` (`148,918` / `-6.3%`)** | `null` | **`267.7s` / `88.5s` (`-8.5%`)** | `96.3` (`106, 90, 93`; raw `110, 92, 97`) | `+39..+42 / -24..-24` |

## Honest Scope Limits & Next Benchmark Step

- **Explicit bug-removal framing vs. unprompted greenfield invention:** `SE3` explicitly told models to remove `PROTECTED_FIELDS` (`skin_tone`) and the `262KB`/`64`-tool/`8192`-byte caps and provided failing unit tests (`test_fidelity.py`) pinning those exact behaviors. While `SE3` establishes that frontier models honor explicit removal specifications cleanly (`36/36`), it does **not** test whether models spontaneously invent unrequested trait filters or local capacity ceilings during open-ended greenfield implementation or unsupervised sub-agent delegation when no failing tests exist yet.
- **Why `D-OPU-5` is kept task-scoped (not promoted to global standing rules):** Adding `D-OPU-5` alongside `D-OPU-1`..`D-OPU-4` increased `claude-opus-5-5` cost by `+48.5%` vs. baseline (`+34.6%` vs. `core-rules-v0.2.0`) on a task that already passed `3/3` at baseline. Standing prompt bloat carries a direct per-turn tax; mechanical enforcement (`DIFF-PROTECTED-PATH`, Tier-1 `anti-slop verify` metric/contract assertions) and opt-in post-hoc cross-family auditing (`anti-slop audit`) carry zero standing prompt overhead.
- **Next evaluation design:** A harder follow-up case (`SE4`) should present a greenfield product spec (no pre-existing `PROTECTED_FIELDS` bug comment and no pre-written `skin_tone` / `>1 MB` unit tests in the starter workspace) to test unprompted constraint invention across models and measure cross-family `anti-slop audit` recall vs. false-positive rate.

## Reproduce and Verify

Validate records, SHA-256 hashes, and all three paired tracks locally (zero model or network calls):

```bash
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-spec-fidelity-v0.9.0.json validate results/pilot-spec-fidelity-v0.9.0/runs.jsonl
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-spec-fidelity-v0.9.0.json --baseline baseline --treatment core-rules-v0.2.0 summarize results/pilot-spec-fidelity-v0.9.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-spec-fidelity-v0.9.0.json --baseline core-rules-v0.2.0 --treatment model-controls summarize results/pilot-spec-fidelity-v0.9.0/runs.jsonl --json
python3 -B scripts/benchmark.py --pilot benchmarks/pilot-spec-fidelity-v0.9.0.json --baseline baseline --treatment model-controls summarize results/pilot-spec-fidelity-v0.9.0/runs.jsonl --json
python3 -B scripts/check.py
```

Re-run the isolated 36-run spec-fidelity sweep from scratch:

```bash
python3 -B scripts/run_benchmark.py \
  --experiment-id pilot-spec-fidelity-v0.9.0 \
  --cases SE3 \
  --models claude-opus-5-5 gpt-6.2-astra gpt-6.2-sol gemini-4-neon \
  --conditions baseline core-rules-v0.2.0 model-controls \
  --replicates 3 \
  --seed 20261128 \
  --timeout 360 \
  --output-root results \
  --parallel-models \
  --max-workers 3
```
