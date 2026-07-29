# W2 Dashboard decision-scoreline canary — 2026-07-19

Result: `PASS_STAGING`

## Release

- Accepted implementation SHA: `01f8a75aa87cfaf58d0db3635eefc02016830d87`.
- Rollback baseline: `b73c43bcdab7bf6c51720ccc5777cd80e46562f3`.
- Delivery used a local `git archive`; GitHub was not read or changed.

## Product correction

- Dashboard remains a decision surface and keeps its existing layout.
- A row without a unified Decision Contract pick now says that no recommended handicap or
  recommended score exists. Raw simulation leaders are not shown as recommendations.
- A row with an `ANALYSIS_PICK` or `RECOMMEND` labels the selected market as `推荐盘口`.
- Recommended scores are selected only from simulated scorelines that settle the selected
  Asian-handicap, totals, or 1X2 direction as `WIN` or `HALF_WIN`.
- Market observations remain visible as explicitly non-recommendation reference data.

## Gates

- Full pytest: `1180 passed / 4 skipped`.
- Ruff, Mypy (230 source files), TypeScript typecheck and Web production build: PASS.
- Offline acceptance, tracked-output guard, secret scan and `git diff --check`: PASS.
- Isolated staging-host predeploy-e2e, migration-to-head, fake-provider and frozen artifact
  contracts: PASS.

## Canary evidence

- `/health`, `/ready`, `/v1/version`, DayView and the public Web bundle returned HTTP 200.
- API and Web release identity matched `01f8a75aa87cfaf58d0db3635eefc02016830d87`; Alembic
  current/head remained `0023_create_checkpoint_refresh_schedule` / `MATCH`.
- The three visible fixtures remained `NOT_READY`, `pick=null`, `lock_eligible=false`, and now
  expose zero `direction_top3` recommendation scores.
- Five sequential and two concurrent reads kept the decision projection hash
  `f486addda98249331b251cfd93fe61c0b1b7813dfe21582a4e47247f76087eb2`.
- Warm in-host DayView latency was 21.7–23.1 ms.
- Provider requests stayed `738`; future market observations stayed `3,812,702`; checkpoints
  stayed `122`; recommendations and all four lock tables stayed zero.
- Redis DB1 Celery queue stayed zero; the forward ledger hash stayed
  `42ef08353e6d103c76673ba6699aef6a397850eca805c4fe631cfbf6bfe04b04`.
- API RSS was 224.6 MiB versus the 280.8 MiB baseline. API, Web, worker and scheduler finished
  healthy with restart zero and OOM false.
- Scheduler was restored to its pre-canary `running/healthy`, `unless-stopped` state.
