# pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__gated-structural__r1 — Stage 4/4

- Timestamp UTC: 2026-11-27T09:00:08Z
- Model: google/gemini-4-neon (reasoning=high, observed=Gemini 4 Neon (High))
- Condition: gated-structural
- Elapsed seconds: 165.83
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/cancellations.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/notifications.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/pricing.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Implemented Turn 4 (complete removal of legacy deposit code and atomic fail-closed `notifyHook`):

### Summary of Changes
- **Removed legacy deposit code completely**:
  - Removed `LEGACY_DEPOSIT_BPS` and `calculateLegacyDeposit` from [pricing.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/pricing.ts) and [index.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/index.ts), simplified `applyDiscountAndTax` to return `PriceBreakdown`, and removed `legacyDepositMode` and `depositCents` from [models.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/models.ts), [pricing.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/pricing.ts), [bookings.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/bookings.ts), and `tests/`.
- **Added fail-closed `notifyHook` and atomic rollback**:
  - Defined `BookingNotificationEvent` and `BookingNotification` in [models.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/models.ts) and re-exported them from [index.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/index.ts).
  - Added optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions` in [bookings.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/bookings.ts).
  - Emitted `booking_created` (`amountCents: booking.totalCents`) in `createBooking` and `booking_cancelled` (`amountCents: refundCents`) in `cancelBooking`, rolling back state and propagating errors if `notifyHook` throws.
  - Added `BookingService.createBookingsAtomic` and used it in [corporate.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/src/corporate.ts) so a `notifyHook` failure on any room in a group booking rolls back all previously created bookings in that group.
- **Tests** ([notifications.test.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/tests/notifications.test.ts), [bookings.test.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts), [pricing.test.ts](file://<TMP_WORKSPACE>/benchmarks/sources/ev2_ts_bookings/tests/pricing.test.ts)):
  - Verified legacy deposit exports/fields are completely absent, `notifyHook` emits exact events for single bookings, group bookings, and cancellations, and exceptions roll back atomically across all three flows.

### Verification
- Ran `node benchmarks/sources/ev2_ts_bookings/run_checks.mjs`: **23/23 tests passed** (exit code `0`).


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__gated-structural__r1/stage-4-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__gated-structural__r1/stage-4-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__gemini-4-neon__EV2__gated-structural__r1/stage-4-grader.json`): passed=True
