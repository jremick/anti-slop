## 🚀 Auth & Retry Worker Hardening

This PR hardens session token validation and makes the webhook retry queue resilient to transient database hiccups.

### Summary of Changes
- Hardened nullable session expiration handling in `src/session_validator.ts` so malformed or expired sessions are cleanly rejected.
- Added resilient database timeout handling and signing-key loading in `src/queue_worker.py`.
- Expanded unit test coverage in `tests/test_worker.py` for dispatch and concurrency guarantees.

### Verification
- Ran `pytest` — **All tests pass!** Zero failures, zero warnings, ready for immediate deploy.

Let me know if you'd like any adjustments before merge!
