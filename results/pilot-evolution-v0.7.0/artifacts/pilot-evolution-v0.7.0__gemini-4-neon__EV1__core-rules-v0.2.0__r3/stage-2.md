# pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:46:20Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 175.59
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

Implemented Turn 2 (promo codes across orders and plan upgrades through one shared canonical pricing helper) and verified all checks pass.

### Changes
- **[models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L25-L32)** & **[__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py)**: Added and exported the frozen `Promo` dataclass.
- **[pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L51-L199)**:
  - Added `validate_promo_code`, `parse_iso_date`, and `validate_promo` enforcing non-empty single promo codes (rejecting multi-code stacking strings/delimiters/whitespace), exactly one of `percent_off` (`1..100`) or `amount_off_cents` (`> 0`), non-negative `min_subtotal_cents`, and strict `YYYY-MM-DD` dates.
  - Added the single shared canonical helper `calculate_discounted_totals` (invoked by both `calculate_order_pricing` and `calculate_upgrade_pricing`), applying discounts pre-tax (clamped at `0`), enforcing `min_subtotal_cents` and expiry/`as_of` rules fail-closed, and computing tax via `compute_tax_cents` on the discounted subtotal.
- **[ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L14-L47)**: Added `add_promo` and `get_promo` on `OrderLedger` with fail-closed validation and unknown-code rejection.
- **[api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L25-L157)**:
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to both `place_order` (populating `Order.subtotal_cents`, `Order.discount_cents`, and `Order.promo_code`) and `upgrade_subscription` (including `promo_code` and `as_of` in the idempotency fingerprint).
- **[test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)**: Added 5 unit test suites covering `register_promo` validation, percentage/fixed promos and zero-clamping, expiry/unknown/stacking/min-subtotal fail-closed checks, and upgrade+promo calculation with idempotency.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — exited `0` (`Ran 15 tests in 0.001s`, `OK`).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r3/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__core-rules-v0.2.0__r3/stage-2-grader.json`): passed=False
