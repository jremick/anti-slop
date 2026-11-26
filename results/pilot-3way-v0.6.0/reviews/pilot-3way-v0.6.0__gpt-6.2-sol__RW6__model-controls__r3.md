# Manual Review: `pilot-3way-v0.6.0__gpt-6.2-sol__RW6__model-controls__r3`

- **Model:** `gpt-6.2-sol` (`openai`, reasoning=`medium`)
- **Case:** `RW6` (`v0.4.0`) | **Condition:** `model-controls` | **Replicate:** `r3`
- **Status:** `completed` | **Accepted:** `False`
- **Stage 1 words & hygiene:** lexical=136, raw wc -w=136, cap=135, opener=False, closer=False, emoji=False, footer=False
- **Stage 2 words & hygiene:** lexical=56, raw wc -w=56, cap=75, opener=False, closer=False, emoji=False, footer=False
- **Workspace changes:** S1(mod=[], created=[], deleted=[]) | S2(mod=[], created=[], deleted=[])

## Acceptance Check Verdicts

- `exact_commit_and_changelog_counts`: **pass**
- `all_four_draft_errors_and_nogo`: **pass**
- `stage2_release_update`: **pass**
- `word_caps_and_readonly`: **fail** — Stage 1 lexical word count 136 exceeds 135-word cap (136 raw wc -w, +1 word); Stage 2 passed (56/75 lex/raw); zero openers/postscripts and zero workspace edits.

## Reviewer Notes

All factual checks pass (No-Go, 43 commits, 25 entries = 6 Changed + 19 Fixed, unshipped #721/#720/#706/#635 + Latin-1/tomllib, #664 and #325/#627 misfiled under 0.15.2/0.15.1, comment/date/non-table AoT ValueError + serialized array sorting, clean S2 update), but Stage 1 drifts +1 lexical word over cap (136/135 lex/raw, replicating LOCAL-03/LOCAL-04 Sol prose drift).
