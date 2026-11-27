# pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:12:37Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 115.53
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

Turn 2 is done. Promo codes now work on both orders and upgrades, and `python3 run_checks.py` passes all 41 tests and exits 0.

**How the pricing is shared**
In `pricing.py`, `apply_promo_and_tax(subtotal, tax_bps, promo, as_of)` is now the single last pricing step for both paths. It takes the discount off the pre-tax subtotal (never below 0), then taxes what's left. `calculate_order_totals` and `calculate_upgrade_proration` both end by calling it, so there's no second copy of the discount or tax logic. Percent discounts use the same half-up rounding as everything else.

**What changed**
- **`register_promo(...)`** checks the definition, then stores a new frozen `Promo` model (exported from the package) in the ledger.
- **`place_order` and `upgrade_subscription`** both accept `promo_code` and `as_of`. Orders now fill in `subtotal_cents` (after the discount), `discount_cents` and `promo_code`. Ledger entries record the discount and code in their metadata.
- **Idempotency covers the new arguments.** Reusing an upgrade key with a different `promo_code` or `as_of` raises `ValidationError`.

**These all raise `ValidationError`, and nothing is recorded:**
- Unknown codes.
- Anything that isn't a single code made of letters, digits, `_` or `-`. That covers `'A,B'`, `'A B'`, `'A;B'`, leading spaces, empty strings and non-strings.
- A subtotal below `min_subtotal_cents`. For orders this is checked after the legacy flat fee is added; for upgrades it's checked against the prorated amount.
- A promo with an expiry date used without `as_of`, or with `as_of` after the expiry date.
- A malformed `as_of` or `expires_on`, such as `2026/12/31`, `20261231`, `2026-02-30` or a `date` object instead of a string. `as_of` is checked even when no promo is given.

**Decisions you may want to change**
- **The expiry date itself is still valid.** An `as_of` equal to `expires_on` is accepted.
- **Codes are case-sensitive**, so `save10` doesn't match `SAVE10`.
- **Registering the same code twice raises an error** rather than overwriting it. Otherwise the terms could change silently between an upgrade and a replay of it.
- **A 0-cent subtotal is allowed.** A 0-day upgrade with a promo that has no minimum produces a 0 discount. That comes from the 0 subtotal, not from a promo being ignored.
- **Two pricing functions now return more fields.** `calculate_order_totals` and `calculate_upgrade_proration` return a `PricedTotals` named tuple `(subtotal, discount, tax, total)` instead of a 3-tuple. I updated their only callers: `api.py` and the Turn 1 tests.

**New tests (`tests/test_promos.py`, 20 tests)**
- **Registration:** valid promos and the 1% and 100% limits, plus rejection of 15 invalid definitions, bad codes and a duplicate code.
- **Orders:**
  - Percent and fixed discounts, including an exact half-cent rounding up.
  - Discounts clamped at 0 and a 100% discount.
  - A promo combined with the legacy flat fee, and the minimum-subtotal boundary.
  - Unknown and stacked codes, expiry (including the last valid day) and malformed `as_of` values.
- **Upgrades:**
  - Percent, fixed and expiring promos on a prorated charge.
  - Rejections that leave the plan unchanged.
  - Idempotency conflicts when only the promo arguments change.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-2-gate-review.txt`): errors=0, warnings=1
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__claude-opus-5-5__EV1__gated-structural__r3/stage-2-grader.json`): passed=False
