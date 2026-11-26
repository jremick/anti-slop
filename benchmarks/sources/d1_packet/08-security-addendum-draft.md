# Security Addendum Proposal: Webhook Hardening Q4

- **Date:** 2026-11-22
- **Status:** DRAFT — PENDING CAB APPROVAL (NOT LIVE IN PRODUCTION)
- **Owner:** Security Engineering

## Proposed Changes (Unapproved)
1. **Payload Cap Reduction:** Further reduce `POST /v3/webhooks` max payload size from `96 KiB` to **`64 KiB`**.
2. **Mutual TLS (mTLS):** Require client-certificate mTLS on all webhook endpoints in addition to Bearer tokens.

Neither proposal is approved or deployed as of 2026-11-22. Do not quote these values as active production limits until CAB approval and rollout dates are finalized.
