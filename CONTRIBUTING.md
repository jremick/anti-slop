# Contributing

Changes should reduce a demonstrated failure or make the evidence easier to assess.

## Rule or model-control changes

1. Link an observed failure and distinguish its evidence from the suspected cause.
2. Propose the smallest appropriate change and its scope — prefer a source fix, tool, or deterministic check in `gates/` over adding standing prompt prose.
3. Test the failure **and** a valid neighbouring case that an overbroad rule or gate could damage.
4. Record outcomes, unwanted effects and the limits of the comparison.
5. Update `standard/core.md`, `gates/model_deltas.json` or `docs/models.md` only when the evidence warrants it.

Editing or clarifying a candidate rule does not require pretending it is already validated. Label the status accurately. Keep mandatory user permissions and project requirements in both experimental conditions.

## Versioning and stable IDs

- `VERSION` tracks the repository, tooling, runtime gates and benchmark-suite release (currently `0.9.0`). `standard/core.md` keeps its own pinned standard version (currently `0.2.0`) so standing-rule stability stays decoupled from tooling and benchmark releases. Update the `standard/core.md` header only on a standing-rule release, and always update `CHANGELOG.md`.
- Rule IDs (`R1`–`R7` in `standard/core.md` and `D-*` in `gates/model_deltas.json`) are stable. Retiring a rule leaves a numeric gap; never renumber or reuse an ID.
- Case `version` changes whenever prompts, inputs, stages or scoring criteria materially change. Preserve earlier case definitions needed by historical results, using separate versioned filenames. Keep `W1`–`C2` unchanged for `v0.1.0` vs. `v0.2.0` comparisons.
- Never edit frozen condition, output or check evidence for an already published run. Add a new run or a clearly documented correction with the original record retained in history.
- Source IDs in `docs/evidence.md` stay stable. New or replacement sources get their own IDs; record supersession explicitly.
- A changed model, harness, effort, tool configuration, source snapshot or treatment is a new recorded configuration. Do not silently pool it with earlier results.

## Results review

Check source support and expected behaviour, not just file existence. Reconcile the predeclared pilot manifest (`benchmarks/pilot*.json`) before describing an experiment as complete. Include failures, blocks and timeouts with non-empty blocker evidence. Preserve unknown metrics as `null`; do not fill them with zero. Distinguish honest blocking from completion.

Reviewers should be blinded to model and condition where practical. Counterbalance first exposure when measuring handling time. Report raw counts, replicate counts (`n`), and actual defects; the current 28-case suite (22 constructed probes including `EV1`, `EV2`, `CM1`, and `CM2`, plus 6 pinned OSS real-work cases) does not support a precise general population effect estimate. Once a held-out case influences tuning, move it to the development/regression set.

Constructed diagnostic cases (`origin: constructed`) and pinned real-work cases (`origin: real_work`) are different populations and must be reported separately. Actual model runs on either are measured evidence; fabricated demonstration records must use `synthetic: true` and must not become performance claims. Never commit personal workstation paths, local dotdir contents, or credentials in run artifacts.

## Submitting

Use a pull request with the problem, proposed change, evidence and validation result. Run:

```bash
python3 -B scripts/check.py
```

Model execution is separate from CI. State exactly which model experiments were run, or say none. Do not claim GitHub branch protection or a hosted CI result until it has been verified in the repository.
