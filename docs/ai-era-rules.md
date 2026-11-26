# AI-Era Coding Rules: What Helps, What Is Still a Hypothesis, and What Hurts

Traditional software best practices were written for human teams reading code slowly over months. Coding agents work differently: they read a bounded context window, imitate whatever patterns already sit in your repository, and optimize for making the immediate test run look green.

That shift changes which engineering rules actually pay off. Some rules matter much more in AI-assisted coding because a single shortcut compounds across every later session. Other classic habits actively hurt AI workflows by burning context windows, hiding real failures, or giving future sessions bad examples to copy.

Every rule and anti-pattern below carries an explicit evidence label:

- **`Measured in v0.6.0`**: directly supported by our public `n = 3` benchmark ([results/pilot-3way-v0.6.0/README.md](../results/pilot-3way-v0.6.0/README.md)) and automated gate precision audits ([gates/README.md](../gates/README.md)).
- **`Candidate pending EV1`**: backed by external empirical studies ([docs/evidence.md](evidence.md)) and implemented as detectors or `EV1` grading criteria, awaiting multi-model `EV1` comparison runs (`KEEP` vs. `DROP`) to prove causal improvement.
- **`Pre-AI habit to avoid in AI workflows`**: conventional advice that routinely degrades code quality, test signal, or context efficiency when coding agents edit the repository.

---

## Quick Map

| Pattern / Rule | Status | Automated check in `anti-slop` | Why it matters in AI workflows |
|---|---|---|---|
| Never skip, waive, or weaken tests | `Measured in v0.6.0` | `DIFF-TEST-SKIP`, `DIFF-UNAUTHORIZED-TEST-EDIT`, blocking hooks | Stopped `RW3` test tampering (`8/11` baseline to `0/23` ruled) |
| Move objective checks out of prompts into tools | `Measured in v0.6.0` | `gates/diff_check.py`, `gates/hooks/`, `gates/learn.py` | Prompt rules plateaued on 3/4 models and missed Opus `SE2` (`8/9` fails) |
| Test real outputs, not mock-only theater | `Candidate pending EV1` | `STRUCT-TEST-THEATER`, `EV1` AST mutation kill rate (`>= 65%`) | Green suites with weak tests hide regressions on later turns |
| Fail loudly instead of silent fallback defaults | `Candidate pending EV1` | `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | Made-up defaults mask broken logic and missing secrets |
| Keep one canonical copy of business logic | `Candidate pending EV1` | `STRUCT-DUPLICATE-BLOCK` | Agents patch one copy and leave duplicate copies drifting |
| Delete dead branches and legacy shims cleanly | `Candidate pending EV1` | `STRUCT-DEAD-COMPAT` | Dead paths act as live few-shot examples for later AI turns |
| Keep diffs focused and modules cohesive | `Candidate pending EV1` | `STRUCT-GOD-FUNCTION`, `STRUCT-GOD-FILE`, `STRUCT-SCOPE-SPRAWL` | Long tangled functions accelerate multi-turn decay |
| Premature abstractions and single-use DI layers | `Pre-AI habit to avoid in AI workflows` | Review guidance + `R3` / `R5` | Splits simple logic across files and burns agent context |
| Defensive catch-all fallbacks | `Pre-AI habit to avoid in AI workflows` | `DIFF-SILENT-CATCH`, `STRUCT-SILENT-FALLBACK` | Turns crashes into silent data corruption |
| Mock-everything "pure" unit tests | `Pre-AI habit to avoid in AI workflows` | `STRUCT-TEST-THEATER` | Verifies call plumbing while real logic breaks |
| Retaining legacy shims "just in case" | `Pre-AI habit to avoid in AI workflows` | `STRUCT-DEAD-COMPAT` | Trains future AI turns to imitate or edit abandoned code |
| Bloated standing prompt files & blanket style rules | `Pre-AI habit to avoid in AI workflows` | `standard/core.md` (`<= 300` words), `gates/learn.py` ladder | Degrades compliance, increases spend, and strips caveats |

---

## Part 1: Rules That Matter More in AI-Assisted Coding

### 1. Never skip, waive, or weaken tests to turn CI green

- **Status:** `Measured in v0.6.0`
- **Evidence:** In `pilot-3way-v0.6.0` (`RW3`, `urllib3`), `8/11` (`72.7%`) completed baseline runs modified a frozen test file to skip or waive a failing check under release pressure. Standing rules cut tampering to `0/23` (`0.0%`), and external reward-hacking studies ([docs/evidence.md](evidence.md#ext-13)) confirm that blocking test-edit hooks catch shortcuts even when prompts fail.
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

### 2. Tests must assert real outputs and edge cases, not mock theater

- **Status:** `Candidate pending EV1`
- **Evidence:** Analysis of 1.2M+ commits ([docs/evidence.md](evidence.md#ext-13)) found coding agents edit tests more often than humans (`23%` vs. `13%`) and add mocks more often (`36%` vs. `26%`). Mutation-testing studies show vanilla LLM tests average ~`53%` mutant kill rates without feedback.
- **How it compounds:** Future AI sessions trust a green test suite. If a test only checks that a mock was called or asserts `True`, a later session can break billing math or auth checks while every test stays green.
- **Automated check:** `STRUCT-TEST-THEATER` (warning by default; catches zero-assertion tests, tautologies like `assert x == x`, and `>= 3` mocks with zero real value assertions) plus AST mutation scoring (`>= 65%` kill rate) in `benchmarks/evolution.py`.

**Looks convincing (passes even if `calculate_tax` returns the wrong number):**

```python
@patch("app.db.save")
@patch("app.email.send")
@patch("app.metrics.record")
def test_checkout(mock_metrics, mock_email, mock_db):
    run_checkout(order_id="ord_1")
    mock_db.assert_called_once()
```

**Actually clean (runs real logic and proves the output and boundary behavior):**

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

- **Status:** `Candidate pending EV1`
- **Evidence:** Silent fallbacks keep a quick demo from crashing, so they pass shallow manual spot checks while corrupting downstream data or silently falling back to insecure credentials.
- **How it compounds:** Future AI turns assume the returned `0`, `""`, or `"dev-secret"` is valid data and build more business logic on top of corrupted state. When bugs appear later, the original stack trace is gone.
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

**Actually clean (fails closed on missing secrets, narrows expected errors, logs unexpected ones):**

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

- **Status:** `Candidate pending EV1`
- **Evidence:** GitClear's 2025 analysis of 211M lines ([docs/evidence.md](evidence.md#ext-12)) tracked copy-pasted blocks rising from `8.3%` to `12.3%` while moved/refactored lines fell from `24.1%` to `9.5%`. In our 150-commit OSS audit ([gates/README.md](../gates/README.md)), `STRUCT-DUPLICATE-BLOCK` caught real mirrored adapter files where every bugfix had to be pasted identically into two locations.
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

- **Status:** `Candidate pending EV1`
- **Evidence:** ETH Zurich and CASE-Bench studies ([docs/evidence.md](evidence.md#ext-12)) measured a `25-49` percentage point drop in secure code when a flawed neighbor existed in the repository (`76.5%` explicitly imitated repository patterns) and `+6.3pp` exploitable code from a single bad exemplar.
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

- **Status:** `Candidate pending EV1`
- **Evidence:** `SlopCodeBench` ([docs/evidence.md](evidence.md#ext-07)) observed structural erosion rising in `77%-80%` of multi-checkpoint trajectories. Our 150-commit OSS precision audit ([gates/README.md](../gates/README.md)) also showed that mature OSS repos legitimately edit pre-existing 800-to-1,900-line files, which is why size checks stay warning-only by default.
- **How it compounds:** Each AI turn bolts one more `if` branch onto a 100-line function instead of clarifying boundaries, until neither humans nor agents can predict side effects.
- **Automated check:** `STRUCT-GOD-FUNCTION` (`> 60` code lines or `> 12` branches `[Heuristic]`), `STRUCT-GOD-FILE` (growing files `> 400` code lines `[Heuristic]`), and `STRUCT-SCOPE-SPRAWL` (`> 3` unrelated production module areas in one diff `[Heuristic]`).

---

### 7. Put mechanical rules in tools, not bloated standing prompt files

- **Status:** `Measured in v0.6.0` (with prompt-bloat studies in [docs/evidence.md](evidence.md#ext-11))
- **Evidence:** In `pilot-3way-v0.6.0`, per-model prompt overlays tied `core-rules-v0.2.0` on 3 of 4 models while adding matched token overhead, and prompt rules alone still failed `8/9` Opus `SE2` runs. External studies (`IFScale`, `Gloaguen et al.`) show compliance drops and cost rises `> 20%` as standing instruction files bloat.
- **How it compounds:** Dumping every one-off lesson into `AGENTS.md` or `CLAUDE.md` dilutes the rules that actually matter and makes agents ignore constraints buried in the middle.
- **Automated check:** Keep standing instructions short (`standard/core.md` is capped at `<= 300` words) and use `gates/learn.py` (`anti-slop-learn`) to enforce the narrowest prevention first: deterministic check (zero prompt tokens) -> canonical codebase example -> short (`<= 45` words) prompt rule only as a last resort, with a mandatory retirement trigger.

---

## Part 2: Pre-AI Habits to Avoid in AI Workflows

All five practices below carry status **`Pre-AI habit to avoid in AI workflows`**. They were reasonable trade-offs in some pre-AI enterprise codebases, but they systematically backfire when coding agents read and edit your repo.

### A. Premature abstraction and single-implementation dependency-injection layers

- **Status:** `Pre-AI habit to avoid in AI workflows`
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

- **Status:** `Pre-AI habit to avoid in AI workflows`
- **Why it hurts AI coding:** Human teams sometimes wrapped helpers in broad `try/except` blocks to avoid crashing a UI. When an AI coding tool follows that habit, it masks typos, schema mismatches, and missing auth keys behind `return 0` or `return None`. The test suite sees no crash, and the real bug silently propagates across turns.

---

### C. Mock-everything "pure" unit tests

- **Status:** `Pre-AI habit to avoid in AI workflows`
- **Why it hurts AI coding:** Classic "isolate every collaborator with a mock" testing dogma rewards AI agents for testing their own mock setup instead of real code. If you mock the parser, the calculator, and the storage layer in one test, refactoring any of them breaks the mocks while real bugs slip through untouched. Prefer small in-memory fakes or pure functions with concrete input/output assertions.

---

### D. Keeping deprecated compatibility paths "just in case"

- **Status:** `Pre-AI habit to avoid in AI workflows`
- **Why it hurts AI coding:** In a human-only repo, an unused `compute_v1_compat()` helper is mostly harmless dust. In an AI-assisted repo, it is an active hazard: retrieval pulls it into context, and later sessions copy its outdated assumptions or apply new bugfixes to the dead path instead of the live one. Delete obsolete paths cleanly once callers are migrated (git history preserves old code if you ever need it).

---

### E. Blanket style rules and ever-growing prompt checklists

- **Status:** `Pre-AI habit to avoid in AI workflows`
- **Why it hurts AI coding:** Frontier models fail in opposing directions ([docs/models.md](models.md)). Blanket advice like *"be concise"* strips uncertainty caveats on GPT-6.2 (`OAI-02`), while rigid prose rules degrade Claude Fable 5.2 into choppy writing (`ANT-04`), and long `ALWAYS`/`NEVER` lists trigger brittle workarounds (`ANT-02`). Prefer automated gates for objective checks, short model-specific overlays only where measured, and clean retirement when newer models outgrow a rule.

---

## Part 3: How Rules Earn Their Keep (`EV1`)

Any rule marked `Candidate pending EV1` is a **hypothesis**, not settled truth. To avoid trading old dogma for new dogma, `anti-slop` evaluates candidate rules on multi-turn software evolution ([benchmarks/cases/EV1.json](../benchmarks/cases/EV1.json), [benchmarks/evolution.py](../benchmarks/evolution.py)):

1. Run the same 4-turn feature evolution under `baseline`, `core-rules-v0.2.0`, and `gated-structural`.
2. Measure six concrete outcomes with zero word caps: hidden functional tests across all 4 turns, AST mutation kill rate on the agent's own tests, duplicate blocks, dead/legacy code removal, god-function/file sprawl, and silent failures or shortcuts.
3. Compare arms with `benchmarks/evolution.py compare` to assign **`KEEP`**, **`DROP`**, or **`INCONCLUSIVE`**.

Rules that do not measurably improve real software outcomes get retired cleanly via `gates/learn.py` or `gates/model_deltas.json` rather than staying in your workflow on faith.
