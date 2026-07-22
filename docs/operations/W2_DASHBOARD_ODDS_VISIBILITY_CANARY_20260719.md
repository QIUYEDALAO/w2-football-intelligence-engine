# W2 Dashboard Odds Visibility Canary — 2026-07-19

Result: `PASS_STAGING`

## Release

- Implementation SHA: `bafeb06261bfa5614903cce4dc9f87a2a498501f`.
- Rollback baseline: `5cd3034878abe7522f8b18c8be32dc86f2a3da1e`.
- Delivery used local `git archive`; GitHub was not read or changed.

## Product correction

- Stale or non-ready quotes remain excluded from `current_odds` and executable decisions.
- Stored fixture-scoped observations are exposed separately as `last_known_odds` with
  `executable=false`, capture time, bookmaker count, Asian-handicap line/prices, and totals
  line/prices.
- Dashboard copy distinguishes “已有早盘·待临场更新” from “等待首轮盘口”.
- Machine-only countdowns, the inactive Boss View button, and false post-match tracking copy were
  removed without changing the page layout.

## Gates

- Full pytest: `1178 passed / 4 skipped`.
- Ruff, Mypy (230 source files), TypeScript typecheck, Web production build: PASS.
- Offline acceptance, tracked-output, secret scan, `git diff --check`: PASS.
- Isolated predeploy-e2e: PASS; staging-parity: `3 passed`.

## Staging evidence

- DayView: 31 cards; 6 cards have stored odds, including fixtures `1494210`, `1494212`, and
  `1494213` at the verified 2026-07-19 22:30 Beijing kickoff.
- Each of those three fixtures has 10 bookmakers and both canonical AH and totals snapshots.
- Five sequential reads: HTTP 200; warm latency 23–26 ms.
- Decision/pick/status projection hash remained
  `fede29c1a1d076e7ba47aff08354ce2dbc458152b037d9056169f5136fa4ab3f`.
- Provider requests stayed 738; market observations stayed 3,812,702; checkpoints stayed 122;
  all four lock tables stayed zero; Redis DB1 Celery queue stayed zero.
- API RSS 253.9 MiB versus 319.7 MiB baseline; all four services healthy with restart 0 and OOM
  false. Scheduler was restored healthy to its pre-canary active state.
- Alembic remained `0023_create_checkpoint_refresh_schedule`.

Safari pixel capture was unavailable because the Mac was locked. The deployed Web bundle and live
API contract were verified; this does not change the staging data-contract result.
