# W2 AI Project Context

> Any AI or human taking over W2 must read this file, `NEXT_ACTION.md`, the operational
> `PROJECT_STATE.yaml`, and the quant authorities listed below. Code, DB constraints,
> migrations, Git history, Actions logs and reproducible evidence remain the final proof.

## Current product direction

W2 now has two explicit tracks.

### A. Existing operational W2 track

- Existing V4, Dashboard and controlled scheduler remain deployed and preserved.
- The current stage does not expand the single-match recommendation product.
- Candidate, Formal, Lock and Production remain off.
- Historical Wave, Canary, independent-oracle, real-fixture replay and deployment receipts
  remain valid.

### B. Sporttery quant-research track

- same GitHub repository;
- independent `src/w2/quant_research/` bounded context;
- sidecar/port integration rather than in-place V4 modification;
- Freeze A0 offline engineering approved;
- Freeze A1 live collection deferred to owner/API/licensing;
- Track 1 clock not started;
- strategy, Shadow, risk, portfolio, 2×1 and real money not authorised.

Quant authorities:

- [`QUANT_PROJECT_STATE.yaml`](QUANT_PROJECT_STATE.yaml)
- [`AI_QUANT_PROJECT_CONTEXT.md`](AI_QUANT_PROJECT_CONTEXT.md)
- [`QUANT_AGENTS.md`](QUANT_AGENTS.md)
- [`W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`](docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md)
- [`W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`](docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md)
- [`W2_QUANT_FREEZE_A0_BINDING_20260805.md`](docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md)

```text
TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
CURRENT_WORKSTREAM = W2_QUANT_CONTEXT_FREEZE_A0
CURRENT_PHASE = QUANT_CONTEXT_CLOSURE
CURRENT_MAIN_SHA = 75159bfd71bb7492eece86da29cdb32e6f25d9c6
DEPLOYED_SOURCE_SHA = f1718ec4d74e3038fd6240429df6efca42d0a520
FREEZE_A0 = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1 = DEFERRED_OWNER_API_AND_LICENSE
TRACK1_FORWARD_CLOCK = NOT_STARTED
LIVE_CAPTURE_ENABLED = false
```

## Freeze A0 engineering boundary

Allowed after this context PR merges:

- `src/w2/quant_research/` domain objects and Provider ports;
- offline schema, append-only ledgers and views;
- local JSON and historical Excel adapters;
- AS-OF and post-event separation;
- deterministic PostgreSQL replay;
- Track 1 data-quality engine and read-only queries.

Forbidden:

- external API calls or collector activation;
- live mapping bootstrap;
- changes to V4, prematch, strategy, future-refresh, operational Scheduler or Dashboard;
- L2 strategy, L3 Shadow orders, L4 bankroll/risk, Portfolio, 2×1 or real money;
- production DB mutation or VPS deployment.

Binding corrections:

```text
CURRENT_SCHEDULER = STANDALONE_SCHEDULER_PROCESS_DEPLOYED_AND_CONTROLLED
CELERY_BEAT = NOT_USED_BY_DESIGN
CANONICAL_SERIALIZER = src/w2/domain/canonical_serialization.py
CANONICAL_SERIALIZER_VERSION = w2.canonical-json.v2
API_FOOTBALL_LEGACY_FETCH = RETIRED_FAIL_CLOSED
API_FOOTBALL_REQUEST_LIVE = CURRENT_WIRED_NETWORK_PATH
Q14_CALLS_PER_DAY = NOT_EVALUATED
```

## Operational authorities and receipts

- Operational machine state: [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)
- Operational task history: [`W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md)
- Independent audit: `docs/operations/W2_INDEPENDENT_FINAL_AUDIT_20260731.md`
- Production recovery receipt: `docs/operations/W2_PRODUCTION_RECOVERY_RECEIPT_20260803.md`
- Recommendation authority and replay receipt:
  `docs/operations/W2_RECOMMENDATION_AUTHORITY_REAL_FIXTURE_REPLAY_RECEIPT_20260804.md`
- Sanitised real-fixture replay manifest:
  `docs/operations/W2_REAL_FIXTURE_REPLAY_SANITIZED_MANIFEST_20260804.json`

## Recommendation authority closure

```text
PUBLIC_RECOMMENDATION_AUTHORITY = SINGLE
REAL_FIXTURE_OFFLINE_REPLAY = PASS
LINEUP_NUMERIC_VALUE_MODEL = NOT_IMPLEMENTED
LINEUP_NUMERIC_ADJUSTMENT = OFF
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

The current public pick can only come from hash-valid V4. Historical V3 is history/settlement
only. The lineup validator is unique, but lineup numeric probability adjustment is not
implemented.

## Canonical serialization and oracle

```text
PRODUCTION_SERIALIZER_IMPLEMENTER = RECORDED_IN_GIT_IDENTITY
ORACLE_IMPORTS_PRODUCTION_SERIALIZER = false
INDEPENDENT_PAIR_HASH_MISMATCH = FAILED
INDEPENDENT_BOOTSTRAP_SEED_MISMATCH = FAILED
SER_05_INDEPENDENT_ORACLE = PASS
```

New quant identities must use the current v2 authority. Historical v1 serializer profiles are
compatibility contracts, not permission to add another serializer.

## Historical operational compatibility record

This block is retained for old operational contracts and receipts. It is no longer the current
quant-program action.

```text
TOP_LEVEL_TASK = EVAL-02B
ACTIVE_NEXT_ACTION = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
ACTIVE_CONTEXT_PR = NONE
CURRENT_WORKSTREAM = POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS
CURRENT_PHASE = PRODUCTION_RECOVERY_CONTEXT_CLOSURE_COMPLETE
AUDIT_BASELINE_SHA = dbc8e1e8aa74a7613fd7121bf6026890c3ee06c6
CURRENT_MAIN_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
DEPLOYED_SHA = 8c6086e37ba62c138bdf059997ca760accef7067
DASHBOARD_REAL_DATA_RECOVERY = PASS
PUBLIC_DASHBOARD_CARDS = 51
PRODUCTION_FUTURE_FIXTURES = 51
PROVIDER_REQUEST_DELTA = 58
ENDPOINT_CAPTURE_DELTA = 58
PROVIDER_ERRORS = 0
COLLECTION_READY_COMPETITIONS = brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien
PROVIDER = ON_CONTROLLED
REAL_PROVIDER = ON_CONTROLLED
PERSISTENT_SCHEDULER = ON_CONTROLLED
SCHEDULER_CONCURRENCY = 1
PROVIDER_ATTEMPTS = 1
DAILY_HARD_CAP = 120
TICK_HARD_CAP = 30
DYNAMIC_EVALUATION_V2 = 0
EXPLICIT_NOT_READY_CARDS = 51
DYNAMIC_EVALUATION_PRODUCTION_RECOVERY = PENDING
EVAL-03 = NOT STARTED
COLD_PULL_SLO = NOT_PROVEN
NEXT_CODE_ACTION = NONE_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
```

Historical registered competitions whose future-refresh and matchday policy coverage was not
simultaneously complete:

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

## Quant context closure stop line

```text
RUNTIME_CODE_CHANGED = false
DATABASE_MIGRATION_CREATED = false
PROVIDER_CALLS = 0
IMAGES_BUILT = 0
DEPLOYMENT_EXECUTED = false
AUTO_MERGE_EXECUTED = false
```
