# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on branch `context/current` without a pull request, CI, Release Candidate, image build or deployment. Superseded context is replaced rather than retained as current authority.

Read with:

- `CURRENT_STATE.yaml`
- `CURRENT_PRODUCT_DESIGN.md`
- `CURRENT_TASK_CHECKLIST.md`
- `NEXT_ACTION.md`

## Owner product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

W2 is not being rebuilt as a betting or profit-claiming quant platform. The existing W2 data, identity, odds, model, scheduler, replay and dashboard infrastructure is preserved and repositioned as market intelligence and model diagnostics.

## Evidence boundary

Phase 0.5 ended with:

```text
FINAL_VERDICT = NO_EDGE
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_FROZEN_SELECTIONS = 7566
OU_PRE_FROZEN_STRATEGY_ROI = -5.32_PERCENT
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

The tested model/selection family may not be retuned on V/H outcomes. This evidence creates a permanent product rule:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

Model/market divergence is a diagnostic state. It must never be displayed as value, edge, opportunity, recommendation or execution guidance.

## New product questions

W2 should answer:

- what is happening in the market;
- whether quotes and identities are complete and fresh;
- whether a market move is persistent, confirmed or noisy;
- whether the model is calibrated and stable;
- which leagues, providers, data sources or model components require attention.

It should not answer what to bet or how much to stake.

## Product structure

```text
Market Overview
Market Radar
Model Lab
Match Intelligence
Data & Operations
```

Top-level states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

`NOT_READY` or `BLOCKED` must not be translated into betting risk.

## League plan

First-division candidate set:

### Core Benchmark

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

### Extended Radar Candidates

```text
Eredivisie
Belgian Pro League
Primeira Liga
Turkish Super Lig
Greek Super League
Scottish Premiership
```

These 11 leagues are candidates, not automatically ready. Second-tier leagues begin as `REGISTERED` or `COVERAGE_MONITORING`.

Live capability levels:

```text
REGISTERED
COVERAGE_MONITORING
MARKET_INTELLIGENCE_READY
MODEL_DIAGNOSTICS_READY
DEGRADED
```

Promotion requires the Round 2 14-day API-Football capability audit.

## Overround alert covariate

Historical analysis found that, within the 11 first-division candidates, higher PRE-to-CLOSE line-movement rates were strongly associated with higher overround. Therefore frequent movement may indicate a thinner, less trusted market rather than stronger information.

Mandatory design rule:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

For the same move:

- lower-overround market context may support higher information confidence;
- higher-overround context requires stronger magnitude, persistence or independent bookmaker confirmation;
- an isolated high-overround move should normally classify as `THIN_MARKET_NOISE`;
- `OVERROUND_SPIKE` is a separate market event, not an opportunity.

Exact formulas and thresholds are not frozen until Round 2 produces live league × market × time-to-kickoff distributions.

## Three-round implementation

### Round 1 — Product semantics and status reframe

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
STATUS = AUTHORIZED_NEXT
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
```

One runtime PR, one full validation, one deployment. Change recommendation-first language and state mapping to intelligence-first semantics. Preserve current league/provider configuration.

### Round 2 — First-division Provider capability audit

```text
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
STATUS = BLOCKED_UNTIL_ROUND_1_ACCEPTED
DURATION = 14_DAYS
MODE = READ_ONLY_CONTROLLED
```

Test the 11 candidates using actual API-Football coverage, freshness, errors, identity quality and call cost. Collect live overround/movement distributions. Do not recommend or infer value.

### Round 3 — Market Radar and Model Lab

```text
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
STATUS = BLOCKED_UNTIL_ROUND_2_CAPABILITY_DECISION
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
```

Implement market timelines, anomaly read models, overround-adjusted confidence/noise scoring, bookmaker confirmation, persistence/reversal logic, calibration and model drift views.

## Current hard boundary

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
