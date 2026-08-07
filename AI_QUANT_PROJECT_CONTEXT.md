# W2 Market Intelligence — AI Handoff

Read first from branch `context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `QUANT_AGENTS.md`

Context updates do not use PR, CI, Release Candidate, image build or deployment.

## Current decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Phase 0.5 is closed with `NO_EDGE`; H is permanently closed under that protocol. The current work is product repositioning, not another betting-edge experiment.

## Permanent evidence guard

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

The Phase 0.5 V evidence showed that the least-regularized model created many apparent selections but did not beat Pinnacle and lost money, while stronger regularization collapsed back toward the market. Therefore model divergence is a model-quality diagnostic, never an opportunity score.

Forbidden language/meaning from divergence alone:

```text
value opportunity
positive edge
market mispricing
recommended side
high-confidence pick
```

## Round 1 handoff

Implement one bounded API/Web semantic refactor:

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
```

Required states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Required risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

`NOT_READY`/`BLOCKED` must not map to betting risk. A stable market/zero-alert day must render as a valid non-empty result.

Preserve existing real data, V4 evidence, Scheduler, Provider policy and current leagues. V4 becomes diagnostic input rather than the public product authority.

## Delivery

- one clean worktree;
- one bounded runtime PR;
- focused local feedback during implementation;
- one exact-head full Release Candidate;
- one merge and one deployment;
- public browser acceptance;
- stop after Round 1; do not start the league audit automatically.

## Future rounds

Round 2:

```text
11 first-division candidates
14-day read-only Provider capability audit
```

Round 3:

```text
Market Radar + Model Lab
only Round 2 promoted leagues
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Overround is a market-thinness/noise confidence covariate. High-overround isolated moves should normally be classified as `THIN_MARKET_NOISE`; exact formulas wait for live Round 2 distributions.

## Hard boundaries

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
