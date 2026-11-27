# pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r1 — Stage 2/4

- Timestamp UTC: 2026-11-27T02:48:51Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: baseline
- Elapsed seconds: 214.95
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

Implemented Turn 2 (promo codes across orders and plan upgrades via one shared canonical pricing helper):

### Changes
- [models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L25-L31) & [__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py): Added and exported the frozen `Promo` dataclass.
- [pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L55-L157): Added `parse_iso_date`, `validate_promo_code`, `validate_promo`, `compute_order_gross_subtotal_cents`, and the single shared canonical `apply_promo_and_tax` helper (used by both order and upgrade flows) that enforces expiry (`as_of` required and `as_of <= expires_on`), `min_subtotal_cents`, single-code validation, pre-tax discount clamped at `0`, and exact half-up tax on the discounted subtotal.
- [ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L22-L54): Added promo storage with `add_promo` and fail-closed `get_promo`.
- [api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L26-L185): Added `OrderService.register_promo(...)` and optional `promo_code=None, as_of=None` on both `place_order` and `upgrade_subscription` (including `promo_code` and `as_of` in the upgrade idempotency fingerprint), populating `Order.subtotal_cents`, `Order.discount_cents`, `Order.promo_code`, and ledger entries.
- [test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py): Added 7 unit tests covering `register_promo` validation, percentage/fixed discounts and zero clamping, expiry and stacking rejection, minimum subtotal enforcement, and upgrade+promo calculation + idempotency.

### Verification
- Ran `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` — all 20 tests passed (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r1/stage-2-workspace.diff`
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__baseline__r1/stage-2-grader.json`): passed=False
