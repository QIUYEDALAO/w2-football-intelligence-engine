# W2 Market Intelligence — AI Handoff

Current authority is `context/current`.

## Current decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Phase 0.5 is closed with `NO_EDGE`; H is permanently closed. Current work is product repositioning, not another betting-edge experiment.

Permanent evidence guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

V4 product role:

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## League baseline correction

Current active whitelist baseline:

```text
COUNT = 13
ROUND_1_CHANGE = FORBIDDEN
```

The 13 identities are:

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

The European `5 + 6` grouping is not a replacement whitelist. Only four members are net-new relative to the current 13:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union:

```text
13 + 4 = 17
```

Do not add/audit/call/schedule these four during Round 1.

## Round 1 execution

Read:

```text
ROUND_1_CODEX_EXECUTION.md
ROUND_1_ACCEPTANCE_CRITERIA.md
```

Implement one bounded API/Web semantic refactor only. Required public states:

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

Preserve current 13 whitelist, current Provider/Scheduler policy and historical V4/settlement evidence.

## Delivery

One clean worktree, one runtime PR, one final exact-head Full Release Candidate, one merge and one deployment; stop after public acceptance.

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
