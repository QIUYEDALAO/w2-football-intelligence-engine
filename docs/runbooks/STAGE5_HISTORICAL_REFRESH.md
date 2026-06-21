# Stage 5 Historical Refresh

Stage 5B uses only fixed sources:

- W1 local international dataset CSV
- W1 raw `WorldCup2026.xlsx` when present
- W1 local historical World Cup OU odds CSV
- W1 2026 raw odds snapshots
- API-Football as the only external completion source

Before every refresh:

1. Confirm the API key is present without printing it.
2. Run one API-Football `status` request.
3. Reserve 2,000 requests for live operations.
4. Stop immediately if remaining quota is at or below the reserve.
5. Write raw provider responses only under ignored `runtime/stage5b/`.
6. Commit only code, schemas, manifests, checks, and reports.

Historical Football-Data aggregate prices are
`UNKNOWN_PREMATCH_AGGREGATE`. They are not opening odds and must not be used for
T-24h, T-1h, or price-movement backtests.

W1 AI outputs are not labels and are not training data.
