# pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r3 — Stage 1/1

- Timestamp UTC: 2026-11-27T07:39:04Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: comment-traps
- Elapsed seconds: 247.98
- Workspace modified: ['api.py', 'dedupe.py', 'models.py', 'retry.py', 'storage.py', 'worker.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect the multi-file job-queue package in this workspace (`models.py`, `storage.py`, `dedupe.py`, `retry.py`, `worker.py`, `api.py`, `tests/test_queue.py`, `run_checks.py`) and run `python3 run_checks.py`. Using Python standard library only, leave `tests/test_queue.py`, `tests/__init__.py`, and `run_checks.py` unmodified while updating the production modules to:
1. Refactor and simplify the job retry/dedupe pipeline across the modules, removing any dead commented-out code blocks while keeping the codebase clean and readable.
2. Implement `JobPipeline.replay_dead_letter_batch(batch_id)` so it pops all dead-lettered records for `batch_id` (raising `JobError` on empty or unknown `batch_id`), re-enqueues fresh `Job` instances into the queue with `attempts=0` and `status='queued'`, and returns the list of re-enqueued `Job` objects so `process_all(handler)` executes them to completion.
3. Re-run `python3 run_checks.py` and confirm it exits 0.

## Raw Model Output

Updated the job-queue retry/dedupe pipeline while leaving [tests/test_queue.py](file://<TMP_WORKSPACE>/tests/test_queue.py), [tests/__init__.py](file://<TMP_WORKSPACE>/tests/__init__.py), and [run_checks.py](file://<TMP_WORKSPACE>/run_checks.py) unmodified:

### Changes
- **[models.py](file://<TMP_WORKSPACE>/models.py)**: Added `validate_positive_int` to centralize positive-integer validation and removed redundant comments.
- **[retry.py](file://<TMP_WORKSPACE>/retry.py)**: Simplified `RetryPolicy` validation via `validate_positive_int` and streamlined `compute_backoff_ms`.
- **[storage.py](file://<TMP_WORKSPACE>/storage.py)**: Simplified `DeadLetterStore.put` and `has_batch`, and cleaned up redundant comments.
- **[dedupe.py](file://<TMP_WORKSPACE>/dedupe.py)**: Removed the dead commented-out `make_dedupe_key_fast` block and misleading comments while preserving epoch-scoped dedupe keys and tenant epoch fencing in `is_duplicate`, and simplified `is_duplicate`, `mark_completed`, and `next_replay_epoch`.
- **[worker.py](file://<TMP_WORKSPACE>/worker.py)**: Removed the dead commented-out completion block while preserving persist-before-ack durability ordering, and extracted `_handle_failure` and `_complete_job` helpers on `JobWorker`.
- **[api.py](file://<TMP_WORKSPACE>/api.py#L72-L94)**: Implemented `JobPipeline.replay_dead_letter_batch(batch_id)` to pop all dead-lettered records for `batch_id` (raising `JobError` on empty/unknown batches), advance each tenant's replay epoch via `DedupeRegistry.next_replay_epoch`, re-enqueue fresh `Job` instances (`attempts=0`, `status="queued"`), and return them.

### Verification
- Ran `python3 run_checks.py`: all 4 tests in `VisibleJobQueueTests` passed (`Ran 4 tests ... OK`, exit code `0`).
- Verified epoch-scoped dedupe/fencing, persist-before-ack ordering on success and storage errors, and multi-record/advanced-epoch dead-letter replays.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r3/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r3/stage-1-grader.json`): passed=True
