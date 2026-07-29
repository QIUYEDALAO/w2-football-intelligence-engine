# W2 R0.1b Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release under test

- Local implementation SHA: `13183b3eabd9022cada47a76d01fa619648bd01f`.
- Accepted predecessor: `3fc2412c258b996d4f8af6bd44f2799438f49504`.
- Delivery used a local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Local focused and full tests, Ruff, Mypy, TypeScript/Web build, acceptance,
  tracked-output, credential, migration, isolated staging-parity and predeploy-e2e
  gates passed. The final full suite reported `1094 passed, 4 skipped`.

## Freshness proof

- Quote time is taken only from authoritative quote-identity `captured_at`.
- Fixture `1576804` reports AH identity conflict as freshness `INCOMPLETE` and
  OU complete identity as `STALE`, aged 39,520.521 seconds against the 1,800
  second limit.
- Neither stale nor incomplete quote is exposed in `current_odds`; generated
  card timestamps were not used as quote timestamps.
- The current DayView window contained 11 cards. All were `STALE/WATCH`, and
  all 11 exposed zero current odds.

## Product and runtime invariants

- The canary crossed a live kickoff boundary, so three fixtures naturally left
  the default `today` upcoming window. For every fixture present in both captures,
  the canonical fixture/tier/pick/recommendation/lock projection compared byte
  for byte equal. All retained WATCH, null pick/recommendation and lock false.
- Provider request rows remained 673 and `future_market_observation` remained
  3,757,226. Recommendation, Gate 5, forward and shadow locks remained zero.
- Redis queue remained zero and Alembic remained
  `0023_create_checkpoint_refresh_schedule`.
- API, worker and web restart counts remained zero with OOM false. API RSS was
  265.2 MiB. The scheduler was created stopped for the canary, then restored
  healthy with restart zero/OOM false; the watchdog timer was restored active.

R0.1b is accepted locally. The next authorized phase is R0.1c.
