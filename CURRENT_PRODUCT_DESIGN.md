# W2 Football Intelligence — Current Product Design

## 1. Product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT_ROLE = MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ROUND_1 = PASS
ROUND_2 = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
BETTING_EDGE_CLAIM = FORBIDDEN
REAL_MONEY = NOT_AUTHORIZED
```

Permanent product guards:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
HIGH_OVERROUND != HIGH_VALUE
HIGH_OVERROUND != HIGH_INFORMATION
```

## 2. Public product surfaces — frozen from Round 1

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Public intelligence states remain:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Risk dimensions remain separate:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Round 2 must not regress the Round 1 public product semantics.

## 3. League universe

Current active whitelist is exactly 13:

```text
chinese_super_league
allsvenskan
eliteserien
premier_league
la_liga
bundesliga
serie_a
ligue_1
brasileirao_serie_a
argentina_primera
mls
eredivisie
primeira_liga
```

Round 2 audit-only candidates:

```text
belgian_pro_league
turkish_super_lig
greek_super_league
scottish_premiership
```

Round 2 audit universe:

```text
13 EXISTING + 4 AUDIT_ONLY = 17
```

The four audit-only candidates must remain outside runtime whitelist discovery, Scheduler, future-refresh, DayView and public cards.

## 4. Capability taxonomy

Existing runtime/product capability states:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

Audit-only current runtime state:

```text
AUDIT_CANDIDATE_ONLY
```

Round 2 may recommend a future capability state, but:

```text
promotion_authorized = false
```

for every row.

No Round 2 audit outcome automatically changes `enabled`, whitelist membership, Scheduler policy or public visibility.

## 5. Round 2 provider capability questions

Round 2 determines, using real evidence:

- exact Provider league identity and current/audit season coverage;
- future fixtures and completed results availability;
- AH and OU market presence;
- line/price/timestamp truth;
- bookmaker depth/confirmation;
- lineup/injury/statistics capability;
- schema safety and Provider errors;
- real freshness and collection coverage;
- observed overround/movement distributions where temporal samples exist;
- Provider call cost and quota blockers.

Round 2 is not an edge test and does not decide what to bet.

## 6. Round 2 phases

### R2-A — Audit foundation and Day-0 baseline

```text
STATUS = ACTIVE
```

One bounded audit-tooling PR must enable the 17-union audit without changing runtime whitelist membership.

The four net-new identities must be resolved using deterministic Provider-backed evidence. No guessed league IDs or fuzzy auto-selection.

Day-0 begins with the existing `evidence-only` audit semantics.

Provider budgets are frozen by `ROUND_2_OWNER_AUTHORIZATION.md`:

```text
DAY0_THEORETICAL_MAX = 68
DAILY_AUDIT_HARD_CAP = 80
CUMULATIVE_AUDIT_HARD_CAP = 200
MIN_PROVIDER_DAILY_REMAINING = 20
REQUEST_INTERVAL_SECONDS_MIN = 10
AUTOMATIC_RETRY = false
```

### R2-B — Fourteen-day read-only observation

```text
STATUS = BLOCKED_UNTIL_DAY0_BASELINE
```

Observation uses existing persisted W2 captures/read models and already-authorized production collection.

Round 2 does not authorize new persistent polling for audit-only candidates.

Missing temporal evidence is reported as insufficient, not manufactured.

### R2-C — Final capability matrix

```text
STATUS = BLOCKED_UNTIL_OBSERVATION_END
```

Exactly 17 final rows are required, with truthful ready/partial/blocked/insufficient outcomes.

## 7. Market Radar evidence for later Round 3

Round 2 gathers descriptive evidence only:

```text
freshness
sample counts
fixture counts
overround distribution where computable
line-movement distribution
bookmaker depth/confirmation
missingness/schema incident rates
```

Round 2 must not freeze alert thresholds.

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE_IN_ROUND_3
OPPORTUNITY_SCORE = FORBIDDEN
```

If the sample is too small, report insufficient evidence rather than a fake percentile.

## 8. Round 2 current task authority

```text
ACTIVE_NEXT_ACTION = W2_MI_R2_AUDIT_FOUNDATION_AND_DAY0_BASELINE
OWNER_AUTHORIZATION = ROUND_2_OWNER_AUTHORIZATION.md
EXECUTION_AUTHORITY = ROUND_2_CODEX_EXECUTION.md
ACCEPTANCE_AUTHORITY = ROUND_2_ACCEPTANCE_CRITERIA.md
```

## 9. Permanent stop lines

```text
ACTIVE_WHITELIST = 13_UNCHANGED
PRODUCTION_PROVIDER_POLICY_CHANGE = false
PRODUCTION_PROVIDER_ALLOWLIST_CHANGE = false
PRODUCTION_SCHEDULER_POLICY_CHANGE = false
NEW_PERSISTENT_COLLECTION_FOR_NET_NEW = false
ROUND_3 = NOT_STARTED
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
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
