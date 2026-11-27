# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:27:28Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 147.34
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

Turn 4 is done, and `node run_checks.mjs` exits 0 with 63 tests passing (48 after the legacy cleanup plus 15 new ones in `tests/turn4.test.ts`).

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are gone from `src/` and `tests/`; a grep for all four finds nothing.
- I deleted the baseline legacy-deposit test and removed the deposit assertions from the other tests.
- Without `depositCents`, Turn 2's `DiscountAndTax` type became identical to `PriceBreakdown`, so I removed it. `applyDiscountAndTax` and `calculateBookingPrice` both return `PriceBreakdown`, and `calculateBookingPrice` now simply returns the result of `applyDiscountAndTax`. Anyone importing the `DiscountAndTax` type will need to switch to `PriceBreakdown`.

**`notifyHook`**
- `BookingNotification` and `BookingNotificationEvent` are added to `src/models.ts` and exported from `src/index.ts`. `notifyHook` is an optional setting on `BookingServiceOptions`.
- **New `BookingService.createBookings(inputs)`:** this is the one place bookings get created, and it's all or nothing. It works in this order:
  1. It validates, conflict-checks and prices every input, including against earlier inputs in the same batch, before saving anything.
  2. It saves the batch, then calls the hook once per booking with `booking_created` and the booking total.
  3. If the hook throws, it deletes every booking in the batch and re-throws the original error.
- **`createBooking`** now just creates a batch of one.
- **`createGroupBooking`** keeps its validation and conflict pre-check, then saves all rooms through `createBookings`. This also replaced Turn 2's "price everything up front" step and removed its "no undo" caveat.
- **`cancelBooking`** saves the cancelled status, then calls the hook with `booking_cancelled` and the refund amount. If the hook throws, the original booking is put back unchanged, including a hold's `expiresAt`, and the error is re-thrown.

**Limitation:** events already sent can't be taken back. If the hook throws on the second room of a group, the first room's `booking_created` has already gone out, even though that booking is rolled back. A test pins this down (the number of events sent equals the position of the failing room). If downstream systems need to know about rollbacks, that would need a compensating event, which I haven't added.

**Behaviour choices**
- **The hook runs after the change is saved,** so it can read the new state with `getBooking`.
- **Confirming a hold sends no event,** because your spec only lists creation and cancellation.
- **Operations that are rejected before saving** (validation errors, conflicts, config errors) send no event.

**Tests**
- **Legacy removal:** no export, `Booking` key or `PriceBreakdown` key matches `legacy|deposit`, and none of the source files or other test files mention them. `turn4.test.ts` uses those words in its test names, so it skips itself, but it contains none of the four removed identifiers.
- **Exact events:** the full event objects are compared for a confirmed booking, a hold (with the customer ID trimmed), a 3-room group (14208, 7875 and 1422, adding up to the group total), and early and late cancellations (refunds of 9742 and 5412).
- **Rollback:**
  - when creating a single booking
  - when the hook fails on room 1, 2 or 3 of a group, nothing is saved, and the same group can be booked once the hook stops failing
  - bookings that already existed are untouched
  - when cancelling, the booking (or hold) is restored exactly, its slot stays blocked, and a retry succeeds
- **Batches:** two overlapping inputs in the same batch are rejected with nothing saved and no events sent.

**Checking the tests:** I temporarily broke the code five ways, one at a time, and the suite failed each time:
1. removing the rollback after a failed create
2. removing the rollback after a failed cancel
3. having the group book its rooms one at a time
4. calling the hook before saving
5. adding a legacy export back

The original files were restored, they match the copies saved before the experiment, and the suite passes again.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2/stage-4-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r2/stage-4-grader.json`): passed=True
