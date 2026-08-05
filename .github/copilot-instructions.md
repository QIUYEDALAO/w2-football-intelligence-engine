# W2 GitHub Copilot Instructions

Read `NEXT_ACTION.md` first. For quant-research work, also read:

- `QUANT_PROJECT_STATE.yaml`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_AGENTS.md`
- `docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`
- `docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`
- `docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md`

## Current quant authority

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
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
```

Only `W2_QUANT_L1_OFFLINE_FOUNDATION` is authorised after the context PR merges.

## Quant placement

```text
allowed:   src/w2/quant_research/ and scripts/quant/
forbidden: src/w2/prematch/, src/w2/strategy/, RecommendationDecisionV4,
           existing future-refresh business paths
```

Reuse `src/w2/domain/canonical_serialization.py` with `w2.canonical-json.v2`.
Do not introduce a second serializer, generic HTTP client, fixture identity or database engine.

Freeze A0 requires:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Do not implement live adapters, collector activation, strategy selection, Shadow orders,
Kelly, bankroll/risk, portfolio, 2×1 or real-money workflows. Do not change the operational
Scheduler, Provider allowlist, V4 or Dashboard.

## Core safety rules

- missing or unverifiable authority fails closed;
- possible Provider delivery followed by failure is persisted and stops later calls;
- idempotency verifies the constraint and every stored business field;
- required zero evidence is failure;
- one business fact has one versioned computation authority;
- historical identity/hash is never silently overwritten;
- no skip, xfail or weakened required-event, five-state, package-matrix, migration, lineage or
  fault-injection guard;
- no workflow write-back to business PR branches;
- merge commit only; no squash or auto-merge.

## Historical operational compatibility record

The following remains completed operational history and is not the current quant action:

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
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
```

Historical registered competition-policy gaps:
`argentina_primera`, `bundesliga`, `eredivisie`, `la_liga`, `ligue_1`, `mls`,
`premier_league`, `primeira_liga`, `serie_a`.
