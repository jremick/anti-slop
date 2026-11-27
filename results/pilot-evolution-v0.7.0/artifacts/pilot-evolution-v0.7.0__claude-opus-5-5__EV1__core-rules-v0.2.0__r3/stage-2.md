# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:20:03Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 139.81
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

Promo codes now work on both `place_order` and `upgrade_subscription`, and `run_checks.py` exits 0 with 44 tests passing (22 from before plus 22 new).

**The shared helper.** All discount and tax maths goes through one function in `pricing.py`, `apply_promo_and_tax(gross_subtotal_cents, tax_bps, *, promo=None, as_of=None)`.
- It returns the discounted subtotal, the discount, the tax and the total.
- It checks that the promo itself is valid, that `as_of` is present when the promo has an expiry, that `as_of` is on or before `expires_on`, and that the pre-discount subtotal meets `min_subtotal_cents`.
- The discount comes off the pre-tax subtotal and is capped at that subtotal. Tax is then worked out on what's left.
- Percentage discounts round half-up.
- Orders and upgrades each work out their pre-discount subtotal (item total plus any legacy fee, or the prorated charge) and then call this helper. The existing `calculate_order_totals` and `calculate_upgrade_totals` also call it now, and still return `(subtotal, tax, total)`, so no earlier test had to change.

**Other changes**
- **`models.py`:** a new `Promo` dataclass, also exported from the package.
- **`ledger.py`:** `add_promo` and `get_promo`.
- **`api.py`:** `register_promo` turns `expires_on` into a date at registration. Orders now fill in `discount_cents` and `promo_code`. Ledger entries for both orders and upgrades record the discount and code in their `metadata`. For upgrades, `promo_code` and `as_of` are now part of the idempotency check, so reusing a key with a different code or date raises `ValidationError`.

**Choices you may want to review**
- **Code format:** a promo code must be letters, digits, `_` or `-`. So `'A,B'`, `'A B'` and `'A;B'` are rejected as stacked codes, even when each part is a registered code. Codes are case-sensitive and must match exactly (`save10` is unknown).
- **Duplicate codes:** registering a code that already exists is rejected rather than overwriting it, so a promo's terms can't change quietly.
- **Date format:** `as_of` and `expires_on` must be exactly `YYYY-MM-DD`. Python 3.12 would otherwise also accept forms like `20261231`. An invalid `as_of` is rejected even when no promo is given.
- **Minimum subtotal:** `min_subtotal_cents` is compared with the subtotal before the discount, which for orders includes the legacy flat fee.

**Tests** (`tests/test_promos.py`)
- **Registration:** valid promos, plus rejection of a missing or double discount, out-of-range values, booleans and floats, bad codes, bad dates and duplicate codes.
- **Orders:** percentage and fixed promos (with hand-worked cents), the cap at a zero subtotal, 100% off, the promo combined with the legacy fee, and the minimum-subtotal boundary.
- **Expiry and bad codes:** a missing `as_of`, the day after expiry, and the expiry date itself (allowed). Unknown and stacked codes are rejected with no entry written.
- **Upgrades:** a prorated upgrade with a promo (900 + 74 tax = 974¢) and a fixed promo larger than the charge. Promo failures leave the plan unchanged and don't use up the idempotency key. Replays return the original entry, and a changed promo or date is rejected.

To check the tests catch mistakes, I made four deliberate breaks one at a time: taxing the pre-discount amount, allowing a missing `as_of`, treating an unknown code as no discount, and removing the cap. Each one made tests fail, and the suite passes again with the code restored.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=False
