# Finance Memo: Atlas Checkout Pilot Budget & Exit Criteria

- **Date:** 2026-11-20
- **From:** FP&A / Finance Operations
- **Subject:** Q3 Pilot Actuals and Q4 Expansion Request Status

## Approved Spend (Q3 Pilot — W01 to W18)
- **Direct pilot spend (approved):** $42,000 (engineering contractor hours + payment gateway fees).
- **Amortized shared GPU allocation[^1]:** $6,000 allocated across the 18-week window.
- **Total fully loaded Q3 pilot cost:** $48,000.

## Q4 Expansion Request ($115,000)
- **Status:** **PENDING CFO SIGN-OFF (UNAPPROVED)**. No purchase orders or commitments may be opened against the $115,000 Q4 request until formal Go/No-Go review passes.

## Pilot Exit Gate (Required for GO)
1. Steady-state **weighted** conversion rate (`sum(conversions) / sum(sessions)` excluding `PARTIAL_OUTAGE` weeks) **>= 3.50%**.
2. **Zero open P1** production incidents in the checkout support queue.

[^1]: Shared inference cluster depreciation billed internally; report direct ($42,000) and fully loaded ($48,000) figures distinctly in board materials.
