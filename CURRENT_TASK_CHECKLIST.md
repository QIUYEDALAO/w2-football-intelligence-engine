# W2 Current Task Checklist

This is the complete current task order for W2. It is maintained directly on branch `context/current`; context updates do not use PR or CI. Runtime changes continue to use the normal guarded delivery process.

## Program status

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
OWNER_DECISION = APPROVED
ACTIVE_TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
NEXT_CODE_TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Current design authority:

```text
CURRENT_PRODUCT_DESIGN.md
```

Permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

---

## MI-00 — Phase 0.5 closeout

```text
STATUS = DONE
FINAL_VERDICT = NO_EDGE
```

Decisive evidence:

```text
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_FROZEN_SELECTIONS = 7566
OU_PRE_FROZEN_STRATEGY_ROI = -5.32_PERCENT
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Consequences:

- do not retune the failed protocol on V/H outcomes;
- do not build a profit-claiming Signal Ledger, Portfolio, Risk/Kelly or execution product;
- preserve the evidence as a model-quality/product-design guard.

---

## MI-R1 — Product semantics and status reframe

```text
STATUS = NEXT_AUTHORIZED
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
CHANGE_CLASS = RUNTIME_API_AND_WEB
ONE_PR = true
ONE_RELEASE = true
ONE_DEPLOYMENT = true
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
```

### R1.1 Source and scope

- start from the latest trusted `origin/main` in one clean worktree;
- use one bounded branch and one PR;
- preserve the existing V4 calculations, Scheduler, Provider policy and current league set;
- do not add new Provider calls;
- do not implement Round 2 or Round 3 early.

### R1.2 Product identity

Change the public product identity to:

```text
W2 Football Intelligence
W2 Football Market Intelligence & Model Diagnostics
```

The top-level user question changes from `what should I pick?` to:

```text
what is happening in the market?
is the data fresh and complete?
is the model behaving reliably?
what needs attention?
```

### R1.3 Intelligence states

Implement one explicit top-level state per card/fixture/read-model projection:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

State precedence and reason codes must be deterministic and tested.

### R1.4 Risk dimensions

Replace generic `high/medium/low risk` semantics with independent dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Rules:

- `NOT_READY` and `BLOCKED` are not betting-risk states;
- missing xG/ratings/lineups become data or model readiness reasons;
- Provider/Scheduler failures become collection incidents;
- event/lineup facts remain event-risk evidence;
- no dimension implies a recommendation.

### R1.5 Permanent divergence guard

Machine and UI guard:

```text
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
```

A model/market difference may display:

```text
model-market disagreement
model calibration review required
model feature may be stale
market information not explained by model
```

It may not display or emit:

```text
value opportunity
positive edge
recommended side
market mispricing
high-confidence pick
```

The guard must apply to API/read-model output, web adapters, labels, tooltips, counters and browser-visible text.

### R1.6 Market stable as a valid result

The system must explicitly show:

```text
MARKET_STABLE
no material market anomaly detected
```

A zero-alert day is successful operation, not an empty/error state. Do not lower thresholds to populate the page.

### R1.7 Page structure

Round 1 may reorganize the existing page into an intelligence-first shell:

```text
Market Overview
Match Intelligence
Data & Operations summary
```

Round 1 does not yet implement the full Market Radar or Model Lab analytics.

Minimum overview counters:

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

### R1.8 Existing V4 role

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Do not delete V4 or settlement history. Stop presenting V4 as a public betting recommendation authority.

### R1.9 Round 1 tests

At minimum:

1. `MODEL_MARKET_DISAGREEMENT` never produces opportunity/recommendation language.
2. `NOT_READY/BLOCKED` maps to data/model/collection state, not high-risk match.
3. stable market renders a non-empty valid state.
4. event/data/model/collection risk dimensions remain separate.
5. current real data cards still render.
6. empty-day behavior remains explicit and non-blank.
7. API/Web release SHA remains synchronized.
8. Candidate/Formal/Lock/Production remain off.
9. Provider/Scheduler configuration and call counts are unchanged by this PR.
10. browser console errors = 0.

### R1.10 Delivery

- focused local tests during implementation;
- PR fast check;
- one exact-head full Release Candidate;
- merge once;
- deploy the verified immutable API/Web images once;
- public browser acceptance;
- do not begin Round 2 automatically.

Round 1 completion state:

```text
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
LEAGUE_SET = UNCHANGED
MARKET_RADAR_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
MODEL_LAB_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
```

---

## MI-R2 — First-division Provider capability audit

```text
STATUS = BLOCKED_UNTIL_MI_R1_ACCEPTED
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
DURATION = 14_DAYS
MODE = READ_ONLY_CONTROLLED
```

### R2.1 Candidate leagues

Core Benchmark:

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar Candidates:

```text
Eredivisie
Belgian Pro League
Primeira Liga
Turkish Super Lig
Greek Super League
Scottish Premiership
```

The label `Extended Radar` does not imply higher value or stronger information.

### R2.2 Capability levels

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

No recommendation/profitability capability level exists.

### R2.3 Endpoint/frequency separation

- fixtures/status: low-frequency baseline monitoring;
- odds: bounded capture windows and per-league caps;
- lineups: near-kickoff only where justified;
- expensive statistics/injuries: opt-in by diagnostic need;
- call volume is governed by league count × fixtures × endpoint × frequency × retry.

### R2.4 Audit metrics

```text
fixture identity success
AH pair completeness
OU pair completeness
quote timestamp coverage
quote freshness distribution
Provider error rate
schema drift
team mapping conflicts
result reconciliation
calls per fixture
lineup return rate near kickoff
overround distribution
line/price movement distribution
bookmaker coverage and agreement
```

Before the first live audit call, freeze exact qualification thresholds and quotas. Historical football-data measurements cannot substitute for API-Football capability evidence.

### R2.5 Round 2 output

- league-by-league capability matrix;
- promoted/degraded decision with reasons;
- live movement/overround baseline by league, market and time-to-kickoff bucket;
- call-cost and quota report;
- no recommendation or opportunity output.

Do not begin Round 3 automatically.

---

## MI-R3 — Market Radar and Model Lab

```text
STATUS = BLOCKED_UNTIL_MI_R2_CAPABILITY_DECISION
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
```

### R3.1 Market Radar events

```text
CONFIRMED_MARKET_MOVE
THIN_MARKET_NOISE
PRICE_REVERSAL
BOOKMAKER_DISAGREEMENT
OVERROUND_SPIKE
STALE_MARKET
MISSING_COUNTERSIDE
SCHEMA_OR_IDENTITY_INCIDENT
```

### R3.2 Mandatory alert evidence

```text
line movement magnitude
price movement magnitude
time to kickoff
persistence
reversal
bookmaker confirmation/dispersion
freshness
overround percentile
league/market/time-bucket baseline
```

### R3.3 Overround alert covariate

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Overround is a market-thinness/noise confidence covariate, not just a display field.

For the same observed move:

- lower-overround context can support higher information confidence;
- higher-overround context requires stronger magnitude, persistence or independent bookmaker confirmation;
- isolated high-overround moves should normally become `THIN_MARKET_NOISE`;
- an overround increase may separately create `OVERROUND_SPIKE`;
- high overround must never be interpreted as high value.

Exact thresholds/formulas are frozen only after Round 2 live distributions are available.

### R3.4 Model Lab

- market vs model Log Loss;
- Brier and calibration;
- ECE and drift;
- model/market divergence distribution;
- feature readiness/staleness;
- league/season/odds-band diagnostics;
- model trust state.

Permanent rule:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

### R3.5 Radar output fields

```text
MOVEMENT_MAGNITUDE
MARKET_CONFIDENCE
NOISE_RISK
CONFIRMATION_COUNT
ALERT_SEVERITY
```

Do not create an opportunity score.

---

## Permanent stop lines

```text
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

A future quant program requires a new information source, genuinely new edge/model hypothesis and a new pre-registered protocol. The failed Phase 0.5 V/H evidence may not be used for post-result tuning.
