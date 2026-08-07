# W2 AI Project Context

Current mutable authority is maintained on branch `context/current`.

## Current program

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Read `ROUND_1_CODEX_EXECUTION.md` for execution and `ROUND_1_ACCEPTANCE_CRITERIA.md` for acceptance.

Phase 0.5 is closed with `NO_EDGE`; H is permanently closed under that protocol.

Permanent product rule:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## League correction

Current active whitelist baseline is 13 and must not change in Round 1:

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

The European `5 + 6` grouping is not a replacement whitelist. `Eredivisie` and `Primeira Liga` are already in the baseline 13. The future net-new candidates are only:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future Round 2 candidate union:

```text
13 EXISTING + 4 NET_NEW = 17
```

Round 1 performs zero league additions and zero new Provider calls.

## Round 1

One bounded API/Web runtime change:

- intelligence-first public product;
- seven deterministic intelligence states;
- four independent risk dimensions;
- `MARKET_STABLE`/zero alerts as valid output;
- V4 diagnostic-only product role;
- divergence guard across API/read-model/Web/browser;
- market facts independent from V4 pick/no-pick state;
- public shell: Market Overview / Match Intelligence / Data & Operations Summary;
- existing 13 whitelist unchanged;
- current Scheduler/Provider policy preserved.

Delivery:

```text
ONE_RUNTIME_PR = true
ONE_FINAL_EXACT_HEAD_FULL_RC = true
ONE_MERGE = true
ONE_DEPLOYMENT = true
```

## Later rounds

Round 2 is blocked until Round 1 PASS and explicit owner authorization. Its future candidate universe is 17, not 11.

Round 3 remains blocked and must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

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
