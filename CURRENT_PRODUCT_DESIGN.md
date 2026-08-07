# W2 Football Intelligence — Current Product Design

This is the current product-design authority for W2. It is maintained on branch `context/current` and is replaced directly when the owner changes the product direction. It is not a historical archive and does not use a context PR or CI.

## 1. Product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT_ROLE = MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
BETTING_EDGE_CLAIM = FORBIDDEN
RECOMMENDATION_AUTHORITY = NOT_A_PRODUCT_GOAL
REAL_MONEY = NOT_AUTHORIZED
```

The existing W2 data, identity, odds, model, scheduler, replay and dashboard infrastructure is preserved. The product shell changes from a single-match recommendation console into a market-intelligence and model-diagnostics platform.

Phase 0.5 ended with `NO_EDGE` for the tested model/selection family. That evidence is a permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

A large model/market difference must be presented as a diagnostic condition, never as a value opportunity, recommendation, positive EV claim or execution signal.

## 2. Product questions

The platform should answer:

1. What is happening in the football market now?
2. Is the market stable, moving, noisy, stale or internally inconsistent?
3. Is the data complete and fresh enough to trust the display?
4. Is the model calibrated and behaving consistently with its historical quality?
5. Which leagues, providers, markets or model components need attention?

It should not answer:

```text
What should I bet?
How much should I stake?
Which selection has positive edge?
```

## 3. Product surfaces

### 3.1 Market Overview

- monitored leagues and future fixtures;
- market-complete fixtures;
- quote freshness;
- market-stable count;
- material market-movement count;
- data/model/collection incidents;
- Provider health and refresh status.

Zero material alerts is a valid product result:

```text
MARKET_STATUS = STABLE
```

The UI must not lower thresholds merely to create content.

### 3.2 Market Radar

Market events may include:

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

A Radar event is market intelligence, not a recommendation.

### 3.3 Model Lab

- market vs model Log Loss;
- Brier score and calibration;
- ECE and drift;
- model/market divergence distribution;
- feature readiness and staleness;
- league, season and odds-band diagnostics;
- model trust state.

Model divergence must always include historical model-quality context. If the model has not demonstrated market increment, the default interpretation is model review, not market mispricing.

### 3.4 Match Intelligence

The existing match card is retained as a diagnostic surface with:

- fixture and identity;
- AH/OU current market state and timeline;
- line/price changes;
- quote freshness and overround;
- lineup/injury/fact readiness;
- model and market probabilities;
- model-quality disclaimer;
- raw evidence lineage and blockers.

Remove recommendation-first language such as `pick`, `recommended side`, `high-value opportunity` and generic `high-risk match`.

### 3.5 Data & Operations

- endpoint coverage and success rate;
- Scheduler checkpoints;
- Provider quota and errors;
- identity/mapping conflicts;
- stale-data incidents;
- result reconciliation;
- league capability level.

## 4. Status and risk taxonomy

Top-level intelligence states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Risk/incident dimensions are separate:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

`NOT_READY`, `BLOCKED` or missing data must never be mapped to a betting-risk conclusion.

## 5. League capability model

Each league has one current capability state:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

There is no current state named:

```text
RECOMMENDATION_READY
POSITIVE_EV_READY
FORMAL_READY
AUTO_EXECUTION_READY
```

### 5.1 First-division target set

The 11 first-division candidates are split by product role, not by profitability:

#### Core Benchmark

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

These are high-quality reference markets. Low overround and fewer alerts are not product defects.

#### Extended Radar Candidates

```text
Eredivisie
Belgian Pro League
Primeira Liga
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Do not label this group `high value` or imply that more movement means more useful information. The group exists to broaden market-structure coverage.

Second-tier leagues remain `REGISTERED` or `COVERAGE_MONITORING` initially.

### 5.2 Live promotion authority

Historical football-data coverage does not prove API-Football live capability. Promotion to `MARKET_INTELLIGENCE_READY` requires a 14-day read-only Provider capability audit.

Audit metrics:

```text
fixture identity success
AH pair completeness
OU pair completeness
quote timestamp coverage
freshness distribution
Provider error rate
team mapping conflicts
result reconciliation
calls per fixture
lineup return rate near kickoff
schema drift count
```

No league is promoted merely because it is in the 11-league target set.

## 6. Market Radar scoring contract

### 6.1 Mandatory evidence

Radar scoring must consider:

```text
line movement magnitude
price movement magnitude
time to kickoff
movement persistence
price reversal
bookmaker confirmation/dispersion
quote freshness
market overround and overround percentile
league/market/time-bucket baseline
```

### 6.2 Overround is a noise/confidence covariate

Historical analysis showed that, among the 11 first-division candidates, PRE-to-CLOSE line-movement rate was strongly positively associated with overround. Therefore higher movement frequency can reflect a thinner, less trusted market rather than higher information value.

Mandatory rule:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Overround is not only a display field. It adjusts the confidence required for a market-movement alert.

For the same observed movement:

- lower-overround markets may receive higher information confidence;
- higher-overround markets require stronger magnitude, persistence or multi-book confirmation;
- a high-overround isolated move should normally classify as `THIN_MARKET_NOISE`, not a high-severity intelligence event;
- an overround increase may separately produce `OVERROUND_SPIKE`.

No hard numeric adjustment is frozen before the 14-day Provider audit. Round 2 must collect the live distributions needed to define league × market × time-to-kickoff conditional percentiles. Round 3 freezes the exact alert model before deployment.

### 6.3 Alert confidence, not opportunity score

Radar should expose separate fields:

```text
MOVEMENT_MAGNITUDE
MARKET_CONFIDENCE
NOISE_RISK
CONFIRMATION_COUNT
ALERT_SEVERITY
```

It must not expose an `opportunity score` derived from model divergence or market movement.

### 6.4 Minimum high-severity rule

A high-severity market-movement alert cannot be created solely from one large move. It must also satisfy frozen evidence rules such as persistence, freshness, low-noise overround context or independent bookmaker confirmation.

## 7. Three-round delivery plan

### Round 1 — Product semantics and status reframe

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
```

One bounded runtime PR and one deployment.

Scope:

- change the public product from recommendation-first to intelligence-first;
- implement the intelligence states and four risk dimensions;
- make `MARKET_STABLE` a valid result;
- remove model-divergence-as-opportunity language;
- preserve V4 and existing model evidence only as diagnostic inputs;
- preserve Scheduler and current league/provider configuration;
- add regression tests proving `MODEL_MARKET_DIVERGENCE` cannot generate recommendation/value language.

### Round 2 — First-division capability audit

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
DURATION = 14_DAYS
TARGET_LEAGUES = 11_FIRST_DIVISIONS
MODE = READ_ONLY_CONTROLLED
```

Scope:

- register/map the 11 candidate leagues without declaring them ready;
- collect fixtures/status at low frequency;
- collect odds only at bounded windows/frequencies;
- collect lineups only near kickoff where justified;
- report API-Football coverage, quality and cost;
- classify each league into the capability model;
- collect live overround and movement distributions needed by Round 3;
- do not produce recommendations or opportunities.

### Round 3 — Market Radar and Model Lab

```text
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
```

Scope:

- build market timeline and anomaly read models;
- implement league/market/time-bucket percentile baselines;
- make overround percentile a mandatory alert covariate;
- calibrate thin-market noise penalties from Round 2 data;
- implement bookmaker agreement, persistence and reversal evidence;
- build Model Lab calibration/drift views;
- preserve the permanent model-divergence guard;
- deploy only for leagues that pass Round 2 capability gates.

## 8. Permanent stop lines

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

A future quant program requires a new information source, genuinely new edge/model hypothesis and a new pre-registered protocol. The failed Phase 0.5 V/H data cannot be used for post-result tuning.
