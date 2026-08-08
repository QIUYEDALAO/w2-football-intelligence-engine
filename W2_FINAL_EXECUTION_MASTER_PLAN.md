# W2 Final Execution Master Plan

```text
AUTHORITY = W2_FINAL_EXECUTION_MASTER_PLAN_V1
OWNER_DATE = 2026-08-09
REPOSITORY = QIUYEDALAO/w2-football-intelligence-engine
EXACT_MAIN = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
PRODUCT = FOOTBALL_MARKET_INTELLIGENCE_PLUS_MODEL_DIAGNOSTICS
ROUND_4 = NOT_STARTED
CURRENT_ACTIVE_DEVELOPMENT = DASHBOARD_INTELLIGENCE_WORKSPACE_P0
```

## 1. Purpose

This is the top-level execution authority for the remaining W2 work.

It is not a historical-task archive and it does not require old work to be re-executed merely because an old checklist contains it. Historical plans are used only to identify capabilities that still matter. Current code, database contracts/migrations, tests, runtime evidence and call evidence determine whether a capability already exists, needs adaptation, or is obsolete.

The previously introduced `R0 legacy reconciliation` is cancelled as a development stage. The required reconciliation decision is incorporated in this document.

```text
R0 = CANCELLED_NOT_A_DEVELOPMENT_STAGE
HISTORICAL_TASKS = RESOLVED_BY_CURRENT_CAPABILITY_AND_PRODUCT_NEED
SILENTLY_REIMPLEMENT_OLD_UI = FORBIDDEN
```

## 2. What current main already proves exists and must be reused, not rebuilt

At exact main `f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3` the repository already contains the following implementation assets.

### 2.1 Decision/readiness contract foundation — EXISTING_CAPABILITY_REUSE

Existing domain contracts include:

- `DecisionTier`
- `DataStatus`
- `LifecycleStatus`
- reason codes
- DecisionCard / decision-contract machinery
- `outcome_tracked`
- `next_eval_at`
- Provider budget status

The data-readiness gate already exposes missing/stale fields, reason, action, next evaluation and Provider-budget status.

Decision: do not create a new historical Decision Contract project. P1/P2 may consume or adapt these fields into the final Intelligence Workspace read model, but old recommendation/lock authority is not restored.

### 2.2 Dashboard DayView / degradation / diagnostics foundation — EXISTING_CAPABILITY_REUSE

Existing Dashboard backend assets include DayView construction, intelligence-state sorting, date navigation, degradation states, L1/L2 diagnostic helpers and read-only behavior.

The current DayView is useful source material, but it is not the final Dashboard contract. It still carries legacy fields/copy such as `lock_eligible`, old DecisionTier presentation and recommendation-oriented degradation wording. P2 must extract the useful data and remove obsolete product semantics from the new unified read model.

Decision: reuse backend capability; do not rebuild the historical L1/L2 product.

### 2.3 Historical replay / audit front door — EXISTING_CAPABILITY_REUSE

A read-only replay front door and date-navigation foundation already exist, including card-hash checks, known-at summary, reason summary and outcome-tracking summary.

Decision: preserve the capability and expose it through the new Validation / Forward Validation Records experience in P4. Do not rebuild the old historical Dashboard page.

### 2.4 Scoreline reference — EXISTING_CAPABILITY_REUSE

The repository already contains seeded 10,000-simulation scoreline projection and Top-3 output with consistent sample count and unconditional probability.

Decision: P2 exposes this existing capability through the unified read model; P3 renders it in Match Inspector / Model Lab with `MODEL SCORELINE REFERENCE` and `NOT_PROVEN` semantics. Do not create a second scoreline engine.

### 2.5 Validation / scoring foundation — EXISTING_CAPABILITY_REUSE

The repository already contains probability-scoring infrastructure including Brier, Log Loss, reliability bins, calibration/ECE-related scoring, forward outcome/ledger performance and finished-match scoring assets.

Decision: P2/P4 adapt these existing scoring/ledger assets to the current validation cohort and final read model. Do not reimplement probability metrics from scratch.

### 2.6 Current public Dashboard authority — EXISTING_CURRENT_BASELINE

The active public chain is:

```text
App
→ DashboardPage
→ IntelligenceConsole
```

Legacy `BossDecisionView`, `RecommendationBoard` and `RecommendationCard` are not part of the active public chain.

Decision: the final Dashboard evolves from the current Intelligence Workspace direction and extracts only useful legacy business capabilities. The old Boss Dashboard must not be restored.

### 2.7 Provider / Scheduler / quota / collection safety — BACKGROUND_RUNTIME_NOT_DASHBOARD_TASK

Existing controlled Scheduler, Provider ledger/quota, endpoint/call safety, checkpoint and SHADOW_ONLY policy remain runtime infrastructure.

Decision: Dashboard work does not reopen or redesign this runtime. Post-R3 Path A continues naturally under the existing policy. No old refresh/scheduler task is re-run as part of the Dashboard plan.

## 3. Historical Step 4 / “Post4” final decision

Historical Step 4 is **not a separate task anymore**.

The old checklist described a Dashboard frontend/static-HTML project. A completely new Intelligence Workspace is now the approved product, so rebuilding old Step 4 would create duplicate architecture and obsolete semantics.

Final disposition:

| Historical item | Final decision |
|---|---|
| `W2-DASH-D01` frontend type convergence | `ABSORBED_IN_P2_P3` — final P2 schema becomes the TS/UI contract; no separate old frontend migration |
| `W2-DASH-E01` old owner/Boss L1 homepage | `SUPERSEDED_DO_NOT_IMPLEMENT` — executive scan goal is replaced by P3 Match Board + Attention + Inspector |
| `W2-DASH-E02` old `lock_eligible → ANALYSIS_PICK → WATCH → NOT_READY` ordering | `SUPERSEDED_DO_NOT_IMPLEMENT` — use frozen seven-state Attention precedence and current Match Board semantics |
| `W2-DASH-F01` old L2 diagnostics drawer | `OLD_UI_SUPERSEDED_CAPABILITY_ABSORBED_IN_P3` — diagnostics belong in Model Lab / Data & Ops / readiness/evidence surfaces |
| `W2-DASH-G01` empty/API/budget/stale/refresh degradation | `EXISTING_CAPABILITY_REUSE` — render truthful states in P3 and verify them in P5 |
| `W2-DASH-H01` historical-date navigation | `EXISTING_CAPABILITY_REUSE_ABSORBED_IN_P4_P5` — expose history/replay through Validation / Forward Validation Records and test it in P5 |

Therefore:

```text
HISTORICAL_STEP_4_POST4 = SUPERSEDED_AS_STANDALONE_WORKSTREAM
REBUILD_OLD_L1_L2_DASHBOARD = NO
REUSE_SURVIVING_CAPABILITIES = YES
```

## 4. Other historical task families — final disposition

### Decision Contract V2

Existing implementation foundation is present. Do not rerun the project. P2 consumes useful identity/readiness/reason/tracking fields. Old staging-A / production-B lock authority is obsolete for the current product.

```text
OLD_DECISION_CONTRACT_PROJECT = NO_REDO
CANDIDATE_FORMAL_LOCK_PRODUCTION = OFF
```

### Data Readiness Gate

Existing implementation foundation is present. P1 does not rebuild the gate; it freezes the final Dashboard field/source/freshness contract. P2 adapts the unified read model to that contract.

### Controlled Refresh / Provider safety

Not a new Dashboard task. Existing Post-R3 runtime policy remains authority. Historical fixed cadence or restart plans do not override it.

### `w2-matchday`

Existing matchday/orchestration/CLI/test assets are infrastructure, not a missing Dashboard feature. Do not create a new `w2-matchday` project. P5 may reuse existing safe test/acceptance entrypoints where appropriate.

### DayView

Existing DayView is an input/source to migration, not the final product contract. P2 replaces public dependency on legacy Dashboard-specific semantics with one final unified read model.

### Replay / audit / outcome tracking

Existing capability remains valuable. It is carried into P4/P5, not developed as a separate old Step 6 project.

### Old acceptance / visual regression tasks

Their useful acceptance intent is absorbed into P5. Old recommendation/lock scenarios are replaced by current Intelligence Workspace truth scenarios and current OFF authority.

### Old P0–P8 / packages / archived plans

They are historical evidence, not an automatically active backlog. Do not reopen or execute an old package solely because it exists in repository history. A historical capability may be revived only when the current P0–P5 implementation exposes a concrete missing prerequisite and the missing capability does not conflict with the current frozen product/runtime contract.

```text
ARCHIVED_PLAN_EXISTENCE != CURRENT_TASK_AUTHORIZATION
```

## 5. What is actually still unfinished

The remaining product-development work is limited to the following final chain.

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

There is no R0 stage and no separate Post4 stage.

## 6. P0 — Final product/page contract freeze

### Why it is still needed

The final Intelligence Workspace specification has been agreed in product discussion but is not yet fully materialized as the binding P0 product spec consumed by subsequent implementation.

### Do

Create/update:

- `DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md`
- context/current references/state

Freeze:

- Football Market Intelligence + Model Diagnostics position
- Market Fact / W2 Analysis / Validation / Formal Recommendation boundary
- exact 13 runtime whitelist
- seven intelligence states and four independent risks
- final page/panel structure and required fields
- Match Board semantics
- Match Inspector semantics
- Market Radar real-observation rules
- Model Lab W2 / Market / API-Football benchmark roles
- Scoreline Top 3 `NOT_PROVEN`
- External Intelligence `NOT_CONNECTED`
- probability validation priority over directional hit-rate
- Market Direction Benchmark `NOT_DEFINED`
- public ROI/CLV forbidden
- domain-specific freshness authority
- Market Memory / canonical-close limitations
- lineup evidence limitations
- approved 1536×1024 visual authority
- historical-task disposition from this master plan: no old L1/L2/Post4 rebuild
- P0→P6 governance and stop lines

### Do not

- no business/UI implementation
- no Provider calls
- no DB business writes
- no Scheduler/cadence changes
- no model changes
- no Round 4 / Phase 0.5 rerun

### Stop

```text
P0 COMPLETE
→ OWNER REVIEW A
```

## 7. P1 — Capability / Data / Freshness Contract

### Do

Produce/freeze:

- Perfect Intelligence Capability Matrix
- Current W2 Gap Matrix
- Dashboard Data Contract
- Freshness Contract

For every final Dashboard field, bind:

```text
FIELD
SOURCE
AVAILABILITY
FRESHNESS_DOMAIN
READINESS_SEMANTICS
NO_CALL_ON_READ
```

Reuse the existing readiness/DayView/runtime sources where valid; do not invent a second readiness engine.

### Do not

- no new Provider calls
- no external Weather/News/Sentiment/Advanced-xG connection
- no collection expansion for chart density
- no whitelist changes

P1 may continue directly into P2.

## 8. P2 — One final Dashboard Read Model / API contract

### This is a real missing implementation task

Current main contains multiple useful existing assets, but the final product still needs one new unified read model that removes legacy public semantics and exposes all approved Intelligence Workspace capabilities consistently.

### Reuse as sources

- current DayView/readiness/reason/next-eval fields
- Round-3 Intelligence/Attention/Market Radar/Model Lab data
- existing scoreline projection
- existing replay/date-navigation capability
- existing forward outcome/ledger/performance assets
- existing probability scoring/calibration assets
- useful legacy analysis evidence only where it remains semantically valid

### Build

One schema/API payload containing the final fields needed by:

- Match Board
- Selected Match Inspector
- W2 Analysis / Model View / Market View / Model-Market Relation
- Formal OFF reason
- Attention Feed
- Market Radar
- Model Lab
- Scoreline Top 3
- External NOT_CONNECTED
- Data/Ops
- Probability Validation
- Directional Outcome
- League Performance
- Forward Validation Records
- historical/replay navigation

### Remove from final public contract

- public ROI
- public CLV
- anonymous live-odds benchmark
- market-as-pick semantics
- old lock/recommendation-first Dashboard ranking
- old Boss L1/L2 product contract

### Acceptance

- explicit schema
- deterministic sample payload
- contract tests
- zero/one/2+ snapshot states
- no-call-on-read
- `NOT_CONNECTED`, `NOT_DEFINED`, `NOT_PROVEN` semantics

### Stop

```text
P2 COMPLETE
→ OWNER REVIEW B
```

## 9. P3 — Build the new Intelligence Workspace UI

### This is a real missing implementation task

Implement one public UI consuming only P2.

Required surfaces:

- compact W2/13-league/SHADOW_ONLY/OFF header
- Attention Feed
- Today Matches / Match Board
- Selected Match Inspector
- W2 Analysis
- Model View
- Market View
- Model / Market Relation
- Formal Recommendation OFF + reason
- Market Radar AH/OU real observation timeline
- Model Lab W2 / Market / API-Football
- Scoreline Top 3 reference
- External Intelligence NOT_CONNECTED
- Data & Operations

Also render truthful degradation/empty/stale/provider-incident states using existing backend capability adapted to current product semantics.

Do not build the old Boss L1 homepage or old L2 drawer as a second product.

Visual authority: approved 1536×1024 Intelligence Workspace reference.

P3 continues into P4.

## 10. P4 — Validation, League Performance, Forward Records and history/replay

### This is a real missing final-product integration task

Reuse current scoring/ledger/replay assets; do not reimplement them.

Primary Probability Validation:

- Brier Score
- Log Loss
- Calibration Error / ECE
- Reliability Diagram / bins
- W2 vs market probability baseline

Secondary Directional Outcome:

- Correct
- Wrong
- PUSH
- VOID
- Direction Accuracy
- effective N
- Market Direction Benchmark = `NOT_DEFINED`

League Performance:

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

Also expose:

- Forward Validation Records
- historical-date navigation
- replay view answering what was known, what W2 judged, why, and what happened afterward

Public ROI and CLV remain zero reachability.

P4 continues into P5.

## 11. P5 — Full-chain truth + visual acceptance

### This is a real missing acceptance task

Test at minimum:

- no matches
- 0 snapshot
- 1 snapshot
- 2+ snapshots
- lineup too early
- lineup expected but absent
- injuries stale
- market stale
- Provider incident / budget/degradation where represented
- model not ready
- validation pending
- SAMPLE_BUILDING
- External NOT_CONNECTED
- historical/replay date with complete evidence
- historical/replay date with incomplete evidence

Assert:

```text
0_SNAPSHOT != TREND
1_SNAPSHOT != TREND
NO_INTERPOLATION
NO_SYNTHETIC_SIGNAL
NO_FAKE_BENCHMARK
NO_PUBLIC_CLV
NO_PUBLIC_ROI
NO_ANONYMOUS_LIVE_PRICE_BENCHMARK
OPTIONAL_EXTERNAL_NOT_CONNECTED != DATA_INCOMPLETE
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
```

Visual acceptance includes the approved golden composition plus responsive integrity.

P5 produces only:

- KEEP
- DELETE
- DEPRECATE
- RETAIN_FOR_EVIDENCE

Do not delete legacy code yet.

### Stop

```text
P5 COMPLETE
→ OWNER REVIEW C
```

## 12. P5.5 — Controlled legacy cleanup

Only after P5 PASS + Owner approval.

Candidates include old Boss UI, old L1/L2 presentation, legacy adapters/styles/feature flags/tests and other code proven unreachable after useful helpers have been extracted.

Deletion requires proof through route/import/entrypoint/runtime/build/tests/config/workflow.

Final gates:

- Repository Hygiene
- TypeScript build
- unit
- contract
- E2E
- public-authority check
- reference search

```text
TASK_FULLY_CLOSED = FUNCTIONAL_ACCEPTANCE_PASS + REPOSITORY_HYGIENE_PASS
```

## 13. P6 — Long-term blueprint only

Not current development work:

- Market Memory accumulation/distributions
- lineup first-seen / league coverage distributions
- Provider forward availability distribution
- Team Form / Injury history
- Weather / News / Sentiment / Advanced xG providers
- sharp canonical-close provider
- MARKET_DIRECTION_BENCHMARK_V1
- Live Intelligence
- user notes/bookmarks

```text
P6_EXECUTION_AUTHORIZED = NO
```

## 14. Parallel background Track A — Post-R3 natural evidence

This remains active background runtime, not an extra Codex development stage.

```text
TRACK_A = PATH_A_NATURAL_EVIDENCE_ACCUMULATION
POLICY = EXISTING_AUTHORIZED_RUNTIME_ONLY
```

Wait for real fixtures to naturally cross the existing lifecycle and persist terminal evidence; then reproject and return to Owner review under the existing Post-R3 authority.

Dashboard development must not alter Track A cadence, Scheduler, Provider plan, whitelist or quota policy.

## 15. Explicit tasks that must NOT be done

- do not execute historical Step 4/Post4 as a separate project
- do not rebuild the old Boss L1/L2 Dashboard
- do not recreate Decision Contract V2 from scratch
- do not recreate Data Readiness Gate from scratch
- do not create another scoreline engine
- do not create another replay system
- do not create another Brier/LogLoss/reliability implementation unless P2 proves a concrete current-code defect
- do not restart old staging-A / production-B lock-authority development
- do not reopen archived P0–P8/packages solely because they exist
- do not change Provider/Scheduler/cadence for Dashboard density
- do not start Round 4
- do not rerun Phase 0.5
- do not enable Candidate / Formal / Lock / Production
- do not delete legacy code before P5.5

## 16. Current next action

```text
NEXT = EXECUTE_DASHBOARD_INTELLIGENCE_WORKSPACE_P0_ONLY
P0_OUTPUT = DASHBOARD_INTELLIGENCE_WORKSPACE_PRODUCT_SPEC.md
AFTER_P0 = STOP_OWNER_REVIEW_A
P1 = NOT_STARTED
ROUND_4 = NOT_STARTED
```

P0 must incorporate this document's historical-task decisions so later phases cannot accidentally resurrect obsolete old Dashboard work.
