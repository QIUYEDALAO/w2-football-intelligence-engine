# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_P3_THEN_P4_THEN_P5_CONTINUOUS
CURRENT_GATE = P3_ACTIVE_CONTINUOUS_TO_OWNER_REVIEW_C
OWNER_REVIEW_B = APPROVED
OWNER_AUTHORITY = OWNER_REVIEW_B_APPROVAL_AND_P3_P5_AUTHORIZATION.md
STARTING_MAIN = f14136f07d69ece09e61fec6b1dd546e67c0267c
P3 = AUTHORIZED
P4 = AUTHORIZED_AFTER_P3_LOCAL_ACCEPTANCE_PASS
P5 = AUTHORIZED_AFTER_P4_LOCAL_ACCEPTANCE_PASS
P5_5 = NOT_AUTHORIZED
TERMINAL_GATE = OWNER_REVIEW_C
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. OWNER_REVIEW_B_APPROVAL_AND_P3_P5_AUTHORIZATION.md
5. OWNER_REVIEW_B_REREVIEW_RESULT.md
6. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
7. W2_FINAL_EXECUTION_MASTER_PLAN.md
8. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
9. DASHBOARD_DATA_CONTRACT.md from current main
10. PERFECT_INTELLIGENCE_CAPABILITY_MATRIX.md from current main
11. FRESHNESS_CONTRACT.md from current main
12. REPOSITORY_HYGIENE_POLICY.md
13. CODEX_EXECUTION_RECEIPT.md
```

## Current execution

Owner Review B is approved and PR #498 is merged to main at:

```text
f14136f07d69ece09e61fec6b1dd546e67c0267c
```

Execute the complete authorized segment:

```text
P3
↓ phase-local acceptance; fix in scope until PASS
P4
↓ phase-local acceptance; fix in scope until PASS
P5
↓
STOP OWNER_REVIEW_C
```

There is no Owner gate between P3, P4 and P5.

Do not stop merely to report P3 complete or P4 complete. Update the same implementation branch/PR and continue automatically after the local acceptance criteria in `OWNER_REVIEW_B_APPROVAL_AND_P3_P5_AUTHORIZATION.md` pass.

## Continuity rule

If a test, contract, TypeScript, E2E, responsive, copy, visual, layout, read-model-consumption or Repository Hygiene gate fails and the correction is within the current P0/P1/P2 product contract, fix it, rerun the affected/dependent gates and continue.

Stop `BLOCKED` before Owner Review C only when continuing would require an unapproved product/runtime authority change explicitly listed in the Owner authorization.

## Delivery rule

Preferred:

- fresh worktree/branch from latest compatible main;
- one Draft PR accumulating P3→P5 changes;
- no merge before Owner Review C;
- run PR Fast/Full CI as required during the continuous segment;
- final exact-head Full CI must end with `RELEASE_REQUIRED = PASS`;
- write one final Owner Review C packet instead of three Owner handoffs.

## P3 outcome

Build the one final Web Intelligence Workspace consuming `GET /v1/dashboard/intelligence-workspace` and no parallel Boss/L1/L2 product. Required P3 surfaces, semantics, timeline truth, Scoreline contract, External NOT_CONNECTED and Data/Ops behavior are defined in the Owner authorization and P0 product spec.

On P3 local PASS, continue to P4 without asking Owner.

## P4 outcome

Complete final Probability Validation, Directional Outcome, League Performance, Forward Validation Records and history/replay presentation from the P2 unified read model. Keep ROI/CLV/value/edge/opportunity public reachability at zero.

On P4 local PASS, continue to P5 without asking Owner.

## P5 outcome

Run full truth-scenario, negative-semantic, visual/geometry, responsive, public-authority, no-call-on-read, full test/CI and Repository Hygiene acceptance. Produce KEEP/DELETE/DEPRECATE/RETAIN_FOR_EVIDENCE classification only; do not delete legacy assets.

Then stop at:

```text
P3 = PASS
P4 = PASS
P5 = COMPLETE_READY_FOR_OWNER_REVIEW_C
P5_5 = NOT_STARTED_NOT_AUTHORIZED
NEXT = OWNER_REVIEW_C
ROUND_4 = NOT_STARTED
```

## Permanent stop lines

```text
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
PROVIDER_PLAN_CHANGE = NOT_AUTHORIZED
NEW_PROVIDER_CALL_FOR_DASHBOARD_WORK = NOT_AUTHORIZED
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_CONNECTION = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
P5_5 = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```

Post-R3 Path A natural evidence accumulation remains independent background runtime and must not be changed by this execution segment.