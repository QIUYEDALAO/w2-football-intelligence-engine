# W2 Market Intelligence — AI Handoff

Current authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_B_FOURTEEN_DAY_READ_ONLY_OBSERVATION
ROUND_3 = NOT_STARTED
```

Phase 0.5 remains closed with `NO_EDGE`; H remains permanently closed.

Permanent evidence guards:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## Round 2 authority

Read:

```text
ROUND_2_OWNER_AUTHORIZATION.md
ROUND_2_CODEX_EXECUTION.md
ROUND_2_ACCEPTANCE_CRITERIA.md
ROUND_2_DAY0_RECEIPT.md
```

Round 2 is a Provider/coverage capability audit, not another edge experiment.

## Audit universe

```text
CURRENT_ACTIVE_WHITELIST = 13
AUDIT_ONLY_NET_NEW = 4
AUDIT_UNION = 17
```

Net-new audit-only IDs:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

They must remain outside runtime whitelist membership and all production Scheduler/DayView paths.

## R2-A result

R2-A is complete in `ROUND_2_DAY0_RECEIPT.md`. The Day-0 matrix has 17 truthful
`PLAN_RESTRICTED` rows, 17 total `/leagues` calls, zero deeper calls and zero
promotion-authorized rows.

## R2-B

The active read-only observation window is:

```text
START = 2026-08-08T01:53:55.509495+00:00
END = 2026-08-22T01:53:55.509495+00:00
```

Use real persisted W2 captures and existing authorized production collection. Do not create new persistent polling for the four audit-only candidates.

Describe freshness, overround, movement, bookmaker depth/agreement, missingness and schema/provider incidents where real samples exist.

Do not freeze Round 3 alert thresholds.

## R2-C

Produce exactly 17 final capability rows with truthful ready/partial/blocked/insufficient outcomes.

Allowed product capability recommendations:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

The four net-new current runtime states remain `AUDIT_CANDIDATE_ONLY`.

```text
promotion_authorized = false
```

for every row.

## Hard boundaries

```text
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
ROUND_3 = NOT_STARTED
BETTING_EDGE_CLAIM = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
