# W2 Football Intelligence — Current Product Design

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT_ROLE = MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_NEXT_ACTION = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
ROUND_3 = AUTHORIZED_IN_PROGRESS
```

## Public surfaces

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Seven intelligence states and four independent risk dimensions remain frozen from Round 1.

## Round-3 product definition

### Market Radar

Market Radar exposes real market facts from eligible persisted AH/OU observations:

```text
current line / prices
freshness and quote times
bookmaker depth
bookmaker de-vig distribution
overround
snapshot count
line / price / probability movement
lineage
```

Movement is descriptive market behavior, not a betting signal.

If temporal evidence is insufficient, state is `INSUFFICIENT`. Statistical anomaly thresholds must not be invented; `NOT_CALIBRATED` is acceptable.

### Model Lab

Model Lab compares existing model probability to the **same market and same canonical line** using a real multi-bookmaker de-vig distribution.

Public disagreement requires:

```text
model READY
market identity/freshness COMPLETE
bookmaker depth >= 3
same market/line
model effective probability outside the observed bookmaker probability range
```

Output is diagnostic only.

## Legacy semantic isolation

Round-3 public authority must not depend on or expose recommendation/edge semantics such as:

```text
expected_value
cashflow_price_edge
analysis_direction_allowed
ev_eligible
formal_eligible
lock_eligible
MODEL_MARKET_EDGE_READY
MIN_MARKET_ANCHOR_DIVERGENCE as a public alert threshold
```

Legacy V4 compatibility code may remain if still referenced, but is not Round-3 product authority.

## Runtime/data baseline

```text
FREE_BRIDGE_MODE = SHADOW_ONLY
API_FOOTBALL_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
```

## Permanent guards

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
MOVEMENT != OPPORTUNITY
ANOMALY != OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ACTIVE_WHITELIST_CHANGE = false
AUDIT_ONLY_PROMOTION = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```

Every task closes only with `REPOSITORY_HYGIENE_POLICY.md` PASS.
