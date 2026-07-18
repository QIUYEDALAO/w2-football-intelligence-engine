# W2 R0.2 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release under test

- Local implementation SHA: `87e2ba15b5920c369ca90583b0b0d2dd1a73a74a`.
- Accepted predecessor and rollback release:
  `58ca49793f2011148e5bfc7d2f1ac5c9062ffbf8`.
- Delivery used a local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- The core implementation full suite reported `1107 passed, 4 skipped`; Ruff,
  Mypy (226 source files), TypeScript/Web build, acceptance, tracked-output,
  credential and migration gates passed. Final shell-only fixture adjustments
  passed their focused contract and syntax gates.
- Staging-parity reported 5 tests passed. Isolated predeploy migration,
  fake-provider, analysis-card, mount and DB assertions passed.

## Canonical readiness proof

- `/health` returned 200 with only service, version and environment; it remained
  200 while the isolated database was stopped.
- Root `/ready` returned 200 READY with PASS results for DB `select 1`, Redis
  ping, Alembic revision, three artifact hashes and runtime/config mounts.
- `/v1/ready` returned the same status and byte-identical body, with
  `Deprecation: true` and `Link: </ready>; rel="canonical"`.
- The API image healthcheck, deploy/recovery probes and watchdog use root
  `/ready`; `/health` is not a deployment gate.

## Isolated fault injection

- Temporary DB stop: `/health` remained 200 and `/ready` returned 503; recovery
  returned 200.
- Temporary Redis stop: deterministic 503, then recovery to 200.
- Temporary Alembic revision mismatch: deterministic 503, then recovery to 200.
- Temporary readiness-manifest hash mismatch: deterministic 503, then recovery
  to 200.
- Temporary runtime mount unreadability: deterministic 503, then recovery to 200.
- The fault project used dedicated containers, network, volume and loopback port;
  it did not reference or stop formal staging dependencies.

## Product and runtime invariants

- DayView canonical product projection hash remained
  `bf3818bd5185ebb367757df5abf4c2dab5375663ee7aa06c2091205033ef02a9`.
- Provider request rows remained 673 and `future_market_observation` remained
  3,757,226. Recommendation, Gate 5, forward and shadow locks remained zero.
- Redis queue remained zero and Alembic remained
  `0023_create_checkpoint_refresh_schedule`.
- API, worker, web and scheduler were healthy with restart zero/OOM false. API
  RSS was 278.3 MiB.
- Scheduler and watchdog were restored to their exact pre-canary active state.

R0.2 is accepted locally. Per the authorized plan, work stops here with
`next_phase=R0.3`; R0.3 has not started.
