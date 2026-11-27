# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T01:31:50Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 131.39
- Workspace modified: ['benchmarks/sources/ev1_order_ledger/__init__.py', 'benchmarks/sources/ev1_order_ledger/api.py', 'benchmarks/sources/ev1_order_ledger/ledger.py', 'benchmarks/sources/ev1_order_ledger/models.py', 'benchmarks/sources/ev1_order_ledger/pricing.py']
- Workspace created: ['benchmarks/sources/ev1_order_ledger/tests/test_promos.py', 'benchmarks/sources/ev1_order_ledger/tests/test_upgrades.py']
- Workspace deleted: []

## Prompt

Implement Turn 2 (promo codes across both orders and upgrades without duplicating pricing logic):
- Add `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)` validating exactly one of `percent_off` (1..100) or `amount_off_cents` (>0), non-negative `min_subtotal_cents`, and non-empty `code`.
- Add optional `promo_code=None` and `as_of=None` (`YYYY-MM-DD`) to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to one shared canonical helper in `pricing.py`.
- Apply discount to pre-tax subtotal (clamped at 0), compute tax on the discounted subtotal, and set `Order.subtotal_cents` to the discounted subtotal with `Order.discount_cents` and `Order.promo_code` populated.
- Fail closed with `ValidationError` (never silently returning 0 discount) on unknown codes, multi-code strings (e.g., `'A,B'`), subtotals below `min_subtotal_cents`, or expiring promos where `as_of` is missing or `as_of > expires_on`.
- Add unit tests for percentage/fixed promos, expiry/stacking rejection, minimum subtotal, and upgrade+promo calculation, then run `run_checks.py`.

## Raw Model Output

Turn 2 is in: promo codes now work on both `place_order` and `upgrade_subscription`, and both get their discount and tax from one shared helper. `run_checks.py` passes 45 tests (22 from before plus 23 new) and exits 0.

**Where the code went**
- **The shared helper:** `pricing.price_charge(gross_subtotal_cents, tax_bps, *, promo, as_of)` takes the discount off the pre-tax subtotal, never going below 0, then taxes what's left. It returns all five numbers: subtotal before discount, discount, subtotal after discount, tax and total. Orders and upgrades both call it, so the discount logic exists in one place only.
- **Other pricing helpers:**
  - `parse_iso_date` accepts only `YYYY-MM-DD`.
  - `validate_promo_code` checks a code is a single well-formed code.
  - `build_promo` checks the terms when a promo is registered.
  - `compute_discount_cents` checks expiry and the minimum subtotal, then rounds percentage discounts half-up.
- **Changed behaviour:** `calculate_order_totals` now returns that five-number result instead of a 3-tuple. Its only caller was `api.py`, which is updated.
- **Elsewhere:** a frozen `Promo` dataclass in `models.py` (exported from `__init__`), and promo storage in `ledger.py` that raises `ValidationError` for unknown codes.
- **Service:**
  - `register_promo` validates the terms, saves the promo and returns it.
  - `place_order` fills in `subtotal_cents` (after discount), `discount_cents` and `promo_code`.
  - On orders and upgrades, the ledger entry records the code, the discount and the pre-discount subtotal in its metadata.

**Choices the spec didn't settle** (each is easy to change):
- **Code format:** a code may contain only letters, digits, `_` and `-`. So `'A,B'`, `'A B'`, `'A;B'` and `' A'` are all rejected rather than split, and codes are case-sensitive (`save10` won't match `SAVE10`).
- **Empty strings fail:** an empty `promo_code` raises an error rather than counting as "no promo". A malformed `as_of` also raises even when no promo is given.
- **Registering a code twice raises an error** rather than overwriting. Plans, by contrast, overwrite silently.
- **The legacy flat fee counts as subtotal.** The promo's minimum and its discount both apply to the subtotal including the $5 fee.
- **Expiry is inclusive:** a promo still works on its `expires_on` date and fails from the next day. A promo with no expiry ignores `as_of`.
- **Upgrade promos use the prorated amount.** The minimum subtotal is compared against the prorated charge, not the plan's monthly price. A 1,000-cent proration therefore fails a promo with a 5,000-cent minimum.

**Idempotency still holds**
- A replay must now also match `promo_code` and `as_of`; a different value in either raises a conflict error.
- A malformed code or date is rejected before the replay check.
- An upgrade that fails a promo check charges nothing, leaves the plan alone and doesn't use up its key.

**What the new tests cover** (`tests/test_promos.py`)
- **Discounts:** percentage discounts with half-up rounding (including an exact half: 500.5→501) and tax on the discounted subtotal. Also fixed discounts, a fixed discount larger than the subtotal (clamped to 0), and a promo combined with the flat fee.
- **Registration:** every invalid case is rejected (neither or both discount types, out-of-range or boolean values, bad dates, bad codes, duplicate codes).
- **Expiry and bad input:** a missing or late `as_of`, malformed dates, combined codes such as `'SAVE10,FIVE'`, unknown codes, and the minimum-subtotal boundary (4999 is rejected, 5000 passes).
- **Upgrade with promo:** 1,000 prorated, minus 100, gives 900 + 74 tax = 974. Failed promo upgrades change nothing, and replays must match the promo arguments.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-2-gate-review.txt`): errors=0, warnings=1
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r1/stage-2-grader.json`): passed=False
