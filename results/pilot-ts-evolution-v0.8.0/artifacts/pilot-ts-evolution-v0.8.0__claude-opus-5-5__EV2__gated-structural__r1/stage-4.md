# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1 — Stage 4/4

- Timestamp UTC: 2026-11-27T07:47:03Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 91.14
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn1.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn2.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn3.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn4.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Turn 4 is in: the legacy deposit feature is gone, and an optional `notifyHook` now reports every new booking and every cancellation. If the hook throws, the change is undone. `run_checks.mjs` passes all 58 tests and exits 0.

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are deleted from all the source files and from the tests.
- The old deposit tests and assertions were removed rather than rewritten.
- **One merged type:** without `depositCents`, `PriceBreakdown` had the same fields as Turn 2's `DiscountedTotals`, so I dropped `DiscountedTotals`. `applyDiscountAndTax` now returns `PriceBreakdown`, and `calculateBookingPrice` simply returns its result.
- `BookingPriceOptions` now only has `discountBps`.
- I added no factory or wrapper classes. The only new helper is a private `notify` method that builds the event.

**`notifyHook`**
- **Event type:** `BookingNotification` lives in `models.ts` and is exported from `index.ts`. The constructor throws `ValidationError` if `notifyHook` is given but isn't a function.
- **New bookings:** every new booking goes through `commitBookings`, whether it comes from `createBooking`, a hold, or a group, so the hook only needed adding there. Bookings are saved, then announced one by one with `amountCents: totalCents`. If the hook throws, every booking from that call is deleted and the same error is rethrown.
- **Cancellations:** the booking is marked cancelled, then announced with `amountCents: refundCents`. If the hook throws, the original booking is put back and the error is rethrown.
- **Timing:** the hook runs after the change is saved, so it can look up the booking it was told about. Conflicts, bad input, config errors and `confirmHold` send no events.

**One limit of the rollback:** if a group's 2nd room fails in the hook, the 1st room's event has already been sent and can't be taken back. Nothing is kept in the service, but whatever receives the events should treat a group as done only once it has an event for every room.

**Tests (`tests/turn4.test.ts`, 10 new)**
- **Removal:** the old deposit names aren't exported from `index.ts` or `pricing.ts`, prices have exactly four fields, bookings have no `depositCents`, and nothing under `src/` mentions "legacy" or "deposit".
- **Events:** checks the exact events for:
  - a plain booking, a hold and a three-room group, with the amounts worked out by hand;
  - a cancellation, where the amount is the refund (5412 at the late tier).
- **Rollback:**
  - A hook failure on a single booking saves nothing, and retrying succeeds.
  - Making the hook fail on the 1st, 2nd and 3rd room of a group each time leaves only the booking that existed before, and the slots can then be booked.
  - A hook failure on cancel restores the booking exactly and keeps its slot blocked; cancelling again then works.

This test file has to name the removed identifiers to check they're absent, so it is the only remaining place they appear.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-4-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-4-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r1/stage-4-grader.json`): passed=True
