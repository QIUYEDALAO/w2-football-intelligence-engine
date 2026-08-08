# W2 Dashboard / Intelligence Workspace — P0 Product Specification

```text
AUTHORITY = W2_DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC_V1
STATUS = P0_COMPLETE_PENDING_OWNER_REVIEW_A
OWNER_DATE = 2026-08-09
REPOSITORY = QIUYEDALAO/w2-football-intelligence-engine
RUNTIME_MAIN_BASELINE = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
P0_CONTEXT_BASELINE = 35ff46000fcfdfb48d103585f5555efd7aa1bbae
FINAL_EXECUTION_MASTER = W2_FINAL_EXECUTION_MASTER_PLAN.md
DASHBOARD_DETAIL_MASTER = DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md
CURRENT_GATE = OWNER_REVIEW_A
P1 = NOT_STARTED
ROUND_4 = NOT_STARTED
```

## 1. Authority and scope

This document is the binding P0 product/page contract for the final W2
Intelligence Workspace. If this specification is ambiguous, the two master
plans named above control. Historical plans do not create work authorization.

W2 is **Football Market Intelligence + Model Diagnostics**.

P0 is documentation-only. It changes no product code, UI, database business
data, Provider integration, Scheduler, cadence, quota, whitelist, model,
threshold, runtime mode, or deployment.

```text
PRODUCT = FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
FORMAL_RECOMMENDATION = OFF
```

## 2. Permanent product semantics

The product keeps these four layers visibly separate:

| Layer | Meaning | Public authority |
|---|---|---|
| `MARKET FACT` | Persisted, source-bound market observation or factual line/price state | Fact only; never a pick |
| `W2 ANALYSIS` | Current model/research interpretation with readiness, evidence and limitations | Diagnostic reference only |
| `VALIDATION` | Post-match measurement of probability and directional quality | Evidence, not prospective authority |
| `FORMAL RECOMMENDATION` | Product action authority | `OFF` with reason |

Binding rules:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
ATTENTION != RECOMMENDATION
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```

Allowed wording is factual or diagnostic: model direction, model/market
disagreement, AH/OU line or quote change, readiness, risk, and validation
result. Forbidden wording includes value, edge, profit opportunity,
betting-worthiness, guaranteed outcome, bookmaker intent, money flow, real
handle/volume, or equivalent claims.

The frozen Phase 0.5 result remains visible and is not reinterpreted:

```text
FINAL_VERDICT = NO_EDGE
HISTORICAL_INCREMENTAL_EDGE = NOT_PROVEN
V_CONTINUATION_GATE = FAIL
H_RESULT_ACCESS = PERMANENTLY_CLOSED
PHASE_0_5_REEXECUTION = FORBIDDEN
```

## 3. Runtime competition boundary

The runtime whitelist is exactly these 13 competitions, in this authority
order:

1. `premier_league`
2. `la_liga`
3. `bundesliga`
4. `serie_a`
5. `ligue_1`
6. `eredivisie`
7. `primeira_liga`
8. `brasileirao_serie_a`
9. `argentina_primera`
10. `allsvenskan`
11. `eliteserien`
12. `mls`
13. `chinese_super_league`

Audit-only competitions remain non-runtime: `belgian_pro_league`,
`turkish_super_lig`, `greek_super_league`, and `scottish_premiership`.
Dashboard work may neither add them nor change the active 13.

## 4. Intelligence state and independent risks

The seven-state Attention precedence is frozen:

1. `COLLECTION_INCIDENT`
2. `DATA_INCOMPLETE`
3. `MODEL_DIAGNOSTIC_WARNING`
4. `MARKET_ANOMALY`
5. `MODEL_MARKET_DISAGREEMENT`
6. `MARKET_MOVEMENT`
7. `MARKET_STABLE`

The four risks are independent dimensions, not a replacement ranking:

- `EVENT_RISK`
- `DATA_RISK`
- `MODEL_RISK`
- `COLLECTION_RISK`

Attention sorts by frozen precedence, then kickoff, then fixture identity. It
uses real evidence/reason codes and never becomes an opportunity score or
recommendation list.

## 5. Final information architecture

The final public product is one workspace, not parallel legacy and new
Dashboards. Major surfaces are:

1. Global header and workspace navigation
2. Attention Feed
3. Today Matches / Match Board
4. Selected Match Inspector
5. Market Radar
6. Model Lab
7. Validation
8. League Performance
9. Forward Validation Records and history/replay
10. External Intelligence
11. Data & Operations

### 5.1 Global header and navigation

Required header facts:

- `W2 INTELLIGENCE`
- `13 LEAGUES`
- `SHADOW_ONLY`
- Candidate, Formal, Lock, and Production all `OFF`
- supported data-update/system-health context

Navigation must reach all major surfaces above. The header is compact and must
not become a wall of KPI cards.

### 5.2 Attention Feed

Required fields:

- intelligence state
- fixture identity and kickoff context
- evidence/reason code
- affected domain
- factual summary
- readiness/risk context
- next evaluation when available

It may surface collection incidents, expected-data gaps, model warnings,
market anomalies, disagreement, real movement, or stable state. It must not
rank bets, picks, value, edge, or profit potential.

### 5.3 Today Matches / Match Board

The board is a fast scan of the real current match population. Required row
fields are:

- time
- league
- matchup
- W2 state
- market main line
- data status
- next evaluation

The market main line is a fact such as `AH -0.25` or `OU 2.5`. A market fact
must not show Home/Under/Over as though the market selected a side. Scoreline
Top 3 does not belong in the primary board row.

### 5.4 Selected Match Inspector

Required structure and fields:

```text
MATCH IDENTITY
W2 ANALYSIS
MODEL VIEW
MARKET VIEW
MODEL / MARKET RELATION
FORMAL RECOMMENDATION = OFF + reason
DATA READINESS / RISK / NEXT EVALUATION
```

The inspector must visibly preserve `ANALYSIS_REFERENCE`, `NOT_PROVEN`, and
`FORMAL_OFF`. A model lean may be shown as analysis; the panel must not look
like a betting ticket.

### 5.5 Scoreline Top 3

Reuse the existing seeded 10,000-simulation capability. Required fields:

- sample count, consistently 10,000 for the existing projection
- top three scorelines
- unconditional probability for each scoreline
- model/readiness context

Placement is Model Lab and/or Match Inspector. Labels are exactly:

```text
MODEL SCORELINE REFERENCE
NOT_PROVEN
```

No second scoreline engine is authorized.

### 5.6 Market Radar

Required fields when evidence exists:

- AH and OU market identity
- bookmaker count
- canonical/main selected line under current W2 construction semantics
- two-sided prices
- snapshot count
- observation count
- domain freshness
- discrete persisted timeline

Timeline truth contract:

```text
0 snapshots = NO_TIMELINE_EVIDENCE
1 snapshot = ONE_OBSERVATION_NOT_A_TREND
2+ snapshots = DISCRETE_REAL_PATH_MAY_BE_SHOWN
```

Every point is a real persisted observation. Interpolation, copied/synthetic
points, fake trends, money-flow inference, bookmaker-intent inference, and
handle/volume claims are forbidden.

### 5.7 Model Lab

The comparison has three clearly labeled parties:

- `W2 MODEL`
- `MARKET`
- `API-FOOTBALL PREDICTION` as `EXTERNAL_MODEL_BENCHMARK`

API-Football Prediction is never product authority. Required readiness/status
semantics include:

- `MODEL_NOT_READY`
- `MARKET_NOT_READY`
- `INSUFFICIENT_BOOKMAKER_DEPTH`
- `MODEL_OUTSIDE_MARKET_RANGE`
- `COMPARABLE_WITHIN_MARKET_RANGE`
- frozen `NO_EDGE` and `NOT_PROVEN` Phase 0.5 context

An outside-range result is a diagnostic warning, not value or opportunity.

### 5.8 Validation — primary probability hierarchy

Probability quality is the primary validation surface, using only existing
validation cohorts/read data:

- Brier Score
- Log Loss
- Calibration Error / ECE
- Reliability Diagram / bins
- W2 versus market probability baseline where the cohort supports it
- cohort identity, effective N, and readiness/statistical status

This surface does not authorize retraining, new factors, threshold changes, or
a new research round.

### 5.9 Directional Outcome — secondary hierarchy

Directional outcome remains secondary. Required fields:

- Correct
- Wrong
- `PUSH`
- `VOID`
- W2 Direction Accuracy
- effective N
- `MARKET_DIRECTION_BENCHMARK = NOT_DEFINED`

Do not promote an absolute hit rate as a green primary KPI. Do not invent
`MARKET_DIRECTION_BENCHMARK_V1`.

Settlement language is binding: `PUSH` is neutral settlement/走水; `VOID` is
invalid settlement; cohort exclusion is neither PUSH nor VOID.

### 5.10 League Performance

Required columns:

- League
- Validation N
- Decisive N
- Correct
- Wrong
- PUSH
- W2 Direction Accuracy
- Brier
- Calibration
- Statistical Status

Statuses include `AVAILABLE`, `SAMPLE_BUILDING`, and `INSUFFICIENT`. Leagues
must not be colored by absolute direction hit rate while the market direction
benchmark is `NOT_DEFINED`.

### 5.11 Forward Validation Records and history/replay

Reuse the existing ledger/scoring/replay/date-navigation foundations. The
surface must answer, from source-bound evidence:

- what was known at the selected time
- what W2 judged and why
- readiness/reason summary
- what happened afterward
- outcome/settlement and tracking status
- card/evidence identity checks where available

The public label may be `Forward Validation Records` / 前向验证记录. No second
replay system is authorized.

### 5.12 External Intelligence

Reserved sources are Weather, News, Sentiment, and Advanced xG. Each is:

```text
STATUS = NOT_CONNECTED
EXECUTION_AUTHORIZED = NO
```

Their placeholders state source absence without fabricated content.
`OPTIONAL_EXTERNAL_SOURCE_NOT_CONNECTED != MATCH_DATA_INCOMPLETE`; optional
absence must not alter the seven-state logic.

### 5.13 Data & Operations

Required fields, where supported by the final read model:

- per-domain freshness/status
- data readiness and missing/stale reason
- next evaluation
- collection/system health
- Provider budget status without exposing secrets
- current runtime/whitelist/mode truth

Opening or refreshing the Dashboard must not create Provider calls.

## 6. Status vocabulary

The following values are not interchangeable:

| Value | Meaning | Must not mean |
|---|---|---|
| `NOT_DEFINED` | A benchmark/contract has not been defined or authorized | zero, failure, or hidden estimate |
| `NOT_PROVEN` | Available evidence does not prove the stated model/research claim | recommendation, confidence guarantee, or opportunity |
| `NOT_CONNECTED` | An optional external source has no active integration | match data incomplete or Provider incident |
| `SAMPLE_BUILDING` | Valid cohort exists but statistical maturity is still accumulating | positive performance claim |
| `INSUFFICIENT` | Evidence is inadequate for the requested result | synthetic fill or default estimate |

## 7. Data, freshness, and evidence contract

P1 will bind every field to a concrete source, but it may not change these P0
authorities:

| Domain | Confirmed Provider refresh authority |
|---|---:|
| fixtures | ~15s |
| fixtures/events | ~15s |
| fixtures/statistics | ~1m |
| fixtures/players | ~1m |
| fixtures/lineups | ~15m |
| odds pre-match | ~3h |
| odds/live | ~5s; forbidden as W2 price benchmark |
| injuries | ~4h |
| predictions | ~1h |
| standings | ~1h |
| teams/statistics | ~12h / ~2 times daily |

Freshness is domain-specific; one universal stale threshold is forbidden.
These values describe the confirmed Provider contract and do not authorize W2
Scheduler/cadence changes.

`W2_MARKET_MEMORY` is required core infrastructure: W2 persists real market
observations because Provider retention is not a long-term W2 odds archive.
Chart density never authorizes added collection.

Current price authority is:

```text
CANONICAL_CLOSE = NOT_OBTAINABLE_FROM_CURRENT_PROVIDER
CURRENT_VALID_CONCEPT = LAST_AVAILABLE_PREMATCH_SNAPSHOT
ANONYMOUS_LIVE_ODDS_AS_BENCHMARK = FORBIDDEN
PUBLIC_CLV_REACHABILITY = 0
PUBLIC_ROI_REACHABILITY = 0
```

Lineup evidence is limited to:

```text
LINEUP_STRUCTURE = OBSERVED
WHITELIST_COVERAGE_VERIFIED = 1/13
COVERAGE_VERIFIED_ON = chinese_super_league
OTHER_12 = UNVERIFIED
FIRST_APPEARANCE_TIME = UNMEASURED
```

No special Provider probe is authorized to improve lineup coverage or timing
distributions.

## 8. Visual authority and acceptance approach

The Owner-approved 1536×1024 Intelligence Workspace reference is the golden
desktop authority. The implementation must preserve its dense desktop
workspace hierarchy, not improvise a different product or restore the legacy
Boss Dashboard.

Binding hierarchy at the golden viewport:

1. compact global identity/runtime header and primary navigation
2. Attention and Match Board as the fast-scan entry layer
3. selected-match Inspector as the central analytical focus
4. Market Radar and Model Lab as supporting diagnostic depth
5. Validation, League Performance, Records, External Intelligence, and
   Data/Ops as clearly reachable evidence/operations surfaces

Before P3 is accepted, the approved reference must be repository-testable as a
committed asset or equivalent deterministic visual contract. P5 must produce a
1536×1024 golden screenshot and prove:

- every required panel is present
- no extra public legacy Dashboard exists
- panel order and hierarchy are stable
- no overlap, clipping, or unintended horizontal overflow exists
- critical semantic labels/statuses pass
- supported secondary viewports preserve responsive integrity

Visual similarity never permits semantic or evidence violations.

## 9. Historical task disposition

Historical work is resolved as follows and is not an active backlog:

| Historical capability/task | Final disposition |
|---|---|
| R0 reconciliation | `CANCELLED_NOT_A_DEVELOPMENT_STAGE` |
| Step 4 / Post4 | `SUPERSEDED_AS_STANDALONE_WORKSTREAM` |
| old Boss L1 homepage/ranking | `SUPERSEDED_DO_NOT_IMPLEMENT` |
| old L2 diagnostics drawer | capability absorbed into Model Lab/Data & Ops; old UI not rebuilt |
| Decision Contract and Data Readiness | reuse existing foundations in P1/P2; no redo |
| DayView/degradation/diagnostics | reuse source capability; not the final public contract |
| scoreline engine | reuse existing projection; no second engine |
| probability scoring | reuse Brier/LogLoss/reliability/calibration assets |
| replay/date navigation | reuse and expose through P4/P5 |
| forward validation ledger | reuse as Forward Validation Records |
| Provider/Scheduler/quota safety | background runtime only; not a Dashboard task |
| old acceptance/visual tasks | useful intent absorbed into P5 under current semantics |
| archived P0–P8/packages | historical evidence only; existence is not authorization |

Legacy deletion is forbidden before P5.5 and Owner approval after P5.

## 10. Execution governance

| Phase | Authorized result | Gate |
|---|---|---|
| P0 | this binding product specification and context closure | stop at `OWNER_REVIEW_A` |
| P1 | capability/data/freshness contracts | may proceed to P2 only after explicit Owner Review A approval/authorization |
| P2 | one unified Dashboard read model/API contract | stop at `OWNER_REVIEW_B` |
| P3 | one public Intelligence Workspace UI | may proceed to P4 under the accepted plan |
| P4 | Validation, League Performance, Records, history/replay | may proceed to P5 |
| P5 | full-chain truth and visual acceptance; cleanup classification only | stop at `OWNER_REVIEW_C` |
| P5.5 | evidence-based legacy cleanup | only after P5 PASS and Owner Review C approval |
| P6 | long-term blueprint | `NOT_AUTHORIZED` |

Global stop lines:

```text
ROUND_4 = NOT_STARTED
PHASE_0_5_REEXECUTION = FORBIDDEN
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
WHITELIST_CHANGE = FORBIDDEN
AUDIT_ONLY_PROMOTION = FORBIDDEN
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
PROVIDER_CUTOVER = NOT_AUTHORIZED
COLLECTION_CADENCE_EXPANSION_FOR_UI = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_V1 = NOT_AUTHORIZED
```

Post-R3 `PATH_A_NATURAL_EVIDENCE_ACCUMULATION` remains parallel background
runtime under the already-authorized `SHADOW_ONLY` policy. Dashboard phases do
not change or accelerate it.

## 11. Final product acceptance contract

P5 must exercise at least: no matches; 0, 1, and 2+ snapshots; lineup too
early; lineup expected but absent; injuries stale; market stale; Provider
incident; model not ready; validation pending; `SAMPLE_BUILDING`; External
Intelligence `NOT_CONNECTED`; and complete/incomplete historical replay.

Binding truth assertions:

```text
0_SNAPSHOT != TREND
1_SNAPSHOT != TREND
NO_INTERPOLATION
NO_SYNTHETIC_SIGNALS
NO_FAKE_BENCHMARK
NO_PUBLIC_CLV
NO_PUBLIC_ROI
NO_ANONYMOUS_LIVE_PRICE_BENCHMARK
OPTIONAL_EXTERNAL_NOT_CONNECTED != DATA_INCOMPLETE
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
```

Final cleanup closes only when functional acceptance and repository hygiene
both pass.

## 12. P0 completion record

P0 changed only this specification, `CURRENT_STATE.yaml`, and
`NEXT_ACTION.md` on the context branch.

```text
P0 = COMPLETE
PRODUCT_OR_BUSINESS_CODE_CHANGED = false
UI_IMPLEMENTED = false
PROVIDER_CALLS = 0
DATABASE_BUSINESS_WRITES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
WHITELIST_CHANGED = false
MODEL_CHANGED = false
ROUND_4 = NOT_STARTED
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = THIS_SPEC_AND_UPDATED_CONTEXT_AUTHORITY
UNRESOLVED_HYGIENE_ITEMS = 0
NEXT = OWNER_REVIEW_A
P1 = NOT_STARTED
```

No further implementation is authorized until the Owner reviews this contract
and explicitly authorizes the next phase.
