# W2 R0.6 Staging Canary — 2026-07-18

Result: `PASS_LOCAL_DIRECT_RELEASE`

## Release and gates

- Accepted implementation SHA: `1d582f1a51370abcb69d3732c2366f28cc80102d`.
- Rollback release: `4b880b49acb0b33376c61d2cf8bba608a8682c47`.
- Delivery used a local `git archive`; no GitHub fetch, pull, push, workflow or PR.
- Final local suite: `1132 passed, 4 skipped`; Ruff, Mypy (227 files), Web
  typecheck/build, acceptance, tracked-output, credential and diff gates passed.
- Isolated predeploy-e2e, staging-parity (`3 passed`) and migration smoke passed.
  R0.6 has no schema change, so migration upgrade/downgrade/upgrade is not applicable.

## Frozen public authority proof

- The bounded public inventory contained 102 fixtures. Forty-four fixtures had
  complete scoped inputs and produced byte-identical artifacts in two independent
  materialization passes; 58 fixtures failed closed with explicit missing-input
  reasons. Of the 71 DayView-visible fixtures, 15 were verified and 56 were
  `BLOCKED/NOT_READY`.
- Analysis-card, fixture detail, Dashboard and DayView agreed for all 71 visible
  fixtures on decision tier, data status, lifecycle, pick, recommendation, lock,
  outcome tracking, quote identity and frozen provenance. The 15 verified
  projections matched the pre-switch semantic baseline; the 56 missing artifacts
  exposed no pick, executable odds, recommendation or lock.
- Twenty-four repeated sequential/concurrent reads retained the same artifact
  hashes. Analysis-card p95 was 0.191 seconds against the 3.706-second limit.
- Dashboard `window=all` is now a bounded 101-row public inventory rather than
  the legacy 639-row global inventory. DayView remained 71 rows.
- Startup cache and request tripwires replaced unbounded release/fixture,
  observation, raw/history, legacy builder, provider and model paths with
  fail-on-call functions. Startup warmed only three bounded public cache keys;
  public Dashboard returned 101 rows with zero forbidden calls.

## Hard-gate failures fixed before acceptance

- A materializer retry exposed wall-clock `next_eval_at`; explicit evaluation time
  now reaches the final Decision Contract and repeated bytes are deterministic.
- The public Dashboard release-count path still called global `fixture_payloads()`;
  it now uses a fixed-limit public count reader.
- Unbounded startup warm data shared a public cache key, and then retained a
  second large cache after key isolation. Public/unbounded cache identities are
  separate and startup now warms only the bounded public scope.
- Each failed canary was immediately restored to R0.5, including release, images,
  symlink, scheduler/watchdog state and deletion of exactly 44 frozen rows.

## Product, database and runtime invariants

- Provider requests stayed 673, future observations 3,757,226, raw payloads
  2,223 and forward result events 20. Recommendation, Gate 5, forward and shadow
  locks stayed zero; Redis queue stayed zero. The only expected database change
  was 44 frozen checkpoints, taking total checkpoints from 76 to 120.
- DayView reported provider calls zero and DB writes zero. All visible cards had
  pick zero and lock zero.
- Final RSS was API 251.5 MiB, worker 310.8 MiB, scheduler 157.3 MiB and Web
  5.488 MiB. API and worker were within 1.20 of the deployment baseline. A
  side-by-side R0.5 Web container with identical network, mount, memory limit and
  health probes measured candidate/base anonymous RSS ratio 1.001 and Docker
  working-set ratio 1.198553, below the 1.20 hard limit.
- All four services ended healthy with restart zero and OOM false. Scheduler and
  watchdog returned to their exact active state; root readiness remained 200.

## Local image identities

- API: `sha256:cbe99f95b372637aa6669ca86e49e4616bc874756e3f95beaa44bed73607bf97`
- Worker: `sha256:e1f0e014c2af7ff492b21990cf7a002dacb569b897daf481aca5ffc6a1e93694`
- Scheduler: `sha256:2d192ccdd4b013e1ab7c8b3ddfc7c75ebfe84493a1f69745ec04ca8b2d77f006`
- Web: `sha256:3e95a92047bcf0aed4e96f53a2a5f05d03d633fe2e6fd44ad954c6c486027abb`
- Migration: `sha256:6c07f81cd291b16b8de36b695803def916c8391bfaf3dd41fcd287d4a70bc646`

R0.6 is accepted locally. `next_phase=R1`.
