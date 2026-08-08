# W2 Market Intelligence — AI Handoff

Current authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ACTIVE_NEXT_ACTION = W2_MI_R2_AUDIT_FOUNDATION_AND_DAY0_BASELINE
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

## R2-A

Create one bounded audit-tooling PR and no product-semantic refactor.

Required:

- audit-only descriptor namespace outside runtime whitelist discovery;
- deterministic Provider-backed identity resolution;
- no fuzzy or guessed Provider IDs;
- 17-row dry-run with zero Provider calls;
- cumulative sanitized audit ledger;
- Provider reserve and hard caps;
- no automatic retries;
- no Provider calls during PR development/CI.

After R2-A tooling is accepted, controlled Provider audit calls are owner-authorized only through the audit path.

```text
DAY0_EVIDENCE_ONLY_CALLS_PER_COMPETITION = 4
DAY0_THEORETICAL_MAX = 68
ROUND2_DAILY_AUDIT_HARD_CAP = 80
ROUND2_CUMULATIVE_AUDIT_HARD_CAP = 200
ROUND2_MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
```

Quota/plan/identity/schema blockers are valid outcomes. Never raise limits or weaken guards.

## R2-B

The first successful Day-0 baseline starts a 14-calendar-day read-only observation window.

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
