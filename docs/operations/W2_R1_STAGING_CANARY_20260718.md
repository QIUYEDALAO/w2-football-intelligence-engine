# W2 R1 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release and gates

- Accepted implementation SHA: `103813d7e8ea422756472cb9b4369e3c80876d09`.
- Pre-canary release source/config: R0.6 `1d582f1a51370abcb69d3732c2366f28cc80102d`.
- Delivery used local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Final local suite: `1150 passed, 4 skipped`; Ruff, Mypy (229 files), Web
  typecheck/build, five Chromium E2E cases, acceptance, tracked-output, credential
  and diff gates passed. NPM audit reported zero vulnerabilities.
- Exact-candidate isolated predeploy-e2e passed. Isolated staging-parity passed
  `3 passed`; its minimal container emitted only the expected missing asyncio
  plugin configuration warning. R1 has no schema change, so isolated
  upgrade/downgrade/upgrade is `NOT_APPLICABLE`; formal `upgrade head` and
  current/head equality passed.

## Reliability and release evidence

- `/metrics` and request middleware used one process registry. Route/status
  request counters, the fixed-bucket `w2_api_latency_ms` histogram, readiness
  gauges, checkpoint lag, tripwire, provider/model and materializer metrics were
  visible together. No latency sample list is retained.
- `/v1/version` reported exact local SHA/release ID, API image ID, Alembic
  current/head match, readiness manifest identity and three matching artifact
  hashes. OCI and registry digests were explicitly `UNAVAILABLE`; no tag was
  represented as a digest. Web `meta.json` reported the same SHA/release ID.
- Root `/ready` and deprecated `/v1/ready` returned identical 200 bodies; the
  alias retained `Deprecation: true` and its canonical `Link`. `/health` returned
  200 as liveness.
- Runtime evidence passed both supported states: scheduler `created` during
  canary with RSS `UNAVAILABLE_NOT_RUNNING`, and scheduler healthy/running after
  restoration. Queue, restart, OOM, exit137, service state and checkpoint-lag
  checks all passed.

## Product and state invariants

- The DayView semantic projection remained byte-identical before/after with
  SHA-256 `18647c8de4838fb384e656540ced5070d32ba96b4cc00934b34a1b0a66d57ba2`.
- Provider requests stayed 677, future observations 3,761,043, raw payloads
  2,226, read-model checkpoints 120 and forward result events 20.
  Recommendation, Gate 5, forward and shadow locks stayed zero; Redis queue
  stayed zero.
- Final anonymous RSS was API 195,170,304 bytes, worker 267,980,800 bytes,
  scheduler 164,388,864 bytes and Web 8,978,432 bytes. A side-by-side Web probe
  using the preserved rollback image measured 4.492 MiB versus 4.324 MiB Docker
  working set and about 8.55 MiB versus 8.54 MiB anonymous RSS (ratio about
  1.001). All services ended healthy with restart zero and OOM false.
- Scheduler and watchdog returned to their exact pre-canary active state;
  canonical readiness remained 200.

## Hard-gate failures fixed before acceptance

- The first deploy build exposed that `docker compose images -q api` can fail
  while enumerating an accepted container whose previous image metadata was
  removed after fixed tags moved. The deploy script now reads the freshly built
  `w2-staging-api:latest` content-addressed ID directly.
- The second canary exposed that runtime evidence accepted a stopped scheduler
  semantically but still tried `docker exec` for RSS. It now reports explicit
  non-running RSS unavailability and never executes inside a stopped container.
- Rebuilding the R0.6 source after that failure did not reproduce the original
  OCI index IDs because BuildKit provenance manifests changed. The original four
  indexes were no longer present in the host content store. This identity loss
  is recorded rather than described as an exact image rollback.
- Before the accepted retry, the recovered R0.6 source/config state was frozen
  again with API `42b59ca6…`, worker `80eb9e49…`, scheduler `1cd97e0b…` and Web
  `88fe358d…`. The deploy script now preserves and validates all four indexes and
  the migration index under revision-scoped rollback tags before moving any
  fixed tag. The accepted retry verified every retained ID before switching.

R1 is `staging_accepted`. `next_phase=R2`; no champion, threshold, league,
RECOMMEND/lock, OFFICIAL or production setting changed.
