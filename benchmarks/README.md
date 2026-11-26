# Benchmark handoff

**Status: flagship clean public `v0.6.0` benchmark (`n = 3`, 144 runs) completed and published under `results/pilot-3way-v0.6.0/`; pre-public internal diagnostics (`LOCAL-01`–`LOCAL-04`, 348 runs) archived off the public tree.** During pre-launch auditing, we found that pre-public Codex runs lacked `CODEX_HOME` isolation and retained local workstation/temp paths in SHA-256-pinned traces. Rather than publishing contaminated Codex traces or mutating historical hashes, `v0.2.0`–`v0.5.0` were archived privately (see [results/README.md](../results/README.md) and [docs/evidence.md](../docs/evidence.md#local-measured-evaluations)), `scripts/run_benchmark.py` was hardened with per-run `CODEX_HOME`/`HOME` isolation and deterministic pre-hash path sanitization, and the clean `n = 3` `pilot-3way-v0.6.0` dataset (`LOCAL-05`) was published in [results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md). Python 3.11+ and the standard library are sufficient; the validation tooling makes no model or network calls.

## Scope

The benchmark suite contains **25 versioned cases** in `benchmarks/cases/`, **12 automated stdlib graders** in `benchmarks/graders/` (see [graders/README.md](graders/README.md)), and the multi-turn compounding-quality & AST mutation engine in [evolution.py](evolution.py):

- **19 `origin: constructed` cases:** six untouched `v0.1.0` starter cases (`W1`–`C2`), four `v0.2.0` production-realism cases (`B1`, `S1`, `T1`, `P1`), six harder `v0.3.0` multi-file/multi-document probes (`M1`, `M2`, `B2`, `D1`, `S2`, `W3`), two `v0.5.0` engineering-credibility probes (`SE1`, `SE2`), and the `v0.7.0` 4-turn feature-evolution case (`EV1`, zero word caps; grades functional correctness, AST mutation kill rate, duplicate code growth, dead/legacy removal, sprawl, and silent failures).
- **6 `origin: real_work` pinned public OSS cases (`RW1`–`RW6`):** `RW1` (`python-poetry/tomlkit`), `RW2` (`Python-Markdown/markdown`), `RW3` (`urllib3/urllib3`), `RW4` (`pypa/packaging`), `RW5` (`andialbrecht/sqlparse`), and `RW6` (`python-poetry/tomlkit` release audit), each with pinned upstream commit provenance and preserved upstream licenses under `benchmarks/sources/`.

Pilot manifests ([pilot.json](pilot.json), [pilot-v0.3.0.json](pilot-v0.3.0.json), [pilot-v0.4.0.json](pilot-v0.4.0.json), [pilot-v0.5.0.json](pilot-v0.5.0.json), the completed clean `n = 3` public release manifest [pilot-v0.6.0.json](pilot-v0.6.0.json), and the planned multi-turn compounding-quality manifest [pilot-evolution-v0.7.0.json](pilot-evolution-v0.7.0.json)) define planned experiment rosters (cases, versions, stage counts, models, conditions, replicates and comparison tracks). Single-stage cases produce one generation stage; multi-stage lineage cases (such as `W2`, `R2`, `C2`, `M1`, `M2`, `B2`, `RW1`–`RW6`, `SE1`, `SE2`, `EV1`) run a multi-stage chain and produce one final run record covering all stages. Repeated runs, models and chain stages are not additional independent task scenarios.

Constructed (`origin: constructed`) and pinned real-work (`origin: real_work`) suites are distinct populations and must be summarized separately. A genuine provider run on either is measured evidence (`synthetic: false`). Run-level `synthetic: true` instead means fabricated or demonstration data and is excluded from measured summaries. Six pinned OSS tasks across five Python repositories remain an initial real-work slice, not a representative sample of all production engineering.

## Execute without contaminating the comparison

1. Freeze the pilot roster, exact case/source versions, tools, budgets, model settings and native harness versions before execution. Verify the requested provider model is available; do not silently substitute another model.
2. Freeze condition snapshots as immutable local files and name each condition using a lowercase identifier matching `^[a-z0-9][a-z0-9._-]{1,63}$` (for example `baseline`, `core-rules`, `core-rules-v0.1.0`, `core-rules-v0.2.0`, `model-controls`, `gated`):
   - **Shared conditions (`(experiment_id, condition)` scope):** Shared treatments such as `core-rules`, `core-rules-v0.1.0`, `core-rules-v0.2.0`, and `gated` must keep **one identical `condition_revision` SHA-256** across all models, cases and replicates within an `experiment_id`.
   - **Per-model conditions (`(experiment_id, condition, model.provider, model.id)` scope):** `baseline` and `model-controls` (plus versioned variants prefixed with `baseline-`/`.`/`_` or `model-controls-`/`.`/`_`) are scoped per model so each model can cryptographically pin its own provider-native harness baseline or per-model delta overlay, while every case and replicate for that same model within the `experiment_id` must still keep an identical `condition_revision`.
3. Start each condition in a fresh session and clean workspace **outside this repository's instruction scope** with an isolated `CODEX_HOME` (carrying only auth credentials and zero personal skills, rules, hooks, or configs). Copy only the required case inputs, preserving their relative paths. Do not expose this repository's `AGENTS.md`, rule files, local user skills, or previous-condition outputs. Supply candidate rules or per-model deltas explicitly only in the corresponding condition. Existing mandatory platform instructions remain in both conditions; record their configuration where exposed.
4. Keep tools, source snapshots, budgets and reasoning settings matched within each model. Randomise execution order. Give the model the task prompt and inputs; retain grading criteria for the evaluator.
5. For a multi-stage lineage chain, `lineage_steps` contains the complete ordered prompts and `validate_case()` enforces `lineage_steps[0] == prompt`: execute stage 1 once. Pass raw outputs into the next stage in the same chain, without human repair or feedback from grading. Preserve every stage's inputs, outputs and sanitized execution logs (`scripts/run_benchmark.py` scrubs host home paths, local usernames, and temp workspace paths deterministically before computing SHA-256 hashes).

Never drop an unsuccessful attempt. Record `failed`, `blocked` or `timeout` as applicable, including known cost, observed review/repair time, non-empty `notes`, and non-empty project-relative `evidence` files (hashed in `artifact_hashes`) documenting unavailable models or execution blockers.

## Create and review records

[run-record.example.json](run-record.example.json) lists the required fields for `W1`. It is a validated synthetic template (`synthetic: true`, `status: blocked`), not a measured result. Copy and populate it after an attempt; replace its placeholder fields, `condition_source`, `evidence` and `notes` with frozen experiment artifacts before saving a JSONL result under `results/`.

Set `synthetic: false` only for genuinely executed attempts; retain `true` for fabricated demonstrations.

Use a unique `run_id`, fixed `experiment_id`, case ID/version, positive `replicate`, valid condition name, model provider/ID/version/reasoning and all six environment fields. `source_snapshot_id` must stay fixed for an experiment/case across both conditions and replicates. Record unavailable version metadata honestly and disclose the resulting reproducibility limit.

Record every acceptance-check ID as `pass`, `fail` or `not_run`. Pass/fail requires project-relative, nonempty evidence files. Describe observed material defects explicitly. A completed run needs an `output_artifact`. Review evidence against the criteria; a model's claim that it succeeded is insufficient. Use blinded review where practical.

For any **completed** run targeting a case with `lineage_steps`, `stage_artifacts` is required: an ordered array of `{"stage": int, "path": str, "sha256": str}` with `len(stage_artifacts) == len(lineage_steps)`, contiguous stage indices `1..N`, valid lowercase SHA-256 digests matching the local files on disk, and the final stage's `path` and `sha256` matching `output_artifact` and `artifact_hashes[output_artifact]`. Single-stage cases do not require `stage_artifacts`. Non-completed runs (`failed`, `blocked`, `timeout`) may omit `stage_artifacts` or record completed prefix stages `1..k`.

For any **failed**, **blocked** or **timeout** run, top-level `notes` (non-empty string) and top-level `evidence` (non-empty list of project-relative nonempty files, covered by `artifact_hashes`) are required so execution failures remain auditable.

Metrics require `cost_usd`, `review_minutes`, `repair_minutes` and `total_tokens`; use `null` for unknown values. Set `repair_capped: true` when repair measurement stopped at a cap. Record the cap in the review evidence. A cap is a censored observation, not time to successful completion. Non-finite JSON constants (`NaN`, `Infinity`, `-Infinity`) are rejected in both JSON cases and JSONL run logs.

Sanitize and freeze evidence before hashing. From the repository root, the public helpers are:

```python
import json
from pathlib import Path
from scripts.benchmark import canonical_json_sha256, sha256

case = json.loads(Path("benchmarks/cases/W1.json").read_text())
# record is your populated run object, not the unchanged example template.
record["case_revision"] = canonical_json_sha256(case)
record["condition_revision"] = sha256(Path(record["condition_source"]))
paths = {p for check in record["checks"] for p in check["evidence"]}
paths.update(record.get("evidence") or [])
if record["output_artifact"] is not None:
    paths.add(record["output_artifact"])
record["artifact_hashes"] = {p: sha256(Path(p)) for p in sorted(paths)}
if "stage_artifacts" in record and record["stage_artifacts"] is not None:
    for entry in record["stage_artifacts"]:
        entry["sha256"] = sha256(Path(entry["path"]))
```

Save one populated object per line in a JSONL file. Keep immutable condition snapshots, per-stage outputs, output artifacts and evidence inside the project. Local case sources with a declared SHA-256 are also checked. Changing a case or artifact invalidates its earlier digest; preserve historical evidence rather than rewriting it.

## Validate and summarise

```bash
python3 -B scripts/benchmark.py validate --pilot benchmarks/pilot.json --run-record benchmarks/run-record.example.json
python3 -B scripts/benchmark.py validate --pilot benchmarks/pilot-v0.6.0.json results/EXPERIMENT/runs.jsonl
python3 -B scripts/benchmark.py summarize --pilot benchmarks/pilot-v0.6.0.json results/EXPERIMENT/runs.jsonl --json
python3 -B scripts/benchmark.py summarize results/EXPERIMENT/runs.jsonl --baseline core-rules-v0.1.0 --treatment core-rules-v0.2.0 --json
python3 -B scripts/benchmark.py summarize results/EXPERIMENT/runs.jsonl --baseline core-rules-v0.2.0 --treatment model-controls --json
python3 -B scripts/check.py
```

The CLI supports `--root`, `--cases`, `--pilot` / `--no-pilot`, `--run-record`, `--baseline` (default `baseline`), `--treatment` (default `core-rules`), `--json` and explicitly labelled `--synthetic-only` summaries. It rejects incompatible, drifted or unmatched comparisons. Acceptance requires completion, every required check passing and no recorded material defect; partial credit cannot become success.

`scripts/check.py` validates all 25 cases in `benchmarks/cases/`, reconciles all `benchmarks/pilot*.json` manifests against those cases, validates `benchmarks/run-record.example.json` via `validate_run()`, validates and summarizes any committed `results/**/*.jsonl` logs against their matching pilot manifest, and runs all `tests/test_*.py` suites.

Summaries compute acceptance rates over **recorded matched runs** and include explicit `missing_pilot_coverage` metadata whenever a pilot manifest is reconciled, listing any missing planned models, missing cases, incomplete `(model, case)` pairs, or unscheduled extra models/cases so dropped models are never hidden silently. Failures remain in denominators; missing metrics remain unknown. Observed timing includes review and repair, with censoring disclosed. Validation checks structure and file integrity, not evidence adequacy. Repository checks do not execute the benchmark.
