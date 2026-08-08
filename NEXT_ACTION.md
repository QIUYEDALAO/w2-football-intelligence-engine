# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_R0_LEGACY_TASK_RECONCILIATION_ONLY
MASTER_TASK_LEDGER = W2_MASTER_TASK_LEDGER_AND_RECONCILIATION.md
DASHBOARD_MASTER_PLAN = DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
CURRENT_GATE = R0_TASK_RECONCILIATION_AUTHORIZED
P0 = NOT_STARTED
AFTER_R0 = STOP_FOR_OWNER_TASK_LEDGER_REVIEW
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. W2_MASTER_TASK_LEDGER_AND_RECONCILIATION.md
4. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
5. POST_R3_READINESS_ATTRIBUTION_REPORT.md
6. POST_R3_READINESS_ATTRIBUTION_MATRIX.json
7. ROUND_3_FINAL_RECEIPT.md
8. REPOSITORY_HYGIENE_POLICY.md
9. older retained task/backlog/package authorities discovered during R0
```

## Owner decision — reconcile all prior W2 tasks before Dashboard P0

The Dashboard / Intelligence Workspace workstream remains approved, but P0 must not begin until the historical task ledger has been reconciled against current repository reality.

R0 must audit every task in `W2_MASTER_TASK_LEDGER_AND_RECONCILIATION.md`, including the legacy Step 4 / historical “Post4” Dashboard work, and recover any older P0–P8/package/Gate/dependency tasks from repository history or retained authorities that are not yet represented.

No legacy task may disappear merely because a newer Dashboard plan exists. Obsolete semantics may be marked superseded, but surviving capabilities must be mapped forward explicitly.

R0 completion classifications must be evidence-backed:

```text
DONE_PROVEN
PARTIAL_PROVEN
NOT_IMPLEMENTED
SUPERSEDED_BY_CURRENT_CONTRACT
CONFLICTS_WITH_CURRENT_CONTRACT
RETAIN_AS_BACKGROUND_RUNTIME
RETAIN_FOR_EVIDENCE
UNKNOWN_INSUFFICIENT_EVIDENCE
```

R0 must use current code, DB models/migrations, tests, runtime/read evidence and call evidence where applicable. Do not accept PR descriptions, status files or comments as proof of completion.

## Post-R3 Track A remains active background work

The prior Post-R3 readiness attribution remains closed with `PATH_A_NATURAL_EVIDENCE_ACCUMULATION`. Existing natural evidence accumulation may continue only under the already-authorized runtime policy. R0 and Dashboard work must not alter it.

```text
POST_R3_READINESS_ATTRIBUTION = PASS_PATH_A_NATURAL_EVIDENCE_ACCUMULATION
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4 = NOT_STARTED
```

## R0 scope

Allowed writes:

- `W2_MASTER_TASK_LEDGER_AND_RECONCILIATION.md`
- `CURRENT_STATE.yaml`
- `NEXT_ACTION.md`
- additional `context/current` reconciliation evidence if needed

Forbidden during R0:

- product/business code changes
- UI implementation
- migrations or database business writes
- Provider calls or probes
- Scheduler/cadence changes
- whitelist changes
- model retraining, new factors, or threshold changes
- Phase 0.5 rerun
- Round 4
- Candidate / Formal / Lock / Production changes
- legacy code deletion

Required completion state:

```text
R0 = COMPLETE
LEGACY_TASKS = FULLY_RECONCILED_OR_EXPLICITLY_UNRESOLVED_WITH_EVIDENCE
P0 = NOT_STARTED
NEXT = OWNER_TASK_LEDGER_REVIEW
```

Do not start Dashboard P0 automatically.