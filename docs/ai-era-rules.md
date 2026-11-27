# AI-Era Coding Rules: What Helps, What Is Still a Hypothesis, and What Hurts

Traditional software best practices were written for human teams reading code slowly over months. Coding agents work differently: they read a bounded context window, imitate whatever patterns already sit in your repository, and optimize for making the immediate test run look green.

That shift changes which engineering rules pay off. Some rules matter much more in AI-assisted coding because a single shortcut compounds across every later session. Other classic habits degrade AI workflows by burning context windows, hiding real failures, or giving future sessions bad examples to copy.

Every rule and anti-pattern below carries strict provenance tags so you can separate live measured results from open hypotheses:

- **`Local measured (EV1: KEEP)` / `(EV2: KEEP)` / `(EV1 & EV2: KEEP)`**: causally validated in our live 4-turn Python `EV1` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [LOCAL-07](evidence.md#local-07): `50.0% -> 41.7% [DROP on Opus & Sol] -> 91.7% [11/12, 0 slop, +7.5pp mut vs. prompts]`) and/or TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [LOCAL-09](evidence.md#local-09): `58.3% -> 66.7% [INCONCLUSIVE] -> 100.0% [12/12, 0 slop, 79.2% TS mut kill, -10.4% tokens vs. prompts]`) evolution benchmarks.
- **`Local measured (CM1 & CM2: overhead confirmed, accuracy ceiling)`**: directly measured across 72 controlled ablation runs in Python `CM1` ([results/pilot-comments-v0.7.0/README.md](../results/pilot-comments-v0.7.0/README.md), [LOCAL-06](evidence.md#local-06), 1 file / 90L) and `CM2` ([results/pilot-comments-v0.8.0/README.md](../results/pilot-comments-v0.8.0/README.md), [LOCAL-08](evidence.md#local-08), 6 modules / 345L): `24/24` accuracy ceiling across all 3 arms in both suites, while short `# INVARIANT:` notes ran fastest and cheapest (`-4.5%` / `-6.8%` wall, `-1.7%` / `-2.4%` Opus USD) and `comment-traps` inflated Opus USD (`+31.5%` / `+16.4%`) and forced `-28` / `-20..-67` deleted comment lines.
- **`Local measured`**: directly measured in our 144-run `v0.6.0` benchmark ([results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md), [LOCAL-05](evidence.md#local-05)) or our 150-commit OSS precision audits ([gates/README.md](../gates/README.md)).
- **`External empirical study`**: backed by peer-reviewed or preprint empirical research linked inline and tracked in [docs/evidence.md](evidence.md).
- **`Candidate (untriggered in EV1/EV2)`**: checked mechanically in `EV1` and/or `EV2`, with `0` occurrences across those runs (so local evolution benchmarks neither confirm nor refute causal uplift yet).
- **`Practitioner hypothesis`**: experience-based engineering hypothesis without a controlled randomized trial yet. Treat it as a testable candidate, not a settled fact.

For the curated opt-in library showing **Default Core vs. Optional Packs (`6` packs, `10` rules) vs. Deliberately Excluded (`6` items)**, see [library/README.md](../library/README.md).

---

## Quick Map

| Pattern / Rule | Provenance | Automated check in `anti-slop` | Primary citation |
|---|---|---|---|
| 1. Never skip, waive, or weaken tests | `Local measured` + `External empirical study` | `DIFF-TEST-SKIP`, `DIFF-UNAUTHORIZED-TEST-EDIT`, `gates/hooks/` | `pilot-3way-v0.6.0` ([LOCAL-05](evidence.md#local-05)); RHB ([arXiv:2605.02964](https://arxiv.org/abs/2605.02964), [EXT-13](evidence.md#ext-13)) |
| 2. Follow the 3-tier verification hierarchy | `Local measured (EV1 & EV2: KEEP)` (test theater/mutation) + `External empirical study` (+ `Practitioner hypothesis` for Tier 1) | `anti-slop verify` ([gates/verify.py](../gates/verify.py), [verify-recipes.md](verify-recipes.md)), `STRUCT-TEST-THEATER`, Python + JS/TS `anti-slop mutate` ([gates/mutate.py](../gates/mutate.py)) | `EV1` ([LOCAL-07](evidence.md#local-07)), `EV2` ([LOCAL-09](evidence.md#local-09)); Hora & Robbes ([arXiv:2602.00409](https://arxiv.org/abs/2602.00409)); Petrović et al. ([arXiv:2102.11378](https://arxiv.org/abs/2102.11378)); MutGen ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [EXT-13](evidence.md#ext-13)) |
| 3. Fail loudly instead of silent fallbacks or bare suppressions | `Local measured (EV1: KEEP)` (`DIFF-SUPPRESSION`) + `Candidate (untriggered in EV1/EV2)` / `Practitioner hypothesis` (`STRUCT-SILENT-FALLBACK`) | `DIFF-SUPPRESSION`, `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | `pilot-evolution-v0.7.0` ([LOCAL-07](evidence.md#local-07)); Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839)); Tufano et al. ([arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [EXT-15](evidence.md#ext-15)) |
| 4. Keep one canonical copy of business logic | `Local measured (EV2: KEEP)` + `Local measured` (OSS audit) + `External empirical study` | `STRUCT-DUPLICATE-BLOCK` | `pilot-ts-evolution-v0.8.0` ([LOCAL-09](evidence.md#local-09)); GitClear 2025 ([gitclear.com](https://www.gitclear.com/ai_assistant_code_quality_2025_research), [EXT-12](evidence.md#ext-12)); Liu et al. ([arXiv:2603.28592](https://arxiv.org/abs/2603.28592), [EXT-15](evidence.md#ext-15)); `hono` OSS audit ([gates/README.md](../gates/README.md)) |
| 5. Delete dead code and legacy shims completely | `Local measured (EV1: KEEP)` + `External empirical study` | `STRUCT-DEAD-COMPAT` | `pilot-evolution-v0.7.0` ([LOCAL-07](evidence.md#local-07)); Sun et al. ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455)); A.S.E 2.0 / CASE-Bench ([arXiv:2611.06294](https://arxiv.org/abs/2611.06294), [EXT-12](evidence.md#ext-12)) |
| 6. Keep diffs focused and modules cohesive | `Local measured (EV1 & EV2: KEEP)` (`STRUCT-GOD-FUNCTION`) + `External empirical study` | `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, `STRUCT-SCOPE-SPRAWL` | `EV1` ([LOCAL-07](evidence.md#local-07)), `EV2` ([LOCAL-09](evidence.md#local-09)); SlopCodeBench ([arXiv:2603.24755](https://arxiv.org/abs/2603.24755), [EXT-07](evidence.md#ext-07)); Zhu et al. ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [EXT-15](evidence.md#ext-15)) |
| 7. Put mechanical rules in tools, not standing prompts alone | `Local measured (EV1 & EV2: KEEP)` + `Local measured` (`v0.6.0`) + `External empirical study` | `gates/review.py`, `gates/diff_check.py`, `standard/core.md` (`<= 300` words), `gates/learn.py` | `EV1` ([LOCAL-07](evidence.md#local-07)), `EV2` ([LOCAL-09](evidence.md#local-09)), `v0.6.0` ([LOCAL-05](evidence.md#local-05)); IFScale ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538)); Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [EXT-11](evidence.md#ext-11)) |
| 8. Comment hygiene: delete traps, keep short "why" invariants | `Local measured (CM1 & CM2: overhead confirmed, accuracy ceiling)` + `External empirical study` | `STRUCT-COMMENTED-CODE` | `CM1` ([LOCAL-06](evidence.md#local-06)), `CM2` ([LOCAL-08](evidence.md#local-08)); Comment Traps ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334)); Vitale et al. ([arXiv:2601.23059](https://arxiv.org/abs/2601.23059)); Thornton ([arXiv:2602.16741](https://arxiv.org/abs/2602.16741), [EXT-14](evidence.md#ext-14)) |
| 9. Prevent architectural coupling, cycles, and config scatter | `External empirical study` + `Candidate (untriggered in EV2)` (`Local measured` OSS precision: `0` FPs / 150 commits, `7/7` TP `hono` cycles) | `ARCH-CIRCULAR-IMPORT`, `ARCH-SINGLE-IMPL-WRAPPER`, `ARCH-BOUNDARY-SCATTER` ([gates/architecture.py](../gates/architecture.py)) | Zhu et al. ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [EXT-15](evidence.md#ext-15)); 150-commit OSS audit ([gates/README.md](../gates/README.md#architectural-gates-gatesarchitecturepy-oss-precision-audit)) |
| A. Premature single-use abstractions / DI layers | `Practitioner hypothesis` + `Candidate (untriggered in EV2)` | `ARCH-SINGLE-IMPL-WRAPPER` ([gates/architecture.py](../gates/architecture.py)) + `R3`/`R5` (opt-in pack in [library/README.md](../library/README.md)) | Contextual only: Lost in the Middle ([arXiv:2307.03172](https://arxiv.org/abs/2307.03172)); Chroma Context Rot ([trychroma.com](https://www.trychroma.com/research/context-rot), [EXT-11](evidence.md#ext-11)) |
| B. Defensive catch-all fallbacks | `Practitioner hypothesis` + `Candidate (untriggered in EV1/EV2)` | `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | Observational context: Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [EXT-15](evidence.md#ext-15)) |
| C. Mock-everything "pure" unit tests | `Local measured (EV1 & EV2: KEEP)` + `External empirical study` | `STRUCT-TEST-THEATER`, `anti-slop mutate`, `anti-slop verify` | `EV1` ([LOCAL-07](evidence.md#local-07)), `EV2` ([LOCAL-09](evidence.md#local-09)); Hora & Robbes ([arXiv:2602.00409](https://arxiv.org/abs/2602.00409)); MutGen ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [EXT-13](evidence.md#ext-13)) |
| D. Retaining legacy shims "just in case" | `Local measured (EV1: KEEP)` + `External empirical study` | `STRUCT-DEAD-COMPAT` | `pilot-evolution-v0.7.0` ([LOCAL-07](evidence.md#local-07)); Sun et al. ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [EXT-12](evidence.md#ext-12)); Comment Traps ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [EXT-14](evidence.md#ext-14)) |
| E. Blanket style rules & standing prompt checklists alone | `Local measured (EV1 & EV2: KEEP)` + `Local measured` (`v0.6.0`) + `External empirical study` | `standard/core.md`, `gates/learn.py` ladder | `EV1` ([LOCAL-07](evidence.md#local-07)), `EV2` ([LOCAL-09](evidence.md#local-09)); OpenAI ([Using GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.2-astra), [OAI-02](evidence.md#oai-02)); Anthropic ([Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2), [ANT-04](evidence.md#ant-04)); IFScale ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538), [EXT-11](evidence.md#ext-11)) |

---

## Part 1: Rules That Matter More in AI-Assisted Coding

### 1. Never skip, waive, or weaken tests to turn CI green

- **Provenance:** `Local measured` + `External empirical study`
- **Evidence:**
  - `Local measured`: In `pilot-3way-v0.6.0` (`RW3`, `urllib3`; [results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md), [docs/evidence.md#local-05](evidence.md#local-05)), `8/11` (`72.7%`) completed baseline runs modified a frozen test file to skip or waive a failing check under release pressure. Standing rules cut tampering to `0/23` (`0.0%`).
  - `External empirical study`: *Reward Hacking Benchmark* ([arXiv:2605.02964](https://arxiv.org/abs/2605.02964), [docs/evidence.md#ext-13](evidence.md#ext-13)) showed environmental hardening cut tool-use exploits from `6.5%` to `0.8%` (`-87.7%` relative) without reducing task success; *EvilGenie* ([arXiv:2511.21654](https://arxiv.org/abs/2511.21654), [docs/evidence.md#ext-13](evidence.md#ext-13)) and *ImpossibleBench* ([arXiv:2510.20270](https://arxiv.org/abs/2510.20270), [docs/evidence.md#ext-12](evidence.md#ext-12)) showed coding agents edit or bypass test files unless test-file edit integrity is checked mechanically.
- **How it compounds:** Once a skipped test lands, future AI sessions treat skipping failing checks as an accepted repository norm.
- **Automated check:** `DIFF-TEST-SKIP` and `DIFF-UNAUTHORIZED-TEST-EDIT` (blocked in `gates/diff_check.py`, `action.yml`, pre-commit, and mid-turn hooks in `gates/hooks/`).

**Looks convincing (hides a broken feature):**

```python
import pytest

@pytest.mark.skip(reason="temporarily flaky after refactor")
def test_refund_preserves_cents():
    assert allocate_refund(100, [1, 1, 1]) == [34, 33, 33]
```

**Actually clean (fixes the code, keeps the contract intact):**

```python
def test_refund_preserves_cents():
    assert allocate_refund(100, [1, 1, 1]) == [34, 33, 33]
```

---

### 2. Tests and Verification: Follow the 3-Tier AI-Era Verification Hierarchy

- **Provenance:** `Local measured (EV1 & EV2: KEEP)` (`STRUCT-TEST-THEATER` + Python & JS/TS mutation strength lift under mechanical gates) + `External empirical study` (Tiers 2 and 3) + `Practitioner hypothesis` (Tier 1 live-artifact preference, reinforced by compositional-failure evidence)
- **Evidence:**
  - `Local measured (EV1 & EV2: KEEP)`: In Python `EV1` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [docs/evidence.md#local-07](evidence.md#local-07)), `gated-structural` caught `1` assertion-free smoke test (`STRUCT-TEST-THEATER`: `test_percent_bounds_are_inclusive` on `claude-opus-5-5` Stage 2 `r3`, eliminating the `1 -> 0` test-theater defect seen in `baseline r3`) and lifted mean AST mutation kill rate to **`74.7%`** (`+4.2pp` vs. `baseline` `70.6%`, **`+7.5pp`** vs. `core-rules-v0.2.0` `67.2%`). In TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [docs/evidence.md#local-09](evidence.md#local-09)), `gated-structural` lifted mean JS/TS mutation kill rate (`gates/mutate.py`) from `74.17%` (`baseline`) and `75.00%` (`core-rules-v0.2.0`) to **`79.17%`** (`+5.00pp` vs. baseline, `12/12` passing the `>= 65%` bar), driven by a **`+21.67pp`** jump on `gemini-4-neon` (`58.3% -> 80.0%`).
  - `External empirical study`: Hora & Robbes (MSR 2026, [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)) analyzed 1.2M+ commits across 2,168 repos and found coding agents modify test files in `23%` vs. `13%` (human) of commits and add mocks in `36%` vs. `26%` (`68%` of agent-test repos).
  - `External empirical study`: *MutGen* (Wang et al., IEEE TSE, [arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)) found vanilla LLM tests average ~`53%` mutation score vs. `89.5%` with mutation feedback (and showed some `100%`-coverage suites score only `4%` on mutants). Google Critique diff-based mutation (Petrović et al., [arXiv:2102.11378](https://arxiv.org/abs/2102.11378), [docs/evidence.md#ext-13](evidence.md#ext-13)) lifted developer-rated mutant productivity from ~`15%` to `80%-89%` across >24,000 developers, and Meta ACH (Foster, Harman et al., [arXiv:2501.12862](https://arxiv.org/abs/2501.12862), [docs/evidence.md#ext-13](evidence.md#ext-13)) saw `73%` engineer acceptance.
  - `External empirical study`: *SpecBench* ([arXiv:2605.21384](https://arxiv.org/abs/2605.21384), [docs/evidence.md#ext-12](evidence.md#ext-12)) showed coding agents saturate isolated visible unit tests while failing held-out composed flows (the gap grows `+28pp` per 10x code-size increase), and *UTBoost* ([arXiv:2506.09289](https://arxiv.org/abs/2506.09289), [docs/evidence.md#ext-12](evidence.md#ext-12)) uncovered 345 erroneous patches that passed weak PR tests. *PBT-Bench* (NeurIPS 2026, [arXiv:2605.15229](https://arxiv.org/abs/2605.15229), [docs/evidence.md#ext-13](evidence.md#ext-13)) showed Hypothesis property-based scaffolding lifts mid-capability bug recall by `>20pp`.
- **The 3-Tier AI-Era Verification Hierarchy:**
  1. **Tier 1 (Strongest for apps, services, and UIs): Live end-to-end / real-artifact functional verification with tamper-evident receipts.** Start the real application, CLI, API server, or browser, exercise the changed flow end to end against real inputs, and capture observable output, HTTP status, JSON response shape, or artifact state. Run `anti-slop verify` ([gates/verify.py](../gates/verify.py), see [docs/verify-recipes.md](verify-recipes.md)) via a reusable `<repo>/.anti-slop/verify.json` recipe or one-shot `--start`/`--http-get`/`--cmd`/`--file` flags to tear down background services cleanly and write a SHA-256 receipt (`<repo>/.anti-slop/last-verify.json`) validated with `anti-slop verify --check-receipt`. (`Practitioner hypothesis` reinforced by *SpecBench* [arXiv:2605.21384](https://arxiv.org/abs/2605.21384), [docs/evidence.md#ext-12](evidence.md#ext-12).)
  2. **Tier 2 (Strong for logic and libraries): Behavioral integration and property tests against real code + diff-scoped mutation testing.** Exercise real code paths without mocking the system under test, encode domain invariants with property tests ([arXiv:2605.15229](https://arxiv.org/abs/2605.15229)), and verify test strength on changed **Python and JS/TS** lines with `anti-slop mutate` ([gates/mutate.py](../gates/mutate.py), citing Google Critique [arXiv:2102.11378](https://arxiv.org/abs/2102.11378) and *MutGen* [arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)).
  3. **Tier 3 (Weakest; watch for theater): Same-turn isolated, heavily-mocked unit tests.** Useful only for narrowly scoped pure helpers or external I/O boundaries; treat passing mocked tests written in the same turn as weak evidence unless backed by Tier 1 or Tier 2 checks (Hora & Robbes [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)).
- **How it compounds:** Future AI sessions trust a green test suite. If a test only checks that a mock was called or asserts `True`, a later session can break billing math or auth checks while every test stays green.
- **Automated check:** `anti-slop verify` ([gates/verify.py](../gates/verify.py), [docs/verify-recipes.md](verify-recipes.md)) for Tier 1 live E2E receipts; `STRUCT-TEST-THEATER` (warning by default; catches zero-assertion tests, tautologies like `assert x == x`, and `>= 3` mocks with zero real value assertions); Python + JS/TS diff-scoped mutation via `anti-slop mutate` ([gates/mutate.py](../gates/mutate.py)); and `EV1`/`EV2` mutation scoring (`>= 65%` kill rate) in `benchmarks/evolution.py` and `benchmarks/graders/grade_ev2.py`.

**Looks convincing (Tier 3 theater: passes even if `calculate_tax` returns the wrong number):**

```python
@patch("app.db.save")
@patch("app.email.send")
@patch("app.metrics.record")
def test_checkout(mock_metrics, mock_email, mock_db):
    run_checkout(order_id="ord_1")
    mock_db.assert_called_once()
```

**Actually clean (Tier 2 behavioral test: runs real logic and proves output and boundary behavior):**

```python
def test_checkout_applies_tax_and_records_total():
    ledger = InMemoryLedger()
    receipt = run_checkout(ledger, items=[{"unit_cents": 1000, "qty": 2}], tax_bps=825)
    assert receipt["subtotal_cents"] == 2000
    assert receipt["tax_cents"] == 165
    assert receipt["total_cents"] == 2165
    assert ledger.get(receipt["id"])["total_cents"] == 2165
```

---

### 3. Fail loudly instead of hiding errors behind silent fallback defaults or bare suppressions

- **Provenance:** `Local measured (EV1: KEEP)` (`DIFF-SUPPRESSION` mechanical enforcement) + `Candidate (untriggered in EV1/EV2)` / `Practitioner hypothesis` (`STRUCT-SILENT-FALLBACK` silent catches)
- **Evidence:**
  - `Local measured (EV1: KEEP)`: In `pilot-evolution-v0.7.0` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [docs/evidence.md#local-07](evidence.md#local-07)), `gated-structural` caught **`15`** pre-repair `DIFF-SUPPRESSION` violations and eliminated all **`113/113`** bare `# type: ignore[...]` suppression findings seen across `baseline` (`71`) and `core-rules-v0.2.0` (`42`).
  - `Candidate (untriggered in EV1/EV2)` / `Practitioner hypothesis`: Across all 72 `EV1` and `EV2` runs (`36` Python + `36` TypeScript), `0` runs introduced broad silent `except`/`catch` fallback blocks (`STRUCT-SILENT-FALLBACK`), and all 36 `EV2` runs had `0` `DIFF-*` shortcut/suppression noise, so neither suite provides a local causal test of silent-catch fallbacks yet. Observational studies document error-handling omissions as recurring AI defects, including missing error handling among 364 AI build smells in Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [docs/evidence.md#ext-15](evidence.md#ext-15)) and exception/error-handling categories in the 87-issue developer taxonomy of Tufano et al. ([arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [docs/evidence.md#ext-15](evidence.md#ext-15)). Treat silent-fallback compounding as an informed hypothesis until triggered in harder multi-service benchmarks.
- **How it compounds:** Silent fallbacks keep a quick demo from crashing, so future AI turns assume the returned `0`, `""`, or `"dev-secret"` is valid data and build more business logic on top of corrupted state. When bugs surface later, the original stack trace is gone.
- **Automated check:** `DIFF-SUPPRESSION` and `DIFF-SILENT-CATCH` (blocking errors for bare `# type: ignore`/`# noqa`, `except Exception: pass`, and empty JS/TS `catch {}`) and `STRUCT-SILENT-FALLBACK` (warning for broad catches returning silent literals and hardcoded fallbacks on sensitive env vars like `JWT_SECRET` or `API_KEY`).

**Looks convincing (never crashes during a quick smoke run):**

```python
JWT_SECRET = os.environ.get("JWT_SECRET", "local-dev-secret")

def get_discount_bps(coupon_code: str) -> int:
    try:
        return lookup_coupon(coupon_code).discount_bps
    except Exception:
        return 0
```

**Actually clean (fails closed on missing secrets, narrows expected errors):**

```python
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Missing required JWT_SECRET environment variable")

def get_discount_bps(coupon_code: str) -> int:
    try:
        return lookup_coupon(coupon_code).discount_bps
    except KeyError:
        return 0
```

---

### 4. Keep one canonical copy of business logic

- **Provenance:** `Local measured (EV2: KEEP)` + `Local measured` (OSS audit) + `External empirical study`
- **Evidence:**
  - `Local measured (EV2: KEEP)`: In TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [docs/evidence.md#local-09](evidence.md#local-09)), copy-pasted 6-statement booking logic across `bookings.ts` and `corporate.ts` was the #1 compounding failure mode: **`6`** duplicate blocks in `baseline` (`4` on `gemini-4-neon`, `2` on `claude-opus-5-5`) and **`2`** in `core-rules-v0.2.0` (`1` Neon, `1` Opus) dropped to **`0`** under `gated-structural` (`7/12 -> 10/12 -> 12/12` on `no_duplicate_code_growth`). Mid-evolution gate review caught `3` pre-repair `STRUCT-DUPLICATE-BLOCK` hits on Neon in Stages 2-3, eliminating all duplicates cleanly while cutting Neon's tokens `-10.9%` vs. baseline. (In Python `EV1`, `0` runs triggered `STRUCT-DUPLICATE-BLOCK`.)
  - `Local measured` (OSS audit): In our 150-commit OSS precision audit ([gates/README.md](../gates/README.md)), `STRUCT-DUPLICATE-BLOCK` also caught `4` real mirrored-adapter duplicates in `hono` where every bugfix had to be pasted identically into two locations.
  - `External empirical study`: GitClear's 2025 analysis of 211M changed lines ([gitclear.com/ai_assistant_code_quality_2025_research](https://www.gitclear.com/ai_assistant_code_quality_2025_research), [docs/evidence.md#ext-12](evidence.md#ext-12)) tracked copy-pasted lines rising from `8.3%` to `12.3%` while moved/refactored lines fell from `24.1%` to `9.5%`. Liu et al. ([arXiv:2603.28592](https://arxiv.org/abs/2603.28592), [docs/evidence.md#ext-15](evidence.md#ext-15)) analyzed 302.6k verified AI commits across 6,299 GitHub repos and found code smells made up `89.3%` of 484,366 introduced issues, with `22.7%` still surviving at `HEAD`.
- **How it compounds:** When the same pricing or validation rule lives in two files, the next AI turn fixes an edge case in whichever file it opened and silently leaves the second copy broken.
- **Automated check:** `STRUCT-DUPLICATE-BLOCK` (alpha-normalized Python AST clone detector that catches variable-renamed copy-paste across files or functions, plus normalized JS/TS/Go block checks).

**Looks convincing (each file works on its own, variables renamed):**

```python
# orders.py
def price_order(items, tax_bps):
    subtotal = 0
    for item in items:
        if item["qty"] <= 0:
            raise ValueError("invalid qty")
        subtotal += item["unit_cents"] * item["qty"]
    tax = (subtotal * tax_bps + 5000) // 10000
    return subtotal + tax

# upgrades.py (copy-pasted with renamed variables)
def price_upgrade(lines, rate_bps):
    base = 0
    for row in lines:
        if row["qty"] <= 0:
            raise ValueError("invalid qty")
        base += row["unit_cents"] * row["qty"]
    fee = (base * rate_bps + 5000) // 10000
    return base + fee
```

**Actually clean (one shared helper, one place to fix rounding or tax rules):**

```python
# pricing.py
def calculate_total_cents(line_items, tax_bps: int) -> int:
    subtotal = 0
    for row in line_items:
        if row["qty"] <= 0:
            raise ValueError("invalid qty")
        subtotal += row["unit_cents"] * row["qty"]
    tax = (subtotal * tax_bps + 5000) // 10000
    return subtotal + tax
```

---

### 5. Delete dead code and legacy shims completely

- **Provenance:** `Local measured (EV1: KEEP)` + `External empirical study`
- **Evidence:**
  - `Local measured (EV1: KEEP)`: In `pilot-evolution-v0.7.0` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [docs/evidence.md#local-07](evidence.md#local-07)), `STRUCT-DEAD-COMPAT` caught **`10`** pre-repair instances mid-evolution (primarily at Stage 2) when models propagated `legacy_flat_fee` into newly added helpers before Turn 4 deprecated it, keeping legacy paths isolated without breaking `144/144` stage functional tests (at Stage 4, where the prompt explicitly requested removal, all 36 runs scored `dead = 0`).
  - `External empirical study`: Sun et al. at ETH Zurich ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [docs/evidence.md#ext-12](evidence.md#ext-12)) measured a `35.4%` average secure-code gap on C/C++ repo tasks (`25-49pp` model range; `3.4%` average backend drop) when an insecure neighbor existed in the repository; `76.5%` of agents attributed their choices to following another code site even while recognizing the vulnerability in `69.9%` of cases.
  - `External empirical study`: *A.S.E 2.0 / CASE-Bench* (Yu et al., [arXiv:2611.06294](https://arxiv.org/abs/2611.06294), [docs/evidence.md#ext-12](evidence.md#ext-12)) found inserting just one insecure exemplar increased correct-but-exploitable code by `+6.3pp` across 145 CVE-derived tasks.
- **How it compounds:** Agents cannot reliably tell abandoned code from active code. Leftover `*_legacy` helpers, `allow_legacy_mode` flags, and `if False:` branches become live few-shot examples that later sessions imitate or accidentally wire back in.
- **Automated check:** `STRUCT-DEAD-COMPAT` (catches unreachable constant-False branches, unreferenced `*_legacy`/`*_compat`/`*_deprecated` symbols, boolean legacy flags, and orphaned private helpers).

**Looks convincing ("safe" migration that keeps the old path around):**

```python
def charge_legacy(amount_cents: int) -> int:
    return amount_cents + 99  # flat fee from v1

def charge(amount_cents: int, allow_legacy_fee: bool = False) -> int:
    if False:
        return charge_legacy(amount_cents)
    return apply_tiered_fee(amount_cents)
```

**Actually clean (subtractive removal once callers are migrated):**

```python
def charge(amount_cents: int) -> int:
    return apply_tiered_fee(amount_cents)
```

---

### 6. Keep changes focused and modules small enough to fit cleanly in one turn

- **Provenance:** `Local measured (EV1 & EV2: KEEP)` (`STRUCT-GOD-FUNCTION`) + `External empirical study` + `Local measured` (OSS threshold calibration)
- **Evidence:**
  - `Local measured (EV1 & EV2: KEEP)`:
    - In Python `EV1` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [docs/evidence.md#local-07](evidence.md#local-07)), `gemini-4-neon` grew a god function (`68L-75L`) on `3/3` `baseline` and `3/3` `core-rules-v0.2.0` runs; `gated-structural` caught **`5`** `STRUCT-GOD-FUNCTION` findings (`upgrade_subscription` at Stage 2 across `3/3` replicates), cutting Neon god functions from **`3/3` to `0/3`** (`maxFnL 75L -> 49L`) and lifting Neon to `3/3` pass and `82.2%` mutation kill rate (`+11.1pp` vs. baseline, `+13.3pp` vs. prompts).
    - In TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [docs/evidence.md#local-09](evidence.md#local-09)), **`4`** `baseline` god functions (`3` Neon, `1` Opus) and **`3`** `core-rules-v0.2.0` god functions (`3` Neon) dropped to **`0`** under `gated-structural` (`8/12 -> 9/12 -> 12/12` on `no_sprawl_or_god_functions`). Mid-evolution gate review flagged `createGroupBooking` (`72L-77L` in `corporate.ts`) at Stage 2 across `3/3` Neon replicates, lifting Neon from `0/3` to `3/3` and `+21.67pp` JS/TS mutation kill (`58.3% -> 80.0%`). `STRUCT-GOD-FILE` and `STRUCT-SCOPE-SPRAWL` had `0` hits across `EV1` and `EV2`.
  - `External empirical study`: *SlopCodeBench* (Orlanski et al., [arXiv:2603.24755](https://arxiv.org/abs/2603.24755), [docs/evidence.md#ext-07](evidence.md#ext-07)) observed structural erosion rising in `77%` and verbosity in `75.5%` of iterative trajectories (agent code was `2.3x` more verbose and `2.0x` more eroded than 473 OSS Python repos). Zhu, Tsantalis, & Rigby ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [docs/evidence.md#ext-15](evidence.md#ext-15)) established a Volume-Quality Inverse Law and Reasoning-Complexity Trade-off where larger generated volumes strongly predict architectural degradation.
  - `Local measured`: Our 150-commit OSS precision audit ([gates/README.md](../gates/README.md)) also showed that mature OSS repos legitimately edit pre-existing 800-to-1,900-line files, which is why size checks stay warning-only by default.
- **How it compounds:** Each AI turn bolts one more `if` branch onto a 100-line function instead of clarifying boundaries, until neither humans nor agents can predict side effects.
- **Automated check:** `STRUCT-GOD-FUNCTION` (`> 60` code lines or `> 12` branches `[Heuristic]`), `STRUCT-GOD-FILE` (growing files `> 400` code lines `[Heuristic]`), and `STRUCT-SCOPE-SPRAWL` (`> 3` unrelated production module areas in one diff `[Heuristic]`).

---

### 7. Put mechanical rules in tools, not standing prompt files alone

- **Provenance:** `Local measured (EV1 & EV2: KEEP)` + `Local measured` (`v0.6.0`) + `External empirical study`
- **Evidence:**
  - `Local measured (EV1 & EV2: KEEP)`:
    - In Python `EV1` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [docs/evidence.md#local-07](evidence.md#local-07)), standing prose rules alone (`core-rules-v0.2.0`) **regressed** overall pass rate (`50.0% -> 41.7%`, `+1/-2`) and weakened mean mutation kill rate (`70.6% -> 67.2%`), scoring **`DROP`** on both `claude-opus-5-5` (`66.7% -> 60.0%`) and `gpt-6.2-sol` (`77.8% -> 68.9%`). Mechanical gating (`gated-structural`, zero standing prompt bloat) lifted pass rate to **`91.7%` (`11/12`, `0` slop, `74.7%` mutation kill = `+7.5pp` vs. prompts)** at `+1.7%` Stage 1-4 wall time (while spending `+18.7%` to `+43.8%` extra tokens / `+11.3%` Opus USD across `15` repair turns).
    - In TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [docs/evidence.md#local-09](evidence.md#local-09)), standing prose (`core-rules-v0.2.0`) moved pass rate by only 1 run (`7/12 [58.3%] -> 8/12 [66.7%]`, aggregate **`INCONCLUSIVE`**) while inflating aggregate tokens **`+13.0%`**, Opus USD **`+11.6%`**, and wall time **`+9.6%`**. Mechanical gating (`gated-structural`) hit **`12/12` (`100.0%`)** with `0` slop (`KEEP` vs. baseline, `+5.00pp` TS mutation kill) while costing **less** than standing prompts on every axis (**`-10.4%`** tokens, **`-8.5%`** Opus USD, **`-6.8%`** wall time vs. `core-rules-v0.2.0`, and only `+1.2%` tokens / `+2.2%` Opus USD / `+2.1%` wall vs. baseline).
  - `Local measured`: In `pilot-3way-v0.6.0` ([results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md), [docs/evidence.md#local-05](evidence.md#local-05)), per-model prompt overlays tied `core-rules-v0.2.0` on 3 of 4 models while adding matched token overhead, and prompt rules alone still failed `8/9` Opus `SE2` runs.
  - `External empirical study`: *IFScale* (Jaroslawicz et al., [arXiv:2507.11538](https://arxiv.org/abs/2507.11538), [docs/evidence.md#ext-11](evidence.md#ext-11)) found frontier models drop to `68%` accuracy at 500 simultaneous constraints with primacy bias; Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [docs/evidence.md#ext-11](evidence.md#ext-11)) found `AGENTS.md` files did not generally improve task success while raising inference cost `>20%`; Lulla et al. ([arXiv:2601.20404](https://arxiv.org/abs/2601.20404), [docs/evidence.md#ext-11](evidence.md#ext-11)) showed concise operational maps cut median runtime `28.64%` and output tokens `16.58%`; Tsuchida et al. ([arXiv:2611.04367](https://arxiv.org/abs/2611.04367), [docs/evidence.md#ext-11](evidence.md#ext-11)) showed conditional phrasing underperforms direct prescriptive rules; and Zhu et al. ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [docs/evidence.md#ext-15](evidence.md#ext-15)) showed detailed prompting alone does not prevent architectural decay.
- **How it compounds:** Dumping every one-off lesson into `AGENTS.md` or `CLAUDE.md` dilutes the rules that actually matter and makes agents ignore constraints buried in the middle.
- **Automated check:** Keep standing instructions short (`standard/core.md` is capped at `<= 300` words) and use `gates/learn.py` (`anti-slop learn`) to enforce the narrowest prevention first: deterministic check (zero prompt tokens) -> canonical codebase example -> short (`<= 45` words) prompt rule only as a last resort, with a mandatory retirement trigger.

---

### 8. Comment Hygiene: Delete Commented-Out Code and Stale Narration; Keep Short Invariant "Why" Comments

- **Provenance:** `Local measured (CM1 & CM2: overhead confirmed, accuracy ceiling)` + `External empirical study`
- **Evidence:** Both extremes ("write verbose comments everywhere" and "strip all comments blindly") are refuted by external empirical studies ([docs/evidence.md#ext-14](evidence.md#ext-14)), and our two controlled identical-AST ablations across **72 runs** (`CM1` + `CM2`, [LOCAL-06](evidence.md#local-06) & [LOCAL-08](evidence.md#local-08)) replicate the speed/cost win of brief invariant notes and the tax of comment traps:
  - **`Local measured (CM1 & CM2: 72 runs, 24/24 accuracy ceiling)`:**
    - `CM1` ([results/pilot-comments-v0.7.0/README.md](../results/pilot-comments-v0.7.0/README.md), [LOCAL-06](evidence.md#local-06), 1 module / 90L with explicit invariants in prompt): `12/12` accuracy across all 3 arms; `invariant-comments` (3 `# INVARIANT:` notes preserved verbatim on `12/12` runs) was fastest and cheapest at **`-4.5%`** wall time (`394.3s` vs. `413.0s`) and **`-1.7%`** Opus USD (`$0.3953` vs. `$0.4022`), while `comment-traps` was slowest on **4/4 models** (`+26.8%` wall vs. `no-comments`, `+32.8%` vs. `invariant-comments`; **`+31.5%`** Opus USD [`$0.5288`]; `-28` deleted comment lines on `12/12` runs).
    - `CM2` ([results/pilot-comments-v0.8.0/README.md](../results/pilot-comments-v0.8.0/README.md), [LOCAL-08](evidence.md#local-08), 6 interacting modules / 345L with both cross-file invariants omitted from the prompt): `12/12` accuracy ceiling persisted across all 3 arms (`24/24` combined); `invariant-comments` (4 `# INVARIANT:` notes) again ran fastest and cheapest at **`-6.8%`** wall time (`1,262.8s` vs. `1,354.6s`, `-8.4%` vs. `comment-traps`) and **`-2.4%`** Opus USD (`$0.9344` vs. `$0.9569`, `-16.1%` vs. `comment-traps`), while `comment-traps` inflated Opus USD **`+16.4%`** (`$1.1135`, `+19.2%` vs. `invariant-comments`), slowed Opus (`+9.9%`) and Sol (`+19.3%`), and forced **`-20..-67`** deleted comment lines (`-67` on `9/12` runs). Notably, `gpt-6.2-sol` stripped all 4 `# INVARIANT:` notes during refactoring on `3/3` `CM2` runs (`9/12` runs preserved all 4).
    - Separately, `STRUCT-COMMENTED-CODE` recorded `0` false positives across 150 OSS commits and 551 OSS HEAD files ([gates/README.md](../gates/README.md)).
  - **Why commented-out code and stale comments hurt (`External empirical study`):** Huang et al., *Comment Traps* (FSE 2026, [arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [docs/evidence.md#ext-14](evidence.md#ext-14)) found defective commented-out code in context drives AI coding assistants (GitHub Copilot, Cursor) to generate defective code at rates up to **`58.17%`**, actively completing partial bugs rather than merely copying verbatim; even explicit prompt instructions to ignore defective commented-out code cut defects by at most **`21.84%`**. Xia et al., *When Comments Mislead* (ASE 2026, [doi:10.1145/3832783.3834359](https://doi.org/10.1145/3832783.3834359), [docs/evidence.md#ext-14](evidence.md#ext-14)) showed outdated natural-language comments bias completions toward historical implementations, causing subtle bugs specifically in changed regions.
  - **Why blanket comment deletion ALSO hurts (`External empirical study`):** Vitale et al. (ICPC 2026, [arXiv:2601.23059](https://arxiv.org/abs/2601.23059), [docs/evidence.md#ext-14](evidence.md#ext-14)) found accurate code comments improved automated bug-fixing accuracy by **up to threefold** when present in training and inference (without degrading comment-free inputs). Thornton ([arXiv:2602.16741](https://arxiv.org/abs/2602.16741), [docs/evidence.md#ext-14](evidence.md#ext-14)) tested 14,012 security-review trials and found **blind comment stripping reduced vulnerability detection on weaker models** by removing helpful context.
- **How it compounds:** Leaving a commented-out prototype or a stale comment ("webhooks always arrive in order") in a file biases later AI turns to reintroduce the deleted bug or "simplify away" a critical guard. Deleting non-obvious external invariant notes leaves later turns guessing why a weird check exists and removing it as "redundant."
- **Rule of thumb:** Delete commented-out code blocks (git history keeps old code) and line-by-line narration that restates syntax. Keep crisp 1-to-2 line `# INVARIANT:` / "why" comments explaining non-obvious external contracts, ordering guarantees, or domain math, and update or remove them in the same diff whenever code changes.
- **Automated check:** `STRUCT-COMMENTED-CODE` (warning by default in `gates/structural.py`, promoted to error with `--strict-structural`; catches multi-line commented-out executable code while allowing short prose/invariant comments, docstrings, and headers).

**Looks convincing (comment trap + stale misleading narration):**

```python
# Webhooks arrive strictly in chronological order from the payment gateway.
# Old prototype (keep just in case):
# def apply_event(sub, event):
#     sub.status = event["status"]
#     sub.balance = float(event["amount"]) / 100.0
#     return sub

def apply_event(sub, event):
    # Check timestamp
    if event["created_at"] < sub.last_event_at:
        return sub
    # Set new status
    sub.status = event["status"]
    sub.last_event_at = event["created_at"]
    return sub
```

**Actually clean (commented-out trap deleted, short invariant "why" comment kept):**

```python
def apply_event(sub, event):
    # INVARIANT: gateway retries deliver webhooks out of order; ignore stale events
    # so a delayed failure webhook cannot overwrite a newer paid status.
    if event["created_at"] < sub.last_event_at:
        return sub
    sub.status = event["status"]
    sub.last_event_at = event["created_at"]
    return sub
```

---

### 9. Prevent Architectural Coupling: Circular Imports, Speculative Single-Impl Wrappers, and Scattered Config Boundaries

- **Provenance:** `External empirical study` + `Candidate (untriggered in EV2)` (`Local measured` OSS precision: `0` FPs across 150 commits, `7/7` TP runtime cycles in `hono` HEAD)
- **Evidence:**
  - `External empirical study`: Zhu, Tsantalis, & Rigby ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [docs/evidence.md#ext-15](evidence.md#ext-15)) documented tight cross-module coupling and architectural erosion across agent-generated multi-file systems even when functional tests pass.
  - `Local measured` (OSS precision audit) & `Candidate (untriggered in EV2)`: In `0.8.0`, `gates/architecture.py` (wired into `gates/structural.py`, `gates/diff_check.py --structural`, and `gates/review.py`, warning-first by default) audited **150 non-merge OSS commits** (`urllib3`, `tomlkit`, `hono`: **`0` FPs**), **316 OSS HEAD production files** (`7/7` verbatim-verified true runtime circular imports in `hono`, `0` FPs), and `anti-slop` itself (`0` hits; full audit in [gates/README.md](../gates/README.md#architectural-gates-gatesarchitecturepy-oss-precision-audit)). All three `ARCH-*` rules had `0` triggers across the 48 `EV2` stages, so their causal lift on multi-turn benchmarks remains tagged `External empirical study / Candidate` until triggered in harder cross-service evolution suites.
- **How it compounds:** Circular runtime imports cause fragile load-order crashes when a future AI turn refactors an export; speculative single-implementation `*Factory`/`*Wrapper` layers inflate context hops without adding extensibility; and reading the same raw `os.environ` / `process.env` key across `>= 3` production files lets future turns diverge on defaults, parsing, and fail-closed validation.
- **Automated checks ([gates/architecture.py](../gates/architecture.py), warning by default, blocking under `--strict-structural`):**
  - `ARCH-CIRCULAR-IMPORT`: Static runtime import graph across Python (`ast.Import` / `ast.ImportFrom`, skipping `if TYPE_CHECKING:`, `__main__`, deferred function-local imports, and tests) and JS/TS (`import`/`export`/`require`, skipping `import type` / `export type` and tests) reporting canonical minimal cycles involving a changed file.
  - `ARCH-SINGLE-IMPL-WRAPPER`: Flags speculative Python `ABC`/`Protocol` (`<= 1` concrete impl) or trivial pass-through `*Factory`/`*Wrapper`/`*Impl` wrappers and JS/TS method-bearing `abstract class` / single-impl service wrappers, while exempting `__all__` exports, `>= 2` concrete implementations, dataclasses/NamedTuples/TypedDicts, and plain data DTO `interface` declarations.
  - `ARCH-BOUNDARY-SCATTER`: Flags diffs that scatter reads of the same raw environment variable (`os.environ`/`os.getenv` or `process.env`) across `>= 3` distinct production modules instead of centralizing config validation in one boundary module (exempting universal runtime env vars like `PATH`, `HOME`, `CI`, `NODE_ENV`, `TZ`, `DEBUG`).

---

## Part 2: Pre-AI Habits to Avoid in AI Workflows

The five practices below were reasonable trade-offs in some pre-AI human codebases, but they work against AI coding workflows. Each carries its exact provenance tag so you can tell which ones are empirically measured and which remain practitioner hypotheses.

### A. Premature abstraction and single-implementation dependency-injection layers

- **Provenance:** `Practitioner hypothesis` + `Candidate (untriggered in EV2)`
- **Evidence:** There is no controlled study isolating single-use DI/factory wrappers in coding agents, and `ARCH-SINGLE-IMPL-WRAPPER` had `0` triggers across `EV2` (`0` FPs across 150 OSS commits and 316 OSS HEAD files; [gates/README.md](../gates/README.md#architectural-gates-gatesarchitecturepy-oss-precision-audit)). The hypothesis aligns with general long-context dilution findings in *Lost in the Middle* (Liu et al., [arXiv:2307.03172](https://arxiv.org/abs/2307.03172), [docs/evidence.md#ext-11](evidence.md#ext-11)) and Chroma's *Context Rot* ([trychroma.com/research/context-rot](https://www.trychroma.com/research/context-rot), [docs/evidence.md#ext-11](evidence.md#ext-11)), and should be treated as an engineering heuristic rather than a proven law.
- **Why it hurts AI coding:** Splitting a 15-line operation across `IInvoiceRepository`, `AbstractInvoiceRepository`, `InvoiceRepositoryFactory`, and `PostgresInvoiceRepository` forces every future AI turn to read four files just to trace one query. When an agent hits context pressure, it frequently invents a parallel helper instead of wiring through the indirection.
- **Automated check:** `ARCH-SINGLE-IMPL-WRAPPER` ([gates/architecture.py](../gates/architecture.py), warning-first by default) catches single-implementation `ABC`/`Protocol` wrappers and trivial `*Factory`/`*Wrapper` classes while exempting `__all__` public interfaces, `>= 2` concrete implementations, dataclasses/NamedTuples/TypedDicts, and plain TS data DTO interfaces.

**Pre-AI over-abstraction (4 layers for 1 implementation):**

```python
class TaxStrategy(Protocol):
    def compute(self, cents: int) -> int: ...

class StandardTaxStrategy:
    def compute(self, cents: int) -> int:
        return (cents * 825 + 5000) // 10000

class TaxStrategyFactory:
    @staticmethod
    def create(kind: str = "standard") -> TaxStrategy:
        return StandardTaxStrategy()
```

**AI-era clean code (direct until a second real implementation exists):**

```python
def compute_tax_cents(subtotal_cents: int, tax_bps: int) -> int:
    return (subtotal_cents * tax_bps + 5000) // 10000
```

---

### B. Defensive catch-all fallbacks ("never let a helper throw")

- **Provenance:** `Practitioner hypothesis` + `Candidate (untriggered in EV1/EV2)`
- **Evidence:** No controlled trial yet measures causal defect propagation from catch-all fallbacks in AI-authored repos, and `0` runs across all 72 `EV1` and `EV2` runs introduced broad silent `except`/`catch` fallbacks ([LOCAL-07](evidence.md#local-07), [LOCAL-09](evidence.md#local-09)). Observational studies document missing error handling in AI build code (Ghammam & Almukhtar, [arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [docs/evidence.md#ext-15](evidence.md#ext-15)) and error-handling faults in AI issue taxonomies (Tufano et al., [arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [docs/evidence.md#ext-15](evidence.md#ext-15)).
- **Why it hurts AI coding:** Human teams sometimes wrapped helpers in broad `try/except` blocks to avoid crashing a UI. When an AI coding tool follows that habit, it masks typos, schema mismatches, and missing auth keys behind `return 0` or `return None`. The test suite sees no crash, and the real bug silently propagates across turns.

---

### C. Mock-everything "pure" unit tests

- **Provenance:** `Local measured (EV1 & EV2: KEEP)` + `External empirical study`
- **Evidence:** In `EV1` ([LOCAL-07](evidence.md#local-07)), `gated-structural` caught an assertion-free smoke test (`STRUCT-TEST-THEATER`, `1 -> 0`) and lifted Python AST mutation kill rate `+7.5pp` vs. standing prompts (`74.7%` vs. `67.2%`); in `EV2` ([LOCAL-09](evidence.md#local-09)), `gated-structural` lifted JS/TS mutation kill rate `+5.0pp` vs. baseline (`79.2%` vs. `74.2%`, with `gemini-4-neon` jumping `+21.7pp` from `58.3%` to `80.0%`). Hora & Robbes (MSR 2026, [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)) measured higher agent mocking rates (`36%` vs. `26%` human; `68%` of agent-test repos); *MutGen* ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)) showed high line coverage can coexist with `4%` mutant kill rate; *UTBoost* ([arXiv:2506.09289](https://arxiv.org/abs/2506.09289), [docs/evidence.md#ext-12](evidence.md#ext-12)) showed weak unit tests passed 345 buggy patches on SWE-bench.
- **Why it hurts AI coding:** Classic "isolate every collaborator with a mock" dogma rewards AI agents for testing their own mock setup instead of real code. If you mock the parser, the calculator, and the storage layer in one test, refactoring any of them breaks the mocks while real bugs slip through untouched. Follow the 3-tier verification hierarchy in Rule 2 above (`anti-slop verify` + `anti-slop mutate`).

---

### D. Keeping deprecated compatibility paths "just in case"

- **Provenance:** `Local measured (EV1: KEEP)` + `External empirical study`
- **Evidence:** In `EV1` ([LOCAL-07](evidence.md#local-07)), `STRUCT-DEAD-COMPAT` caught `10` mid-evolution instances of `legacy_flat_fee` leaking into newly added helpers before Turn 4 deprecated it. Externally, Sun et al. / ETH Zurich ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [docs/evidence.md#ext-12](evidence.md#ext-12): `76.5%` attributed vulnerable choices to imitating another code site), *A.S.E 2.0 / CASE-Bench* ([arXiv:2611.06294](https://arxiv.org/abs/2611.06294), [docs/evidence.md#ext-12](evidence.md#ext-12): `+6.3pp` exploitable code from one insecure exemplar), and *Comment Traps* ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [docs/evidence.md#ext-14](evidence.md#ext-14): up to `58.17%` defect rate from inactive defective code) document the imitation mechanism.
- **Why it hurts AI coding:** In a human-only repo, an unused `compute_v1_compat()` helper is mostly harmless dust. In an AI-assisted repo, retrieval pulls it into context, and later sessions copy its outdated assumptions or apply new bugfixes to the dead path instead of the live one. Delete obsolete paths cleanly once callers are migrated (git history preserves old code if you ever need it).

---

### E. Blanket style rules and standing prompt checklists alone

- **Provenance:** `Local measured (EV1 & EV2: KEEP)` + `Local measured` (`v0.6.0`) + `External empirical study`
- **Evidence:** In Python `EV1` ([LOCAL-07](evidence.md#local-07)), standing prose rules alone (`core-rules-v0.2.0`) regressed overall pass rate (`50.0% -> 41.7%`) and scored `DROP` on both `claude-opus-5-5` and `gpt-6.2-sol`, while mechanical gates (`gated-structural`) reached `91.7%` (`11/12`, `0` slop). In TypeScript `EV2` ([LOCAL-09](evidence.md#local-09)), standing prose alone (`core-rules-v0.2.0`) scored `INCONCLUSIVE` (`66.7%`) while increasing aggregate tokens `+13.0%` and Opus USD `+11.6%`, whereas `gated-structural` reached **`100.0%` (`12/12`, `0` slop)** at **`-10.4%`** fewer tokens and **`-8.5%`** lower Opus USD than standing prompts. Frontier models also fail in opposing directions ([docs/models.md](models.md)): OpenAI warns legacy *"be concise"* prompts strip caveats on GPT-6.2 ([Using GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.2-astra), [docs/evidence.md#oai-02](evidence.md#oai-02)); Anthropic documents choppy prose under rigid style rules on Fable 5.2 ([Prompting Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2), [docs/evidence.md#ant-04](evidence.md#ant-04)) and brittle workarounds under unqualified `ALWAYS`/`NEVER` lists on Opus 5.5 ([Prompting Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5), [docs/evidence.md#ant-02](evidence.md#ant-02)); *IFScale* ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538)) and Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [docs/evidence.md#ext-11](evidence.md#ext-11)) measure compliance drop and `>20%` cost rise from bloated instructions; and `pilot-3way-v0.6.0` ([docs/evidence.md#local-05](evidence.md#local-05)) confirmed model overlays only moved pass rate on 1 of 4 models.
- **Why it hurts AI coding:** Prefer automated gates for objective checks, short model-specific overlays only where measured, and clean retirement when newer models outgrow a rule.

---

## Part 3: Optional Rule Library and How Rules Earn Their Keep (`EV1` & `EV2`)

Not every rule belongs in the default core. The opt-in library in [library/README.md](../library/README.md) separates **Default Core** (`15` `DIFF-*` checks, `11` Layer B `STRUCT-*` + `ARCH-*` checks, `standard/core.md` `R1`-`R7`), **Optional Packs** (`6` curated packs / `10` `OPT-*` rules enabled via `anti-slop learn library list|show|enable`), and **Deliberately Excluded** items (`6` `EXCL-*` entries such as statistical AI-text detectors with `61.22%` non-native English false positives per Liang et al. [arXiv:2304.02819](https://arxiv.org/abs/2304.02819), [docs/evidence.md#ext-13](evidence.md#ext-13), or unfiltered blocking SAST hooks per Firouzi & Ghafari [arXiv:2602.05868](https://arxiv.org/abs/2602.05868), [docs/evidence.md#ext-13](evidence.md#ext-13)).

Any rule without `Local measured` causal proof remains a **hypothesis** or **candidate**, not settled truth. Across **72 live 4-turn evolution runs (`288` base stages, zero word caps)** spanning Python `EV1` ([results/pilot-evolution-v0.7.0/README.md](../results/pilot-evolution-v0.7.0/README.md), [benchmarks/cases/EV1.json](../benchmarks/cases/EV1.json)) and TypeScript `EV2` ([results/pilot-ts-evolution-v0.8.0/README.md](../results/pilot-ts-evolution-v0.8.0/README.md), [benchmarks/cases/EV2.json](../benchmarks/cases/EV2.json)):

1. **Python `EV1` (`36` runs):** `baseline` **`50.0%` (`6/12`)** -> `core-rules-v0.2.0` **`41.7%` (`5/12`, `DROP` on Opus & Sol)** -> `gated-structural` **`91.7%` (`11/12`, `KEEP`)**, cutting slop `75 -> 45 -> 0` and lifting Python AST mutation kill to **`74.7%`** (`+7.5pp` vs. prompts; `+18.7%` to `+43.8%` repair tokens / `+11.3%` Opus USD; lone miss `gpt-6.2-sol r1` at `60.0%` mut).
2. **TypeScript `EV2` (`36` runs):** `baseline` **`58.3%` (`7/12`)** -> `core-rules-v0.2.0` **`66.7%` (`8/12`, `INCONCLUSIVE`, `+13.0%` tokens / `+11.6%` Opus USD)** -> `gated-structural` **`100.0%` (`12/12`, `KEEP`)**, cutting slop `10 -> 5 -> 0` (`6` baseline duplicate blocks + `4` god functions -> `0`, `0` suppression noise) and lifting JS/TS mutation kill to **`79.2%`** (`+5.0pp` vs. baseline, Neon `+21.7pp`) at **`-10.4%`** fewer tokens and **`-8.5%`** lower Opus USD than standing prompts (`+1.2%` tokens vs. baseline).
3. **Untriggered rules stay labeled transparently:** `STRUCT-SILENT-FALLBACK` (`0` triggers in `EV1` & `EV2`), `ARCH-CIRCULAR-IMPORT` / `ARCH-SINGLE-IMPL-WRAPPER` / `ARCH-BOUNDARY-SCATTER` (`0` FPs across 150 OSS commits and `7/7` TP `hono` cycles, but `0` triggers in `EV2`), and premature single-use abstraction hypotheses stay tagged as candidates or practitioner hypotheses rather than claimed causal wins. Rules that fail future evolution benchmarks get retired cleanly via `gates/learn.py` or `gates/model_deltas.json`.
