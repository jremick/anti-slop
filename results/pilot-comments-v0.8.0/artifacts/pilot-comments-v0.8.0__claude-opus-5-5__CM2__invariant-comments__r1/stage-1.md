# pilot-comments-v0.8.0__claude-opus-5-5__CM2__invariant-comments__r1 — Stage 1/1

- Timestamp UTC: 2026-11-27T06:59:01Z
- Model: anthropic/claude-opus-5-5 (reasoning=medium, observed=claude-opus-5-5)
- Condition: invariant-comments
- Elapsed seconds: 50.99
- Workspace modified: ['api.py', 'dedupe.py', 'retry.py', 'storage.py', 'worker.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect the multi-file job-queue package in this workspace (`models.py`, `storage.py`, `dedupe.py`, `retry.py`, `worker.py`, `api.py`, `tests/test_queue.py`, `run_checks.py`) and run `python3 run_checks.py`. Using Python standard library only, leave `tests/test_queue.py`, `tests/__init__.py`, and `run_checks.py` unmodified while updating the production modules to:
1. Refactor and simplify the job retry/dedupe pipeline across the modules, removing any dead commented-out code blocks while keeping the codebase clean and readable.
2. Implement `JobPipeline.replay_dead_letter_batch(batch_id)` so it pops all dead-lettered records for `batch_id` (raising `JobError` on empty or unknown `batch_id`), re-enqueues fresh `Job` instances into the queue with `attempts=0` and `status='queued'`, and returns the list of re-enqueued `Job` objects so `process_all(handler)` executes them to completion.
3. Re-run `python3 run_checks.py` and confirm it exits 0.

## Raw Model Output

`replay_dead_letter_batch` now works, and `python3 run_checks.py` passes all 4 tests and exits 0. Before the change, one test failed because the method only raised "not yet implemented". I didn't modify `tests/test_queue.py`, `tests/__init__.py` or `run_checks.py`.

**The replay method (`api.py`)**
- It removes every dead-lettered record for the batch. An empty or unknown `batch_id` raises `JobError`, and so does a blank one.
- It puts a fresh `Job` for each record back on the queue with `attempts=0` and `status='queued'`, and returns the list. `process_all` then runs them to completion.
- **One choice to check:** a replayed job doesn't keep its original epoch. It gets a new one that is higher than both the epoch it failed at and the newest epoch that tenant has completed. Without this, a replay could be silently skipped as a duplicate ("deduped") if the tenant had completed newer work since the failure. In a manual test, a job that failed at epoch 1 was replayed after the tenant completed an epoch-3 job. It ran at epoch 4 and completed. Replaying the same batch again, or an unknown one, raised `JobError` as expected.

**Cleanup**
- There were no commented-out code blocks in the modules, so there was nothing to remove. I kept the `# INVARIANT:` comments because they describe rules the code relies on, not dead code.
- `worker.py`: the failure path (retry or dead-letter) is now its own `_handle_failure` method. The dead-letter record is built with named fields instead of seven positional arguments.
- `dedupe.py`: the duplicate check and the epoch calculations are shorter, with the same behaviour.
- `retry.py`: the backoff calculation is now one line, still 50 ms, 100 ms, … doubling per attempt.
- `storage.py`: two small simplifications to adding and checking batches.
- `api.py`: removed an unused `JobError` import.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__claude-opus-5-5__CM2__invariant-comments__r1/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__claude-opus-5-5__CM2__invariant-comments__r1/stage-1-grader.json`): passed=True
