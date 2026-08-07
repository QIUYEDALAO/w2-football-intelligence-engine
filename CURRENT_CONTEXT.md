# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on branch `context/current` without a pull request, CI, Release Candidate, image build or deployment.

## Read order

1. `CURRENT_STATE.yaml`
2. `CURRENT_PRODUCT_DESIGN.md`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `ROUND_1_CODEX_EXECUTION.md`
6. `ROUND_1_ACCEPTANCE_CRITERIA.md`

## Owner product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

W2 is being repositioned from a recommendation-first public shell into a football market-intelligence and model-diagnostics platform while preserving the existing data, identity, odds, model, Scheduler, replay and Dashboard foundations.

## Evidence boundary

Phase 0.5 is complete and closed:

```text
FINAL_VERDICT = NO_EDGE
H_RESULT_ACCESS = PERMANENTLY_CLOSED
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

Do not reopen H or retune the failed model family with V/H outcomes.

## Public product states

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Round 1 precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

`NOT_READY/BLOCKED` is not a betting-risk conclusion.

## League baseline correction

The current active whitelist is **13 competitions** and Round 1 must preserve it exactly.

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

The European `5 + 6` grouping is not a replacement whitelist.

Core Benchmark 5 are already within the baseline 13:

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar cohort 6 contains two existing baseline leagues plus four net-new future candidates:

```text
Eredivisie              EXISTING
Primeira Liga           EXISTING
Belgian Pro League      NET_NEW
Turkish Super Lig       NET_NEW
Greek Super League      NET_NEW
Scottish Premiership    NET_NEW
```

Future candidate union after explicit Round 2 authorization:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Round 1 performs **zero** league registration/enablement/audit/scheduling/provider calls.

## Product authority

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

V4 and historical settlement/replay evidence remain preserved. Public intelligence state, market-fact visibility, ranking, counters and wording must not be controlled by V4 recommendation outcome alone.

## Round 1

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
STATUS = AUTHORIZED_NEXT
ONE_RUNTIME_PR = true
ONE_FINAL_EXACT_HEAD_RC = true
ONE_MERGE = true
ONE_DEPLOYMENT = true
ACTIVE_WHITELIST = 13_UNCHANGED
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
```

Detailed execution authority: `ROUND_1_CODEX_EXECUTION.md`.

Binding acceptance authority: `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Later rounds

Round 2 is blocked until Round 1 acceptance and a new explicit owner authorization. Its future candidate universe is the 17-competition union, not an 11-competition replacement whitelist.

Round 3 is blocked until Round 2 capability decisions and must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Exact Market Radar formulas wait for Round 2 live distributions.

## Permanent hard boundary

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
