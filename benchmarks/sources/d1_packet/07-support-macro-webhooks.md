# Support Macro: Webhook Integration Limits

- **Macro ID:** `SUP-WH-03`
- **Last Updated:** 2026-07-05

Hi there! Our `POST /v3/webhooks` API supports payloads up to `128 KiB` at `120 req/min` (burst `20`) per workspace. Failed deliveries retry up to `5` times over `15 minutes`. Sign requests with `X-Hook-Signature-256` and authenticate with your Bearer token.
