# W2 Current Context

This is the mutable current authority for W2 on `context/current`.

## Read order

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. ROUND_2_FINAL_RECEIPT.md
4. ROUND_2_FINAL_CAPABILITY_MATRIX.json
5. ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
6. ROUND_2_ACCEPTANCE_CRITERIA.md
7. REPOSITORY_HYGIENE_POLICY.md
8. ROUND_2_DAY0_RECEIPT.md
9. ROUND_2_OBSERVATION_LOG.md
10. ROUND_2_ACCEPTANCE_EVIDENCE_INDEX.md
11. ROUND_1_FINAL_RECEIPT.md
12. CURRENT_PRODUCT_DESIGN.md
13. CURRENT_TASK_CHECKLIST.md
```

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
ROUND_3 = NOT_STARTED
WAIT_14_DAYS = false
REPOSITORY_HYGIENE = PASS
```

Round 2 closed truthfully with 17/17 Provider rows `PLAN_RESTRICTED`, 17/17
temporal outcomes `TEMPORAL_EVIDENCE_INSUFFICIENT`, and zero promotions. The
active whitelist remains the exact existing 13; four audit-only candidates
remain outside runtime, Scheduler, future refresh and DayView.

```text
FINAL_MATRIX_SHA256 = 9eded59fbfb01913c5ad8a90880bd5fa0acc819565b62e9f5a05ce6055e57ab6
R2_C_PROVIDER_CALLS = 0
R2_C_DB_BUSINESS_WRITES = 0
UNRESOLVED_HYGIENE_ITEMS = 0
HEARTBEAT_w2-mi-round-2 = DELETED
```

## Permanent repository hygiene

`REPOSITORY_HYGIENE_POLICY.md` applies to every future W2 task.

```text
TASK_FULLY_CLOSED = FUNCTIONAL_ACCEPTANCE_PASS + REPOSITORY_HYGIENE_PASS
```

Delete only assets proven unused by repository evidence. Preserve reusable
tooling, migrations/history, final receipts, required audit evidence,
CI/release authorities and protected baselines.

## Permanent product and safety guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```
