# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_DASHBOARD_INTELLIGENCE_WORKSPACE_P0_ONLY
DASHBOARD_MASTER_PLAN = DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
CURRENT_DASHBOARD_GATE = P0_AUTHORIZED
AFTER_P0 = STOP_FOR_OWNER_REVIEW_A
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
4. POST_R3_READINESS_ATTRIBUTION_REPORT.md
5. POST_R3_READINESS_ATTRIBUTION_MATRIX.json
6. ROUND_3_FINAL_RECEIPT.md
7. REPOSITORY_HYGIENE_POLICY.md
```

## Owner decision — Dashboard / Intelligence Workspace

The active product-development workstream is now the final W2 Dashboard / Intelligence Workspace refactor. The complete task hierarchy, functional scope, semantic boundaries, acceptance criteria, Owner gates, and P0→P6 governance are defined in `DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md`.

Only **P0** is authorized now.

P0 is documentation-only. It must freeze the final product semantics and page specification into `DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md`, reconcile the current-context authority files, perform documentation/repository hygiene checks, and then stop for Owner Review A.

Do not start P1 automatically.

## Post-R3 background state remains in force

The prior Post-R3 readiness attribution remains closed with `PATH_A_NATURAL_EVIDENCE_ACCUMULATION`. Existing natural evidence accumulation may continue only under the already-authorized runtime policy. The Dashboard workstream does not authorize changing that policy, collection cadence, whitelist, Provider plan, scheduler behavior, or product authority.

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

## P0 execution stop line

Forbidden during P0:

- product/business code changes
- UI implementation
- Provider calls or probes
- database business writes
- Scheduler/cadence changes
- model retraining, new factors, or threshold changes
- Phase 0.5 rerun
- Round 4
- Candidate / Formal / Lock / Production changes

Required completion state:

```text
P0 = COMPLETE
P0_OUTPUT = DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
NEXT = OWNER_REVIEW_A
P1 = NOT_STARTED
```
