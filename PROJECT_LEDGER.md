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

## 2026-07-18 — R0.6 frozen public cutover

- Implementation SHA `1d582f1a51370abcb69d3732c2366f28cc80102d` moves
  analysis-card, fixture detail, Dashboard and DayView onto one bounded frozen
  authority. Missing artifacts fail closed without legacy rebuild.
- Final local validation passed with `1132 passed, 4 skipped`, all static/Web/
  acceptance guards, isolated predeploy-e2e, staging-parity and migration smoke.
- The 102-fixture inventory produced 44 deterministic artifacts and 58 explicit
  unavailable results. All 71 visible fixtures were consistent across four
  endpoints; 15 matched the frozen baseline and 56 were safely NOT_READY.
- Hard gates found and forced rollback for wall-clock artifact data, a global
  Dashboard count read, startup cache pollution and excess dual-cache RSS. Each
  issue was fixed and covered before the accepted canary.
- Provider, observation, raw, queue, ledger and lock counts did not change. Only
  44 expected frozen checkpoint rows were added. Final p95 was 0.191 seconds;
  RSS ratios, restart and OOM gates passed.
- All services, scheduler and watchdog ended healthy/active. R0.6 is PASS and R1
  is authorized by the full local execution plan.

Detailed canary evidence:
[W2 R0.6 Staging Canary](docs/operations/W2_R0_6_STAGING_CANARY_20260718.md).

## 2026-07-18 — R1 local checkpoints before phase canary

- R1.1 `locally_verified`: API metrics and `/metrics` share a thread-safe process
  registry; fixed-bucket histograms retain no samples. Route/status/readiness,
  provider/model, checkpoint, tripwire and materializer metrics are exposed.
- R1.2 `locally_verified`: `/v1/version` exposes local SHA, release/image digest
  availability, Alembic current/head and readiness artifact hashes. Release Gate
  manifests hash their evidence and are written atomically.
- R1.3 `locally_verified`: retries and response cache are bounded; observation
  batches fail without partial writes; runtime evidence fails on queue, restart,
  OOM, exit137, service state, RSS or checkpoint-lag anomalies.
- R1.4 `locally_verified`: Chromium covers READY, STALE, BLOCKED, INCOMPLETE and
  checkpoint-missing Dashboard/DayView/analysis-card contracts. Non-ready Web
  projection clears residual pick, current odds, recommendation and lock fields.
- R1.5 `implemented`: the four delivery states are now explicit. This entry is not
  staging acceptance. R1 phase-wide gates and its single canary remain pending.
- No GitHub synchronization, champion switch, RECOMMEND/lock enable, OFFICIAL or
  production action occurred.

## 2026-07-18 — R1 staging acceptance

- Exact local candidate `103813d7e8ea422756472cb9b4369e3c80876d09` passed
  `1150 passed / 4 skipped`, Ruff, Mypy, Web typecheck/build, five Chromium E2E
  cases, acceptance/guards, exact-candidate isolated predeploy and parity.
- Formal staging proved exact API/Web release identity, matching Alembic and
  readiness artifacts, shared bounded metrics, stopped/running scheduler runtime
  evidence and byte-identical product projection hash `18647c8de4838fb3…`.
- Provider/business/checkpoint/ledger/lock/queue counts had zero canary delta.
  Four services finished healthy with restart/OOM/exit137 zero; scheduler and
  watchdog returned active.
- Two hard failures were rolled back and fixed before acceptance: stale-container
  image enumeration and stopped-scheduler RSS collection. The second rollback
  could restore the R0.6 source/config but not its original BuildKit index IDs;
  that identity loss is recorded in the canary report. Revision-scoped rollback
  tags are now retained and verified before fixed tags move.
- R1 is `staging_accepted`; `next_phase=R2`. GitHub, champion, thresholds,
  league scope, RECOMMEND/lock, OFFICIAL and production remain unchanged.

Detailed evidence:
[W2 R1 Staging Canary](docs/operations/W2_R1_STAGING_CANARY_20260718.md).

## 2026-07-18 — R2 offline corrections and staging acceptance

- R2.1–R2.4 completed as separate deterministic commits: persistent rolling
  form, explicit half-goal `0.5` contract, truthful `signal_strength` semantics,
  and fixed-snapshot paired offline evaluation.
- Final exact candidate `6f300d028939bb227683cc644461a7dc67988a77`
  passed `1158 passed / 4 skipped`, all static/Web/acceptance guards, staging-host
  parity and isolated predeploy.
- Offline evaluation changed all 12 validation rolling-form feature rows but no
  probability row because the selected model does not consume that feature;
  log loss, Brier, RPS and ECE deltas were honestly zero. The result remains
  shadow-only.
- The first canary found legacy frozen payloads bypassing the confidence-to-
  strength projection. Exact R1 rollback completed before repair; a real-shape
  regression was added and every gate rerun.
- The accepted canary verified three real legacy checkpoints under sequential
  and concurrent load. Provider/business/checkpoint/ledger/lock/queue counts
  had zero canary delta, and 39 DayView cards matched R1 after only allowed field,
  derived-hash and request-time normalization.
- All services ended healthy with RSS within 1.20x, restart/OOM/exit137 zero;
  scheduler and watchdog returned active. R2 is `staging_accepted` and R3 is
  authorized for append-only forward shadow evidence only.

Detailed evidence:
[W2 R2 Staging Canary](docs/operations/W2_R2_STAGING_CANARY_20260718.md).

## 2026-07-18 — R3 read-only staging candidate

- R3 ledger performance v2 now separates VALIDATION, OFFICIAL and SHADOW;
  `record_count` remains L2 audit only. Historical rows are certified without
  rewriting, identity conflicts fail closed, and ledger v3 links outcomes to
  original capture identity.
- The rejected Dashboard redesign was reverted. Exact implementation SHA
  `7e4c0aea790f2bce678b4ab6a2d20ba51d583316` retains the original layout and
  corrects only visible data semantics. All qualifying matches are displayed;
  no arbitrary three-match cap remains.
- Local gates passed with `1163 passed / 4 skipped`, all static/Web/acceptance
  guards and six Chromium contracts. Staging health/readiness/version/DayView/
  Dashboard probes passed with provider delta zero, queue zero, exact release
  identity, schema/artifact match and runtime/RSS gates green.
- Current real figures are 23 validation fixtures, 15 settled, 8 pending,
  10 hit, 3 miss, 2 push, 0 void and 12 canonical settled fixtures.
- The candidate is `staging_accepted_awaiting_three_cycles`, not production
  approved. Consecutive Beijing 09:00 cycles are `0/3`; the first eligible
  cycle is 2026-07-19. Champion, RECOMMEND/lock and OFFICIAL remain unchanged.

Detailed evidence:
[W2 R3 read-only staging candidate](docs/operations/W2_R3_READONLY_STAGING_CANDIDATE_20260718.md).

## 2026-07-18 — R4 approval packs prepared in parallel

- Champion review material is prepared but does not support or authorize a
  champion switch; explicit later approval remains required.
- RECOMMEND/lock review material is prepared; the 200 canonical settled-fixture
  target and explicit later approval remain required. RECOMMEND, lock and
  OFFICIAL are unchanged.
- Read-only production has the user's conditional authorization after three
  consecutive real Beijing 09:00 patrol PASS cycles. The current immutable
  implementation is `94bcd62`; state remains `0/3` and not production approved.
- This documentation-only preparation does not rebuild staging and does not
  reset the cycle candidate.

Detailed evidence:
[W2 R4 approval packs](docs/operations/W2_R4_APPROVAL_PACKS_20260718.md).

## 2026-07-18 — repeated quote capture and freshness correction

- Final staging implementation `94bcd62c67ed3fe50bba5ee65be10133556f83d0`
  retains a new append-only observation identity when a later authoritative
  provider response repeats unchanged odds. It does not overwrite historical
  `captured_at`, loosen the 30-minute gate or substitute page generation time.
- Dashboard layout remains unchanged. Page update, odds confirmation and next
  collection are separately labeled, and cache reuse is invalidated by a newer
  fixture-scoped refresh watermark.
- The natural 23:45 T-15 checkpoint proved all 3,870 quotes for fixture 1494704
  were unchanged from 23:00 while all 3,870 new observation IDs remained
  distinct. Both refreshed fixtures were rematerialized before checkpoint
  completion.
- The public card's odds field is no longer stale and its quote identity is
  COMPLETE. Its current NOT_READY reason is the truthful, separate
  `MARKET_UNAVAILABLE` condition; no pick, recommendation or lock was created.
- Local gates passed with `1173 passed / 4 skipped`; all static, Web, browser,
  acceptance and safety guards passed. Public probe provider delta and business
  writes were zero; queue, restart/OOM/exit137 and RSS gates passed.
- R3 remains `staging_accepted_awaiting_three_cycles`, reset to `0/3`; first
  eligible patrol is 2026-07-19 09:00 Beijing. GitHub, champion,
  RECOMMEND/lock, OFFICIAL and write-enabled production remain unchanged.

Detailed evidence:
[W2 repeated-capture freshness canary](docs/operations/W2_REPEAT_CAPTURE_FRESHNESS_STAGING_CANARY_20260718.md).

## Delivery rule

R0.1a may start only after the R0.0 PR is merged with `verify`,
`staging-parity` and `predeploy-e2e` passing. Every later phase follows the same
merge-before-next-phase rule.

## 2026-07-19 — LMM0-LMM8 implementation started

- User authorized the complete lineup identity, valuation, formation and
  independent AH/OU decision workstream from local `main@8e171dc`.
- Work continues on `codex/w2-lmm-lineup-multimarket`; GitHub synchronization
  remains prohibited and no staging deployment has occurred.
- The accepted staging implementation remains `01f8a75`. The three-cycle gate
  will restart at `0/3` only after the exact LMM candidate passes all local and
  isolated gates and its single staging canary.
- Champion, RECOMMEND/lock, OFFICIAL and write-enabled production remain
  unchanged.

## 2026-07-19 — LMM0-LMM8 staging acceptance

- Exact local implementation
  `198c603db424371014e1f738596a9befa8a9486c` passed `1206 passed / 4 skipped`,
  all static/Web/Playwright/acceptance guards, exact-archive predeploy,
  staging parity and isolated migration roundtrip.
- Migration `0024_create_lineup_intelligence` is active. Staging contains
  50,149 Transfermarkt player references, 31,507 valuation observations,
  60 structured lineup snapshots, 1,527 lineup players, 60 deterministic team
  baselines and 660 player identity mappings.
- Formal sequential and concurrent public canaries kept provider, business,
  checkpoint, ledger, lock and queue deltas at zero. Non-ready cards exposed no
  pick or directional scoreline. All four services finished healthy with
  restart/OOM/exit137 zero and scheduler/watchdog restored.
- Earlier candidates with scoreline leakage, missing persisted baselines,
  hidden runtime policy and runtime `uv run` dependency sync were rejected,
  rolled back and covered by regression or release contract tests before the
  successful deployment.
- LMM4 numeric lineup adjustment remains zero because its frozen offline
  evidence gate has not passed; readiness, provenance, explanation and AH/OU
  independent market selection are accepted without inventing an effect.
- The three-cycle gate is reset to `0/3`; first eligible patrol is
  2026-07-20 09:00 Beijing on the same SHA and images. GitHub, champion,
  RECOMMEND/lock, OFFICIAL and write-enabled production remain unchanged.

Detailed evidence:
[W2 LMM staging acceptance](docs/operations/W2_LMM_STAGING_CANARY_20260719.md).
