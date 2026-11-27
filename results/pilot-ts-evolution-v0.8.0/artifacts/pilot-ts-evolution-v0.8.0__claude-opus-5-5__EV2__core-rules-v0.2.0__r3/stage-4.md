# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:41:16Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 77.08
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/cancellation.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/notify.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/turn1.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Turn 4 is done, and `run_checks.mjs` exits 0 with 47 tests passing.

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are gone from `src/` and `tests/`. A search for "deposit" in either folder finds nothing, and a new test checks for this.
- I deleted the two deposit tests (one original, one I added in Turn 1) and removed the deposit check from the original baseline test.
- With `depositCents` gone, my Turn 2 `DiscountedPrice` type had the same fields as `PriceBreakdown`. I removed it, so `applyDiscountAndTax` now returns `PriceBreakdown`. That is a small change to the public API.
- No factory or wrapper layers were added.

**`notifyHook`**
- `BookingNotification` is defined in `models.ts` and exported from `index.ts`. `notifyHook` is an optional setting on `BookingServiceOptions`.
- **New bookings:** both `createBooking` and `createGroupBooking` save through `commitBookings`. It saves the batch, then calls the hook once per booking with `booking_created` and the booking's total. If the hook throws, every booking in that batch is deleted (all rooms of a group, including ones already reported) and the error is passed on.
- **Cancellations:** `cancelBooking` sets the booking to cancelled and calls the hook with `booking_cancelled` and the refund. If the hook throws, the original booking is restored unchanged (a hold keeps its expiry time) and the error is passed on.
- Inputs that fail validation or hit a conflict never reach the hook.

**New tests (`tests/notify.test.ts`)**
- The legacy names are no longer exported, and prices and bookings have no `depositCents`.
- The exact events for single bookings, holds, groups (14208¢, 7875¢ and 4813¢ per room) and cancellations (9742¢ refund).
- When the hook fails on a single booking, nothing is saved, and the same slot can be booked afterwards.
- When the hook fails on the 1st, 2nd or 3rd room of a group, nothing from the group is saved and an existing booking is untouched.
- When the hook fails on a cancellation, the booking stays active and its slot stays blocked. A failed cancellation of a hold leaves it still confirmable.

To check the tests work, I deleted each of the two rollbacks in turn; each time the matching tests failed.

**Limits of the rollback:** the hook runs synchronously and is called one booking at a time. If a group fails on its third room, the hook has already received events for the first two, even though those bookings are then removed. Undoing that is up to whatever receives the events. Also, booking IDs used by a rolled-back attempt are not reused.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3/stage-4-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r3/stage-4-grader.json`): passed=True
