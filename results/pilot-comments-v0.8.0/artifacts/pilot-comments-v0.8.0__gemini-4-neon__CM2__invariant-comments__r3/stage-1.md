# pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r3 — Stage 1/1

- Timestamp UTC: 2026-11-27T07:34:55Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: invariant-comments
- Elapsed seconds: 176.93
- Workspace modified: ['api.py', 'dedupe.py', 'models.py', 'retry.py', 'storage.py', 'worker.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect the multi-file job-queue package in this workspace (`models.py`, `storage.py`, `dedupe.py`, `retry.py`, `worker.py`, `api.py`, `tests/test_queue.py`, `run_checks.py`) and run `python3 run_checks.py`. Using Python standard library only, leave `tests/test_queue.py`, `tests/__init__.py`, and `run_checks.py` unmodified while updating the production modules to:
1. Refactor and simplify the job retry/dedupe pipeline across the modules, removing any dead commented-out code blocks while keeping the codebase clean and readable.
2. Implement `JobPipeline.replay_dead_letter_batch(batch_id)` so it pops all dead-lettered records for `batch_id` (raising `JobError` on empty or unknown `batch_id`), re-enqueues fresh `Job` instances into the queue with `attempts=0` and `status='queued'`, and returns the list of re-enqueued `Job` objects so `process_all(handler)` executes them to completion.
3. Re-run `python3 run_checks.py` and confirm it exits 0.

## Raw Model Output

Updated the job-queue production modules while leaving [tests/test_queue.py](file://<TMP_WORKSPACE>/tests/test_queue.py), [tests/__init__.py](file://<TMP_WORKSPACE>/tests/__init__.py), and [run_checks.py](file://<TMP_WORKSPACE>/run_checks.py) unmodified.

### Changes
- **[models.py](file://<TMP_WORKSPACE>/models.py)**: Added `validate_positive_int` to centralize positive-integer validation.
- **[retry.py](file://<TMP_WORKSPACE>/retry.py)**: Simplified `RetryPolicy.__init__` and `compute_backoff_ms` using `validate_positive_int`.
- **[dedupe.py](file://<TMP_WORKSPACE>/dedupe.py)**: Simplified `is_duplicate` and `next_replay_epoch` while preserving tenant/epoch dedupe keys and fencing invariants.
- **[storage.py](file://<TMP_WORKSPACE>/storage.py)**: Simplified `DeadLetterStore.put` and `DeadLetterStore.has_batch` while keeping synchronous commit ordering intact.
- **[worker.py](file://<TMP_WORKSPACE>/worker.py)**: Extracted `JobWorker._handle_failure` to keep `process_next` concise while preserving epoch-aware dedupe checks and `storage.persist_result` before `queue.ack`.
- **[api.py](file://<TMP_WORKSPACE>/api.py)**: Implemented `JobPipeline.replay_dead_letter_batch(batch_id)` to pop the dead-letter batch (raising `JobError` on empty or unknown `batch_id`), advance each tenant's replay epoch via `DedupeRegistry.next_replay_epoch` based on the tenant's highest `failed_epoch` in the batch, re-enqueue fresh `Job` instances (`attempts=0`, `status="queued"`), and return them.
- No dead commented-out code blocks were present; existing `# INVARIANT:` comments were preserved.

### Verification
- `python3 run_checks.py` exited `0` with all 4 tests in `VisibleJobQueueTests` passing, and additional edge-case checks passed for cross-epoch replay, stale-epoch fencing, multi-tenant/mixed-epoch replay batches, error handling, and `persist_result` before `ack` ordering.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r3/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r3/stage-1-grader.json`): passed=True
