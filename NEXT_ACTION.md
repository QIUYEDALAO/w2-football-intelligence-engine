# NEXT ACTION

Current action:

```text
W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Current product authority:

- `CURRENT_CONTEXT.md`
- `CURRENT_STATE.yaml`
- `CURRENT_PRODUCT_DESIGN.md`
- `CURRENT_TASK_CHECKLIST.md`

These files are maintained directly on `context/current`; context updates do not use PR or CI.

## Owner decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
```

Phase 0.5 ended with `NO_EDGE`. Do not retune the failed model family on V/H outcomes and do not reopen H. The permanent product guard is:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

## Round 1 objective

Convert the public product from recommendation-first to intelligence-first while preserving the existing data/model/scheduler foundations.

Required outcomes:

1. Replace public recommendation/pick language with market-intelligence and model-diagnostic language.
2. Implement deterministic intelligence states:
   - `MARKET_STABLE`
   - `MARKET_MOVEMENT`
   - `MARKET_ANOMALY`
   - `MODEL_MARKET_DISAGREEMENT`
   - `DATA_INCOMPLETE`
   - `MODEL_DIAGNOSTIC_WARNING`
   - `COLLECTION_INCIDENT`
3. Split risk into event/data/model/collection dimensions.
4. Make market stability and zero material alerts a valid non-empty result.
5. Prevent model/market divergence from generating opportunity, edge, recommendation or pick language anywhere in API/read-model/web output.
6. Reposition V4 as a diagnostic input rather than the public product authority.
7. Preserve current real cards, empty-day behavior, release SHA visibility and operational health.

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2_CAPABILITY_AUDIT = NOT_STARTED
ROUND_3_MARKET_RADAR = NOT_STARTED
```

Use one bounded runtime PR, one exact-head full validation and one deployment. Do not split Round 1 into multiple delivery cycles.

## Later rounds

Round 2, after Round 1 acceptance:

```text
11 first-division candidates
14-day read-only API-Football capability audit
no recommendation/profit output
```

Round 3, after Round 2 capability decisions:

```text
Market Radar + Model Lab
only promoted leagues
overround percentile required as alert confidence/noise covariate
```

The exact Round 3 alert formula is frozen after live Round 2 distributions, not before.

## Permanent stop lines

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
