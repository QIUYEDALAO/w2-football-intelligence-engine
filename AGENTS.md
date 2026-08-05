# W2 Repository Agent Instructions

Before any W2 change, read:

- `NEXT_ACTION.md`
- `AI_PROJECT_CONTEXT.md`
- `PROJECT_STATE.yaml`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_PROJECT_STATE.yaml`
- `QUANT_AGENTS.md`
- `docs/operations/W2_QUANT_PROGRAM_MASTER_CHECKLIST.md`
- `docs/architecture/W2_SPORTTERY_QUANT_RESEARCH_PROTOCOL_V2_3_1.md`
- `docs/operations/W2_QUANT_FREEZE_A0_BINDING_20260805.md`
- the historical architecture checklist and independent audit receipts.

## Current quant program

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

The only newly authorised code objective after this context PR is merged is
`W2_QUANT_L1_OFFLINE_FOUNDATION`.

## Quant code boundary

New quant code must be isolated under:

```text
src/w2/quant_research/
scripts/quant/
```

It must not be placed in:

```text
src/w2/prematch/
src/w2/strategy/
RecommendationDecisionV4
existing future-refresh business paths
```

Required reuse:

- `src/w2/domain/canonical_serialization.py`;
- `w2.canonical-json.v2`;
- existing PostgreSQL/Alembic and canonical fixture/team identities through explicit ports.

Do not create a second canonical serializer, generic HTTP transport, database engine or fixture
identity.

Freeze A0 stop line:

```text
REAL_PROVIDER_CALLS = 0
LIVE_CAPTURE_ENABLED = false
TRACK1_FORWARD_CLOCK = NOT_STARTED
PRODUCTION_DB_MODIFIED = false
DEPLOYMENT_EXECUTED = false
```

Do not implement live adapters, collector activation, strategies, Shadow orders, Kelly,
bankroll/risk, portfolio, 2×1 or real-money workflows. Do not modify the existing Scheduler,
Provider allowlist, V4 or Dashboard.

## Source and branch rules

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' origin/main
```

- start from the latest trusted `origin/main` in a clean worktree;
- stop on source drift or a dirty workspace;
- do not use PR #453, `agent/eval-02b-c9-*`, `e875050f...` or automation-authored remediation;
- one bounded task per PR; merge commit only; no squash or auto-merge.

## Operational safety rules retained

1. Missing, illegal, stale, unknown or unverifiable authority fails closed.
2. After a possible external Provider side effect, failure is persisted, surfaced, stops later
   calls and forbids automatic retry.
3. Idempotency requires the expected constraint and all stored business fields to agree.
4. Required empty, swallowed failure, no lock or not executed is not success.
5. One business fact has one versioned computation authority.
6. Historical identity and hash are not overwritten without migration.
7. Do not delete, skip, xfail or weaken required event, five-state `1e-9`, package matrix,
   delta, lineage, migration, fault-injection or historical guards.
8. Workflows may not push business implementation into PR branches.
9. Same-source tests are not an independent oracle.
10. Completion reports must distinguish implementation from independent review.

## R5 canonical serialization

- production authority: `src/w2/domain/canonical_serialization.py`;
- current contract: `w2.canonical-json.v2`, UTF-8, sorted compact keys, `allow_nan=False`;
- historical v1 profiles remain explicit compatibility contracts;
- SER-05 oracle author differs from production implementer and does not import production
  serializer;
- CI rejects a second unauthorised serializer or hash writer.

## Historical operational compatibility record

The following is retained as completed operational history, not as the current quant action:

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

Registered historical policy gaps remain recorded:

- `argentina_primera`
- `bundesliga`
- `eredivisie`
- `la_liga`
- `ligue_1`
- `mls`
- `premier_league`
- `primeira_liga`
- `serie_a`

The operational V4 chain, Wave 1–4 receipts, real canary, independent oracle and real-fixture
replay remain historical evidence. Candidate, Formal, Lock and Production stay off.
