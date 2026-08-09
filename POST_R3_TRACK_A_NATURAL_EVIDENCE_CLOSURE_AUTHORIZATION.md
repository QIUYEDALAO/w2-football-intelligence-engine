# Post-R3 Track A Natural Evidence Closure Authorization

```text
AUTHORITY = W2_POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_V1
OWNER_DATE = 2026-08-09
BASE_MAIN = d61768ecf8457a72df80a5cb0220072de76dfdd4
TRACK = PATH_A_NATURAL_EVIDENCE_ACCUMULATION
MODE = READ_ONLY_EVIDENCE_CLOSURE
ROUND_4 = NOT_STARTED
DASHBOARD_WORKSTREAM = REPOSITORY_FULLY_CLOSED
```

## Purpose

Close the only remaining pre-Round-4 evidence question: after the accepted SHADOW_ONLY restore, did real fixtures naturally traverse the existing T12/T6/T3/T60 lifecycle with source-bound terminal evidence, and did the existing collection/readiness path behave as designed without a recurring internal defect?

This task is not a new feature project and must not reopen the Dashboard workstream.

## Execution authority

Codex may perform one continuous read-only audit from the latest `origin/main` and current runtime evidence. It may read repository code, database/checkpoint state, raw-payload and endpoint-capture lineage, request/call ledgers, scheduler/task evidence already persisted, and existing tests/logs/artifacts.

It may NOT make Provider calls, write business data, alter Scheduler/cadence, quota policy, whitelist, models/factors/thresholds, Phase 0.5, Candidate/Formal/Lock/Production, external integrations, or start Round 4.

Production-code changes are not authorized in this task.

## Required audit

1. Record exact main/context SHA and one explicit audit `as_of` timestamp.
2. Identify real active-whitelist fixtures that naturally crossed T12, T6, T3 and T60 after the accepted SHADOW_ONLY restore.
3. For each relevant checkpoint, prove from persisted evidence where available:
   - checkpoint planned/due/window identity;
   - task/scheduler execution or explicit terminal non-execution reason;
   - request-ledger identity and quota state;
   - raw payload / endpoint capture identity;
   - fixture identity and market normalization lineage;
   - captured_at / source_event_at timing;
   - current snapshot freshness and timeline depth;
   - model/readiness terminal status and reason codes.
4. Distinguish expected lifecycle states from real recurring failures. In particular, determine whether `DUE_WINDOW_BUT_NO_FRESH_CAPTURE` recurred after the controlled Round-3 OFF/restore interval.
5. Reproject the existing Round-3 intelligence/readiness view using only already persisted natural evidence. No Provider call or synthetic evidence is allowed.
6. Reconcile current 0/1/2+ timeline depth and Model Lab/readiness status against the frozen Post-R3 baseline. Do not reinterpret the frozen baseline.
7. Preserve exact 13 runtime whitelist and audit-only isolation.

## Terminal classification

Exactly one result must be selected:

```text
A = TRACK_A_CLOSED_PASS
B = WAIT_MORE_NATURAL_EVIDENCE
C = RECURRING_INTERNAL_DEFECT_PROVEN
```

### A — TRACK_A_CLOSED_PASS

Use only if enough real fixtures have naturally crossed the authorized lifecycle and the evidence proves the collection path behaves as designed, with no recurring internal defect that invalidates the closure.

Produce:
- `POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_REPORT.md`
- `POST_R3_TRACK_A_NATURAL_EVIDENCE_CLOSURE_MATRIX.json`
- `ROUND4_READINESS_DECISION_PACKET.md`

Round 4 must still remain `NOT_STARTED`; the decision packet is evidence only.

### B — WAIT_MORE_NATURAL_EVIDENCE

Use if the path appears healthy but the terminal sample is not yet sufficient. Produce the same closure report/matrix with the exact missing evidence, next naturally eligible fixture/checkpoint windows, and why waiting is evidence-correct. Do not change runtime policy or create artificial collection.

### C — RECURRING_INTERNAL_DEFECT_PROVEN

Use only if repeated post-restore evidence proves a real internal scheduler/cache/ledger/capture/normalization/readiness defect. Trace source-to-terminal cause and provide a bounded remediation proposal, but do not modify production code in this task.

## Acceptance gates

```text
PROVIDER_CALLS_FOR_AUDIT = 0
DB_BUSINESS_WRITES = 0
PRODUCTION_CODE_CHANGES = 0
SCHEDULER_OR_CADENCE_CHANGES = 0
WHITELIST_CHANGES = 0
MODEL_OR_THRESHOLD_CHANGES = 0
PHASE_0_5_REEXECUTION = 0
ROUND_4 = NOT_STARTED
SOURCE_BOUND_EVIDENCE = REQUIRED
EXACT_AS_OF_AND_IDENTITY = REQUIRED
REPOSITORY_HYGIENE = PASS
```

Codex must update `CODEX_EXECUTION_RECEIPT.md`, `CURRENT_STATE.yaml` and `NEXT_ACTION.md` with the selected terminal classification and stop. Do not begin any remediation or Round 4 work automatically.

## Continuity rule

This task should run continuously through evidence collection, reconciliation and report generation. Do not stop for intermediate Owner approval. Only a terminal result that would require new runtime/product authority becomes a new decision point.
