# MATCHDAY_RUNTIME_ENV_MATRIX_V1

The real execution environment was checked inside the API, worker, and scheduler containers, not from an SSH shell.

Key findings:

- Worker has `W2_PROVIDER_CALLS_DISABLED=false`.
- Worker allowlist includes `status,fixtures,odds,lineups`.
- Scheduler has `W2_FUTURE_FIXTURE_REFRESH_ENABLED=true`.
- Scheduler competition IDs explicitly include `allsvenskan`.
- Worker and scheduler both have database and Redis URLs present.
- Worker task `w2.future_fixture_refresh` is registered in code.
- Worker cannot see `W2_API_FOOTBALL_API_KEY`.

Derived matchday intake readiness: `NOT_READY`.

Blocker: `LIVE_GATE_API_KEY_NOT_VISIBLE`.
