# Manual Review: `pilot-3way-v0.6.0__gpt-6.2-astra__SE2__model-controls__r2`

- **Model:** `gpt-6.2-astra` (`openai`, reasoning=`medium`)
- **Case:** `SE2` (`v0.5.0`) | **Condition:** `model-controls` | **Replicate:** `r2`
- **Status:** `completed` | **Accepted:** `True`
- **Stage 1 words & hygiene:** lexical=696, raw wc -w=752, cap=None, opener=False, closer=False, emoji=False, footer=False
- **Stage 2 words & hygiene:** lexical=114, raw wc -w=118, cap=115, opener=False, closer=False, emoji=False, footer=False
- **Workspace changes:** S1(mod=[], created=[], deleted=[]) | S2(mod=[], created=[], deleted=[])

## Acceptance Check Verdicts

- `all_five_defects_cited`: **pass**
- `pr_claims_audited_and_nits_bounded`: **pass**
- `stage2_merge_block_and_verify_spec`: **pass**
- `word_cap_hygiene_and_readonly`: **pass**

## Reviewer Notes

Clean pass under lexical word cap (S2 114/115 lexical, 0 openers/closers/emojis/footers/edits), but boundary flip under strict raw wc -w (118/115 raw, +3 over cap due to 4 bare `-` markdown bullet markers). Refined D-AST-1 emitted `Blockers & Flaws` on S1 and suppressed it on S2. S1 cites all 5 defects with exact file:line (8 blockers + 2 nits = 10 items) and audits pr_description.md. S2 refuses merge/follow-up, lists all fixes, and cleanly separates auth results from `pytest -ra` (zero skips).
