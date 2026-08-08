# W2 Master Task Ledger + Legacy Reconciliation

```text
AUTHORITY = W2_MASTER_TASK_LEDGER_AND_RECONCILIATION_V1
OWNER_DATE = 2026-08-09
REPOSITORY = QIUYEDALAO/w2-football-intelligence-engine
RUNTIME_MAIN_BASELINE = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
CONTEXT_BASELINE_BEFORE_THIS_LEDGER = d35c3c26c737c93f9ee8f30e6333e5e7323962e8
ROUND_4 = NOT_STARTED
CURRENT_EXECUTION_AUTHORIZATION = R0_LEGACY_TASK_RECONCILIATION_ONLY
```

## 1. Why this ledger exists

This is the top-level W2 task ledger. It prevents prior approved work from disappearing when a newer workstream is introduced.

The Dashboard / Intelligence Workspace plan is still binding for the new Dashboard, but it is not allowed to silently replace older W2 tasks. Every legacy task must be reconciled against current repository reality and given an evidence-backed disposition before P0 starts.

This ledger therefore adds one gate before Dashboard P0:

```text
R0 — HISTORICAL / LEGACY TASK RECONCILIATION
↓
STOP — OWNER TASK-LEDGER REVIEW

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

P6 remains blueprint-only. Round 4 remains NOT_STARTED.

## 2. Evidence rule

A legacy task may not be marked complete because of a PR description, status file, code comment, task receipt, or prior chat statement.

R0 must classify each task from current evidence only:

- code and actual entrypoints
- database models and migrations
- tests and contract tests
- build/runtime graph
- real persisted/runtime evidence where the task requires runtime proof
- Provider/call evidence where the task requires call proof

Allowed R0 completion classifications:

```text
DONE_PROVEN
PARTIAL_PROVEN
NOT_IMPLEMENTED
SUPERSEDED_BY_CURRENT_CONTRACT
CONFLICTS_WITH_CURRENT_CONTRACT
RETAIN_AS_BACKGROUND_RUNTIME
RETAIN_FOR_EVIDENCE
UNKNOWN_INSUFFICIENT_EVIDENCE
```

The mapping in this document is a planning disposition, not a claim that implementation is complete.

## 3. Conflict resolution rule

Newer frozen product/runtime contracts override obsolete execution semantics, but not the underlying business capability unless that capability was explicitly rejected.

Examples:

- old `lock_eligible`, staging-A / production-B and RECOMMEND activation semantics do not authorize Candidate/Formal/Lock/Production now;
- old fixed refresh cadence does not override the currently authorized Post-R3 scheduler/checkpoint policy;
- old Dashboard recommendation-first presentation does not override the current `Football Market Intelligence + Model Diagnostics` product position;
- useful capabilities such as readiness, reason codes, replay, validation, scorelines, diagnostics, safe refresh, ledger/quota, and audit must not disappear merely because their old UI/authority wording is obsolete.

Permanent current stop lines remain:

```text
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_4 = NOT_STARTED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ACTIVE_WHITELIST = EXACT_EXISTING_13
```

## 4. Current parallel workstreams

### Track A — Post-R3 natural evidence accumulation

```text
POST_R3_READINESS_ATTRIBUTION = PASS_PATH_A_NATURAL_EVIDENCE_ACCUMULATION
STATUS = RETAIN_AS_BACKGROUND_RUNTIME
```

This track is not cancelled by Dashboard work. Existing natural evidence accumulation may continue under the already-authorized runtime policy only.

Completion remains event-based: represented active competitions naturally cross the existing T12/T6/T3/T60 lifecycle with explicit persisted terminal evidence, followed by re-projection and Owner review.

Dashboard work must not change Scheduler policy, cadence, Provider plan, whitelist, quota policy, or authority for Track A.

### Track B — R0 legacy-task reconciliation

This is the only newly authorized Codex task now.

R0 is read-only except for `context/current` documentation updates. No product/business code changes.

### Track C — Dashboard / Intelligence Workspace

Governed by `DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md` after R0 Owner approval.

### Track D — Long-term blueprint

P6 only; execution not authorized.

## 5. Historical task source A — W2 Next-Phase Upgrade Task List

The historical source used these principles and task IDs. Every row below must be reconciled in R0.

### 5.1 Global principles

| ID | Historical intent | Current planning disposition |
|---|---|---|
| G-01 | freeze new Stage/checker growth | VERIFY_CURRENT_MAIN; preserve as architecture-governance intent |
| G-02 | converge, do not rewrite; preserve audit/settlement/provider safety | KEEP_INTENT; verify current implementation and map survivors |
| G-03 | staging A / production B recommendation/lock policy | SUPERSEDED_BY_CURRENT_CONTRACT for activation semantics; do not reopen authority |
| G-04 | controlled Provider refresh with allowlist/hard-cap/ledger/dedupe | KEEP_SAFETY_INTENT; verify against current runtime policy without changing cadence |
| G-05 | high-risk operations require separate approval | KEEP_GOVERNANCE_INTENT |

### 5.2 Historical prerequisite

| ID | Historical intent | Current target |
|---|---|---|
| W2-RUNTIME-005 | OOM-safe controlled refresh and complete raw/audit persistence | VERIFY_CURRENT_MAIN; if already proven mark DONE_PROVEN, otherwise classify; no new Provider call in R0 |

### 5.3 Step 0 — freeze and reality sync

| ID | Historical intent | Current target |
|---|---|---|
| W2-STEP0-01 | freeze Stage 16 / new stage machinery | R0 architecture audit / P5.5 hygiene if residue remains |
| W2-STEP0-02 | README reflects real operating state | R0 documentation reconciliation / later hygiene |
| W2-STEP0-03 | authoritative next-phase execution plan | SUPERSEDED as document form by current context authorities; preserve non-conflicting intent |

### 5.4 Step 1 — Decision Contract V2

| ID | Historical intent | Current target |
|---|---|---|
| W2-DC-01 | single domain DecisionTier | R0 verify; P2 only if a still-needed read-model contract remains |
| W2-DC-02 | DataStatus / LifecycleStatus alignment | R0 verify; P1/P2 mapping for truthful readiness/lifecycle data |
| W2-DC-03 | canonical DecisionCard | R0 verify; useful fields may migrate into new unified Dashboard Read Model, but old card is not mandatory product authority |
| W2-DC-04 | decision_tier / outcome_tracked / lock_eligible / recommendation_id governance fields | R0 verify; tracking may be retained, activation semantics remain OFF |
| W2-DC-05 | staging A / production B lock policy | SUPERSEDED_BY_CURRENT_CONTRACT; no activation |
| W2-DC-06 | legacy shim; preserve historical locked snapshots | R0 verify; historical evidence must not be destroyed; cleanup only P5.5 |
| W2-DC-07 | reason_code + action + next_eval_at | KEEP_CAPABILITY; map to P1/P2/P3 readiness and next-evaluation surfaces |
| W2-DC-08 | contract regressions | KEEP_TEST_INTENT; map to P2/P5 where still applicable |

### 5.5 Step 2 — unified data readiness

| ID | Historical intent | Current target |
|---|---|---|
| W2-READINESS-01 | one Data Readiness Gate with status/missing/stale/reason/action/next_eval | R0 verify; P1/P2 authoritative freshness/readiness contract |
| W2-READINESS-02 | required fields and freshness by domain | KEEP_CAPABILITY but current domain-specific freshness authority overrides old hard-coded assumptions; P1 |
| W2-READINESS-03 | Provider budget affects readiness and prevents API hammering | KEEP_SAFETY_INTENT; verify current quota/readiness semantics; P1/P5 |
| W2-READINESS-04 | lineup timing/readiness policy | MIGRATE_INTENT to current lineup evidence contract; no old staging/production recommendation activation |

### 5.6 Step 2b — controlled refresh formalization

| ID | Historical intent | Current target |
|---|---|---|
| W2-REFRESH-01 | fixed historical T-24/T-3/T-90/T-30/T-15 cadence, no 60s loop | CADENCE_SEMANTICS_SUPERSEDED; verify safety history only. Current Post-R3 policy is authority; do not change it in Dashboard work |
| W2-REFRESH-02 | endpoint allowlist | KEEP_SAFETY_INTENT; verify current runtime |
| W2-REFRESH-03 | per-tick hard cap | KEEP_SAFETY_INTENT; verify current runtime/quota controls |
| W2-REFRESH-04 | request ledger / quota / audit reconciliation | KEEP_CORE_INFRASTRUCTURE_INTENT; verify current runtime |
| W2-REFRESH-05 | scheduler restart only after safety gates | HISTORICAL_GOVERNANCE; current Scheduler policy/Track A authority controls now |

### 5.7 Historical Step 2 — `w2-matchday` single entrypoint

| ID | Historical intent | Current target |
|---|---|---|
| W2-MATCHDAY-01 | `w2-matchday` console entry | R0 verify whether it exists/is authoritative/reachable |
| W2-MATCHDAY-02 | matchday dry-run | R0 verify; retain useful deterministic ops capability if still used |
| W2-MATCHDAY-03 | controlled end-to-end matchday run | R0 verify; any current execution must obey SHADOW_ONLY and OFF stop lines |
| W2-MATCHDAY-04 | approval before lock write | RETAIN_GOVERNANCE_EVIDENCE; Lock remains OFF, so no lock path activation |
| W2-MATCHDAY-05 | settlement dry-run before write | KEEP_SAFETY/REPLAY_INTENT; verify current settlement/replay path |

### 5.8 Step 3 — Dashboard backend convergence

| ID | Historical intent | Current target |
|---|---|---|
| W2-DASH-A01 | Dashboard reads one decision authority, no multi-field archaeology | KEEP_CONVERGENCE_INTENT; P2 unified read model |
| W2-DASH-A02 | retire duplicate Dashboard recommendation enum | R0 verify; P2/P5.5 if obsolete duplicate remains |
| W2-DASH-A03 | readiness converges on one contract | KEEP_CONVERGENCE_INTENT; P1/P2 |
| W2-DASH-A04 | scoreline/model pricing logic outside presentation layer | KEEP_LAYERING_INTENT; P2; public edge/value fields forbidden under current product contract |
| W2-DASH-A05 | readiness summary by reason code | KEEP_CAPABILITY; P2/P3 |

### 5.9 Step 3B — deterministic human explanation

| ID | Historical intent | Current target |
|---|---|---|
| W2-DASH-B01 | deterministic one-line explanation stored with evidence | R0 verify; P2/P3 if still required by new read model |
| W2-DASH-B02 | template-based explanation by state | MIGRATE_INTENT to seven-state/readiness/current analysis semantics; do not restore old recommendation tiers as product authority |
| W2-DASH-B03 | wording guardrails | KEEP_GUARDRAIL_INTENT; current stronger forbidden-language contract controls |

### 5.10 Step 3C — Dashboard API / day envelope

| ID | Historical intent | Current target |
|---|---|---|
| W2-DAYVIEW-C01 | coherent DashboardDayView envelope | R0 verify; concept may be replaced by P2 unified Dashboard Read Model |
| W2-DAYVIEW-C02 | frontend consumes backend decision/read model without recomputing | KEEP_CORE_RULE; P2/P3 |
| W2-DAYVIEW-C03 | freshness, refresh and provider-budget context | KEEP_CAPABILITY; P1/P2/P3 |
| W2-DAYVIEW-C04 | checkpointed day-view read | R0 verify actual current checkpoint/read path; no Provider call on public read |

### 5.11 Step 4 — Dashboard frontend / static HTML upgrade (historical “Step 4 / Post4” work)

This block is explicitly preserved. It is not cancelled. It must be migrated to the new Intelligence Workspace semantics rather than executed literally with obsolete recommendation/lock presentation.

| ID | Historical intent | Current target |
|---|---|---|
| W2-DASH-D01 | frontend types converge on backend contract | P2 contract + P3 UI; verify legacy string/union residue |
| W2-DASH-E01 | owner-facing L1 overview | MIGRATE to P3 Match Board + Inspector + Attention/summary hierarchy; no recommendation-first cockpit |
| W2-DASH-E02 | deterministic ordering | SUPERSEDE old lock/recommendation ordering with frozen seven-state Attention precedence and current Match Board rules |
| W2-DASH-F01 | L2 technical diagnostics accessible without overwhelming primary view | KEEP_INTENT; P3 Data/Ops, Model Lab, evidence/readiness surfaces |
| W2-DASH-G01 | readable empty/error/stale/budget/refresh degradation states | KEEP_CAPABILITY; P3/P5 mandatory truth scenarios |
| W2-DASH-H01 | historical-date replay navigation | KEEP_CAPABILITY; map to P4/P5 if current evidence/read model supports it; R0 must determine current implementation |

### 5.12 Step 5 — environment and credibility

| ID | Historical intent | Current target |
|---|---|---|
| W2-ENV-I01 | staging-A labeling / analysis-only credibility | PARTIALLY_SUPERSEDED; preserve explicit analysis-reference/non-proven labeling, discard lock activation |
| W2-ENV-I02 | production-B RECOMMEND-only lock | SUPERSEDED_BY_CURRENT_CONTRACT; Production/Lock remain OFF |
| W2-ENV-I03 | environment stamp through public/audit/replay artifacts | KEEP_TRACEABILITY_INTENT; R0 verify, map to P2/P5 where relevant |

### 5.13 Step 6 — replay / audit front door

| ID | Historical intent | Current target |
|---|---|---|
| W2-REPLAY-01 | historical replay: what was known, judged, why, and eventual result | KEEP_CAPABILITY; R0 verify; map to P4/P5 |
| W2-REPLAY-02 | deterministic hash/replay consistency | KEEP_AUDIT_INTENT; R0 verify; P2/P5 contract tests if still relevant |
| W2-REPLAY-03 | tracked analysis views enter post-match replay | KEEP_VALIDATION_INTENT, but current Validation semantics and cohort authority control; P4/P5 |

### 5.14 Step 7 — acceptance

| ID | Historical intent | Current target |
|---|---|---|
| W2-ACCEPT-01 | 5-second owner comprehension test | MIGRATE to P5 product acceptance using current intelligence-first semantics |
| W2-ACCEPT-02 | contract test coverage | KEEP; P2/P5 |
| W2-ACCEPT-03 | refresh safety tests | KEEP_RUNTIME_SAFETY_INTENT; R0 verify current coverage; Dashboard work cannot change cadence |
| W2-ACCEPT-04 | Dashboard visual regression | KEEP; P3/P5 against current approved Intelligence Workspace visual authority |
| W2-ACCEPT-05 | full-chain exercise | MIGRATE to P5 truth acceptance; no lock/formal/production activation and no unapproved Provider calls |

## 6. Historical source B — earlier W2 master backlog / package governance

Earlier W2 governance treated the master backlog as cumulative authority rather than a disposable “current task” file. The historical backlog included P0–P8 / packaged work and required completed, pending, deferred, Gate and dependency entries to remain visible rather than being erased by later status updates.

R0 must therefore inspect repository history and retained authority files for older task registers/packages that predate the Next-Phase Upgrade Task List. Any concrete task found there that is not already represented above or in the current Dashboard P0–P6 plan must be appended to this ledger with its original identifier and evidence-backed disposition.

This section is intentionally fail-closed:

```text
OLDER_BACKLOG_RECONCILIATION = REQUIRED
SILENT_TASK_DROPPING = FORBIDDEN
ASSUME_DONE_FROM_AGE = FORBIDDEN
```

Codex must not invent missing historical task names. It must recover them from repository history/retained authorities or classify the source as unavailable with explicit evidence.

## 7. Current Dashboard / Intelligence Workspace task hierarchy

The full detailed requirements remain in `DASHBOARD_INTELLIGENCE_WORKSPACE_MASTER_PLAN.md`.

### P0 — Product semantics and page specification freeze

Docs-only authoritative product/page spec. Freeze product position, information architecture, panel semantics, Market Fact / W2 Analysis / Validation / Formal boundary, seven states, four risks, exact 13, forbidden content, External NOT_CONNECTED, validation hierarchy, scoreline semantics, cadence authority, domain-specific freshness, Market Memory, canonical-close limitation, lineup evidence limitation, visual authority, Owner gates and stop lines.

Stop after P0 for Owner Review A.

### P1 — Capability / Data / Freshness Contract

Produce Perfect Intelligence Capability Matrix, Current W2 Gap Matrix, Dashboard Data Contract and Freshness Contract. Bind every public field to real source/read model. No new Provider calls or external-source connection.

### P2 — Unified Dashboard Read Model / API Contract

Merge useful legacy business capabilities with Round-3 Intelligence capabilities into one new read model. Required contract/schema/sample payload/tests. May aggregate Brier, Log Loss, Calibration, reliability bins, market probability baseline, league validation summaries, Forward Validation Records and Scoreline Top 3 from existing cohorts.

Stop after P2 for Owner Review B.

### P3 — Final Intelligence Workspace UI

Single public UI consuming only P2 read model: header/status, Attention, Match Board, selected Match Inspector, W2 Analysis, Model/Market relation, Formal OFF reason, Market Radar, External Intelligence NOT_CONNECTED, Model Lab three-way benchmark, Scoreline Top 3, Data/Ops. Preserve approved 1536×1024 visual authority. No old/new dual public Dashboard.

### P4 — Validation + League Performance

Probability Validation primary: Brier, Log Loss, Calibration Error, Reliability, W2 vs market probability baseline. Directional outcome secondary: Correct/Wrong/PUSH/VOID, direction accuracy, effective N, market direction benchmark NOT_DEFINED. League Performance with statistical status. Public ROI/CLV reachability zero.

### P5 — Full-chain truth acceptance

Mandatory runtime/read-model scenarios, no fake trends/benchmarks/synthetic signals, no CLV/ROI/live-anonymous benchmark, optional external source absence is not Data Incomplete, only new workspace public. Produce KEEP/DELETE/DEPRECATE/RETAIN_FOR_EVIDENCE classification; do not delete yet. Includes visual acceptance.

Stop after P5 for Owner Review C.

### P5.5 — Controlled legacy cleanup

Only after P5 PASS + Owner approval. Prove route/import/entrypoint/runtime/build/tests/config/workflow reachability before deletion. Migrate helpers first. Finish Repository Hygiene, TS build, unit/contract/E2E/public-authority/reference-search gates.

### P6 — Long-term blueprint only

Market Memory accumulation, lineup first-seen distributions, league lineup coverage, provider forward availability, Team Form/Injury history, Weather/News/Sentiment/Advanced xG, sharp canonical-close provider, MARKET_DIRECTION_BENCHMARK_V1, Live Intelligence, user notes/bookmarks.

```text
P6_EXECUTION_AUTHORIZED = NO
```

## 8. R0 required Codex deliverable

R0 must produce/update this ledger with an evidence matrix containing at least:

```text
TASK_ID
SOURCE / HISTORICAL AUTHORITY
CURRENT_CODE_OR_DOC_EVIDENCE
DB_MODEL_OR_MIGRATION_EVIDENCE
TEST_EVIDENCE
RUNTIME_OR_CALL_EVIDENCE_IF_REQUIRED
CURRENT_CLASSIFICATION
CURRENT_TARGET_PHASE_OR_BACKGROUND_TRACK
CONFLICT_WITH_CURRENT_CONTRACT
REQUIRED_FOLLOW_UP
```

R0 must specifically answer:

1. Which historical tasks are already implemented and proven on latest main?
2. Which are only partially implemented?
3. Which remain genuinely missing and must be carried into P1/P2/P3/P4/P5/P5.5 or a separate future package?
4. Which old tasks are obsolete only because newer product/runtime contracts superseded their exact semantics?
5. Which old capabilities must still be preserved even though their old presentation or recommendation authority is obsolete?
6. Is historical Step 4 / “Post4” fully represented in the new P2/P3/P4/P5 plan?
7. Are replay, audit, outcome tracking, readiness, safe refresh, DayView/read-model, diagnostics, empty/error degradation and visual regression all still accounted for?
8. Does any older P0–P8/package/Gate/dependency task exist in repository history that is missing from this ledger?
9. Does Track A Post-R3 natural evidence remain intact and independent?
10. Does any proposed reconciliation accidentally authorize Round 4, Phase 0.5 rerun, Provider probes, Candidate/Formal/Lock/Production, whitelist change, or cadence change?

## 9. R0 scope and stop line

R0 is reconciliation/audit only.

Allowed writes:

- this ledger
- `CURRENT_STATE.yaml`
- `NEXT_ACTION.md`
- additional context/current reconciliation evidence files if needed

Forbidden:

- product/business code changes
- UI implementation
- migrations or DB business writes
- Provider calls/probes
- Scheduler/cadence changes
- whitelist changes
- model retraining/new factors/threshold changes
- Phase 0.5 rerun
- Round 4
- Candidate/Formal/Lock/Production changes
- legacy code deletion

Required terminal state:

```text
R0 = COMPLETE
LEGACY_TASKS = FULLY_RECONCILED_OR_EXPLICITLY_UNRESOLVED_WITH_EVIDENCE
P0 = NOT_STARTED
NEXT = OWNER_TASK_LEDGER_REVIEW
```

Do not start Dashboard P0 automatically.
