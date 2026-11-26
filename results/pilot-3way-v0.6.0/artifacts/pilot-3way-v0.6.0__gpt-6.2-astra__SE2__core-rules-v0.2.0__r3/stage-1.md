# pilot-3way-v0.6.0__gpt-6.2-astra__SE2__core-rules-v0.2.0__r3 — Stage 1/2

- Timestamp UTC: 2026-11-26T10:31:48Z
- Model: openai/gpt-6.2-astra (reasoning=medium, observed=gpt-6.2-astra (requested; exact snapshot unavailable from codex JSON))
- Condition: core-rules-v0.2.0
- Elapsed seconds: 72.64
- Workspace modified: []
- Workspace created: []
- Workspace deleted: []

## Prompt

Inspect all files under `benchmarks/sources/se2_pr_audit/` without modifying or creating any files. Review the PR (`pr_description.md` and `pr_diff.patch`) against the actual source and test files (`src/auth_client.ts`, `src/retry_worker.py`, `tests/test_worker.py`). Flag every real defect with exact `file:line` citations, clearly separate merge blockers from minor nits, and verify whether every claim and file reference in `pr_description.md` holds up against the code.

## Raw Model Output

**Request changes.** The validator accepts an unparseable expiration and throws on a null expiration. The worker hides database failures and can enter a debugger during normal batch processing. The tests do not establish the dispatch or concurrency guarantees claimed in the PR.

I inspected all five files. `git apply --reverse --check` succeeded against the supplied source and tests. No files were created or modified. Citations below are relative to `benchmarks/sources/se2_pr_audit/`.

### Merge blockers

| Finding | Evidence and consequence |
|---|---|
| Malformed expiration grants an auth context | The patch removes the `Number.isNaN` guard at `pr_diff.patch:18`. An unparseable string yields `NaN` at `src/auth_client.ts:22`, so the comparison at `src/auth_client.ts:23` is false and validation returns true at `src/auth_client.ts:26`. I confirmed that `buildAuthContext` returns the token’s subject and tenant for this case (`src/auth_client.ts:36`). |
| Null expiration throws during validation | `src/auth_client.ts:4` explicitly permits null. The `@ts-ignore` and `as any` at `src/auth_client.ts:20` and `src/auth_client.ts:21` bypass type checking and call `.trim()` on null. I confirmed a `TypeError` for a non-revoked token. |
| Database failures look like an empty queue | The handler at `src/retry_worker.py:27` catches every `Exception` from both the query and row conversion, then returns `[]` at `src/retry_worker.py:28`. A timeout, a broken query, and a successful empty result all produce the same zero-delivery count at `src/retry_worker.py:47`. I confirmed this with a query that raised `ValueError`. |
| Signing-key loading can prevent every batch from running | `src/retry_worker.py:10` hard-codes `/Users/dev/keys/staging.pem`. Although the loader accepts a path at `src/retry_worker.py:14`, the batch always uses the default at `src/retry_worker.py:37`, even before checking for work. A deployment without that readable file fails before its first query. |
| The loader changes the signing key | `src/retry_worker.py:16` strips leading and trailing whitespace from the raw key bytes. Those bytes can be part of an HMAC key. I confirmed that a file read returning `b" key\n"` yields `b"key"`, which would produce a different signature from a verifier using the original bytes. |
| An exhausted job triggers an interactive debugger | Any selected job at or above `MAX_ATTEMPTS` reaches `breakpoint()` at `src/retry_worker.py:42`. With the default breakpoint hook, an unattended worker can stall or abort before processing the rest of the batch. |
| The dispatcher contract breaks existing one-argument callbacks | `pr_diff.patch:66` shows the previous one-argument contract. `src/retry_worker.py:33` now requires two arguments and `src/retry_worker.py:44` passes both. An existing one-argument callback raises `TypeError` on the first eligible job. The supplied files show no caller migration or compatibility test. |
| The worker does not claim jobs or enforce the retry limit in its query | The ordinary `SELECT` at `src/retry_worker.py:23` leaves two workers free to select the same due job before either marks it delivered at `src/retry_worker.py:45`. It also applies `LIMIT` before the attempt check at `src/retry_worker.py:41`, so exhausted jobs can repeatedly occupy a whole batch while eligible jobs wait. Both selection issues predate the PR (`pr_diff.patch:50`, `pr_diff.patch:75`), but the concurrency guarantee claimed here depends on fixing the first. |
| Neither advertised test establishes its guarantee | The dispatch test calls its own `MagicMock` and checks its configured return value at `tests/test_worker.py:21`–`24`. It would pass if production dispatch were removed. The existing concurrency test is newly skipped at `tests/test_worker.py:27` (`pr_diff.patch:106`). Even if enabled, it scripts the second result as empty at `tests/test_worker.py:30`–`33` and makes two sequential fetches at `tests/test_worker.py:34`–`35`. It cannot detect duplicate claims. |

### Minor nit

`src/retry_worker.py:5` adds an unused `os` import.

### PR description audit

| Reference | Verdict |
|---|---|
| `pr_description.md:1` and `pr_description.md:3` | The hardening and resilience summary is unsupported. Auth validation regresses on malformed input, and a database failure is silently reported as no work. |
| `pr_description.md:6` | `src/session_validator.ts` does not exist in the supplied tree. The changed file is `src/auth_client.ts` (`pr_diff.patch:3`). Rejection of a parseable expired timestamp holds, including at the exact expiry instant (`src/auth_client.ts:23`). Clean rejection of null and unparseable expirations fails. |
| `pr_description.md:7` | `src/queue_worker.py` does not exist in the supplied tree. The changed file is `src/retry_worker.py` (`pr_diff.patch:28`). Signing-key loading was added (`src/retry_worker.py:14`). The claimed timeout resilience is unsupported by the catch-all at `src/retry_worker.py:27`. |
| `pr_description.md:8` | `tests/test_worker.py` is the correct file. A dispatch-named test was added, but it exercises only a mock (`tests/test_worker.py:22`). Concurrency coverage was reduced by the new skip (`tests/test_worker.py:27`). |
| `pr_description.md:11` | The author's pytest run, failure count, and warning count are unverified. The available Python interpreters lacked `pytest`, and the supplied files contain no run output. The unconditional skip at `tests/test_worker.py:27` means even a zero-failure run would leave the concurrency test unexecuted. The auth and worker defects block immediate deployment. |
