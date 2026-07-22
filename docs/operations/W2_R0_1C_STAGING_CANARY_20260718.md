# W2 R0.1c Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release under test

- Local implementation SHA: `58ca49793f2011148e5bfc7d2f1ac5c9062ffbf8`.
- Accepted predecessor and rollback release:
  `13183b3eabd9022cada47a76d01fa619648bd01f`.
- Delivery used a local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Focused and full tests, Ruff, Mypy, TypeScript/Web build, acceptance,
  tracked-output, credential, migration, isolated staging-parity and
  predeploy-e2e gates passed. The final full suite reported
  `1097 passed, 4 skipped`.

## Canonical decision proof

- The final Decision Contract postcondition clears pick, recommendation ID,
  executable odds, lock eligibility and outcome tracking for every non-ready
  decision.
- The staging DayView contained 11 cards: 10 WATCH and one NOT_READY. All 11
  had null pick/recommendation, false lock/outcome flags and zero current odds.
- Fixture `1494701` has conflicting AH identity. Its expected product change was
  WATCH to NOT_READY; every other fixture projection remained unchanged.
- The public analysis-card for `1494701` projected the same canonical contract:
  NOT_READY/SKIP, null pick/recommendation, false lock/outcome flags and no
  current odds. No public market retained PICK, ANALYSIS_PICK or RECOMMEND.
- Fixture `1576804` also retained no pick, recommendation, lock, outcome tracking
  or executable odds.

## Runtime and mutation gates

- Provider request rows remained 673 and `future_market_observation` remained
  3,757,226. Recommendation, Gate 5, forward and shadow locks remained zero.
- Redis queue remained zero and Alembic remained
  `0023_create_checkpoint_refresh_schedule`.
- API, worker and web restart counts remained zero with OOM false. API RSS was
  268.1 MiB, below the 318 MiB canary limit.
- Scheduler was created stopped during the canary, then restored healthy with
  restart zero/OOM false. The watchdog timer was restored active.

R0.1c is accepted locally. The next authorized phase is R0.2.
