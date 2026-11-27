# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:10:56Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: gated-structural
- Elapsed seconds: 80.81
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

Turn 4 is in place, and `run_checks.mjs` exits 0 with all 56 tests passing.

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are gone from `src/` and `tests/`, with no fallback code left behind. Nothing in `src/` mentions "deposit" any more.
- With `depositCents` gone, `PriceBreakdown` had exactly the same fields as the `DiscountedTotals` type I added in Turn 2. So I deleted `DiscountedTotals`, and `applyDiscountAndTax` now returns `PriceBreakdown`. That type was a public export, so anything importing it will need updating.
- I deleted the baseline legacy-deposit test and removed the deposit assertions from the other tests.

**`notifyHook`**
- **Options:** `BookingServiceOptions` takes an optional `notifyHook`. `BookingNotification` is `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }` and is exported.
- **Creating bookings:** `createBookings` saves the whole batch, then calls the hook once per booking in order, with `amountCents` set to the booking total. Single bookings and group bookings both go through this path. If the hook throws, every booking from that batch is removed again and the error propagates unchanged, so a failed group leaves no rooms booked.
- **Cancelling:** `cancelBooking` saves the cancellation, then calls the hook with `amountCents` set to the refund. If the hook throws, the original booking is put back and the error propagates.
- **Failures before saving:** validation errors, conflicts and config errors happen before anything is saved, so they never reach the hook.

**Behaviour to be aware of**
- **Earlier events can't be recalled.** If the hook fails on the third room of a group, it has already been called for the first two. Those bookings are rolled back, but whatever the hook did with those events can't be undone.
- **The hook sees the saved state.** During a creation event, `getBooking` already finds the new booking, and during a cancellation it shows `'cancelled'`.
- **IDs from a rolled-back batch are not reused,** so an ID the hook recorded can never later point to a different booking.
- **`confirmHold` sends no notification,** because the spec only lists the two events.

**`tests/turn4.test.ts`**
- **Deposit removal:**
  - none of the deposit names are exported any more
  - prices and bookings no longer have a `depositCents` field
  - no other source or test file mentions "deposit"
- **Exact events:** checked for single bookings, holds, three-room groups (13802, 5100 and 3506) and cancellations (refund 5412).
- **No events on failure:** validation, conflict and config failures produce no events.
- **Rollback when the hook fails:**
  - on a single booking, which is removed, and the retry gets a fresh ID
  - on each of the three rooms of a group in turn, with the rooms left empty each time and an unrelated existing booking untouched
  - on cancelling a confirmed booking, which stays confirmed and keeps blocking its slot
  - on cancelling a hold, which can still be confirmed afterwards


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-4-workspace.diff`
- Structural gate review (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-4-gate-review.txt`): errors=0, warnings=0
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__gated-structural__r2/stage-4-grader.json`): passed=True
