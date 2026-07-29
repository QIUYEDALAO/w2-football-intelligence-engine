# W2 R0.3 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release and gates

- Accepted implementation SHA: `7e383e2f21fcd0b488ffc95cd58c6c6394291855`.
- Rollback release: `87e2ba15b5920c369ca90583b0b0d2dd1a73a74a`.
- Delivery used local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Local suite: `1112 passed, 4 skipped`; Ruff, Mypy (226 files), Web typecheck/build,
  acceptance, tracked-output, credential and diff gates passed.
- Isolated predeploy-e2e and staging-parity (`3 passed`) completed without using
  formal staging dependencies.

## Bounded-read proof

- Fixtures `1576804`, `1494701` and `1494210` returned HTTP 200.
- The first, five sequential and two concurrent probes completed in 0.30–0.53s.
- In-container fail-on-call global readers recorded zero calls. Scoped calls were
  observation 10, raw 60 and xG 60; every result remained within its fixed limit.
- Dashboard, DayView, fixture detail, analysis-card, odds timeline and market
  probabilities use request-local scoped dependencies. Offline global readers
  remain separate and were not invoked by public requests.

## Product and runtime invariants

- DayView product projection remained byte-identical with SHA-256
  `f2e282491966350c04a317d39d53424a25d6a09eee5421bb8e249f4b96917280`.
- Alembic stayed `0023_create_checkpoint_refresh_schedule`; provider requests
  stayed 673, observations 3,757,226, raw payloads 2,223 and checkpoints 73.
- Recommendation, Gate 5, forward and shadow locks remained zero; queue stayed zero.
- API RSS was 219.4 MiB against a 349.2 MiB limit. API, worker, scheduler and web
  ended healthy with restart zero and OOM false.
- Scheduler and watchdog were restored to their exact pre-canary active state.

R0.3 is accepted locally. `next_phase=R0.4`.
