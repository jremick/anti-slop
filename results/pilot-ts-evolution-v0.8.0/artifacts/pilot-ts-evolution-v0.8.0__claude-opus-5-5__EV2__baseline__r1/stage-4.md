# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1 — Stage 4/4

- Timestamp UTC: 2026-11-27T08:03:28Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: baseline
- Elapsed seconds: 106.03
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

Turn 4 is in, and `node run_checks.mjs` exits 0 with all 69 tests passing. To check the rollback tests are real, I temporarily switched off the rollback code: all four rollback tests failed, and they passed again once I restored it.

**Legacy deposit removal**
- `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are gone from `src/` and `tests/`, with no shims or leftover branches.
- I deleted the baseline legacy-deposit test and removed the deposit assertions from the other tests.
- **Type merge:** without `depositCents`, my Turn 2 `DiscountAndTax` type was identical to `PriceBreakdown`, so I deleted it. `applyDiscountAndTax` now returns `PriceBreakdown`. This removes `DiscountAndTax` from the public exports.
- `calculateBookingPrice` now just calls `applyDiscountAndTax`.

**`notifyHook`**
- `BookingNotification` and `BookingEventType` are defined in `src/models.ts` and re-exported. The constructor throws `ValidationError` if `notifyHook` is given but isn't a function.
- One private method in `bookings.ts`, `applyAndNotify`, handles every save and notification:
  1. It records each affected booking's current state.
  2. It saves the changes.
  3. It calls the hook for each event.
  4. If the hook throws, it restores the recorded states (new bookings are deleted, a cancelled booking goes back to how it was) and re-throws the original error.
- Where it's used:
  - `createBooking` sends `booking_created` with the total, including for holds.
  - `commitBookings` sends one `booking_created` per room in `roomIds` order, so `createGroupBooking` gets rollback without changing `corporate.ts`. A hook failure on any room removes every booking in that group.
  - `cancelBooking` sends `booking_cancelled` with the refund.
- The hook runs after the save, so it can look the booking up through the service. `confirmHold` sends no event, since you didn't list one for it.
- **Event order on failure:** cancellation config is still loaded before anything changes, so a `ConfigError` fails before the hook is called.

**Tests (`tests/notify.test.ts`, 15 new)** cover:
- **Removal:** the legacy names aren't exported, prices and bookings have no `depositCents`, and no source or test file mentions the legacy deposit.
- **Exact events:** single bookings, holds, three-room groups with amounts to the cent, and early and late refunds. `confirmHold` and failed operations send nothing.
- **Rollback:** after a hook failure, nothing is saved, the slot stays free and a retry succeeds. For groups this is checked with the failure on the first, second and third room. A cancelled booking, including a hold with its expiry, comes back exactly as it was.

The first run had one failure, and the mistake was in my test: it expected 3 events where only 2 happen. I corrected the test, not the code.

**Behaviour you might not expect:**
- **Partial notifications:** if the hook fails on the second room of a group, the hook has already been told about the first room, even though that booking is rolled back. Notifications don't need to be undone for the saved data to stay consistent, so I left it at that.
- **Skipped ids:** ids handed out in a failed attempt aren't reused, because the hook may already have seen them. Ids can therefore skip numbers.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1/stage-4-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__baseline__r1/stage-4-grader.json`): passed=False
