# pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1 — Stage 4/4

- Timestamp UTC: 2026-11-27T07:55:50Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: core-rules-v0.2.0
- Elapsed seconds: 104.03
- Workspace modified: ['benchmarks/sources/ev2_ts_bookings/src/bookings.ts', 'benchmarks/sources/ev2_ts_bookings/src/config.ts', 'benchmarks/sources/ev2_ts_bookings/src/index.ts', 'benchmarks/sources/ev2_ts_bookings/src/models.ts', 'benchmarks/sources/ev2_ts_bookings/src/pricing.ts', 'benchmarks/sources/ev2_ts_bookings/tests/bookings.test.ts']
- Workspace created: ['benchmarks/sources/ev2_ts_bookings/src/corporate.ts', 'benchmarks/sources/ev2_ts_bookings/tests/cancellation.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/corporate.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/holds_pricing.test.ts', 'benchmarks/sources/ev2_ts_bookings/tests/notify.test.ts']
- Workspace deleted: []

## Prompt

Implement Turn 4 (complete removal of `legacyDepositMode` / `calculateLegacyDeposit` and atomic fail-closed `notifyHook`):
- Completely remove `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode`, and `depositCents` from `src/models.ts`, `src/pricing.ts`, `src/bookings.ts`, `src/index.ts`, and `tests/` (do NOT leave dead branches, legacy shims, or speculative single-implementation `*Factory`/`*Wrapper` abstractions).
- Add optional `notifyHook?: (event: BookingNotification) => void` to `BookingServiceOptions`, where `BookingNotification` has `{ event: 'booking_created' | 'booking_cancelled', bookingId, roomId, customerId, amountCents }`.
- Invoke `notifyHook` on every newly created booking (including every room booking created via `createGroupBooking`, with `amountCents: booking.totalCents`) and on every cancellation (`event: 'booking_cancelled'`, `amountCents: refundCents`). Enforce fail-closed atomicity: if `notifyHook` throws, propagate the error AND roll back so zero new bookings (including partial group bookings) or cancellation status changes are persisted.
- Update `tests/` to verify legacy deposit exports are gone and `notifyHook` emits exact events and rolls back atomically on failure, then run `run_checks.mjs`.

## Raw Model Output

Turn 4 is done: the legacy deposit code is completely gone and `notifyHook` is in place with rollback on failure. `node run_checks.mjs` exits 0 with all 56 tests passing.

**Legacy deposit removal:** `LEGACY_DEPOSIT_BPS`, `calculateLegacyDeposit`, `legacyDepositMode` and `depositCents` are gone from `src/` and from the existing tests, and no shims or leftover branches remain. The only places those names still appear are in the new test file, as strings it checks are absent. I deleted the baseline legacy-deposit test and took the deposit assertions out of three other tests, since they tested removed behaviour.

**notifyHook**
- `BookingNotification` lives in `models.ts` and is re-exported. `BookingServiceOptions.notifyHook` is optional, and passing something that isn't a function throws `ValidationError` when the service is created.
- All rollback logic is in one private method, `commitAndNotify`, which `createBooking`, `cancelBooking` and group bookings all go through. It saves the changes, then calls the hook once per changed booking. If the hook throws, it removes the new bookings, puts cancelled ones back, and rethrows the hook's original error. No factory or wrapper classes were added.
- Validation, conflict and config errors are all raised before anything is saved, so failed operations never call the hook.

**Behaviour to be aware of**
- **Earlier hook calls in a failed group can't be undone.** If the hook fails on the second room of a group, it has already been called for the first room. That booking is removed, but your hook has seen an event for it. Undoing that is up to whatever receives the hook.
- **Booking IDs aren't reused after a rollback.** An ID the hook has already seen is never given to a different booking later.
- **The hook can see the new state.** It runs after the change is saved, so calling `getBooking` inside it works.
- **`confirmHold` sends no event**, because neither event type covers confirming a hold.

**Tests (`tests/notify.test.ts`, 12 tests)**
- **Removal:** the two exports are gone, price and booking objects have no deposit field, and a scan of `src/` finds no "legacy" or "deposit".
- **Events:** exact contents for confirmed bookings, holds, every room in a group (in order) and cancellations (amount is the refund), plus no events from failed operations.
- **Rollback:**
  - The hook failing on a single booking, on the second room of a group, or on the last room each leaves no new bookings behind.
  - The hook failing on a cancel leaves the booking active and its slot still blocked.
  - The service keeps working normally after a rollback.

**Checking the tests:** I broke the code six ways, restoring it after each:

| Change | Tests failed |
|---|---|
| Hook error swallowed | 5 |
| Only the first change rolled back | 3 |
| Cancelled booking not restored | 1 |
| Booking marked cancelled before the save step | 1 |
| Cancel event carries the total instead of the refund | 1 |
| Group bookings send no events | 8 |

The final run passes, and `src` and `tests` contain no `enum`, `namespace`, constructor parameter properties, or `Factory`/`Wrapper` classes.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1/stage-4-workspace.diff`
- Automated grader (`runs-local/pilot-ts-evolution-v0.8.0/artifacts/pilot-ts-evolution-v0.8.0__claude-opus-5-5__EV2__core-rules-v0.2.0__r1/stage-4-grader.json`): passed=False
