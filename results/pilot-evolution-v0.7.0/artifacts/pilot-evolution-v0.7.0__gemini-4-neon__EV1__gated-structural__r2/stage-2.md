# pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r2 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:04:34Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: gated-structural
- Elapsed seconds: 230.30
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

Implemented Turn 2 promo codes across both orders and mid-cycle subscription upgrades using a single shared canonical pricing helper:

### Changes
- [models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L25-L31): Added frozen `Promo` dataclass and exported it from [__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py#L5-L18).
- [pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L27-L195):
  - Added strict validators `validate_promo_code` (rejecting empty/blank strings and multi-code separators/whitespace), `parse_iso_date` (`YYYY-MM-DD`), and `validate_promo` (enforcing XOR of `percent_off` in `1..100` vs `amount_off_cents > 0`, `min_subtotal_cents >= 0`, and valid `expires_on`).
  - Added canonical `calculate_discounted_totals`, which enforces expiry (`as_of` required and `<= expires_on`) and `min_subtotal_cents`, applies percentage (half-up) or fixed discount clamped at 0, and computes tax on the discounted subtotal.
  - Routed both `calculate_order_pricing` / `calculate_order_totals` and `calculate_upgrade_pricing` / `calculate_upgrade_totals` through `calculate_discounted_totals`.
- [ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L46-L55): Added `add_promo` and fail-closed `get_promo` to `OrderLedger`.
- [api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L24-L185):
  - Added `OrderService.register_promo(code, *, percent_off=None, amount_off_cents=None, expires_on=None, min_subtotal_cents=0)`.
  - Added optional `promo_code=None` and `as_of=None` to `place_order` (populating discounted `Order.subtotal_cents`, `Order.discount_cents`, `Order.promo_code`, and ledger entry) and `upgrade_subscription` (including `promo_code` and `as_of` in the idempotency fingerprint and recording discount metadata).
- [test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py): Added 9 test cases covering promo registration validation, percentage and fixed promos (with 0-clamping and legacy flat fee), minimum subtotals, expiry/`as_of` boundaries, unknown and multi-code rejection, upgrade+promo pricing and idempotency, and canonical helper parity.

### Verification
- Ran [run_checks.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/run_checks.py): all 24 tests passed (`OK`), with zero lint/type suppressions.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r2/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r2/stage-2-gate-review.txt`): errors=0, warnings=3
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r2/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r2/stage-2-grader.json`): passed=False
