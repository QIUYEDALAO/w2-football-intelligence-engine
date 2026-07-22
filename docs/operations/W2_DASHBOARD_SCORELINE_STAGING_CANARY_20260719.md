# W2 Dashboard simulated-scoreline canary — 2026-07-19

Result: `PASS_STAGING`

## Release

- Accepted implementation SHA: `b73c43bcdab7bf6c51720ccc5777cd80e46562f3`.
- Rollback baseline: `bafeb06261bfa5614903cce4dc9f87a2a498501f`.
- Delivery used local `git archive`; GitHub was not read or changed.
- The first candidate `09244d5b39a325243a522c098440fc5c2d3253f5` was not accepted: it exposed that
  Dashboard was re-deriving a frozen Decision Contract after scoreline materialization. The
  scheduler remained stopped until the final correction passed.

## Product correction

- DayView now projects frozen scoreline picks, scoreline readiness and the actual simulation count.
- The team row again shows the top three results from the stored 10,000-run simulation, including
  each scoreline probability. Odds and data-readiness copy remain in their existing columns.
- A verified frozen Decision Contract is projected by Dashboard without being re-derived. Adding
  scoreline evidence therefore cannot promote a `NOT_READY/BLOCKED` fixture to `WATCH/STALE`.
- The three current fixtures remain `NOT_READY/BLOCKED`, with `pick=null` and
  `lock_eligible=false`; only their scoreline reference became visible.

## Real staging scorelines

- `1494210`: `0-1 (11%)`, `0-2 (10%)`, `1-1 (10%)`.
- `1494212`: `1-1 (11%)`, `1-2 (10%)`, `0-1 (9%)`.
- `1494213`: `2-0 (11%)`, `1-0 (10%)`, `2-1 (10%)`.
- All three report `scoreline_simulations=10000` and `scoreline_readiness=READY`.

## Gates

- Full pytest: `1178 passed / 4 skipped`.
- Ruff, Mypy (230 source files), TypeScript typecheck and Web production build: PASS.
- Playwright Decision Contract suite: `8 passed`.
- Offline acceptance, tracked-output guard, secret scan and `git diff --check`: PASS.
- Isolated predeploy-e2e, migration-to-head, fake-provider contract and frozen artifact checks: PASS.

## Canary invariants

- Five sequential plus two concurrent reads returned HTTP 200 and the same normalized projection
  hash: `c1eb9f4a0548d2ec056ffee2a5e357a58b84258082f570b7c918088f90b22196`.
- Provider requests stayed `738`; future market observations stayed `3,812,702`; checkpoint row
  count stayed `122`. Exactly three existing frozen checkpoint payloads were updated.
- Recommendations and all four recommendation/forward/shadow lock tables stayed zero.
- Redis DB1 Celery queue stayed zero. Forward ledger hash stayed
  `0bf4398f26f733c96a1f01494848f47e6763ad9acffd40731a18c5cbf711727c`.
- Alembic remained `0023_create_checkpoint_refresh_schedule`.
- API RSS was `253.2 MiB` versus the `272.5 MiB` baseline; API, Web and worker were healthy with
  restart zero and OOM false.
- Scheduler was restored to `running/healthy`, restart zero, OOM false and `unless-stopped`.

The in-app browser navigation check timed out because the live page continuously polls; the
deployed Web bundle, live DayView contract and focused Playwright rendering contract were verified.
