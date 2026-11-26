# RFC-041: Webhook Delivery v3 Initial Specification

- **Date:** 2026-06-10
- **Status:** Accepted (baseline v3.0 contract)
- **Endpoint:** `POST /v3/webhooks`

## Contract Parameters
- **Authentication:** `Authorization: Bearer <token>`
- **Signing:** `X-Hook-Signature-256` (HMAC-SHA256 hex digest of raw body)
- **Max Payload Size:** `128 KiB`
- **Rate Limit:** `120 req/min` per workspace (burst `20`)
- **Retry Schedule:** `5` total attempts over `15 minutes`
