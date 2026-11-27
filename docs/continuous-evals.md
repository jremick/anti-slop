# Continuous Evals, Self-Learning, and Model Onboarding

Static rule sets go stale as codebases change and new frontier models drop. Rules that once prevented real regressions can become dead weight, while newly emerging failure modes slip past older checks.

This guide defines the repeatable operating loop that keeps `anti-slop` grounded in evidence: local telemetry and git mining, automated 3-way verification, objective multi-turn keep/drop decisions, repeatable onboarding for new models, and explicit rule retirement. Keep this document outside standing prompts (`standard/core.md` remains pinned at `<= 300` words).

## 1. Continuous Self-Learning and Autoresearch Ratchet (Human-Approved)

The self-learning loop in `gates/learn.py` follows a strict ratchet: **mine -> capture -> propose -> verify -> human approve -> enforce -> retire**. Every candidate rule must prove it catches a real failure without breaking valid code or bloating prompts, and no agent may self-approve a rule.

```mermaid
flowchart LR
    M["1. Read-Only Mine (telemetry + git log)"] --> C["2. Capture Bad + Valid Pair"]
    C --> P["3. Propose Smallest Layer (det. -> example -> prompt)"]
    P --> V["4. Auto-Verify (bad + neighbour + repo scan + EV1)"]
    V --> H{"5. Human Approval (SHA-256 bound)"}
    H -->|Approved| E["6. Enforce in Hooks, Review, CI"]
    H -->|Rejected| D["Discard / Keep Regression Case"]
    E --> R["7. Stale Watch -> Retire (Keep ID Gap)"]
```

### Step A: Read-Only Continuous Mining (`anti-slop learn mine`)

Run read-only pattern mining periodically or on demand:

```bash
python3 -B gates/learn.py mine --repo-root . --commits 30 --stale-days 60
# Or via the unified CLI in JSON mode for agent workflows:
anti-slop learn mine --json
```

`mine` combines two read-only local signals without modifying `<repo>/.anti-slop/learned/rules.json`:

1. **Opt-in local hook and review telemetry (`<repo>/.anti-slop/telemetry.jsonl`):** Records only timestamps, event types (`stop_hook`, `pretool_hook`, `review`), harness names, `blocked` booleans, rule codes, and file extensions (zero source snippets, secrets, or workstation paths; ignored via `.gitignore`). `mine` skips malformed lines safely, aggregates rule counts, flags recurring patterns (`count >= 2`), and checks active approved `L-*` rules for zero-hit staleness past `--stale-days`.
2. **Recent non-merge git history (`--commits N`):** Scans newly added lines across the last `N` non-merge commits against all uninstalled deterministic `OPT-*` rules in `library/catalog.json` to recommend relevant optional packs with exact commit counts and sample SHAs. It also scans recent commit diffs for recurring `DIFF-*` and `STRUCT-*` patterns plus `fix:` / `revert` churn signals.

### Step B: Narrowest-Layer Escalation and 3-Way Verification

Before asking a human reviewer to approve any candidate surfaced by `mine` or a code review:

1. **Check the curated library first:** Inspect and dry-run verify a matching optional pack before inventing a custom regex (`anti-slop learn library show <pack>` and `anti-slop learn library enable <pack> --by <human> --dry-run`).
2. **Escalate from narrowest to broadest layer:** Prefer `deterministic_check` (zero standing prompt tokens) first, `codebase_example` second, and a scoped `<= 45`-word `prompt_rule` last (requiring explicit `--why-not-deterministic` and `--retirement-trigger`).
3. **Pass 3-way automated verification (`anti-slop learn verify <id>`):** Every deterministic candidate must (a) catch its captured `bad_example`, (b) leave its `valid_neighbouring_case` untouched, and (c) pass an existing-repository false-positive scan (`repo_scan_hits <= max_repo_hits`). Any candidate that fails is fixed or discarded automatically before reaching a human.
4. **Prove prompt-layer rules empirically:** Any candidate that cannot be enforced deterministically must prove net quality gain via paired multi-turn `EV1`/`EV2` comparison (`benchmarks/evolution.py compare` returning `KEEP`) rather than intuition.
5. **Require explicit human approval:** Enforcement activates only after a human runs `anti-slop learn approve <id> --by <name>`. Approval binds a SHA-256 hash of the verified proposal; editing a rule after approval fails closed until re-verified and re-approved.

## 2. Onboarding New Frontier Models

Whenever a new frontier model releases, measure it in isolation before writing a single model-specific rule. Do not assume an older model's failure modes still exist, and do not copy deltas from a previous generation without testing baseline first.

### Step-by-Step Protocol

1. **Generate the exact isolated run plan and stage budget:**

```bash
python3 -B scripts/eval_cycle.py plan \
  --model <provider>:<model_id> \
  --suites all \
  --replicates 3
```

Use `--suites evolution`, `--suites ts-evolution`, `--suites comments`, `--suites comments-multifile`, or `--suites integrity` to stage suites incrementally, or `--json` for automated orchestration.

2. **Register the model adapter cleanly:** Add the model entry to `DEFAULT_MODELS` and `FROZEN_MODEL_VERSIONS` in `scripts/run_benchmark.py`. Keep `gates/model_deltas.json` untouched on the first pass so `baseline` and `core-rules-v0.2.0` are measured without speculative model deltas.
3. **Dry-run and verify isolation:** Run each planned `--dry-run` command first to verify condition hashes, stage counts, and model routing with zero API spend. Confirm every run executes in a fresh temp directory outside the repository with isolated `CODEX_HOME`/`HOME`, `ANTI_SLOP_BENCHMARK_SUBJECT=1`, and pre-hash path sanitization.
4. **Execute the isolated suites into `runs-local/`:** Run the generated `scripts/run_benchmark.py` commands (with `--resume` and `--child-max-rss-mb 1536`). Keep all timeouts, blocked attempts, and failures inside `runs.jsonl` denominators with hashed blocker evidence.
5. **Grade, validate, and compute keep/drop decisions:**
   - Validate hashes and schema with `scripts/benchmark.py validate`.
   - Summarize paired tracks with `scripts/benchmark.py summarize` and confirm `missing_pilot_coverage.complete = true` against a matching pilot manifest under `benchmarks/`.
   - For `EV1` and `EV2`, run `benchmarks/evolution.py compare` on Stage-4 grader metrics to classify each arm (`KEEP`, `DROP`, or `INCONCLUSIVE`).
6. **Promote clean results and refresh the longitudinal scorecard:** Move sanitized datasets from `runs-local/` into `results/<experiment-id>/`, update the scorecard, and run all repository integrity checks:

```bash
python3 -B scripts/eval_cycle.py scorecard --markdown
python3 -B scripts/check.py
```

7. **Add model deltas only for verified recurring defects:** Add an entry in `gates/model_deltas.json` only if baseline and `core-rules-v0.2.0` exhibit a concrete, recurring model-specific defect that deterministic gates cannot catch directly, backed by a falsification check and a valid neighbouring case.

## 3. Rule Retirement Discipline

Accumulating rules indefinitely slows reviews, raises token overhead, and triggers false-positive churn. Treat every standing rule (`R1`-`R7`), model delta (`D-*`), and learned rule (`L-*`) as code with an explicit retirement path.

### Two Retirement Signals

1. **Project-level staleness (`anti-slop learn mine --stale-days 60`):** Any approved `L-*` rule with zero hits across the `--stale-days` window (or whose recorded `retirement_trigger` is now satisfied by a linter, static type, or framework upgrade) is surfaced under `retirement_candidates`. Retire it with:

```bash
python3 -B gates/learn.py retire L-001 --reason "Enforced by static type check in CI."
```

2. **Benchmark-level ceilings and regressions (`scripts/eval_cycle.py scorecard`):** The scorecard's **Rule-Retirement Watch** highlights two conditions automatically:
   - **Baseline 100% ceiling across all tested models:** In both `results/pilot-comments-v0.7.0/` (`CM1`, 1 file / 90L) and `results/pilot-comments-v0.8.0/` (`CM2`, 6 modules / 345L with invariants omitted from the prompt), the `no-comments` baseline already passes `12/12` (`100.0%`) across all four focus models on accuracy (while `invariant-comments` runs `-4.5%` / `-6.8%` faster and `comment-traps` adds `+31.5%` / `+16.4%` Opus USD tax). Accuracy-only rules targeting small single-context-window packages have no accuracy headroom left; retire them or scale future comment evals to 1,000+ line cross-repo context-rot tasks with external side effects.
   - **Treatment regression or `DROP` / `INCONCLUSIVE` verdicts:** In `results/pilot-evolution-v0.7.0/` (`EV1`), standing prose (`core-rules-v0.2.0`) dropped overall pass rate from `6/12` (`50.0%`) to `5/12` (`41.7%`) and triggered `DROP` on `claude-opus-5-5` and `gpt-6.2-sol`, whereas deterministic + structural gating (`gated-structural`) reached `11/12` (`91.7%`) with `0` slop defects. In `results/pilot-ts-evolution-v0.8.0/` (`EV2`), standing prose scored `INCONCLUSIVE` (`8/12`, `+13.0%` tokens / `+11.6%` Opus USD), whereas `gated-structural` reached **`12/12` (`100.0%`, `KEEP`)** with `0` slop at `-10.4%` fewer tokens than prompts alone. Both results reinforce moving enforcement from standing prose into deterministic gates rather than expanding `standard/core.md`.

### Stable ID Invariant

Retiring any rule (`R*`, `D-*`, or `L-*`) stops its enforcement while keeping its regression examples in the repository and leaving its ID permanently unused. Never renumber or reuse retired IDs; if a future model regresses on a previously retired failure mode, the preserved bad/valid pair catches it cleanly.

## 4. Roadmap Beyond Pre-v1 (`0.8.0` -> `1.0.0`)

Release `0.8.0` is an active pre-v1 milestone shipping Tier-1 live E2E verification receipts (`gates/verify.py`, [docs/verify-recipes.md](verify-recipes.md)), architectural compounding-slop detectors (`gates/architecture.py`, `ARCH-*`, `0` FPs across 150 OSS commits), Python + JS/TS diff-scoped mutation testing (`gates/mutate.py`), the human-gated learning loop (`gates/learn.py`), and `288` clean `CODEX_HOME`-isolated public runs across five datasets (`results/`).

Planned post-`0.8.0` priorities toward `1.0.0`, ordered by impact:

1. **Playwright and browser visual verification adapter:** Extend `gates/verify.py` (`anti-slop verify`) to drive headless browser UI flows, assert DOM/console health, and attach visual verification artifacts to tamper-evident receipts.
2. **Deeper architectural coupling and data-model drift checks:** Extend `gates/architecture.py` to detect cross-module fan-in/fan-out spikes, schema/DTO drift across service boundaries, and leaky abstraction layers.
3. **Broader language and large-scale evaluations:**
   - **Go and Rust multi-turn evolution (`EV3+`):** Replicate multi-turn compounding decay measurements beyond Python and TypeScript.
   - **1,000+ line cross-repo context-rot comment evals:** Test external side effects and undocumented invariants that cannot be inferred from a single context window of local source alone.
4. **PyPI publication and scheduled cross-model re-evaluations:** Publish `anti-slop` to PyPI and run `scripts/eval_cycle.py plan` and `scorecard` on a recurring cadence as new frontier models release, retiring rules that models outgrow and updating `gates/model_deltas.json` strictly from measured clean datasets.
