# Operating guide

Use [the core standard](../standard/core.md) as the reusable instructions. This guide explains verification, context maintenance and learning; it is not additional standing prompt text. For workload routing, 4-tier stakes review, cross-family verification, safe legacy cleanup and rule-pruning cadences, see [operations and routing](operations-and-routing.md). For opt-in deterministic CI, API and prose checks, see [gates](../gates/README.md).

## How each rule can be checked

Apply checks in proportion to the task stakes (see the [4-tier stakes matrix](operations-and-routing.md#4-tier-stakes-review-matrix)). A small edit usually needs only a few checks; a complex request must still cover all material requirements. Routine checks can remain internal. The user needs the result, material evidence and unresolved limits.

| Rule | Observable question | Useful evidence |
|---|---|---|
| **R1. Define done** | Does the result satisfy every material part of the brief? | A brief-to-result checklist or a stated acceptance criterion. |
| **R2. Ground claims and premises** | Were user premises and cited sources verified at the stated date/version before acting? | Inspected source passage, repo `file:line`, calculation or approved decision. |
| **R3. Keep scope simple** | Does each material change serve the task or a necessary structural correction? | Actual diff, existing conventions, clone/diff gates and preserved behaviour. |
| **R4. Verify and report** | What establishes success, what remains unverified, and were tests kept intact? | Automated test/grader output, read-only test diff check, observed output or independent review. |
| **R5. Remove burden** | Can something be removed without losing required meaning, behaviour or maintainability? | Before/after comparison against the same acceptance criteria. |
| **R6. Preserve context** | Can a later reader tell what is fact, decision, assumption, draft or superseded? | Canonical reference, status, provenance and supersession record where needed. |
| **R7. Learn** | Does the prevention fix the reproduced failure without breaking valid neighbouring cases, and is its ID retired cleanly when obsolete? | A regression case, valid neighbouring case, comparison result and defined applicability/expiry. |

Material means that an error, omission or ambiguity could change the user's decision, action, ability to use the result, or maintenance burden.

For code, derive expected behaviour from the requirement and existing contract. Tests that merely assert the generated implementation's current output are weak evidence; never edit or weaken tests to fit broken code. Use a targeted negative case, automated grader (`benchmarks/graders/`), or pre-fix failure when practical and valuable. Do not create test suites for cosmetic changes.

For prose, check preservation of facts, uncertainty and the intended action before checking tone. For visual work, inspect the rendered result against the brief and supplied design references.

## Prevent errors from becoming authoritative context

Use lightweight status distinctions, preferably through metadata the repository or knowledge system already provides.

| Status | Treatment |
|---|---|
| **Supported fact** | Retain the source and relevant date/version. Recheck when the fact can change. |
| **Approved decision** | Retain who decided, what was decided and when. Do not rewrite it as an empirical fact. |
| **Assumption or hypothesis** | Keep the qualification and what would resolve it. |
| **Draft** | Available for editing or explicit reference; not automatically evidence for later conclusions. |
| **Superseded** | Point to the current source and prevent the obsolete version from silently becoming the default. |

A summary is a navigation aid, not an additional independent source. Repetition across generated documents does not increase evidential support. Permission and privacy boundaries continue to apply to retention, edits and removal.

When an error is discovered:

1. Identify the earliest incorrect claim, decision interpretation or implementation.
2. Correct the canonical artifact, retaining the appropriate change history.
3. Find affected summaries, plans, tests, memories and implementations. Fix or invalidate the ones that depend on the error.
4. Verify the corrected result and the important downstream behaviour.
5. Add a prevention only if the failure warrants one.

For code, removal means deleting obsolete paths or duplicated implementations where authorised, then checking the required behaviour (see [safe legacy slop removal](operations-and-routing.md#safe-legacy-slop-removal)). Adding another fallback around an unexplained failure is not evidence of a repair.

## A small continuous-learning loop

Record a serious defect immediately. Record a recurring minor defect when the pattern shows up twice or becomes useful to investigate (an operational starting policy, not an empirically optimal threshold).

Use one short record (matching `.github/ISSUE_TEMPLATE/slop-defect.md`):

```text
Case and affected artifact:
Expected result:
Observed defect and evidence:
Consequence:
Suspected cause and alternative explanation:
Current repair and downstream repair:
Proposed prevention and scope:
Regression case plus valid neighbouring case:
Validation result:
Review trigger or expiry condition:
```

Prefer the narrowest effective place for the prevention: source correction, retrieval configuration, tool behaviour, deterministic check (`gates/`), task template, project instruction, then global instruction only if necessary. A model's explanation of its own failure is a hypothesis to investigate.

Example: a shortened research brief drops the fact that results came from a small internal pilot. Repair the brief and derived recommendation. Preserve the before/after example as a regression case. Test a qualification-preservation check alongside a valid neighbouring case where concise output is appropriate. Do not respond by adding a global requirement that every answer contain a long limitations section.

Keep incident records separate from always-loaded instructions. Review controls on the schedule in [operations and routing](operations-and-routing.md#golden-eval-ablation-and-rule-pruning) or whenever triggering conditions change, the model changes, or contrary results appear. Retain useful regression cases even when an obsolete instruction is retired (leaving its stable ID unused).

## Boundaries for prose editing

Use `unslop` (`REF-02`) as an optional editorial reference—and if automating deterministic prose checks via `gates/vale/`, keep stylistic rules (`Vocab`, `Phrasing`) at **`warning` level with technical allowlists** while reserving `error` blocks for objective defects (such as chatbot openers or broken local paths). Do not treat punctuation, vocabulary, sentence length or an AI-detector score as evidence of truth or usefulness. Preserve meaningful qualifications, domain terms and variation in sentence structure.

The test is whether the intended reader can correctly understand and use the result with less avoidable effort.
