# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = WAIT_FOR_SOURCE_BOUND_NATURAL_EVIDENCE
CURRENT_GATE = POST_R3_TRACK_A_WAIT_MORE_NATURAL_EVIDENCE
TERMINAL_CLASSIFICATION = WAIT_MORE_NATURAL_EVIDENCE
AUTHORITY = POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_AUTHORIZATION.md
EXACT_MAIN = d61768ecf8457a72df80a5cb0220072de76dfdd4
AUDIT_AS_OF = 2026-08-09T06:10:16.671712Z
DASHBOARD_WORKSTREAM = REPOSITORY_FULLY_CLOSED
TRACK = PATH_A_NATURAL_EVIDENCE_ACCUMULATION
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
GLOBAL_PROJECT_COMPLETION_REQUIRES_VPS_DEPLOYMENT = YES
CURRENT_DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
APPROVED_MAIN_SHA = d61768ecf8457a72df80a5cb0220072de76dfdd4
VPS_DEPLOYMENT_STATUS = PENDING_NOT_AUTHORIZED_BY_TRACK_A
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_AUTHORIZATION.md
5. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md
6. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json
7. POST_R3_READINESS_ATTRIBUTION_REPORT.md
8. POST_R3_READINESS_ATTRIBUTION_MATRIX.json
9. CODEX_EXECUTION_RECEIPT.md
10. W2_FINAL_EXECUTION_MASTER_PLAN.md
```

## Current terminal state

The authorized closure audit ended at `WAIT_MORE_NATURAL_EVIDENCE`.

Natural evidence now covers all four normal checkpoint classes and all four
represented active competitions, but 30 of 38 ended post-restore windows lack
a complete source-bound terminal trace on the available read surface. A
post-restore `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` recurrence condition is visible,
but the task/scheduler reason, request-ledger identity, quota state and capture
lineage needed to distinguish policy/quota behavior from an internal defect are
not exposed. The persisted Round-3 projection also remains frozen at
`2026-08-08T10:19:12Z`, so a truthful current timeline/Model Lab reprojection is
not available.

Do not rerun continuously on elapsed time alone. Resume only when naturally
persisted evidence can provide the missing terminal fields for the next crossed
windows.

## Exact evidence required to resume

- checkpoint terminal status and reason per legal window;
- scheduler task identity or explicit terminal non-execution reason;
- request-ledger identity and quota state;
- raw-payload and endpoint-capture identity for new captures;
- post-baseline persisted Round-3 reprojection with current 0/1/2+ timeline and
  Model Lab/readiness status.

The first natural windows following the audit are listed in
`POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md` and the exact machine rows
are in `POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json`.

## Mandatory overall-project follow-on

Track A terminal classification must **not** be treated as overall W2 project completion while VPS still runs an older source SHA.

After the appropriate Track A terminal handling, the remaining mandatory delivery gate is a separately authorized controlled VPS deployment of the approved main, followed by post-deploy verification of:

```text
VPS_SOURCE_SHA_MATCHES_APPROVED_MAIN
API_HEALTH_PASS
WEB_HEALTH_PASS
GET_/v1/dashboard/intelligence-workspace_PASS
DASHBOARD_REAL_DATA_SMOKE_PASS
SCHEDULER_PROVIDER_RUNTIME_STATUS_VERIFIED
NO_UNAUTHORIZED_RUNTIME_SWITCH_CHANGES
POST_DEPLOY_VISUAL_SMOKE_PASS
```

Do not declare overall project completion before this deployment gate passes.

## Stop lines

```text
PROVIDER_CALLS_FOR_AUDIT = 0
DB_BUSINESS_WRITES = 0
PRODUCTION_CODE_CHANGES = 0
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_CONNECTION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
VPS_DEPLOYMENT = REQUIRED_FOR_OVERALL_COMPLETION_BUT_NOT_AUTHORIZED_BY_THIS_TRACK_A_TASK
```

`ROUND4_READINESS_DECISION_PACKET.md` was not created because the closure
evidence is insufficient. No remediation or Round 4 work is authorized.
