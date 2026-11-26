# ADR-019: Webhook Rate-Limit and Backoff Amendment

- **Date:** 2026-08-18
- **Status:** Accepted (amends RFC-041)

## Decision
Downstream ingestion workers saturated during peak fan-out under RFC-041 limits. Effective with v3.2:
1. Reduce per-workspace rate limit on `POST /v3/webhooks` from `120 req/min` (burst `20`) to **`60 req/min` (burst `10`)**.
2. Reduce delivery retries from `5` attempts over `15 minutes` to **`4` total attempts** over `10 minutes` (initial delivery + retries at `30s`, `2m`, `5m`).
3. Keep max payload size (`128 KiB`), Bearer auth, and `X-Hook-Signature-256` unchanged.
