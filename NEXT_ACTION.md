# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = EXECUTE_OWNER_REVIEW_C_BOUNDED_REMEDIATION
CURRENT_GATE = OWNER_REVIEW_C_REMEDIATION
OWNER_REVIEW_C = CHANGES_REQUIRED_BOUNDED
REMEDIATION_AUTHORITY = OWNER_REVIEW_C_REMEDIATION.md
IMPLEMENTATION_PR = 499
REVIEWED_HEAD = e9fda39783b7e0ce80cff635e9e2d61dd51bf73f
P5_5 = NOT_STARTED_NOT_AUTHORIZED
TERMINAL_GATE = OWNER_REVIEW_C_REREVIEW
ROUND_4 = NOT_STARTED
```

## Binding read order

```text
1. CODEX_EXECUTION_PROTOCOL.md
2. CURRENT_STATE.yaml
3. NEXT_ACTION.md
4. OWNER_REVIEW_C_REMEDIATION.md
5. OWNER_REVIEW_C_PACKET.md
6. OWNER_REVIEW_B_APPROVAL_AND_P3_P5_AUTHORIZATION.md
7. DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
8. DASHBOARD_DATA_CONTRACT.md from current main
9. W2_FINAL_EXECUTION_MASTER_PLAN.md
10. DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
11. REPOSITORY_HYGIENE_POLICY.md
12. CODEX_EXECUTION_RECEIPT.md
```

## Current action

The P3→P5 architecture and truth/CI foundation on Draft PR #499 are accepted, but Owner Review C found six bounded presentation-contract omissions. Fix all six on the existing PR #499 in one continuous pass:

```text
ORC-01 typed Match Board main line (AH/OU identity)
ORC-02 visible Market Radar two-sided prices
ORC-03 visible Probability Validation checkpoint/cohort identity
ORC-04 League Performance Decisive N
ORC-05 compact header update/system-health context
ORC-06 Scoreline model/readiness context
```

The exact requirements and evidence are in `OWNER_REVIEW_C_REMEDIATION.md`.

Do not stop after an individual item. Ordinary TypeScript, Playwright, layout, responsive, copy, screenshot, contract or CI failures that are fixable inside this bounded authority must be corrected and rerun automatically.

## Required execution flow

```text
FETCH LATEST MAIN + CONTEXT
↓
CONTINUE EXISTING PR #499
↓
FIX ORC-01..ORC-06
↓
FOCUSED CONTRACT / TYPECHECK / PLAYWRIGHT PASS
↓
REGENERATE 1536x1024 + 1920x1080 + 1440x900 + 1366x768 SCREENSHOTS
↓
RESPONSIVE / TRUTH / FORBIDDEN-SEMANTIC REGRESSION PASS
↓
EXACT-HEAD FULL CI
↓
RELEASE_REQUIRED = PASS
↓
REPOSITORY_HYGIENE = PASS
↓
STOP OWNER_REVIEW_C_REREVIEW
```

## Accepted behavior that must remain unchanged

- one public `NEW_INTELLIGENCE_WORKSPACE_ONLY`;
- only `GET /v1/dashboard/intelligence-workspace` for the public Web read;
- no legacy fallback / second Dashboard;
- exact seven states / four risks;
- 0/1/2+ discrete timeline truth;
- 10,000 scoreline + unconditional probability/sample count;
- probability/directional/league/replay source-bound semantics;
- NOT_CONNECTED / NOT_DEFINED / NOT_PROVEN;
- public ROI/CLV/value/edge/opportunity zero reachability;
- no Provider call/no DB business write on read;
- Candidate/Formal/Lock/Production OFF.

## Forbidden

```text
MERGE_PR_499 = NO
P5_5 = NOT_AUTHORIZED
LEGACY_DELETION = NOT_AUTHORIZED
PROVIDER_CALL_OR_PLAN_CHANGE = NOT_AUTHORIZED
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_RETRAINING = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_CONNECTION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
ROUND_4 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

## Terminal state

```text
ORC_01_TO_ORC_06 = PASS
EXISTING_P3_P4_P5_ACCEPTANCE = PASS
FOUR_SCREENSHOTS_REGENERATED = PASS
FULL_EXACT_HEAD_CI = PASS
RELEASE_REQUIRED = PASS
REPOSITORY_HYGIENE = PASS
P5_5 = NOT_STARTED_NOT_AUTHORIZED
NEXT = OWNER_REVIEW_C_REREVIEW
ROUND_4 = NOT_STARTED
```

Do not merge or start P5.5 automatically.