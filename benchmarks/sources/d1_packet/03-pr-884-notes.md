# PR #884 Release Notes: Webhook Replay Protection and Idempotency

- **Merged:** 2026-09-29 (targeted for release v3.4.0)
- **Author:** @dchen

## Summary of Changes
- Made `Idempotency-Key` header **mandatory** on `POST /v3/webhooks`; requests omitting it now fail with HTTP `400`.
- Added `X-Hook-Timestamp` header validated alongside `X-Hook-Signature-256` with a **5-minute (`300s`) replay window**; requests outside the window fail with HTTP `401`.
- **Note on payload cap:** Reviewers asked whether to cut max payload size in this PR. We explicitly kept **`128 KiB`** unchanged in PR #884 pending capacity analysis.
