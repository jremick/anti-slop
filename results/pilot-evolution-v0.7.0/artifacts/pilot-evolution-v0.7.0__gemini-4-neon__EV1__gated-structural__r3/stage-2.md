# pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r3 — Stage 2/4

- Timestamp UTC: 2026-11-27T03:58:54Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: gated-structural
- Elapsed seconds: 197.42
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

Implemented Turn 2 (promo codes across orders and mid-cycle plan upgrades via a single canonical pricing helper):

- **[models.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/models.py#L25-L31)** & **[__init__.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/__init__.py#L5-L18)**: Added and exported the frozen `Promo` dataclass.
- **[pricing.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/pricing.py#L52-L122)**: Added `parse_iso_date`, `validate_promo_code`, `validate_promo`, `compute_order_pre_tax_subtotal`, and the shared canonical `apply_promo_and_tax(subtotal_cents, tax_bps, *, promo=None, as_of=None)` helper used by both orders and upgrades. Validates single-code tokens (rejecting multi-code stacking strings such as `'A,B'`), strict `YYYY-MM-DD` dates, required/unexpired `as_of`, and `min_subtotal_cents`, applies pre-tax discount clamped at `0`, and computes tax on the discounted subtotal.
- **[ledger.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/ledger.py#L46-L61)**: Added `OrderLedger.add_promo` and `OrderLedger.get_promo` delegating to canonical promo validators and failing closed on unknown/invalid codes.
- **[api.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/api.py#L27-L162)**: Added `OrderService.register_promo(...)` and optional `promo_code=None, as_of=None` to both `place_order` and `upgrade_subscription` (including `promo_code` and `as_of` in upgrade idempotency fingerprints and populating `Order.subtotal_cents`, `Order.discount_cents`, and `Order.promo_code`).
- **[test_promos.py](file://<TMP_WORKSPACE>/benchmarks/sources/ev1_order_ledger/tests/test_promos.py)**: Added unit tests for promo registration validation, percentage and fixed-amount discounts with zero clamping, expiry/stacking/unknown/min-subtotal fail-closed checks, and upgrade+promo idempotency.

Verification: `python3 benchmarks/sources/ev1_order_ledger/run_checks.py` exited `0` (18/18 tests passing).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r3/stage-2-workspace.diff`
- Structural gate review (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r3/stage-2-gate-review.txt`): errors=0, warnings=2
- Automated gate repair turn completed (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r3/stage-2-gate-repair-trace.log`)
- Automated grader (`runs-local/pilot-evolution-v0.7.0/artifacts/pilot-evolution-v0.7.0__gemini-4-neon__EV1__gated-structural__r3/stage-2-grader.json`): passed=False
