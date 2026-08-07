# W2 Football Intelligence — Current Product Design

This is the current product-design authority for W2 on branch `context/current`.

## 1. Product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT_ROLE = MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
BETTING_EDGE_CLAIM = FORBIDDEN
RECOMMENDATION_AUTHORITY = NOT_A_PRODUCT_GOAL
REAL_MONEY = NOT_AUTHORIZED
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_RUNTIME_PR = 493
```

The existing W2 data, identity, odds, model, Scheduler, replay and Dashboard infrastructure is preserved. The public shell changes from recommendation-first to intelligence-first.

Permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

A model-market difference is a diagnostic condition, never a value/opportunity/recommendation/positive-EV claim.

## 2. Product questions

W2 should answer:

1. What is happening in the market?
2. Is the market stable, moving, anomalous, stale or incomplete?
3. Is the data complete/fresh/trustworthy?
4. Is the model calibrated/reliable or showing warning/disagreement?
5. Which matches, leagues, data paths or runtime systems need attention?

It should not answer what to bet, how much to stake, or which side has positive edge.

## 3. Round 1 public surfaces

### 3.1 Market Overview

Minimum counters:

```text
monitored fixtures
market-complete fixtures
fresh quotes
market-stable fixtures
market-movement fixtures
model diagnostic warnings
data incidents
collection incidents
```

Zero material alerts is a valid success result. Do not lower thresholds to create content.

### 3.2 Match Intelligence

Retain real match cards as diagnostic surfaces with existing truthful evidence where available:

- fixture/team/competition identity;
- AH/OU current or last-known market facts;
- line/price/freshness/capture time;
- existing market movement evidence;
- lineup/data readiness;
- model/market probabilities and diagnostic disagreement;
- model-quality context;
- evidence lineage and blockers.

Market facts must not disappear merely because V4 has no pick/selected candidate or says `NOT_READY/NO_EDGE`.

Never promote stale/reference-only quotes into current/executable truth.

### 3.3 Data & Operations Summary

Preserve operational truth:

- Provider/Scheduler status;
- quote freshness and stale incidents;
- identity/mapping/data issues;
- release SHA and API/Web synchronization;
- Candidate/Formal/Lock/Production state.

Historical settlement/performance may remain as clearly historical diagnostics, not as proof of current betting edge.

## 4. Intelligence state taxonomy

Every public fixture/card/read-model projection has one top-level state:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Frozen Round 1 precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Secondary reason codes remain deterministic so lower-precedence facts are not lost.

Round 1 may only map existing explicit movement/anomaly evidence. New market-alert formulas belong to Round 3.

## 5. Risk dimensions

Risk/incident dimensions are separate:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Rules:

- `NOT_READY/BLOCKED` is not a high-risk match;
- identity/xG/quote/readiness problems -> data/model readiness;
- Provider/Scheduler/schema/runtime failures -> collection;
- actual injury/lineup/event facts -> event;
- model readiness/calibration/feature staleness/divergence -> model;
- do not combine data and collection back into one generic risk;
- no risk dimension implies a recommendation.

## 6. League plan — corrected authority

### 6.1 Existing active whitelist baseline

W2 currently has **13 active-whitelist competitions**. Round 1 preserves them exactly.

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Baseline identities:

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

Whitelist membership does not mean every league is currently high-frequency Provider collection-ready or market-intelligence-ready. Capability and collection policy are separate.

### 6.2 European market-role cohort — not the whitelist

The earlier `5 + 6` grouping is retained only as a European market-role lens.

Core Benchmark — 5 already inside the baseline 13:

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar — 6:

```text
Eredivisie              existing baseline
Primeira Liga           existing baseline
Belgian Pro League      net-new candidate
Turkish Super Lig       net-new candidate
Greek Super League      net-new candidate
Scottish Premiership    net-new candidate
```

Do not label Extended Radar as high-value or imply that more line movement means better information.

### 6.3 Future expansion arithmetic

The next capability-audit universe is not 11. It is the union:

```text
CURRENT_BASELINE = 13
NET_NEW = 4
FUTURE_CANDIDATE_UNION = 17
```

The four net-new candidates are:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Round 1 does not register, enable, call, schedule or audit these four leagues.

### 6.4 Capability states

Each league may later have one product capability state:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

There is no `RECOMMENDATION_READY`, `POSITIVE_EV_READY`, `FORMAL_READY` or `AUTO_EXECUTION_READY` product state.

## 7. Market Radar guard for later rounds

Round 3 must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Higher overround may indicate thin/noisy markets and is not high value. Exact thresholds, persistence rules, bookmaker-confirmation rules and alert formulas wait for Round 2 live distributions.

Public Radar outputs may later include:

```text
MOVEMENT_MAGNITUDE
MARKET_CONFIDENCE
NOISE_RISK
CONFIRMATION_COUNT
ALERT_SEVERITY
```

No opportunity score.

## 8. Three-round delivery plan

### Round 1 — authorized and in remediation

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = IN_PROGRESS_REMEDIATION
ACTIVE_WHITELIST = 13_UNCHANGED
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
```

Explicit owner continuation authority is `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`.

Delivery-count wording is binding as follows:

```text
ONE_RUNTIME_PR = PR_493_ONLY
PR_FAST_ATTEMPTS = AS_NEEDED_AFTER_EACH_SOURCE_HEAD_CHANGE
FULL_RC_ATTEMPTS = AS_NEEDED_UNTIL_FINAL_SUCCESS
FAILED_PR_FAST_OR_FULL_RC_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
ONE_FINAL_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

Therefore **`one final exact-head Full Release Candidate` means one successful final RC on the final accepted head; it is not a cap of one RC attempt.**

For any in-scope failure:

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1
DIAGNOSE -> MINIMAL_FIX_IN_PR_493 -> LOCAL_VALIDATION -> NEW_HEAD_PR_FAST -> NEW_EXACT_HEAD_FULL_RC -> REPEAT_IF_NEEDED
```

No new owner authorization is required for bounded Round 1 remediation, PR Fast re-runs or replacement exact-head Full RC attempts.

Detailed execution authority: `ROUND_1_CODEX_EXECUTION.md`.

Binding acceptance authority: `ROUND_1_ACCEPTANCE_CRITERIA.md`.

Round 1 closes only after final RC success, one merge commit, same-verified-source API/Web deployment, public API/browser acceptance and all acceptance criteria PASS.

### Round 2 — blocked

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
STATUS = BLOCKED_UNTIL_ROUND_1_ACCEPTED_AND_OWNER_AUTHORIZED
DURATION = 14_DAYS
MODE = READ_ONLY_CONTROLLED
TARGET_CANDIDATE_UNION = 17
```

Audit the wider union without automatically promoting all members to high-frequency collection or readiness.

### Round 3 — blocked

```text
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
STATUS = BLOCKED_UNTIL_ROUND_2_CAPABILITY_DECISION
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
```

## 9. Permanent stop lines

```text
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
