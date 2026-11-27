# pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:15:04Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 171.02
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

Implemented Turn 2 (promo codes across orders and plan upgrades via a single canonical pricing helper):

### Changes
- **[models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py)** & **[__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py)**: Added and exported the frozen `Promo` dataclass.
- **[pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py)**:
  - Added `parse_iso_date`, `validate_promo_code_format`, `validate_promo`, `compute_promo_discount_cents`, `compute_order_gross_subtotal_cents`, and the shared canonical helper `apply_discount_and_tax`.
  - Applies exact integer-cent percentage (half-up) or fixed discount to the pre-tax subtotal (clamped at `0`), computes tax on the discounted subtotal, and fails closed with `ValidationError` on unknown/empty/multi-code strings, subtotals below `min_subtotal_cents`, or expiring promos with missing/invalid `as_of` or `as_of > expires_on`.
  - Updated `calculate_order_totals` and `calculate_upgrade_totals` to delegate to `apply_discount_and_tax`.
- **[ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py)**: Added `OrderLedger.add_promo` and `OrderLedger.get_promo` (failing closed with `ValidationError` for unknown promo codes).
- **[api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py)**:
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to both `place_order` and `upgrade_subscription`, delegating discount + tax calculation to `apply_discount_and_tax`, populating `Order.subtotal_cents` (discounted), `Order.discount_cents`, and `Order.promo_code`, and including `promo_code` and `as_of` in `upgrade_subscription`'s idempotency fingerprint.
- **[test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)**: Added unit tests covering promo registration validation, percentage and fixed promos (including clamping at 0 and legacy flat fee interaction), expiry/stacking/unknown code rejection, minimum subtotal enforcement, upgrade+promo calculations with idempotency, and direct coverage of `apply_discount_and_tax`.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py`: **19 tests passed (`OK`, exit code 0)**.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r2/stage-2-grader.json`): passed=False
