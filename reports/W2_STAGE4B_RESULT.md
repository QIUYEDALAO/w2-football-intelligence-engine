# W2 Stage 4B Result

Controlled live ingestion data-link smoke completed.

Gate 2: CLOSED
Auth probe requests: 1
Discovery requests: 0
Data requests: 2
Total provider requests: 3
Provider remaining quota: 6751
Continuation cumulative provider requests: 48
Continuation request note: includes earlier failed live attempts and redacted status diagnostics during automatic repair; final controlled run audit remains the per-request source of truth.

Local fixture discovery:

- Scanned W1 files: 74
- Records read: 133
- Kickoff parsed: 133 success / 0 failed
- Future / past fixtures: 35 / 98
- now_utc: 2026-06-21T18:22:48.584864+00:00
- Earliest kickoff: 2026-06-11T19:00:00+00:00
- Latest kickoff: 2026-06-28T02:00:00+00:00
- Full scanned file list is recorded in `reports/W2_STAGE4B_DATA_QUALITY.json`.

WARN_ONLY:

- SECONDARY_ODDS_PROVIDER_UNDECIDED

BLOCKER:

- None

Notes:

- W1 local fixture files are only a priority discovery source.
- If no upcoming World Cup fixture is available, a supported provider fixture may be used only for Gate 2 data-link smoke.
- Authorization headers and raw API keys are not recorded.
- Runtime raw responses are under ignored `runtime/live_smoke/`.
- No recommendations, models, or AI calls were executed.
- PUSH_BLOCKED_NO_ORIGIN
