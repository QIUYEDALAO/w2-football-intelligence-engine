# W2 R0.1a-B1 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release under test

- Local implementation SHA: `3fc2412c258b996d4f8af6bd44f2799438f49504`.
- Rollback baseline: `b5cfd6575ba7274692714c9fc814916a00c13e36`.
- Delivery: local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Isolated staging-parity, predeploy-e2e, migration smoke and fake-provider
  contract: pass.

## Product projection proof

- Baseline and post-deploy DayView each contained 14 cards, all WATCH/PARTIAL,
  with ANALYSIS_PICK, RECOMMEND and lock eligibility at zero.
- The canonical projection was serialized with `jq -S -c` and compared byte for
  byte before hashing.
- Baseline, post-deploy and final projection SHA-256:
  `107a5e35c76f6736ffb0ce73060006c229549ad8572af740796c1e5ac1b4f92e`.
- The earlier `09160e08...` value was rejected as a capture-recording error: a
  fresh b5 response and the saved 3fc response produced identical projection
  bytes and the same reproducible hash.

## Bounded-read canary

- Fixture `1576804` first public request: HTTP 200 in 1.708 seconds.
- Five sequential requests: HTTP 200 in 1.25–1.36 seconds.
- Concurrent fixtures `1576804` and `1494210`: both HTTP 200 in 2.13–2.16
  seconds.
- Quote identity remained explainable: AH reported deterministic LINE_MISMATCH
  conflict and OU reported COMPLETE provenance.
- Every returned quote observation belonged to the requested fixture.
- In-container contract used the real staging DB fixture-scoped reader while a
  global reader failed on invocation: 5,388 scoped rows, global calls 0, route
  PASS.

## Runtime and mutation gates

- API restart 0, OOM false, exit 0 throughout.
- API RSS after the final probe: 276.6 MiB, below the 347.9 MiB limit derived
  from the 289.9 MiB baseline.
- Provider request rows: 673 before and after.
- `future_market_observation`: 3,757,226 before and after.
- Celery queue: 0 before and after.
- Recommendation, Gate 5, forward and shadow lock tables: all 0.
- Alembic revision remained `0023_create_checkpoint_refresh_schedule`.
- Scheduler was stopped during canary, then restored healthy with restart 0 and
  OOM false. The staging watchdog timer was restored active.

R0.1a is accepted locally. The next authorized phase is R0.1b.
