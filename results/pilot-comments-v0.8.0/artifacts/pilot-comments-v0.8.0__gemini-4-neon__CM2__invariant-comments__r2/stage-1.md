# pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r2 — Stage 1/1

- Timestamp UTC: 2026-11-27T07:24:56Z
- Model: google/gemini-4-neon (reasoning=high, observed=gemini-4-neon-high)
- Condition: invariant-comments
- Elapsed seconds: 244.36
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

### Summary of Changes
1. **Pipeline refactoring & simplification** (no dead commented-out code blocks were present; all `# INVARIANT:` comments and guarantees were preserved):
   - [models.py](file://<TMP_WORKSPACE>/models.py#L23-L26): Added `validate_positive_int` alongside the existing validators.
   - [retry.py](file://<TMP_WORKSPACE>/retry.py#L9-L16): Deduplicated positive-integer validation via `validate_positive_int` and simplified `compute_backoff_ms`.
   - [dedupe.py](file://<TMP_WORKSPACE>/dedupe.py#L27-L42): Simplified `is_duplicate`, `mark_completed`, and `next_replay_epoch` while preserving tenant/epoch dedupe keying and older-epoch fencing.
   - [storage.py](file://<TMP_WORKSPACE>/storage.py#L35-L40): Simplified `DeadLetterStore.put` and `has_batch` while keeping synchronous `persist_result` behavior intact.
   - [worker.py](file://<TMP_WORKSPACE>/worker.py#L34-L108): Extracted `InMemoryQueue._pop_in_flight` and `JobWorker._handle_failure` to simplify `ack`/`nack` and `process_next`, preserving dedupe epoch checks and `persist_result`-before-`ack` ordering.
2. **Dead-letter batch replay**:
   - [api.py](file://<TMP_WORKSPACE>/api.py#L63-L84): Implemented `JobPipeline.replay_dead_letter_batch(batch_id)` to pop all records for `batch_id` via `DeadLetterStore.pop_batch` (raising `JobError` on empty or unknown `batch_id`), compute the next replay epoch per tenant with `DedupeRegistry.next_replay_epoch` so cross-epoch replays execute without fencing each other, re-enqueue fresh `Job` instances (`attempts=0`, `status="queued"`), and return the re-enqueued `Job` list.

### Verification
- Ran `python3 run_checks.py`: all 4 unit tests in [tests/test_queue.py](file://<TMP_WORKSPACE>/tests/test_queue.py) passed (`exit code 0`), along with extra checks for cross-epoch replays with prior payload hashes, older-epoch fencing, `epoch=0`/mixed-epoch batches, and `persist_result`-before-`ack` crash safety.


## Workspace Grader & Diff
- Workspace diff: `runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r2/stage-1-workspace.diff`
- Automated grader (`runs-local/pilot-comments-v0.8.0/artifacts/pilot-comments-v0.8.0__gemini-4-neon__CM2__invariant-comments__r2/stage-1-grader.json`): passed=True
