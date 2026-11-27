# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:22:48Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: model-controls
- Elapsed seconds: 7.86
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` honors every user-declared field by default. `excluded_fields` removes only matching clauses unless `drop_whole_item=True`. Excerpt validation still checks every clause in the source. No hardcoded field exclusions remain.
- `runner.py` uses `fast_tensor` without truncation, hardcoded capacity caps, or a size-based fallback. Callers can set `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Invalid or exceeded limits raise `ValueError`.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0`: `Ran 4 tests in 0.000s`, `OK`. Additional edge checks passed. `git status` was unavailable because the workspace had no Git repository.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__model-controls__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 85/120 (raw=87)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
