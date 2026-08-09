# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE
CURRENT_GATE = POST_R3_TRACK_A_CLOSURE_ACTIVE
AUTHORITY = POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_AUTHORIZATION.md
BASE_MAIN = d61768ecf8457a72df80a5cb0220072de76dfdd4
DASHBOARD_WORKSTREAM = REPOSITORY_FULLY_CLOSED
TRACK = PATH_A_NATURAL_EVIDENCE_ACCUMULATION
MODE = READ_ONLY_EVIDENCE_CLOSURE
ROUND_4 = NOT_STARTED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_AUTHORIZATION.md
5. POST_R3_READINESS_ATTRIBUTION_REPORT.md
6. POST_R3_READINESS_ATTRIBUTION_MATRIX.json
7. CODEX_EXECUTION_RECEIPT.md
8. W2_FINAL_EXECUTION_MASTER_PLAN.md
```

## Current action

Run one continuous read-only closure audit of Post-R3 Track A using current persisted natural runtime evidence after the accepted SHADOW_ONLY restore.

Do not reopen the Dashboard workstream and do not start Round 4.

Required terminal classification is exactly one of:

```text
TRACK_A_CLOSED_PASS
WAIT_MORE_NATURAL_EVIDENCE
RECURRING_INTERNAL_DEFECT_PROVEN
```

The task must inspect naturally crossed T12/T6/T3/T60 lifecycle evidence, source/capture/request lineage, checkpoint terminal states, current timeline depth and Model Lab/readiness projection. It must determine whether the earlier `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` condition recurs after the controlled Round-3 restore.

If Track A closes, create the Round4 readiness decision packet but leave Round4 `NOT_STARTED`. If more evidence is needed, identify the exact missing natural evidence and next eligible windows. If a recurring internal defect is proven, trace it and propose bounded remediation without changing production code.

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
```

## Required outputs

Update `CODEX_EXECUTION_RECEIPT.md`, `CURRENT_STATE.yaml`, and `NEXT_ACTION.md` and produce:

- `POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md`
- `POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json`
- `ROUND4_READINESS_DECISION_PACKET.md` only when the evidence is sufficient to make that decision meaningful

No intermediate Owner gate is required. Stop only at the terminal classification.
