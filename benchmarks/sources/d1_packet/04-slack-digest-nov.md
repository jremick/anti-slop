# `#eng-platform` Slack Digest (2026-11-12 to 2026-11-19)

- **2026-11-12 10:14 — @pm-jordan:** Hey team, customer asked if our webhook payload cap is already 64 KiB?
- **2026-11-12 10:19 — @dev-sam:** Pretty sure we lowered it to 64 KiB in v3.4, let me check later.
- **2026-11-14 21:05 — @oncall-priya:** INC-214 active — flipping emergency circuit breaker on webhooks to 32 KiB payload and 30 req/min until queues drain.
- **2026-11-18 14:40 — @support-alex:** Just pasted our standard support macro to Acme (`128 KiB`, `120 req/min`, 5 attempts) — let me know if anything changed.
- **2026-11-19 09:02 — @lead-maya:** @support-alex please stop using that July macro! And @dev-sam v3.4.0 did NOT drop to 64 KiB. Check `05-changelog-v3.4.md` (v3.4.2) and the closed INC-214 postmortem for the actual live numbers after we lifted the Nov 14 emergency breaker.
