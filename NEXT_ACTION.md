# NEXT ACTION

当前唯一新代码动作：`W2_QUANT_L1_OFFLINE_FOUNDATION`。

W2 采用双轨架构：现有 V4 / Dashboard / 受控 Scheduler 继续运行；新的竞彩足球量化能力在同一仓库的独立 `quant_research` bounded context 中旁路建设。当前只批准 Freeze A0 离线工程，不批准任何实时 API、策略、Shadow、组合或真钱执行。

## Current authority

- Quant machine state: [`QUANT_PROJECT_STATE.yaml`](QUANT_PROJECT_STATE.yaml)
- Quant AI handoff: [`AI_QUANT_PROJECT_CONTEXT.md`](AI_QUANT_PROJECT_CONTEXT.md)
- Quant agent instructions: [`QUANT_AGENTS.md`](QUANT_AGENTS.md)
- Quant task order: [`W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`](docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md)
- Freeze A0 binding: [`W2_QUANT_FREEZE_A0_BINDING_20260805.md`](docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md)
- Research protocol: [`W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`](docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md)
- Existing operational state remains in [PROJECT_STATE.yaml](PROJECT_STATE.yaml)
- Historical operational task authority remains [`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`](docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md)

```text
TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
CURRENT_WORKSTREAM = W2_QUANT_CONTEXT_FREEZE_A0
CURRENT_PHASE = QUANT_CONTEXT_CLOSURE
BASE_MAIN_SHA = SEE_QUANT_PROJECT_STATE
DEPLOYED_SOURCE_SHA = SEE_QUANT_PROJECT_STATE
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1

FREEZE_A0_OFFLINE_ENGINEERING = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1_LIVE_COLLECTION = DEFERRED_OWNER_API_AND_LICENSE
TRACK1_FORWARD_CLOCK = NOT_STARTED
LIVE_CAPTURE_ENABLED = false

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

## Allowed next scope

`W2_QUANT_L1_OFFLINE_FOUNDATION` may implement only:

- `src/w2/quant_research/` domain and Provider ports;
- offline schema/tables/views and append-only ledgers;
- local JSON and historical Excel adapters;
- AS-OF / post-event isolation;
- deterministic offline replay;
- Track 1 data-quality engine and read-only research queries.

## Stop lines

The next task must not:

- call FiroApi, API-Football or any external Provider;
- activate a collector or capture schedule;
- modify the existing V4 recommendation chain, operational Scheduler or Dashboard;
- implement L2 strategy, L3 Shadow orders, L4 bankroll/risk, Portfolio or 2×1;
- modify the production database or deploy to VPS;
- open Candidate, Formal, Lock or Production.

## Historical receipt / 历史回执

The following block is retained solely so existing historical context contracts continue to
recognise the completed operational workstream. It is not the current quant-program action.

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
T00_RERUN = FORBIDDEN_UNLESS_NEW_APPROVED_EVIDENCE
NEXT_CODE_ACTION = NONE_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
AUTO_MERGE = FORBIDDEN
DELIVERY_MODEL = RELEASE_CANDIDATE_PROMOTION_V1
```

Registered competitions whose historical coverage remains recorded:

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

## Context-only closure invariants

```text
RUNTIME_CODE_CHANGED = false
DATABASE_MIGRATION_CREATED = false
PROVIDER_CALLS = 0
IMAGES_BUILT = 0
DEPLOYMENT_EXECUTED = false
AUTO_MERGE_EXECUTED = false
```
