# pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:37:21Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: gated-structural
- Elapsed seconds: 202.08
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

Implemented Turn 2 (promo codes across orders and mid-cycle upgrades with shared canonical pricing logic):

- **Domain model ([models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L26-L32), [__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py)):** Added and exported the frozen `PromoCode` dataclass.
- **Shared canonical pricing & validation ([pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L53-L165)):**
  - Added `validate_promo_code`, `parse_iso_date`, `build_promo_code`, `compute_promo_discount_cents`, `compute_order_pre_discount_subtotal_cents`, and the single shared helper `apply_discount_and_tax`.
  - Enforces fail-closed `ValidationError` on unknown/empty/stacked codes (e.g. `'A,B'`, `'A+B'`, `'A;B'`, `'A|B'`, `'A B'`), invalid `percent_off`/`amount_off_cents` combinations or ranges, negative `min_subtotal_cents`, subtotals below `min_subtotal_cents`, malformed `YYYY-MM-DD` dates, and expiring promos where `as_of` is missing or `as_of > expires_on`.
  - Applies exact integer-cent half-up percentage or fixed discounts to pre-tax subtotal (clamped at `0`) and computes tax on the discounted subtotal.
- **Ledger storage ([ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L45-L53)):** Added `add_promo` and `get_promo` on `OrderLedger`.
- **Service facade ([api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L25-L184)):**
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to both `place_order` and `upgrade_subscription`, delegating discount and tax calculation to `apply_discount_and_tax`, populating `Order.subtotal_cents` (discounted), `Order.discount_cents`, and `Order.promo_code`, and including `promo_code` and `as_of` in `upgrade_subscription` idempotency fingerprinting.
- **Unit tests ([test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)):** Added 9 test methods covering promo registration validation, percentage/fixed discounts and zero-clamping, legacy flat fee + promo, expiry/`as_of` enforcement, stacking/unknown code rejection, minimum subtotal enforcement, upgrade + promo calculation and idempotency, and direct `apply_discount_and_tax` checks.

### Verification
Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — all 22 tests passed (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r1/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r1/stage-2-gate-review.txt`): errors=0, warnings=2
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r1/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r1/stage-2-grader.json`): passed=False
