# W2 Football Intelligence — Current Product Design

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT_ROLE = MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
ROUND_3 = NOT_STARTED
```

## Public product surfaces

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Public intelligence states and four risk dimensions remain frozen from Round 1.

## League capability result

```text
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_NET_NEW = 4_NOT_ENABLED
AUDIT_UNION = 17
PLAN_RESTRICTED_ROWS = 17
TEMPORAL_EVIDENCE_INSUFFICIENT_ROWS = 17
PROMOTION_AUTHORIZED_ROWS = 0
```

The final truth is in `ROUND_2_FINAL_CAPABILITY_MATRIX.json`. The four
audit-only candidates remain outside runtime whitelist discovery, Scheduler,
future refresh, DayView and public cards. No Round 2 result authorizes runtime
promotion.

## Permanent engineering and product guards

Every future task must satisfy:

```text
TASK_FULLY_CLOSED = FUNCTIONAL_ACCEPTANCE_PASS + REPOSITORY_HYGIENE_PASS
```

`REPOSITORY_HYGIENE_POLICY.md` is mandatory. Reusable validated tooling and
required audit/history evidence must be retained; only provably dead assets are
deleted.

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
BETTING_EDGE_CLAIM = FORBIDDEN
ACTIVE_WHITELIST_CHANGE = false
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```
