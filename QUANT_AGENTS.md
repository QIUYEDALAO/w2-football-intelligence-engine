# W2 Quant Research Agent Instructions

2026-09-25 Candidate C R0 前向时钟已按 Owner 单独授权启动，实际时点 `2026-09-25T09:43:11.620864Z`。下方 Freeze A0 stop line 是独立 quant 平台历史约束；Candidate C R0 的当前状态以 `NEXT_ACTION.md`、`QUANT_PROJECT_STATE.yaml` 和数据库 `forward_clock_registry` 为准。Freeze A1 Provider 采集仍未授权。

Before changing the quant-research program, read in order:

1. `QUANT_PROJECT_STATE.yaml`
2. `NEXT_ACTION.md`
3. `AI_QUANT_PROJECT_CONTEXT.md`
4. `docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`
5. `docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`
6. `docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md`
7. the existing operational `AGENTS.md` safety rules.

## Current task

```text
ACTIVE_NEXT_ACTION = W2_QUANT_L1_OFFLINE_FOUNDATION
FREEZE_A0 = APPROVED_WITH_BINDING_ERRATA_A
FREEZE_A1 = DEFERRED_OWNER_API_AND_LICENSE
```

## Source and workspace

- fetch and verify the latest trusted `origin/main`;
- use a new clean worktree;
- stop on main drift or a dirty source tree;
- do not use quarantined or automation-authored remediation history;
- keep one PR for the bounded task.

## Code boundary

All new quant production code belongs under:

```text
src/w2/quant_research/
scripts/quant/
```

Do not place it in:

```text
src/w2/prematch/
src/w2/strategy/
RecommendationDecisionV4
existing future-refresh business paths
```

## Required reuse

- canonical serialization: `src/w2/domain/canonical_serialization.py`;
- serializer contract: `w2.canonical-json.v2`;
- PostgreSQL/Alembic framework;
- existing fixture/team identity through explicit read-only ports;
- existing request transport only in a later Freeze A1 adapter.

Do not create a second canonical serializer, generic database engine, fixture identity or HTTP
transport.

## Freeze A0 hard stops

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Do not implement strategies, Shadow orders, Kelly, bankroll/risk, portfolio, 2×1 or real-money
execution. Do not change the existing operational Scheduler, Provider allowlist, V4 or
Dashboard. Candidate, Formal, Lock and Production stay off.
