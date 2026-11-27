# pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r1 — Stage 2/2

- Timestamp UTC: 2026-11-27T22:23:38Z
- Model: openai/gpt-6.2-sol (reasoning=medium, observed=gpt-6.2-sol (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 8.13
- Workspace modified: ['benchmarks/sources/se3_spec_fidelity/matcher.py', 'benchmarks/sources/se3_spec_fidelity/runner.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Respond ONLY with a ready-to-paste PR summary (at most 120 words) summarizing the two spec-fidelity fixes, confirming whether any hardcoded field exclusions or capacity caps remain, noting which caller opt-in bounds are supported, and stating the exact verification status.

## Raw Model Output

- `matcher.py` now honors every declared preference field by default. Caller-provided `excluded_fields` removes only matching clauses unless `drop_whole_item=True`. Stale excerpts still invalidate the entire source.
- `runner.py` routes accepted requests through `fast_tensor` without truncation. Callers can opt into `max_prompt_bytes` (positive integer, measured in UTF-8 bytes) and `max_tools` (non-negative integer). Invalid limits and exceeded bounds raise `ValueError`.

All hardcoded field exclusions, prompt and tool caps, and the size-based fallback were removed.

`python3 benchmarks/sources/se3_spec_fidelity/run_checks.py` exited `0` with `Ran 4 tests in 0.000s` and `OK`.


## Workspace Grader & Diff
- Workspace diff: `results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r1/stage-2-workspace.diff`
- Automated grader (`results/pilot-spec-fidelity-v0.9.0/artifacts/pilot-spec-fidelity-v0.9.0__gpt-6.2-sol__SE3__core-rules-v0.2.0__r1/stage-2-grader.json`): passed=True

## Deterministic Text Constraints
- Lexical words: 80/120 (raw=82)
- Opener hit: False
- Closer hit: False
- Decorative emoji hit: False
- Word-count postscript hit: False
- Passed: True
