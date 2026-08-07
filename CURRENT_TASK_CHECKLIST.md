# W2 Current Task Checklist

This is the complete current task order for W2. It is maintained directly on branch `context/current`; context updates do not use PR or CI. Runtime changes continue to use the guarded PR / Release Candidate / deployment process.

## Program status

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
OWNER_DECISION = APPROVED
ACTIVE_TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
NEXT_CODE_TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Execution authority:

```text
ROUND_1_CODEX_EXECUTION.md
```

Acceptance authority:

```text
ROUND_1_ACCEPTANCE_CRITERIA.md
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
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Do not reopen, retune, or build execution products around the failed hypothesis.

---

## MI-R1 — Product semantics and status reframe

```text
STATUS = NEXT_AUTHORIZED
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
CHANGE_CLASS = RUNTIME_API_AND_WEB
ONE_PR = true
ONE_RELEASE_CANDIDATE = true
ONE_MERGE = true
ONE_DEPLOYMENT = true
```

### R1.0 League baseline correction — hard boundary

The current active whitelist is **13**, not 11.

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

The European `5 + 6` grouping is a future market-role cohort, **not a replacement whitelist**.

Of the six Extended Radar names, `Eredivisie` and `Primeira Liga` are already in the 13 baseline. Only four are net-new:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union after owner-authorized Round 2 planning:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Round 1 must leave all 13 unchanged and must not register/enable/call/schedule the four new candidates.

### R1.1 Source and scope

- latest trusted `origin/main` in one clean worktree;
- task authority from `origin/context/current`;
- one bounded runtime branch and one PR;
- preserve Scheduler, Provider policy, current 13 whitelist, V4 calculations and historical settlement/replay;
- no new Provider calls;
- no Round 2/3 implementation.

### R1.2 Product identity

Public product identity:

```text
W2 Football Intelligence
W2 Football Market Intelligence & Model Diagnostics
```

Top-level product questions become:

```text
what is happening in the market?
is the data fresh and complete?
is the model behaving reliably?
what needs attention?
```

### R1.3 Intelligence states

Each public fixture/read-model card exposes exactly one:

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

Preserve secondary deterministic reason codes.

Do not invent Round 3 alert thresholds in Round 1.

### R1.4 Four risk dimensions

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

- `NOT_READY/BLOCKED` is not high betting risk;
- identity/xG/quote/readiness problems -> data/model readiness;
- Provider/Scheduler/schema/runtime -> collection;
- actual lineup/injury/event facts -> event;
- model calibration/simulation/feature staleness/divergence -> model;
- do not collapse data + collection into one generic risk;
- no dimension implies a recommendation.

### R1.5 Public authority switch

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Do not delete V4 or settlement/history.

Public card state, visibility, market facts, priority, counters and wording must no longer be controlled by V4 recommendation outcome alone.

### R1.6 Permanent divergence guard

Model-market divergence may produce diagnostic disagreement/model-review language only.

It may not produce or rank:

```text
value opportunity
positive edge
market mispricing
recommended side
high-confidence pick
价值机会
正 EV 机会
推荐方向
值得介入
```

Remove the public chain where divergence status/magnitude/direction_allowed determines recommendation readiness.

### R1.7 Market fact independence

Real current/last-known AH/OU facts must not disappear merely because V4 is `NOT_READY`, `NO_EDGE`, has no selected candidate or no pick.

Never promote stale/reference-only quote evidence to current/executable.

### R1.8 MARKET_STABLE

```text
MARKET_STABLE = VALID_SUCCESS_RESULT
ZERO_MATERIAL_ALERTS = VALID_SUCCESS_RESULT
```

Stable fixtures render non-empty. Do not lower thresholds to manufacture alerts.

A truly fixture-empty day remains a real empty-day state; do not fabricate stable fixtures.

### R1.9 Public page structure

Minimum public shell:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

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

Do not use analysis picks, formal recommendations, lock eligible, NO_EDGE, opportunity or positive EV as primary Market Overview KPIs.

### R1.10 Tests and acceptance

All requirements in `ROUND_1_ACCEPTANCE_CRITERIA.md` are mandatory.

At minimum prove:

1. active whitelist remains exact 13 with identity diff empty;
2. `MODEL_MARKET_DISAGREEMENT` never produces recommendation/opportunity language;
3. `NOT_READY/BLOCKED` maps to data/model/collection semantics, not high-risk match;
4. `MARKET_STABLE` renders a valid non-empty state;
5. four risk dimensions remain independent;
6. market facts remain visible independently of V4 pick state;
7. current real cards still render;
8. empty-day behavior remains explicit and nonblank;
9. API/Web release SHA sync remains correct;
10. Candidate/Formal/Lock/Production remain OFF;
11. Provider/Scheduler policy and call counts remain unchanged;
12. browser console errors = 0.

### R1.11 Delivery

- focused local tests during implementation;
- one PR Fast;
- one final exact-head Full Release Candidate on the final PR head;
- merge once using merge commit only;
- deploy verified immutable API/Web images once;
- public browser acceptance once;
- stop after Round 1 acceptance.

Round 1 completion state:

```text
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
ACTIVE_WHITELIST = 13_UNCHANGED
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
MARKET_RADAR_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
MODEL_LAB_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
```

---

## MI-R2 — Provider capability audit

```text
STATUS = BLOCKED_UNTIL_MI_R1_ACCEPTED_AND_OWNER_AUTHORIZED
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
MODE = READ_ONLY_CONTROLLED
DURATION = 14_DAYS
TARGET_CANDIDATE_UNION = 17
```

Round 2 target is the **union of the existing 13 whitelist competitions and 4 net-new European first-division candidates**, not a replacement 11-league whitelist.

The `5 + 6` European cohort remains a product-analysis lens inside the wider 17-candidate universe.

No competition is promoted merely by membership in the target pool.

Round 2 must separately audit live API-Football coverage, freshness, identity, AH/OU completeness, quote timestamps, Provider errors, lineup availability, schema drift, overround/movement distribution, bookmaker agreement and call cost.

Do not begin Round 2 automatically.

---

## MI-R3 — Market Radar and Model Lab

```text
STATUS = BLOCKED_UNTIL_MI_R2_CAPABILITY_DECISION
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Round 3 freezes exact market alert thresholds only after Round 2 live distributions exist.

No opportunity score.

---

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
