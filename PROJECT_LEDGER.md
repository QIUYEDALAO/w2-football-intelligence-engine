# W2 Project Ledger

This ledger starts at the recovery baseline. Earlier PRs and reports are historical
specifications and failure cases, not proof of behavior in the current tree.

## 2026-07-18 — R0.0 baseline freeze

- GitHub main: `7c7f16fd2c44468ba4932ef83473bd35f285cbd4`.
- Tree: `31eae0ba07361eb7ad195afccc985784f868c5c7`.
- Staging release: `b5cfd6575ba7274692714c9fc814916a00c13e36`.
- Staging and main have the same Git tree.
- PR #347 and the main push workflow both have successful current-tree CI evidence.
- Local current-tree acceptance: `1071 passed, 4 skipped`; Ruff, Mypy, Web,
  acceptance, tracked-output and secret scan passed.
- Staging database snapshot and isolated restore rehearsal passed; the temporary
  restore database was removed.
- `/health` and `/ready` currently expose the same weak 200 payload. This is
  recorded evidence, not an accepted readiness implementation.
- Staging remains fail-safe at the product boundary: RECOMMEND, lock, OFFICIAL and
  production are closed.

Detailed evidence: [W2 R0.0 Baseline Freeze](docs/operations/W2_R0_0_BASELINE_FREEZE_20260718.md).

- PR #348 passed `verify`, `staging-parity` and `predeploy-e2e`, then merged as
  `37767123313483ecd8dc9607b4bb085d7cb6db36`.

## 2026-07-18 — R0.1a quote identity observation

- Projects quote identity only from the two authoritative selected observation rows.
- Records observation IDs, fixture, provider, bookmaker, market, selection, line,
  odds, captured time, raw payload hash and source revision.
- Reports `COMPLETE`, `INCOMPLETE` or `CONFLICT` with deterministic blockers.
- Historical compatibility cards report unavailable authoritative observations;
  they never synthesize IDs from card fields.
- The projection is audit-only: it does not enter `current_odds`, pricing, pick or tier.
- Local validation: `1075 passed, 4 skipped`; 55 focused tests, Ruff, Mypy,
  TypeScript and Web production build passed.
- PR #349 passed `verify`, `staging-parity` and `predeploy-e2e`, then merged as
  `5849374e61bc7b7fe91b6da41c637b5c65a4b9fb`.
- The staging canary preserved all 14 DayView cards as WATCH, kept the product
  projection hash unchanged, and made zero provider calls.
- A public analysis-card probe then caused an API OOM, exit 137 and two restarts.
  This is the confirmed read-time rebuild boundary already scheduled for later
  bounded/frozen-read phases, not a quote projection assertion failure.
- The hard runtime gate failed, so staging was immediately rolled back to
  `b5cfd6575ba7274692714c9fc814916a00c13e36`. Four services are healthy with zero
  restarts after rollback; queue, provider baseline and locks remain unchanged.
- R0.1b has not started.

### R0.1a-B1 local direct reacceptance

- Local SHA `3fc2412c258b996d4f8af6bd44f2799438f49504` replaced the unbounded public
  analysis-card observation read with a request-local fixture-scoped reader.
- Local validation passed with `1084 passed, 4 skipped`, Ruff, Mypy, TypeScript,
  Web production build, acceptance, tracked-output, credential scan and migration gates.
- Isolated staging-parity/predeploy-e2e, migration and fake-provider contracts
  passed without GitHub.
- First, five sequential and two-fixture concurrent public probes all returned
  200. API restart and OOM stayed zero; final RSS was 276.6 MiB.
- The real staging scoped reader returned 5,388 target rows while the injected
  global reader was never called.
- Provider, observation, queue and lock counts were unchanged. Canonical DayView
  projection bytes were identical before and after deployment.
- R0.1a is PASS. R0.1b is now authorized.

Detailed canary evidence:
[W2 R0.1a Staging Canary](docs/operations/W2_R0_1A_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.1b quote freshness isolation

- Local SHA `13183b3eabd9022cada47a76d01fa619648bd01f` introduced one freshness
  evaluator using authoritative observation `captured_at` only.
- Missing, invalid or conflicting provenance is INCOMPLETE; quotes older than 30
  minutes are STALE. Neither class enters current odds or current pricing.
- Final local validation reported `1094 passed, 4 skipped`; static, Web,
  acceptance, migration and isolated predeploy gates passed.
- Staging DayView cards remained WATCH with no pick/recommendation/lock. All
  visible cards were STALE and exposed no current odds.
- Shared-fixture product projections were byte-identical. Provider, observation,
  queue and lock counts did not change; all services remained restart zero/OOM
  false and scheduler/watchdog state was restored.
- R0.1b is PASS. R0.1c is now authorized.

Detailed canary evidence:
[W2 R0.1b Staging Canary](docs/operations/W2_R0_1B_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.1c non-READY no-pick invariant

- Local SHA `58ca49793f2011148e5bfc7d2f1ac5c9062ffbf8` established one final
  Decision Contract postcondition and made DayView, public analysis-card and
  tracking project it without restoring legacy picks.
- Final local validation reported `1097 passed, 4 skipped`; static, Web,
  acceptance, migration and isolated predeploy gates passed.
- Staging contained 10 WATCH cards and one expected NOT_READY card. Every card
  had zero pick, recommendation, executable odds, lock eligibility and outcome
  tracking. The public analysis-card projected the same semantics.
- Provider, observation, queue and lock counts did not change. API RSS was
  268.1 MiB; all services remained restart zero/OOM false and scheduler/watchdog
  state was restored.
- R0.1c is PASS. R0.2 is now authorized.

Detailed canary evidence:
[W2 R0.1c Staging Canary](docs/operations/W2_R0_1C_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.2 canonical readiness 503

- Local SHA `87e2ba15b5920c369ca90583b0b0d2dd1a73a74a` separated pure liveness
  from canonical fail-closed readiness.
- Root and legacy readiness share one payload/status; the legacy route adds
  deprecation and canonical Link headers. Docker, release and watchdog probes
  now use root `/ready`.
- Local full validation reported `1107 passed, 4 skipped`; static, Web,
  acceptance, migration, staging-parity and predeploy gates passed.
- Dedicated temporary dependencies proved DB, Redis, schema, artifact and mount
  failures return 503 and recover to 200 without touching formal staging.
- Formal staging remained product-identical and mutation-free. All services are
  healthy with restart zero/OOM false; scheduler/watchdog state was restored.
- R0.2 is PASS. `next_phase=R0.3`; this run stops before R0.3.

Detailed canary evidence:
[W2 R0.2 Staging Canary](docs/operations/W2_R0_2_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.3 fixture-scoped bounded public reads

- Implementation SHA `7e383e2f21fcd0b488ffc95cd58c6c6394291855` separates
  public bounded readers from explicitly offline global readers.
- Observation reads are capped at 256 rows per fixture; raw payload reads at 32
  payloads/256 response items; xG history at 20 rows per team.
- Local validation passed with `1112 passed, 4 skipped`, Ruff, Mypy, Web build,
  acceptance, tracked-output, credential and diff gates.
- Isolated predeploy-e2e and staging-parity passed. Formal canary injected
  fail-on-call global observation/raw/xG readers and recorded zero global calls.
- DayView product hash stayed `f2e282491966350c04a317d39d53424a25d6a09eee5421bb8e249f4b96917280`.
  Provider, observation, raw, checkpoint, queue and lock counts did not change.
- API RSS was 219.4 MiB against a 349.2 MiB cap; all services ended healthy with
  restart zero/OOM false, and scheduler/watchdog state was restored.
- R0.3 is PASS. R0.4 is authorized by the full local execution plan.

Detailed canary evidence:
[W2 R0.3 Staging Canary](docs/operations/W2_R0_3_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.4 deterministic sidecar materializer

- Implementation SHA `7a5181f3b0cc0e12ae3dbade225d3725b7b06518` adds a
  versioned three-fixture canary namespace without changing public reads.
- An explicit evaluation reference is part of the input manifest; write time and
  run identity are excluded from canonical bytes and hashes.
- Local validation passed with `1118 passed, 4 skipped`, all static/Web/acceptance
  guards, isolated predeploy-e2e and staging-parity.
- The three staging fixtures repeated with byte-identical payloads and artifact
  hashes. Sequential and concurrent reads returned one stable hash per fixture.
- Missing inputs, old schema, identity conflict and hash mismatch fail closed;
  batch writes are one transaction and leave no partial visible checkpoint.
- Public analysis cards and the DayView product projection stayed unchanged.
  Provider, observation, raw, queue and lock counts did not change; only three
  canary checkpoint rows were added.
- All services ended healthy with restart zero/OOM false; scheduler and watchdog
  were restored. R0.4 is PASS and R0.5 is authorized.

Detailed canary evidence:
[W2 R0.4 Staging Canary](docs/operations/W2_R0_4_STAGING_CANARY_20260718.md).

## 2026-07-18 — R0.5 frozen analysis-card canary

- Implementation SHA `4b880b49acb0b33376c61d2cf8bba608a8682c47` switches only
  the three named canary fixtures to verified frozen checkpoint reads.
- Local validation passed with `1125 passed, 4 skipped`, all static/Web/acceptance
  guards, isolated predeploy-e2e and staging-parity.
- Sequential and concurrent staging reads returned stable bytes and the three R0.4
  artifact hashes. An in-container fail-on-call tripwire recorded three artifact
  reads and zero legacy/global/provider/model calls.
- Decision, tier, pick, quote identity/freshness and DayView product semantics
  stayed unchanged. Frozen `evaluated_at` replaced the live request reference for
  two audits by design; authoritative quote `captured_at` did not change.
- Provider, observation, raw, checkpoint, queue, business and lock counts did not
  change. All services ended healthy with restart zero/OOM false; scheduler and
  watchdog were restored. R0.5 is PASS and R0.6 is authorized.

Detailed canary evidence:
[W2 R0.5 Staging Canary](docs/operations/W2_R0_5_STAGING_CANARY_20260718.md).

## Delivery rule

R0.1a may start only after the R0.0 PR is merged with `verify`,
`staging-parity` and `predeploy-e2e` passing. Every later phase follows the same
merge-before-next-phase rule.
