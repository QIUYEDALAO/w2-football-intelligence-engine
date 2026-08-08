# W2 Dashboard / Intelligence Workspace — Master Plan

```text
AUTHORITY = W2_DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN_V1
OWNER_DATE = 2026-08-09
REPOSITORY = QIUYEDALAO/w2-football-intelligence-engine
RUNTIME_MAIN_BASELINE = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
WORKSTREAM = DASHBOARD_INTELLIGENCE_WORKSPACE_FINAL_REFACTOR
ROUND_4 = NOT_STARTED
CURRENT_EXECUTION_AUTHORIZATION = P0_ONLY
```

## 1. Purpose and authority

This file is the master task list and product/development authority for the final W2 Dashboard / Intelligence Workspace refactor.

It does **not** authorize Round 4, model research, Provider expansion, Candidate, Formal, Lock, Production, or real-money use. The existing Post-R3 natural-evidence accumulation may continue under its already-authorized runtime policy, but Dashboard work must not alter that policy.

Execution order is binding:

```text
P0
↓
STOP — OWNER REVIEW A

P1
↓
P2
↓
STOP — OWNER REVIEW B

P3
↓
P4
↓
P5
↓
STOP — OWNER REVIEW C

P5.5
↓
REPOSITORY FULLY CLOSED
```

P6 is a long-term blueprint only and is not part of current development authorization.

## 2. Permanent product position

W2 is:

```text
Football Market Intelligence + Model Diagnostics
```

The public product must keep four layers distinct:

1. `MARKET FACT` — observed market facts.
2. `W2 ANALYSIS` — current W2 research/model view.
3. `VALIDATION` — post-match validation of those views.
4. `FORMAL RECOMMENDATION` — product authority.

The first three may exist. The fourth remains OFF.

```text
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Permanent semantics:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Forbidden public framing includes value/edge/profit opportunity, betting-worthiness, guaranteed outcome language, bookmaker intent, money flow, real handle/volume claims, or equivalent wording.

Allowed factual/diagnostic wording includes model direction, model/market disagreement, AH/OU line change, bookmaker quote change, readiness state, risk state, and validation result.

## 3. Frozen research context that must remain visible

Phase 0.5 is closed and must not be rerun or reinterpreted.

```text
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32%
V_CONTINUATION_GATE = FAIL
FINAL_VERDICT = NO_EDGE
HISTORICAL_INCREMENTAL_EDGE = NOT_PROVEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Model Lab must continue to surface `NO_EDGE` and `NOT_PROVEN` as frozen context.

## 4. Runtime competition authority

The runtime whitelist remains exact 13:

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

Audit-only and not runtime-whitelisted:

- `belgian_pro_league`
- `turkish_super_lig`
- `greek_super_league`
- `scottish_premiership`

Dashboard work must not change this boundary.

## 5. Current public UI reality to preserve as evidence

Current public chain:

```text
App
→ DashboardPage
→ IntelligenceConsole
```

Current public chain must not regress to the legacy Boss UI. Existing Round-3 IntelligenceConsole capabilities to retain are:

- Market Overview / Today context
- Attention Feed
- Match Intelligence
- Market Radar
- real market timeline
- Model Lab
- Phase 0.5 context
- four independent risks
- reason codes
- Data & Operations Summary

Legacy Boss components remain repository evidence until P5.5, but are not the target UI. Valuable business capabilities to extract from legacy code include:

- W2 Analysis / match research view
- Scoreline Top 3
- post-match validation
- directional outcome summary
- league performance
- Forward Validation Records

Target rule:

```text
DO_NOT_RESTORE_OLD_BOSS_UI
EXTRACT_USEFUL_BUSINESS_CAPABILITIES
+
ROUND_3_INTELLIGENCE_CAPABILITIES
→
ONE_NEW_INTELLIGENCE_WORKSPACE
```

## 6. Frozen intelligence state and risks

Seven-state precedence remains frozen:

1. `COLLECTION_INCIDENT`
2. `DATA_INCOMPLETE`
3. `MODEL_DIAGNOSTIC_WARNING`
4. `MARKET_ANOMALY`
5. `MODEL_MARKET_DISAGREEMENT`
6. `MARKET_MOVEMENT`
7. `MARKET_STABLE`

Independent risks remain:

- `EVENT_RISK`
- `DATA_RISK`
- `MODEL_RISK`
- `COLLECTION_RISK`

Attention Feed must continue to sort by the frozen precedence. `ATTENTION != RECOMMENDATION`.

## 7. Dashboard Data/Freshness authority

Do not invent or re-guess API-Football cadence. Use the already-confirmed data contract:

| Domain | Provider refresh authority |
|---|---:|
| fixtures | ~15s |
| fixtures/events | ~15s |
| fixtures/statistics | ~1m |
| fixtures/players | ~1m |
| fixtures/lineups | ~15m |
| odds pre-match | ~3h |
| odds/live | ~5s, but forbidden as W2 price benchmark |
| injuries | ~4h |
| predictions | ~1h |
| standings | ~1h |
| teams/statistics | ~12h / ~2 times daily |

Freshness must be domain-specific. Do not apply one universal stale threshold to every domain.

P1 must bind UI cadence labels to the data contract rather than duplicating ad-hoc cadence text in components.

## 8. Market Memory and price semantics

```text
W2_MARKET_MEMORY = REQUIRED_CORE_INFRASTRUCTURE
```

Provider retention is not a long-term W2 odds archive. Real observations must be persisted.

Market Radar timeline rules:

```text
0 snapshots → no timeline evidence
1 snapshot  → one observation, not a trend
2+ snapshots → discrete real path may be shown
```

Forbidden:

- interpolation
- copied/synthetic points
- fake trends
- money-flow inference
- bookmaker-intent inference
- handle/volume claims

Each timeline point must represent one real persisted market observation.

Canonical close is not available from the current Provider under the frozen confirmatory contract:

```text
CANONICAL_CLOSE = NOT_OBTAINABLE_FROM_CURRENT_PROVIDER
CURRENT_VALID_CONCEPT = LAST_AVAILABLE_PREMATCH_SNAPSHOT
```

`/odds/live` is anonymous and may not be used as a price benchmark or confirmatory source.

Public Dashboard:

```text
CLV = REMOVE / ZERO REACHABILITY
ROI = REMOVE / ZERO REACHABILITY
```

Restoration requires a future source satisfying the required price-source contract and is not part of this workstream.

## 9. Lineup evidence authority

Current hard evidence:

```text
LINEUP_STRUCTURE = OBSERVED
COVERAGE_VERIFIED_ON = CHINESE_SUPER_LEAGUE_ONLY
WHITELIST_COVERAGE_VERIFIED = 1/13
OTHER_12 = UNVERIFIED
FIRST_APPEARANCE_TIME = UNMEASURED
```

Do not claim whitelist-wide lineup coverage.

Future normal Scheduler operation may passively record:

- `lineup_first_seen_at`
- `kickoff_utc`
- `lead_minutes_to_kickoff`
- `lineup_complete`
- `formation_available`
- `starting_xi_count`
- `substitute_count`

This workstream does not authorize special Provider probing to fill those distributions.

## 10. External Intelligence boundary

Final product reserves space for:

- Weather
- News
- Sentiment
- Advanced xG

Current state for all four:

```text
NOT_CONNECTED
EXECUTION_AUTHORIZED = NO
```

Critical semantic rule:

```text
OPTIONAL_EXTERNAL_SOURCE_NOT_CONNECTED
!=
MATCH_DATA_INCOMPLETE
```

Missing optional external sources must not turn a match into `DATA_INCOMPLETE` or otherwise distort the seven-state logic.

## 11. Final Intelligence Workspace functional specification

### 11.1 Global header

Must surface compactly:

- `W2 INTELLIGENCE`
- `13 LEAGUES`
- `SHADOW_ONLY`
- Candidate OFF
- Formal OFF
- Lock OFF
- Production OFF
- data update / system health context as supported by the read model

Do not rebuild the header as a wall of KPI cards.

### 11.2 Navigation / major product surfaces

The new single workspace must provide access to:

- Today / Match Board
- Attention Feed
- Match Intelligence / selected-match Inspector
- Market Radar
- Model Lab
- Validation
- League Performance
- External Intelligence
- Data & Operations

Navigation labels may be refined in P0/P3, but the capabilities and semantic boundaries may not be removed.

### 11.3 Today Matches / Match Board

Fast-scan fields only:

- time
- league
- matchup
- W2 state
- market main line
- data status
- next evaluation

Market main line is a fact and may show examples such as `AH -0.25` or `OU 2.5`.

Market itself must not display a selected side such as Home/Under/Over as if the market made a recommendation.

The board must support the real current match population rather than a hard-coded demo subset.

### 11.4 Attention Feed

Must use the frozen seven-state precedence and real evidence/reason codes.

It may summarize:

- collection incidents
- missing/late expected data
- model diagnostic warnings
- market anomalies
- model/market disagreement
- market movement
- stable market state

It must never become a recommendation ranking or hidden opportunity score.

### 11.5 Selected Match Inspector

Core structure:

```text
MATCH IDENTITY

W2 ANALYSIS

MODEL VIEW
MARKET VIEW
MODEL / MARKET RELATION
FORMAL RECOMMENDATION = OFF + reason

DATA READINESS / RISK / NEXT EVALUATION
```

Allowed example: `模型观点：主队方向` / model currently leans home.

Must visibly preserve:

```text
ANALYSIS_REFERENCE
NOT_PROVEN
FORMAL_OFF
```

Do not format this panel as a betting ticket.

### 11.6 Scoreline Top 3

Retain the existing business capability:

- 10,000 simulations
- Top 3 scorelines
- unconditional probability
- consistent sample count

Placement:

```text
Model Lab / Match Inspector
```

Not in the primary Match Board row.

Must be labeled:

```text
MODEL SCORELINE REFERENCE
NOT_PROVEN
```

### 11.7 Market Radar

Must provide, when evidence exists:

- AH
- OU
- bookmaker count
- canonical/main selected line under current W2 market-construction semantics
- prices
- snapshot count
- observation count
- freshness
- real discrete market timeline

The timeline must obey the zero/one/two-plus rules in Section 8.

### 11.8 Model Lab

Keep Round-3 diagnostics and upgrade comparison to three parties:

```text
W2 MODEL
MARKET
API-FOOTBALL PREDICTION
```

API-Football Prediction role:

```text
EXTERNAL_MODEL_BENCHMARK
```

It never becomes product authority.

Readiness/status semantics to retain:

- `MODEL_NOT_READY`
- `MARKET_NOT_READY`
- `MODEL_OUTSIDE_MARKET_RANGE`
- `COMPARABLE_WITHIN_MARKET_RANGE`

Frozen Phase 0.5 context must remain visible:

- `NO_EDGE`
- `NOT_PROVEN`

### 11.9 Probability Validation — primary visual hierarchy

Primary validation must be probability quality, comparing W2 with a market probability baseline where the existing cohort supports it:

- Brier Score
- Log Loss
- Calibration Error
- Reliability Diagram / bins
- W2 vs market probability baseline

These metrics must be computed only from existing validation cohorts/read data. No retraining, new feature, threshold change, or new research round is authorized.

### 11.10 Directional Outcome — secondary visual hierarchy

Directional metrics are retained but deliberately downgraded:

- Forward Validation Records
- Correct
- Wrong
- PUSH
- VOID
- W2 Direction Accuracy
- effective N
- Market Direction Benchmark = `NOT_DEFINED`

Do not present an absolute hit rate such as 63.9% as a green primary KPI.

No `MARKET_DIRECTION_BENCHMARK_V1` may be invented in this workstream. That requires separate preregistered research in the future.

### 11.11 League Performance

Required columns/capabilities:

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

Statuses must include at least:

- `AVAILABLE`
- `SAMPLE_BUILDING`
- `INSUFFICIENT`

Do not color leagues by absolute direction hit rate. A future benchmark-relative color scheme is only allowed if a separately authorized market direction benchmark exists.

### 11.12 Settlement language

UI may rename `Forward Validation Ledger` to `Forward Validation Records` / 前向验证记录.

Settlement semantics must remain correct:

- `PUSH` = 走水 / neutral settlement
- `VOID` = invalid settlement
- cohort exclusion is not the same thing as VOID

Do not label PUSH as a draw line.

### 11.13 Data & Operations

Must preserve operational truth for the current read model, including supported domain freshness/status and system health where available.

It must not create Provider calls merely because the Dashboard is opened.

### 11.14 Visual authority

The Owner-approved Dashboard reference is the current 1536×1024 Intelligence Workspace design supplied with this workstream.

Before P3 implementation is accepted, P0/P3 must make the reference repository-testable (committed asset or equivalent deterministic visual contract). P3 must preserve its information hierarchy and dense desktop workspace composition rather than improvising a different UI.

Minimum visual acceptance required by P5:

- 1536×1024 golden viewport screenshot artifact
- no missing required panel
- no extra public legacy Dashboard
- no overlap, clipping, or unintended horizontal overflow
- stable panel order and hierarchy
- semantic text/status contract PASS
- responsive integrity on supported non-golden viewports

Visual acceptance does not permit semantic violations.

## 12. P0 — Product semantics and page specification freeze

### Goal

Create the binding product/page specification before any product code is changed.

### Scope

Docs only. No product code, Provider calls, scheduler changes, database business writes, model changes, or UI implementation.

### Required outputs

1. `DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md`
2. updates to `CURRENT_STATE.yaml`
3. updates to `NEXT_ACTION.md`
4. references from those files back to this master plan

### Product spec must freeze

- final product positioning
- final information architecture
- every panel's role and required fields
- Market Fact / W2 Analysis / Validation / Formal Recommendation boundaries
- seven-state and four-risk semantics
- exact 13 whitelist
- prohibited public wording/content
- External Intelligence placeholder semantics
- probability-validation priority
- direction-accuracy downgrade
- `MARKET_DIRECTION_BENCHMARK = NOT_DEFINED`
- Scoreline Top 3 `NOT_PROVEN` semantics
- API-Football cadence authority
- domain-specific freshness requirement
- Market Memory requirements
- canonical-close / last-available-prematch conclusion
- lineup evidence limitation
- visual authority and acceptance approach
- P0→P6 execution governance
- Owner gates and stop lines
- final acceptance criteria

### P0 acceptance

- docs are internally consistent
- no Dashboard requirement conflicts with frozen Round-3/Phase-0.5 semantics
- no hidden Round-4 authorization
- no runtime/code changes
- Repository Hygiene for context docs is clean

### Stop line

```text
P0 COMPLETE
→ STOP
→ OWNER REVIEW A
```

Do not start P1 automatically.

## 13. P1 — Capability / Data / Freshness Contract

### Goal

Define what the final Dashboard can truthfully show and the exact freshness/readiness contract for each domain.

### Required outputs

- Perfect Intelligence Capability Matrix
- Current W2 Gap Matrix
- Dashboard Data Contract
- Freshness Contract

### Required work

- bind every Dashboard field/panel to a real source/read model
- distinguish available, partial, unavailable, and not-connected capability
- use domain-specific freshness
- bind cadence to the confirmed API-Football data contract
- define Market Memory observation availability semantics
- define lineup availability semantics without overclaiming 13/13 coverage
- define External Intelligence as optional-not-connected
- define no-call-on-read behavior

### Forbidden

- new Provider calls for this task
- Weather/News/Sentiment/Advanced-xG connection
- whitelist change
- collection cadence expansion for chart density
- Round 4

P1 may continue directly into P2 after its own tests/checks; Owner Review is after P2.

## 14. P2 — Unified Dashboard Read Model / API Contract

### Goal

Create one new read model that merges useful legacy business capabilities with Round-3 Intelligence capabilities.

### Inputs to inspect/extract from

Legacy business surfaces/helpers:

- BossDecisionView
- RecommendationCard
- DashboardPerformance
- Forward Validation Ledger/Records helpers

Round-3 surfaces/helpers:

- IntelligenceConsole
- Market Radar
- Model Lab
- Attention
- seven-state logic
- four-risk logic
- evidence/reason codes

### Required result

```text
ONE_NEW_DASHBOARD_READ_MODEL
```

The new UI in P3 must consume this model rather than separately reusing two public Dashboard architectures.

### P2 may add read/aggregation outputs for existing validation cohorts

- Brier
- Log Loss
- Calibration Error
- Reliability bins
- market probability baseline metrics
- league-level validation summaries
- Forward Validation Records summary
- Scoreline Top 3 data needed by Inspector/Model Lab

### P2 contract requirements

- explicit schema
- explicit API payload
- deterministic sample payload
- contract tests
- zero/one/multi-snapshot representation
- readiness/reason-code representation
- `NOT_CONNECTED` representation for optional external sources
- `NOT_DEFINED` representation for market direction benchmark
- no CLV/ROI public fields
- no anonymous live-odds benchmark field

### Forbidden

- model retraining
- new model factors
- threshold changes
- Round 4
- Phase 0.5 rerun
- new market-direction benchmark
- Provider calls for UI/read-contract development

### Stop line

```text
P2 COMPLETE
→ STOP
→ OWNER REVIEW B
```

Owner Review B must inspect at minimum:

- schema
- API payload
- sample payload
- contract tests

No P3 UI implementation before approval.

## 15. P3 — Final Intelligence Workspace UI

### Goal

Implement the approved single public Dashboard using only the P2 unified read model.

### Required public workspace capabilities

- global W2/13-league/shadow/off-status header
- navigation to the major surfaces
- Attention Feed
- Today Matches / Match Board
- Selected Match Inspector
- W2 Analysis
- Model View
- Market View
- Model/Market Relation
- Formal Recommendation OFF reason
- Market Radar AH/OU real-observation timeline
- External Intelligence NOT_CONNECTED surface
- Model Lab three-way benchmark
- Scoreline Top 3 reference
- Data & Operations

### UI rules

- do not restore BossDecisionView as the product
- do not make both old and new Dashboards public
- do not turn market facts into picks
- do not turn Attention into recommendations
- do not promote direction hit rate as primary KPI
- do not show CLV or ROI
- do not invent unavailable external intelligence
- do not synthesize market timeline data
- do not generate Provider calls from public reads

### Visual implementation

Use the Owner-approved 1536×1024 reference as the golden desktop composition once repository-bound by the accepted contract. Preserve the panel hierarchy and dense information layout while consuming real data/readiness states.

P3 may continue into P4.

## 16. P4 — Validation + League Performance

### Goal

Complete post-match validation and league-performance surfaces using the P2 read model and existing validation cohort.

### Primary surface: Probability Validation

- Brier Score
- Log Loss
- Calibration Error
- Reliability Diagram
- W2 vs market probability baseline

### Secondary surface: Directional Outcome

- Correct
- Wrong
- PUSH
- VOID
- direction accuracy
- effective N
- Market Direction Benchmark = `NOT_DEFINED`

### League Performance

Implement the columns/statuses in Section 11.11.

### Public reachability constraints

```text
PUBLIC_ROI_REACHABILITY = 0
PUBLIC_CLV_REACHABILITY = 0
```

P4 may continue into P5.

## 17. P5 — Full-chain truth acceptance

### Goal

Prove that the new public workspace is truthful across important runtime/read-model states. Only scope-limited minimum fixes are allowed.

### Mandatory scenarios

- no matches
- 0 snapshot
- 1 snapshot
- 2+ snapshots
- lineup too early / not yet expected
- lineup expected but absent
- injuries stale
- market stale
- Provider incident
- model not ready
- validation pending
- `SAMPLE_BUILDING`
- External Intelligence `NOT_CONNECTED`

### Mandatory truth assertions

```text
0 snapshot != trend
1 snapshot != trend
NO_INTERPOLATION
NO_SYNTHETIC_SIGNALS
NO_FAKE_BENCHMARK
NO_CLV
NO_ROI
NO_ANONYMOUS_LIVE_PRICE_BENCHMARK
OPTIONAL_EXTERNAL_NOT_CONNECTED != DATA_INCOMPLETE
```

### Public-authority assertion

Only the new Intelligence Workspace may be public-reachable.

```text
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
```

### Visual acceptance

- deterministic golden screenshot at 1536×1024
- required panels all present
- panel hierarchy matches approved contract/reference
- no clipping/overlap/unintended overflow
- critical status/semantic labels verified
- responsive-integrity checks on supported secondary viewports

### P5 repository output

Produce a classification list only:

- `KEEP`
- `DELETE`
- `DEPRECATE`
- `RETAIN_FOR_EVIDENCE`

Do **not** delete legacy code in P5.

### Stop line

```text
P5 COMPLETE
→ STOP
→ OWNER REVIEW C
```

## 18. P5.5 — Controlled Legacy Cleanup

### Entry condition

```text
P5 = PASS
AND
OWNER_REVIEW_C = APPROVED
```

### Goal

Remove/deprecate only code proven unreachable or safely migrated.

### Before any deletion, prove actual reachability through

- route
- import
- entrypoint
- runtime
- build graph
- tests
- config
- workflow

Do not delete because something merely looks unused.

### Legacy candidates to classify individually

- BossDecisionView
- RecommendationCard
- RecommendationBoard
- legacy styles
- legacy feature flags
- legacy public copy
- legacy UI tests

If a helper is still needed by the new read model/UI, extract/migrate it first, then remove only the obsolete UI surface.

### Final gates

- Repository Hygiene
- TypeScript build
- unit tests
- contract tests
- E2E
- public-authority reachability
- reference search

Final closure condition:

```text
TASK_FULLY_CLOSED
=
FUNCTIONAL_ACCEPTANCE_PASS
+
REPOSITORY_HYGIENE_PASS
```

## 19. P6 — Long-term blueprint, not current authorization

Blueprint only:

- Market Memory accumulation
- lineup first-seen distribution
- league lineup coverage
- Provider forward-availability distribution
- Team Form history
- Injury history
- Weather provider
- News provider
- Sentiment provider
- Advanced xG provider
- sharp canonical-close provider
- `MARKET_DIRECTION_BENCHMARK_V1`
- Live Intelligence
- user notes / bookmarks

```text
P6_EXECUTION_AUTHORIZED = NO
```

Capability Matrix entries are future-product blueprint, not an implementation backlog automatically authorized for development.

## 20. Global stop lines for P0–P5.5

Unless a later explicit Owner decision changes them:

```text
ROUND_4 = NOT_STARTED
PHASE_0_5_REEXECUTION = FORBIDDEN
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
WHITELIST_CHANGE = FORBIDDEN
AUDIT_ONLY_PROMOTION = FORBIDDEN
NEW_PROVIDER_PURCHASE = NOT_AUTHORIZED
PROVIDER_CUTOVER = NOT_AUTHORIZED
COLLECTION_CADENCE_EXPANSION_FOR_UI = NOT_AUTHORIZED
ANONYMOUS_LIVE_ODDS_AS_BENCHMARK = FORBIDDEN
PUBLIC_CLV = FORBIDDEN
PUBLIC_ROI = FORBIDDEN
MARKET_DIRECTION_BENCHMARK_V1 = NOT_AUTHORIZED
```

## 21. Repository Hygiene rule

Every implementation stage must finish with repository hygiene appropriate to that stage. Final cleanup is intentionally deferred to P5.5 so functional acceptance and deletion are not mixed.

No stage may claim completion solely from a PR description, status file, code comment, or self-declared receipt. Acceptance must be grounded in code, models/migrations where relevant, tests, real read/runtime evidence, and call evidence.

## 22. Current next action

```text
NEXT = EXECUTE_P0_ONLY
P0_OUTPUT = DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
AFTER_P0 = OWNER_REVIEW_A
DO_NOT_START_P1_AUTOMATICALLY
```

Codex must re-fetch the latest `origin/main` and `origin/context/current`, read `CURRENT_STATE.yaml`, `NEXT_ACTION.md`, and this master plan, then execute only P0. If repository reality conflicts with this plan, report the conflict and stop rather than silently changing product semantics.
