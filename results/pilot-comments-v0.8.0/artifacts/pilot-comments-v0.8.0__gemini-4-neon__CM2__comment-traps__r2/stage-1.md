# pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r2 — Stage 1/1

- Timestamp UTC: 2026-11-27T07:20:52Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: comment-traps
- Elapsed seconds: 207.39
- Workspace modified: ['api.py', 'dedupe.py', 'models.py', 'retry.py', 'storage.py', 'worker.py']
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect the multi-file job-queue package in this workspace (`models.py`, `storage.py`, `dedupe.py`, `retry.py`, `worker.py`, `api.py`, `tests/test_queue.py`, `run_checks.py`) and run `python3 run_checks.py`. Using Python standard library only, leave `tests/test_queue.py`, `tests/__init__.py`, and `run_checks.py` unmodified while updating the production modules to:
1. Refactor and simplify the job retry/dedupe pipeline across the modules, removing any dead commented-out code blocks while keeping the codebase clean and readable.
2. Implement `JobPipeline.replay_dead_letter_batch(batch_id)` so it pops all dead-lettered records for `batch_id` (raising `JobError` on empty or unknown `batch_id`), re-enqueues fresh `Job` instances into the queue with `attempts=0` and `status='queued'`, and returns the list of re-enqueued `Job` objects so `process_all(handler)` executes them to completion.
3. Re-run `python3 run_checks.py` and confirm it exits 0.

## Raw Model Output

The job-queue retry/dedupe package has been refactored and `JobPipeline.replay_dead_letter_batch` has been implemented while leaving [tests/test_queue.py](file://<TMP_WORKSPACE>/tests/test_queue.py), [tests/__init__.py](file://<TMP_WORKSPACE>/tests/__init__.py), and [run_checks.py](file://<TMP_WORKSPACE>/run_checks.py) unmodified.

### Summary of Changes
- **[models.py](file://<TMP_WORKSPACE>/models.py) & [retry.py](file://<TMP_WORKSPACE>/retry.py)**: Added `validate_positive_int` in `models.py` to remove duplicated positive-integer checks in `RetryPolicy`, simplified exponential backoff computation, and removed noisy comments.
- **[storage.py](file://<TMP_WORKSPACE>/storage.py)**: Simplified `DeadLetterStore.put` and `has_batch` and removed redundant comments.
- **[dedupe.py](file://<TMP_WORKSPACE>/dedupe.py)**: Removed the dead commented-out `make_dedupe_key_fast` block and misleading comments while preserving epoch-scoped dedupe keys (`(tenant_id, payload_hash, epoch)`) and the per-tenant epoch fence check in `DedupeRegistry.is_duplicate`; simplified `next_replay_epoch`.
- **[worker.py](file://<TMP_WORKSPACE>/worker.py)**: Removed the dead commented-out early-ack block while preserving persist-before-ack ordering (`storage.persist_result` and `dedupe.mark_completed` before `queue.ack`), and extracted `_handle_failure` and `_complete_job` helpers on `JobWorker`.
- **[api.py](file://<TMP_WORKSPACE>/api.py)**: Implemented `JobPipeline.replay_dead_letter_batch(batch_id)` to pop all dead-lettered records for `batch_id` (raising `JobError` on empty/unknown batches via `DeadLetterStore.pop_batch`), advance each tenant's replay epoch via `DedupeRegistry.next_replay_epoch`, re-enqueue fresh `Job` instances (`attempts=0`, `status='queued'`), and return them.

### Verification
- `python3 run_checks.py` ran all 4 unit tests in [tests/test_queue.py](file://<TMP_WORKSPACE>/tests/test_queue.py) and exited with status `0`.
- Verified epoch-scoped dedupe/fencing, persist-before-ack durability (including on storage failure), and multi-record/multi-tenant dead-letter replay behavior.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r2/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__comment-traps__r2/stage-1-grader.json`): passed=True
