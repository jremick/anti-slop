# INC-214 Postmortem: Webhook Worker OOM Storm

- **Incident Date:** 2026-11-14
- **Report Closed:** 2026-11-17
- **Status:** Resolved in v3.4.2 (2026-11-16)

## Timeline & Mitigation
- **2026-11-14 21:05 UTC:** Queue workers hit OOM under simultaneous `128 KiB` payloads and 4-attempt retry bursts. On-call activated an **emergency temporary circuit breaker**: `32 KiB` payload limit and `30 req/min` workspace rate limit.
- **2026-11-16 16:30 UTC:** Deployed **v3.4.2**, lifting both temporary emergency overrides and establishing new steady-state production limits:
  - Max payload size: **`96 KiB`**
  - Rate limit: **`60 req/min` (burst `10`)**
  - Delivery attempts: **`3` total attempts** (`1` initial + `2` retries at `30s`, `2m`)
- Replay protection (`X-Hook-Timestamp` `300s`), `X-Hook-Signature-256`, Bearer auth, and mandatory `Idempotency-Key` were unaffected.
