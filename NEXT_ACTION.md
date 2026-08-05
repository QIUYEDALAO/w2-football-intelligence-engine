# NEXT ACTION

当前唯一新代码动作：`W2_QUANT_L1_OFFLINE_FOUNDATION`。

W2 采用双轨架构：现有 V4 / Dashboard / 受控 Scheduler 继续运行；新的竞彩足球量化能力在同一仓库的独立 `quant_research` bounded context 中旁路建设。当前只批准 Freeze A0 离线工程，不批准任何实时 API、策略、Shadow、组合或真钱执行。

## Current authority

- Quant machine state: [`QUANT_PROJECT_STATE.yaml`](QUANT_PROJECT_STATE.yaml)
- Quant task order: [`W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`](docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md)
- Freeze A0 binding: [`W2_QUANT_FREEZE_A0_BINDING_20260805.md`](docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md)
- Research protocol: [`W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`](docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md)
- Existing operational state remains in [`PROJECT_STATE.yaml`](PROJECT_STATE.yaml)

```text
TOP_LEVEL_PROGRAM = W2_SPORTTERY_QUANT_RESEARCH_PLATFORM
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
CURRENT_WORKSTREAM = W2_QUANT_CONTEXT_FREEZE_A0
CURRENT_PHASE = QUANT_CONTEXT_CLOSURE
BASE_MAIN_SHA = 75159bfd71bb7492eece86da29cdb32e6f25d9c6
DEPLOYED_SOURCE_SHA = f1718ec4d74e3038fd6240429df6efca42d0a520

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

## Historical operational action

`POST_RECOVERY_OBSERVATION_AND_DYNAMIC_EVALUATION_READINESS` is no longer the active action. Its receipts and historical facts remain valid under the existing operational authorities and Git history.

## Context-only closure invariants

```text
RUNTIME_CODE_CHANGED = false
DATABASE_MIGRATION_CREATED = false
PROVIDER_CALLS = 0
IMAGES_BUILT = 0
DEPLOYMENT_EXECUTED = false
AUTO_MERGE_EXECUTED = false
```
