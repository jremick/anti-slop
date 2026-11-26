---
name: Proposed rule or control change
about: Propose a narrow gate, model delta, or rule change that can be evaluated
title: "Rule: "
---

## Triggering evidence

## Target layer and proposed change

Prefer the narrowest effective layer: source fix -> retrieval/tool -> `gates/` deterministic check -> `gates/model_deltas.json` -> `standard/core.md` (last resort, keep <= 300 words).

## Intended benefit and scope

## Regression case and valid neighbouring case

Include both the reproduced failure case and an adjacent valid case that an overbroad rule/gate could damage.

## Possible unwanted effects

## Paired evaluation plan

Specify `--baseline` and `--treatment` conditions (e.g., `core-rules` vs. `model-controls` or `core-rules-v0.1.0` vs. `core-rules-v0.2.0`).

## Results or current unvalidated status

## Review trigger or expiry condition

## Existing rule/ID this replaces or retires

Remember: rule IDs (`R1`–`R7`, `D-*`) are stable; retiring an ID leaves a gap and keeps its regression case.
