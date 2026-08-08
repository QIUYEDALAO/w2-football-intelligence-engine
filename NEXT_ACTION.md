# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_INTELLIGENCE_WORKSPACE_P1_THEN_P2
CURRENT_GATE = P1_P2_EXECUTION_AUTHORIZED
OWNER_REVIEW_A = APPROVED
P0 = PASS_APPROVED
P1 = AUTHORIZED
P2 = AUTHORIZED_AFTER_P1_SELF_CHECK_PASS
P3 = NOT_AUTHORIZED
AFTER_P2 = STOP_FOR_OWNER_REVIEW_B
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. OWNER_REVIEW_A_APPROVAL.md
4. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
5. W2_FINAL_EXECUTION_MASTER_PLAN.md
6. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
7. POST_R3_READINESS_ATTRIBUTION_REPORT.md
8. POST_R3_READINESS_ATTRIBUTION_MATRIX.json
9. ROUND_3_FINAL_RECEIPT.md
10. REPOSITORY_HYGIENE_POLICY.md
```

## Execution segment

Owner Review A is approved. Execute exactly:

```text
P1
↓
P1 SELF-CHECK / CONTRACT CONSISTENCY PASS
↓
P2
↓
STOP
OWNER REVIEW B
```

P1 may continue directly into P2 only if its source/freshness/readiness contracts are internally consistent and no unresolved product-authority conflict exists.

## P1 — Capability / Data / Freshness Contract

Produce/finalize:

- Perfect Intelligence Capability Matrix
- Current W2 Gap Matrix
- Dashboard Data Contract
- Freshness Contract

Every final Dashboard field must bind:

```text
FIELD
SOURCE
AVAILABILITY
FRESHNESS_DOMAIN
READINESS_SEMANTICS
NO_CALL_ON_READ
```

Reuse the existing Decision Contract, Data Readiness, DayView/runtime sources, diagnostics, replay/date navigation, scoreline and validation foundations. Do not create duplicate engines/contracts.

P1 is evidence/contract work. It must make zero Provider calls and may not change Scheduler/cadence, whitelist, model, thresholds, external-source connectivity, or runtime authority.

## P2 — Unified Dashboard Read Model / API Contract

After P1 PASS, implement the one final unified Dashboard Read Model / API Contract required by the approved P0 specification.

Required P2 result:

```text
ONE_FINAL_UNIFIED_DASHBOARD_READ_MODEL
```

It must expose all approved final-product fields needed by Match Board, Selected Match Inspector, Attention, Market Radar, Model Lab, Scoreline Top 3, External Intelligence, Data/Ops, Probability Validation, Directional Outcome, League Performance, Forward Validation Records and history/replay.

Required evidence at Owner Review B:

- explicit schema
- API/read-model payload contract
- deterministic sample payload
- contract tests
- zero/one/2+ snapshot representation
- readiness/reason-code representation
- `NOT_CONNECTED`, `NOT_DEFINED`, `NOT_PROVEN` representation
- no-call-on-read proof
- exact main/base/head SHA
- changed-file list
- Repository Hygiene evidence

P2 implementation must use the normal PR/CI workflow. Stop before P3 and before any unapproved product rollout.

## Historical task decisions remain frozen

```text
R0 = CANCELLED_NOT_A_DEVELOPMENT_STAGE
HISTORICAL_STEP_4_POST4 = SUPERSEDED_AS_STANDALONE_WORKSTREAM
REBUILD_OLD_L1_L2_BOSS_DASHBOARD = NO
REUSE_EXISTING_CAPABILITIES = YES
```

Do not rebuild old Step4/Post4, old Boss L1/L2, Decision Contract V2, Data Readiness Gate, Scoreline engine, Replay system, or probability-scoring engine as separate projects.

## Parallel Post-R3 Track A remains unchanged

```text
PATH_A = NATURAL_EVIDENCE_ACCUMULATION_BACKGROUND_RUNTIME_ONLY
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
```

P1/P2 must not alter its Scheduler, cadence, Provider plan, quota policy, whitelist, or completion condition.

## Permanent stop lines

```text
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
PROVIDER_CUTOVER = NOT_AUTHORIZED
COLLECTION_CADENCE_EXPANSION_FOR_UI = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_V1 = NOT_AUTHORIZED
P3 = NOT_AUTHORIZED
```

Required terminal state:

```text
P1 = PASS
P2 = COMPLETE_READY_FOR_REVIEW
NEXT = OWNER_REVIEW_B
P3 = NOT_STARTED
ROUND_4 = NOT_STARTED
```

Do not start P3 automatically.