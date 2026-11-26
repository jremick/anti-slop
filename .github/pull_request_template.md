## Problem and change

What observed problem does this address, and what changes? (Prefer source fixes, tools, or `gates/` checks over standing prompt prose.)

## Evidence and scope

Link the source ID (`docs/evidence.md`) or regression case + valid neighbouring case. Distinguish observations from hypotheses. Note any changed case, model delta (`gates/model_deltas.json`), prompt, or standard version—and confirm retired stable IDs were left unused.

## Validation

Record `python3 -B scripts/check.py` output and any model experiments actually run (or state `none`). Describe regressions or untested limits. State whether `benchmarks/pilot.json` was reconciled if publishing results.
