# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:34:41Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 86.74
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/cancellation.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/group_bookings.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/holds_conflicts_pricing.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/notifications.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Turn 4 is implemented, and `node run_checks.mjs` exits 0 with all 63 tests passing (48 from before plus 15 new; two legacy-deposit tests were removed).

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are deleted from `models.ts`, `pricing.ts`, `bookings.ts` and `index.ts`.
- With `depositCents` gone, `PriceBreakdown` and Turn 2's `DiscountedTaxBreakdown` had identical fields, so I deleted `DiscountedTaxBreakdown`. `calculateBookingPrice` now just calls `applyDiscountAndTax`.
- The baseline legacy-deposit test is removed, and the existing tests no longer mention deposits; the only mentions left are in the new tests checking they're gone.
- No compatibility shims or new wrapper layers were added.

**`notifyHook`**
- `BookingNotification` lives in `models.ts`, and `notifyHook` is an optional field on `BookingServiceOptions`. Passing something that isn't a function throws `ValidationError`.
- **Creation:** new bookings are saved first, then the hook is called once per booking with `booking_created` and `totalCents`. This means the hook can look the booking up through the service. Single bookings, holds and every room of a group booking all go through this path.
- **Creation rollback:** if the hook throws, every booking from that call is removed, including rooms whose events were already sent, and the original error is passed on.
- **Cancellation:** `booking_cancelled` is sent with `refundCents`. If the hook throws, the original booking is put back, so it stays confirmed and its slot stays blocked.
- **IDs:** booking IDs from a rolled-back create are never reused. The hook may already have received events for them, and reusing them would confuse anything downstream.

**One limitation:** events can't be taken back. If the hook throws on room `b` of a group, it has already received `booking_created` for room `a`, even though nothing is kept. Avoiding that would need a separate pre-commit step, so the hook should treat a thrown error as cancelling the whole operation.

**Tests**
- **Legacy removal:** the deposit exports are gone from the API, prices and bookings have no `depositCents` field, and no file in `src/` mentions deposits.
- **Exact events:** single bookings, holds and groups (one event per room, in order: 13802, 9626 and 4675¢), and cancellation (10825¢ refund at the late tier).
- **Hook timing:** the hook can read the saved booking while it runs. Rejected operations send no events.
- **Rollback:**
  - a throwing hook on a single booking saves nothing, and its ID isn't reused;
  - a failure on the middle or last room of a group saves zero bookings;
  - a failure on cancellation restores the booking exactly as it was, with the slot still blocked, and it can be cancelled successfully later.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-4-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-4-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r3/stage-4-grader.json`): passed=True
