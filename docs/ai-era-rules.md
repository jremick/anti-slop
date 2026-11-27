# AI-Era Coding Rules: What Helps, What Is Still a Hypothesis, and What Hurts

Traditional software best practices were written for human teams reading code slowly over months. Coding agents work differently: they read a bounded context window, imitate whatever patterns already sit in your repository, and optimize for making the immediate test run look green.

That shift changes which engineering rules pay off. Some rules matter much more in AI-assisted coding because a single shortcut compounds across every later session. Other classic habits degrade AI workflows by burning context windows, hiding real failures, or giving future sessions bad examples to copy.

Every rule and anti-pattern below carries one or more strict provenance tags so you can separate measured results from open hypotheses:

- **`Local measured`**: directly measured in our public `n = 3` benchmark ([results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md)) or our 150-commit OSS gate precision audit ([gates/README.md](../gates/README.md)).
- **`External empirical study`**: backed by peer-reviewed or preprint empirical research linked inline and tracked in [docs/evidence.md](evidence.md). Unless also tagged `Local measured`, local causal uplift in `anti-slop` remains pending multi-model `EV1` ablation (`KEEP` vs. `DROP`).
- **`Practitioner hypothesis`**: experience-based engineering hypothesis without a controlled randomized trial yet. Treat it as a testable candidate in `EV1` or local telemetry, not a settled fact.

For opt-in rule packs beyond the default core (and the list of rules we evaluated and deliberately excluded), see the optional rule library in [library/README.md](../library/README.md).

---

## Quick Map

| Pattern / Rule | Provenance | Automated check in `anti-slop` | Primary citation |
|---|---|---|---|
| 1. Never skip, waive, or weaken tests | `Local measured` + `External empirical study` | `DIFF-TEST-SKIP`, `DIFF-UNAUTHORIZED-TEST-EDIT`, `gates/hooks/` | `pilot-3way-v0.6.0` ([LOCAL-05](evidence.md#local-05)); RHB ([arXiv:2605.02964](https://arxiv.org/abs/2605.02964), [EXT-13](evidence.md#ext-13)) |
| 2. Follow the 3-tier verification hierarchy | `External empirical study` (+ `Practitioner hypothesis` for Tier 1) | `STRUCT-TEST-THEATER`, `anti-slop-mutate` ([gates/mutate.py](../gates/mutate.py)), `EV1` mutation | Hora & Robbes ([arXiv:2602.00409](https://arxiv.org/abs/2602.00409)); Petrović et al. ([arXiv:2102.11378](https://arxiv.org/abs/2102.11378)); MutGen ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [EXT-13](evidence.md#ext-13)) |
| 3. Fail loudly instead of silent fallback defaults | `Practitioner hypothesis` | `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | Observational context: Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839)); Tufano et al. ([arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [EXT-15](evidence.md#ext-15)) |
| 4. Keep one canonical copy of business logic | `External empirical study` + `Local measured` (OSS hits) | `STRUCT-DUPLICATE-BLOCK` | GitClear 2025 ([gitclear.com](https://www.gitclear.com/ai_assistant_code_quality_2025_research), [EXT-12](evidence.md#ext-12)); Liu et al. ([arXiv:2603.28592](https://arxiv.org/abs/2603.28592), [EXT-15](evidence.md#ext-15)) |
| 5. Delete dead code and legacy shims completely | `External empirical study` | `STRUCT-DEAD-COMPAT` | Sun et al. ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455)); A.S.E 2.0 / CASE-Bench ([arXiv:2611.06294](https://arxiv.org/abs/2611.06294), [EXT-12](evidence.md#ext-12)) |
| 6. Keep diffs focused and modules cohesive | `External empirical study` + `Local measured` (OSS audit) | `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, `STRUCT-SCOPE-SPRAWL` | SlopCodeBench ([arXiv:2603.24755](https://arxiv.org/abs/2603.24755), [EXT-07](evidence.md#ext-07)); Zhu et al. ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [EXT-15](evidence.md#ext-15)) |
| 7. Put mechanical rules in tools, not bloated prompts | `Local measured` + `External empirical study` | `standard/core.md` (`<= 300` words), `gates/learn.py` | `pilot-3way-v0.6.0` ([LOCAL-05](evidence.md#local-05)); IFScale ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538)); Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [EXT-11](evidence.md#ext-11)) |
| 8. Comment hygiene: delete traps, keep short "why" invariants | `External empirical study` | `STRUCT-COMMENTED-CODE` | Comment Traps ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334)); Xia et al. ([doi:10.1145/3832783.3834359](https://doi.org/10.1145/3832783.3834359)); Vitale et al. ([arXiv:2601.23059](https://arxiv.org/abs/2601.23059), [EXT-14](evidence.md#ext-14)) |
| A. Premature single-use abstractions / DI layers | `Practitioner hypothesis` | Review guidance + `R3` / `R5` (opt-in pack in [library/README.md](../library/README.md)) | Contextual only: Lost in the Middle ([arXiv:2307.03172](https://arxiv.org/abs/2307.03172)); Chroma Context Rot ([trychroma.com](https://www.trychroma.com/research/context-rot), [EXT-11](evidence.md#ext-11)) |
| B. Defensive catch-all fallbacks | `Practitioner hypothesis` | `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | Observational context: Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [EXT-15](evidence.md#ext-15)) |
| C. Mock-everything "pure" unit tests | `External empirical study` | `STRUCT-TEST-THEATER`, `anti-slop-mutate` | Hora & Robbes ([arXiv:2602.00409](https://arxiv.org/abs/2602.00409)); MutGen ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [EXT-13](evidence.md#ext-13)) |
| D. Retaining legacy shims "just in case" | `External empirical study` | `STRUCT-DEAD-COMPAT` | Sun et al. ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [EXT-12](evidence.md#ext-12)); Comment Traps ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [EXT-14](evidence.md#ext-14)) |
| E. Blanket style rules & bloated prompt checklists | `Local measured` + `External empirical study` | `standard/core.md`, `gates/learn.py` ladder | OpenAI ([Using GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.2-astra), [OAI-02](evidence.md#oai-02)); Anthropic ([Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2), [ANT-04](evidence.md#ant-04)); IFScale ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538), [EXT-11](evidence.md#ext-11)) |

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

- **Provenance:** `External empirical study` (Tiers 2 and 3; pending local `EV1` causal ablation) + `Practitioner hypothesis` (Tier 1 live-artifact preference, reinforced by compositional-failure evidence)
- **Evidence:**
  - `External empirical study`: Hora & Robbes (MSR 2026, [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)) analyzed 1.2M+ commits across 2,168 repos and found coding agents modify test files in `23%` vs. `13%` (human) of commits and add mocks in `36%` vs. `26%` (`68%` of agent-test repos).
  - `External empirical study`: *MutGen* (Wang et al., IEEE TSE, [arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)) found vanilla LLM tests average ~`53%` mutation score vs. `89.5%` with mutation feedback (and showed some `100%`-coverage suites score only `4%` on mutants). Google Critique diff-based mutation (Petrović et al., [arXiv:2102.11378](https://arxiv.org/abs/2102.11378), [docs/evidence.md#ext-13](evidence.md#ext-13)) lifted developer-rated mutant productivity from ~`15%` to `80%-89%` across >24,000 developers, and Meta ACH (Foster, Harman et al., [arXiv:2501.12862](https://arxiv.org/abs/2501.12862), [docs/evidence.md#ext-13](evidence.md#ext-13)) saw `73%` engineer acceptance.
  - `External empirical study`: *SpecBench* ([arXiv:2605.21384](https://arxiv.org/abs/2605.21384), [docs/evidence.md#ext-12](evidence.md#ext-12)) showed coding agents saturate isolated visible unit tests while failing held-out composed flows (the gap grows `+28pp` per 10x code-size increase), and *UTBoost* ([arXiv:2506.09289](https://arxiv.org/abs/2506.09289), [docs/evidence.md#ext-12](evidence.md#ext-12)) uncovered 345 erroneous patches that passed weak PR tests. *PBT-Bench* (NeurIPS 2026, [arXiv:2605.15229](https://arxiv.org/abs/2605.15229), [docs/evidence.md#ext-13](evidence.md#ext-13)) showed Hypothesis property-based scaffolding lifts mid-capability bug recall by `>20pp`.
- **The 3-Tier AI-Era Verification Hierarchy:**
  1. **Tier 1 (Strongest for apps, services, and UIs): Live end-to-end / real-artifact functional verification.** Start the real application, CLI, API server, or browser, exercise the changed flow end to end against real inputs, and capture observable output, HTTP status, database/file state, or rendered screenshot. (`Practitioner hypothesis` reinforced by *SpecBench* [arXiv:2605.21384](https://arxiv.org/abs/2605.21384), [docs/evidence.md#ext-12](evidence.md#ext-12).)
  2. **Tier 2 (Strong for logic and libraries): Behavioral integration and property tests against real code + diff-scoped mutation testing.** Exercise real code paths without mocking the system under test, encode domain invariants with property tests ([arXiv:2605.15229](https://arxiv.org/abs/2605.15229)), and verify test strength on changed lines with diff-scoped AST mutation testing (`anti-slop-mutate`, implemented in [gates/mutate.py](../gates/mutate.py), citing Google Critique [arXiv:2102.11378](https://arxiv.org/abs/2102.11378) and *MutGen* [arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)).
  3. **Tier 3 (Weakest; watch for theater): Same-turn isolated, heavily-mocked unit tests.** Useful only for narrowly scoped pure helpers or external I/O boundaries; treat passing mocked tests written in the same turn as weak evidence unless backed by Tier 1 or Tier 2 checks (Hora & Robbes [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)).
- **How it compounds:** Future AI sessions trust a green test suite. If a test only checks that a mock was called or asserts `True`, a later session can break billing math or auth checks while every test stays green.
- **Automated check:** `STRUCT-TEST-THEATER` (warning by default; catches zero-assertion tests, tautologies like `assert x == x`, and `>= 3` mocks with zero real value assertions), diff-scoped AST mutation via `anti-slop-mutate` ([gates/mutate.py](../gates/mutate.py)), and `EV1` mutation scoring (`>= 65%` kill rate) in `benchmarks/evolution.py`.

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

### 3. Fail loudly instead of hiding errors behind silent fallback defaults

- **Provenance:** `Practitioner hypothesis` (no controlled RCT yet; candidate pending `EV1`)
- **Evidence:** We do not yet have a controlled randomized trial isolating silent fallback defaults in AI-assisted coding. Observational studies note error-handling omissions as recurring AI defects, including missing error handling among 364 AI build smells in Ghammam & Almukhtar ([arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [docs/evidence.md#ext-15](evidence.md#ext-15)) and exception/error-handling categories in the 87-issue developer taxonomy of Tufano et al. ([arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [docs/evidence.md#ext-15](evidence.md#ext-15)). Treat the compounding risk below as an informed hypothesis to validate in `EV1` and local code reviews.
- **How it compounds:** Silent fallbacks keep a quick demo from crashing, so future AI turns assume the returned `0`, `""`, or `"dev-secret"` is valid data and build more business logic on top of corrupted state. When bugs surface later, the original stack trace is gone.
- **Automated check:** `DIFF-SILENT-CATCH` (blocking error for `except Exception: pass` and empty JS/TS `catch {}`) and `STRUCT-SILENT-FALLBACK` (warning for broad catches returning silent literals and hardcoded fallbacks on sensitive env vars like `JWT_SECRET` or `API_KEY`).

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

- **Provenance:** `External empirical study` + `Local measured` (OSS audit hits; causal uplift pending `EV1`)
- **Evidence:**
  - `External empirical study`: GitClear's 2025 analysis of 211M changed lines ([gitclear.com/ai_assistant_code_quality_2025_research](https://www.gitclear.com/ai_assistant_code_quality_2025_research), [docs/evidence.md#ext-12](evidence.md#ext-12)) tracked copy-pasted lines rising from `8.3%` to `12.3%` while moved/refactored lines fell from `24.1%` to `9.5%`. Liu et al. ([arXiv:2603.28592](https://arxiv.org/abs/2603.28592), [docs/evidence.md#ext-15](evidence.md#ext-15)) analyzed 302.6k verified AI commits across 6,299 GitHub repos and found code smells made up `89.3%` of 484,366 introduced issues, with `22.7%` still surviving at `HEAD`.
  - `Local measured`: In our 150-commit OSS precision audit ([gates/README.md](../gates/README.md)), `STRUCT-DUPLICATE-BLOCK` caught real mirrored adapter files where every bugfix had to be pasted identically into two locations.
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

- **Provenance:** `External empirical study` (pending local `EV1` causal ablation)
- **Evidence:**
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

- **Provenance:** `External empirical study` + `Local measured` (OSS threshold calibration; causal uplift pending `EV1`)
- **Evidence:**
  - `External empirical study`: *SlopCodeBench* (Orlanski et al., [arXiv:2603.24755](https://arxiv.org/abs/2603.24755), [docs/evidence.md#ext-07](evidence.md#ext-07)) observed structural erosion rising in `77%` and verbosity in `75.5%` of iterative trajectories (agent code was `2.3x` more verbose and `2.0x` more eroded than 473 OSS Python repos). Zhu, Tsantalis, & Rigby ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [docs/evidence.md#ext-15](evidence.md#ext-15)) established a Volume-Quality Inverse Law and Reasoning-Complexity Trade-off where larger generated volumes strongly predict architectural degradation.
  - `Local measured`: Our 150-commit OSS precision audit ([gates/README.md](../gates/README.md)) also showed that mature OSS repos legitimately edit pre-existing 800-to-1,900-line files, which is why size checks stay warning-only by default.
- **How it compounds:** Each AI turn bolts one more `if` branch onto a 100-line function instead of clarifying boundaries, until neither humans nor agents can predict side effects.
- **Automated check:** `STRUCT-GOD-FUNCTION` (`> 60` code lines or `> 12` branches `[Heuristic]`), `STRUCT-GOD-FILE` (growing files `> 400` code lines `[Heuristic]`), and `STRUCT-SCOPE-SPRAWL` (`> 3` unrelated production module areas in one diff `[Heuristic]`).

---

### 7. Put mechanical rules in tools, not bloated standing prompt files

- **Provenance:** `Local measured` + `External empirical study`
- **Evidence:**
  - `Local measured`: In `pilot-3way-v0.6.0` ([results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md), [docs/evidence.md#local-05](evidence.md#local-05)), per-model prompt overlays tied `core-rules-v0.2.0` on 3 of 4 models while adding matched token overhead, and prompt rules alone still failed `8/9` Opus `SE2` runs.
  - `External empirical study`: *IFScale* (Jaroslawicz et al., [arXiv:2507.11538](https://arxiv.org/abs/2507.11538), [docs/evidence.md#ext-11](evidence.md#ext-11)) found frontier models drop to `68%` accuracy at 500 simultaneous constraints with primacy bias; Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [docs/evidence.md#ext-11](evidence.md#ext-11)) found `AGENTS.md` files did not generally improve task success while raising inference cost `>20%`; Lulla et al. ([arXiv:2601.20404](https://arxiv.org/abs/2601.20404), [docs/evidence.md#ext-11](evidence.md#ext-11)) showed concise operational maps cut median runtime `28.64%` and output tokens `16.58%`; Tsuchida et al. ([arXiv:2611.04367](https://arxiv.org/abs/2611.04367), [docs/evidence.md#ext-11](evidence.md#ext-11)) showed conditional phrasing underperforms direct prescriptive rules; and Zhu et al. ([arXiv:2605.02741](https://arxiv.org/abs/2605.02741), [docs/evidence.md#ext-15](evidence.md#ext-15)) showed detailed prompting alone does not prevent architectural decay.
- **How it compounds:** Dumping every one-off lesson into `AGENTS.md` or `CLAUDE.md` dilutes the rules that actually matter and makes agents ignore constraints buried in the middle.
- **Automated check:** Keep standing instructions short (`standard/core.md` is capped at `<= 300` words) and use `gates/learn.py` (`anti-slop-learn`) to enforce the narrowest prevention first: deterministic check (zero prompt tokens) -> canonical codebase example -> short (`<= 45` words) prompt rule only as a last resort, with a mandatory retirement trigger.

---

### 8. Comment Hygiene: Delete Commented-Out Code and Stale Narration; Keep Short Invariant "Why" Comments

- **Provenance:** `External empirical study` (local multi-model ablation pending)
- **Evidence:** Both extremes ("write verbose comments everywhere" and "strip all comments blindly") are refuted by empirical evidence ([docs/evidence.md#ext-14](evidence.md#ext-14)):
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

## Part 2: Pre-AI Habits to Avoid in AI Workflows

The five practices below were reasonable trade-offs in some pre-AI human codebases, but they work against AI coding workflows. Each carries its exact provenance tag so you can tell which ones are empirically measured and which remain practitioner hypotheses.

### A. Premature abstraction and single-implementation dependency-injection layers

- **Provenance:** `Practitioner hypothesis` (no controlled RCT yet)
- **Evidence:** There is no controlled study isolating single-use DI/factory wrappers in coding agents. The hypothesis aligns with general long-context dilution findings in *Lost in the Middle* (Liu et al., [arXiv:2307.03172](https://arxiv.org/abs/2307.03172), [docs/evidence.md#ext-11](evidence.md#ext-11)) and Chroma's *Context Rot* ([trychroma.com/research/context-rot](https://www.trychroma.com/research/context-rot), [docs/evidence.md#ext-11](evidence.md#ext-11)), but should be treated as an engineering heuristic rather than a proven law.
- **Why it hurts AI coding:** Splitting a 15-line operation across `IInvoiceRepository`, `AbstractInvoiceRepository`, `InvoiceRepositoryFactory`, and `PostgresInvoiceRepository` forces every future AI turn to read four files just to trace one query. When an agent hits context pressure, it frequently invents a parallel helper instead of wiring through the indirection.

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

- **Provenance:** `Practitioner hypothesis` (no controlled RCT yet)
- **Evidence:** No controlled trial yet measures causal defect propagation from catch-all fallbacks in AI-authored repos. Observational studies document missing error handling in AI build code (Ghammam & Almukhtar, [arXiv:2601.16839](https://arxiv.org/abs/2601.16839), [docs/evidence.md#ext-15](evidence.md#ext-15)) and error-handling faults in AI issue taxonomies (Tufano et al., [arXiv:2611.32676](https://arxiv.org/abs/2611.32676), [docs/evidence.md#ext-15](evidence.md#ext-15)).
- **Why it hurts AI coding:** Human teams sometimes wrapped helpers in broad `try/except` blocks to avoid crashing a UI. When an AI coding tool follows that habit, it masks typos, schema mismatches, and missing auth keys behind `return 0` or `return None`. The test suite sees no crash, and the real bug silently propagates across turns.

---

### C. Mock-everything "pure" unit tests

- **Provenance:** `External empirical study`
- **Evidence:** Hora & Robbes (MSR 2026, [arXiv:2602.00409](https://arxiv.org/abs/2602.00409), [docs/evidence.md#ext-13](evidence.md#ext-13)) measured higher agent mocking rates (`36%` vs. `26%` human; `68%` of agent-test repos); *MutGen* ([arXiv:2506.02954](https://arxiv.org/abs/2506.02954), [docs/evidence.md#ext-13](evidence.md#ext-13)) showed high line coverage can coexist with `4%` mutant kill rate; *UTBoost* ([arXiv:2506.09289](https://arxiv.org/abs/2506.09289), [docs/evidence.md#ext-12](evidence.md#ext-12)) showed weak unit tests passed 345 buggy patches on SWE-bench.
- **Why it hurts AI coding:** Classic "isolate every collaborator with a mock" dogma rewards AI agents for testing their own mock setup instead of real code. If you mock the parser, the calculator, and the storage layer in one test, refactoring any of them breaks the mocks while real bugs slip through untouched. Follow the 3-tier verification hierarchy in Rule 2 above.

---

### D. Keeping deprecated compatibility paths "just in case"

- **Provenance:** `External empirical study`
- **Evidence:** Sun et al. / ETH Zurich ([arXiv:2611.11455](https://arxiv.org/abs/2611.11455), [docs/evidence.md#ext-12](evidence.md#ext-12): `76.5%` attributed vulnerable choices to imitating another code site), *A.S.E 2.0 / CASE-Bench* ([arXiv:2611.06294](https://arxiv.org/abs/2611.06294), [docs/evidence.md#ext-12](evidence.md#ext-12): `+6.3pp` exploitable code from one insecure exemplar), and *Comment Traps* ([arXiv:2512.20334](https://arxiv.org/abs/2512.20334), [docs/evidence.md#ext-14](evidence.md#ext-14): up to `58.17%` defect rate from inactive defective code).
- **Why it hurts AI coding:** In a human-only repo, an unused `compute_v1_compat()` helper is mostly harmless dust. In an AI-assisted repo, retrieval pulls it into context, and later sessions copy its outdated assumptions or apply new bugfixes to the dead path instead of the live one. Delete obsolete paths cleanly once callers are migrated (git history preserves old code if you ever need it).

---

### E. Blanket style rules and ever-growing prompt checklists

- **Provenance:** `Local measured` + `External empirical study`
- **Evidence:** Frontier models fail in opposing directions ([docs/models.md](models.md)). OpenAI warns legacy *"be concise"* prompts strip caveats on GPT-6.2 ([Using GPT-6.2](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6.2-astra), [docs/evidence.md#oai-02](evidence.md#oai-02)); Anthropic documents choppy prose under rigid style rules on Fable 5.2 ([Prompting Fable 5.2](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2), [docs/evidence.md#ant-04](evidence.md#ant-04)) and brittle workarounds under unqualified `ALWAYS`/`NEVER` lists on Opus 5.5 ([Prompting Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5), [docs/evidence.md#ant-02](evidence.md#ant-02)); *IFScale* ([arXiv:2507.11538](https://arxiv.org/abs/2507.11538)) and Gloaguen et al. ([arXiv:2602.11988](https://arxiv.org/abs/2602.11988), [docs/evidence.md#ext-11](evidence.md#ext-11)) measure compliance drop and `>20%` cost rise from bloated instructions; and `pilot-3way-v0.6.0` ([docs/evidence.md#local-05](evidence.md#local-05)) confirmed model overlays only moved pass rate on 1 of 4 models.
- **Why it hurts AI coding:** Prefer automated gates for objective checks, short model-specific overlays only where measured, and clean retirement when newer models outgrow a rule.

---

## Part 3: Optional Rule Library and How Rules Earn Their Keep (`EV1`)

Not every rule belongs in the default core. Domain-specific checks (network timeouts, security boundaries, build-config hygiene, optional architecture or verification prompts) live in the curated optional library in [library/README.md](../library/README.md), alongside an explicit list of rules we evaluated and deliberately excluded (such as statistical AI-text detectors with `61.22%` non-native English false positives per Liang et al. [arXiv:2304.02819](https://arxiv.org/abs/2304.02819), [docs/evidence.md#ext-13](evidence.md#ext-13), or unfiltered blocking SAST hooks per Firouzi & Ghafari [arXiv:2602.05868](https://arxiv.org/abs/2602.05868), [docs/evidence.md#ext-13](evidence.md#ext-13)).

Any rule without `Local measured` causal proof remains a **hypothesis**, not settled truth. To avoid trading old dogma for new dogma, `anti-slop` evaluates candidate rules on multi-turn software evolution ([benchmarks/cases/EV1.json](../benchmarks/cases/EV1.json), [benchmarks/evolution.py](../benchmarks/evolution.py)):

1. Run the same 4-turn feature evolution under `baseline`, `core-rules-v0.2.0`, and `gated-structural`.
2. Measure six concrete outcomes with zero word caps: hidden functional tests across all 4 turns, AST mutation kill rate on the agent's own tests, duplicate blocks, dead/legacy code removal, god-function/file sprawl, and silent failures or shortcuts.
3. Compare arms with `benchmarks/evolution.py compare` to assign **`KEEP`**, **`DROP`**, or **`INCONCLUSIVE`**.

Rules that do not measurably improve real software outcomes get retired cleanly via `gates/learn.py` or `gates/model_deltas.json` rather than staying in your workflow on faith.
