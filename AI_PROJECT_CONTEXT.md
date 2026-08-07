# W2 AI Project Context

Current mutable context is maintained on branch `context/current`. Read:

- `CURRENT_CONTEXT.md`
- `CURRENT_STATE.yaml`
- `CURRENT_PRODUCT_DESIGN.md`
- `CURRENT_TASK_CHECKLIST.md`
- `NEXT_ACTION.md`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_AGENTS.md`

Context changes are direct replacements and do not use PR, CI, Release Candidate, image build or deployment.

## Current product decision

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

The deployed operational W2 data, identity, odds, model, Scheduler, replay and Dashboard foundations are preserved. The product is being reframed from a recommendation console into a market-intelligence and model-diagnostics platform.

## Phase 0.5 evidence boundary

```text
FINAL_VERDICT = NO_EDGE
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_FROZEN_SELECTIONS = 7566
OU_PRE_FROZEN_STRATEGY_ROI = -5.32_PERCENT
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Do not retune that model family with V/H results. Permanent product rule:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

## Round 1

Round 1 changes product semantics only:

- intelligence-first public page;
- market/model/data/collection states;
- event/data/model/collection risk dimensions;
- stable market as a valid result;
- no opportunity/recommendation language from model divergence;
- V4 retained as diagnostic evidence input;
- no league, Provider or Scheduler expansion.

One runtime PR, one exact-head full validation, one deployment, then stop.

## League program after Round 1

Candidate first divisions:

```text
Core Benchmark:
Premier League, La Liga, Bundesliga, Serie A, Ligue 1

Extended Radar Candidates:
Eredivisie, Belgian Pro League, Primeira Liga, Turkish Super Lig,
Greek Super League, Scottish Premiership
```

Promotion requires the 14-day API-Football capability audit. Historical football-data behavior is not live Provider authority.

## Market Radar guard

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Historical evidence indicates that higher first-division PRE-to-CLOSE movement rates co-occurred with higher overround. Therefore frequent movement may reflect thin-market noise.

- lower overround can support higher information confidence;
- high overround requires stronger magnitude, persistence or independent bookmaker confirmation;
- isolated high-overround movement normally maps to `THIN_MARKET_NOISE`;
- high overround is not high value;
- exact alert parameters wait for live Round 2 distributions.

## Permanent boundaries

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
