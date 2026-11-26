# Webhook Service Changelog (v3.4.x)

## v3.4.2 — 2026-11-16 (Current Production)
- **Payload limit:** Lifted the Nov 14 INC-214 emergency `32 KiB` breaker and set permanent production max payload size to **`96 KiB`** (down from `128 KiB`).
- **Rate limit:** Lifted the temporary `30 req/min` breaker; restored steady-state ADR-019 limit of **`60 req/min` per workspace (burst `10`)**.
- **Retries:** Reduced max deliveries from `4` to **`3` total attempts** (`1` initial + `2` retries at `30s` and `2m`) to prevent retry amplification.

## v3.4.0 — 2026-10-02
- Shipped PR #884: mandatory `Idempotency-Key` (HTTP `400` if missing) and `X-Hook-Timestamp` with `300s` (5-minute) replay window (HTTP `401` if stale).
- Retained Bearer auth, `X-Hook-Signature-256`, `60 req/min` rate limit, and `128 KiB` payload cap.
