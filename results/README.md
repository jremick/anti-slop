# Results

**Public dataset status:** `results/` holds clean, `CODEX_HOME`-isolated, pre-hash-sanitized public benchmark datasets starting with the completed flagship `v0.6.0` benchmark:

- **[pilot-3way-v0.6.0/](pilot-3way-v0.6.0/README.md)** (`LOCAL-05`, completed 26 November 2026, reconciled against [benchmarks/pilot-v0.6.0.json](../benchmarks/pilot-v0.6.0.json) with `missing_pilot_coverage.complete = true`): `n = 3` replicates per cell across 4 focus models (`claude-opus-5-5`, `gpt-6.2-astra`, `gpt-6.2-sol`, `gemini-4-neon`) × 4 cases (`RW3` `urllib3`, `RW5` `sqlparse`, `RW6` `tomlkit`, `SE2` polyglot PR audit) × 3 conditions (`baseline`, `core-rules-v0.2.0`, `model-controls`) = **144 runs** (`142` completed, `2` `720s` timeouts kept in denominators).
  - **All 4 cases (`48`/arm):** **`31/48` (`64.6%`) -> `40/48` (`83.3%`) -> `43/48` (`89.6%`, `+12/-0` vs. baseline)**.
  - **Pinned OSS `origin: real_work` (`RW3`/`RW5`/`RW6`, `36`/arm):** **`22/36` (`61.1%`) -> `30/36` (`83.3%`) -> `34/36` (`94.4%`, `34/35` completed)**.
  - **Constructed (`SE2`, `12`/arm):** **`9/12` (`75.0%`) -> `10/12` (`83.3%`) -> `9/12` (`75.0%`)** (`claude-opus-5-5` failed `8/9` Stage 2 verification/pushback checks).
  - **Strict `wc -w` sensitivity (`48`/arm):** **`26/48` (`54.2%`) -> `37/48` (`77.1%`) -> `42/48` (`87.5%`)** (`17/36 -> 27/36 -> 34/36` on `real_work` OSS).
  - **Frozen-test tampering (`RW3`):** **`8/11` (`72.7%`)** baseline -> **`0/12` (`0.0%`)** `core-rules-v0.2.0` -> **`0/11` (`0.0%`)** `model-controls`.

## Why pre-public internal pilots (`v0.2.0`–`v0.5.0`) were archived

Before publishing this repository, four internal `n = 1` diagnostic pilots (`LOCAL-01` through `LOCAL-04`, 348 total runs) were executed locally to calibrate benchmark difficulty, test automated graders, and refine per-model deltas. A pre-public privacy and methodology audit uncovered two blockers in those early artifacts:

1. **Unisolated Codex sessions:** Pre-public Codex runs executed without an isolated `CODEX_HOME`, allowing Codex subjects (`gpt-6.2-sol`, plus one `gpt-6.2-astra` run) to read local `~/.codex/skills/` files into SHA-256-pinned trace logs—both a privacy leak and a benchmark-isolation defect.
2. **Unredacted host and temp paths:** Early trace logs and outputs retained local machine home paths and macOS temp directory paths inside SHA-256-pinned artifacts.

Rather than silently re-hashing historical artifacts or publishing contaminated Codex traces, all four pre-public diagnostic runs (`v0.2.0`–`v0.5.0`) were archived privately off the public repository. Their summary metrics, failures, cost regressions, and methodology caveats are disclosed transparently in [docs/evidence.md](../docs/evidence.md#local-measured-evaluations). Starting with `v0.6.0`, `scripts/run_benchmark.py` isolates `CODEX_HOME` per run and sanitizes host/workspace paths deterministically before computing SHA-256 artifact hashes so every published dataset is clean from birth.

## Recording a public experiment

For each completed public experiment, add `results/EXPERIMENT/runs.jsonl` with its frozen prompt/configuration snapshots, sanitized outputs, per-stage artifacts (`stage_artifacts` for multi-stage lineage cases), check evidence, blocker evidence/notes for any `failed`/`blocked`/`timeout` runs, and an experiment report. Keep unfinished collection in the ignored `runs-local/` directory.

## Experiment integrity invariants

- **Condition revision scope:** Shared conditions (`core-rules`, `core-rules-v0.1.0`, `core-rules-v0.2.0`, `gated`, or other non-model-scoped conditions) must keep one identical `condition_revision` SHA-256 across all models, cases and replicates within an `experiment_id` (scoped per `(experiment_id, condition)`). Per-model conditions (`baseline`, `model-controls`, and versioned variants starting with `baseline-`/`.`/`_` or `model-controls-`/`.`/`_`) are scoped per `(experiment_id, condition, model.provider, model.id)`, allowing distinct provider-native harness baselines or per-model delta overlays across models while forbidding drift within a model across cases or replicates.
- **Per-stage lineage pinning:** Completed runs for cases with `lineage_steps` must record and hash every stage `1..N` in `stage_artifacts`, with the final stage path and SHA-256 matching `output_artifact` and `artifact_hashes`.
- **Auditable blockers:** Unsuccessful attempts (`failed`, `blocked`, `timeout`) stay in denominators and must include non-empty `notes` and non-empty hashed `evidence` files.
- **Pilot coverage transparency:** `scripts/benchmark.py summarize` reconciles recorded matched pairs against the matching pilot manifest (`benchmarks/pilot*.json`) and reports any missing planned models, cases or pairs in `missing_pilot_coverage`. Never silently omit failing or unavailable models.

The report must identify the case and configuration versions, explain the scoring evidence, reconcile planned and recorded attempts, and state the limits of the sample. Put sensitive source material outside this repository unless its use and sharing are authorised. A checksum cannot replace access to evidence needed for review.

Actual model runs use `synthetic: false`, including actual runs on constructed diagnostic cases. Fabricated records used to demonstrate or test tooling use `synthetic: true` and cannot support performance claims. Unit-test fixtures are generated in temporary directories and are not published results.

Do not store an empty or invented successful run to make this directory look populated. Validation and unit-test results describe the tooling, not model effectiveness.
