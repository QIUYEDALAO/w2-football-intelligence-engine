# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
NEXT_CODE_ACTION = CONDITIONAL_ONLY_IF_INTERNAL_W2_DEFECT_IS_PROVEN
```

Round 2 is closed. The current owner-authorized task is defined in:

```text
POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
```

## Immediate objective

Determine why all 17 Round-2 audit rows stopped at `PLAN_RESTRICTED` and choose the data-source path that can actually support W2 Market Intelligence / Model Diagnostics before Round 3.

Required sequence:

```text
1. re-fetch latest origin/main and origin/context/current
2. read ROUND_2_FINAL_RECEIPT.md and ROUND_2_FINAL_CAPABILITY_MATRIX.json
3. audit exact Provider plan-restriction classification and season/request logic
4. verify current API-Football plan/season/endpoint semantics from official current evidence
5. if necessary, use no more than 8 total read-only diagnostic Provider calls; no retries or business writes
6. if an internal W2 season/request defect is proven, implement one bounded fix PR and validate it
7. otherwise do not create a fake code fix
8. compare current API-Football, upgrade, alternate full Provider, dedicated odds Provider and hybrid paths using official current sources
9. produce one preferred recommendation + one fallback with cost/coverage/engineering/licensing tradeoffs
10. run repository hygiene and stop before Round 3
```

## Hard boundaries

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_CANDIDATES = 4_NOT_ENABLED
MAX_NEW_DIAGNOSTIC_PROVIDER_CALLS = 8
AUTOMATIC_RETRY = false
PRODUCTION_PROVIDER_CUTOVER = NOT_AUTHORIZED
PROVIDER_PURCHASE_OR_PLAN_CHANGE = NOT_AUTHORIZED
PRODUCTION_SCHEDULER_CHANGE = false
PERSISTENT_COLLECTION_EXPANSION = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Do not request another owner authorization for bounded diagnosis or an internal-fix PR that stays within `POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md`. New authorization is required for spending, subscription/account changes, Provider cutover, production collection changes, league enablement or Round 3.
