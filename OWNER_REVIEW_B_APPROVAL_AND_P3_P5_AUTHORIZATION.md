# W2 Owner Review B Approval + Continuous P3→P5 Authorization

```text
AUTHORITY = W2_OWNER_REVIEW_B_APPROVAL_P3_P5_CONTINUOUS_V1
OWNER_DATE = 2026-08-09
OWNER_DECISION = APPROVED
OWNER_REVIEW_B = PASS
P1 = PASS
P2 = PASS_MERGED
P2_PR = 498
P2_REMEDIATED_HEAD = eeafd2658cffb38dab8e6ed4b7b521e157d106ef
P2_MERGE_MAIN = f14136f07d69ece09e61fec6b1dd546e67c0267c
P3 = AUTHORIZED
P4 = AUTHORIZED_AFTER_P3_LOCAL_ACCEPTANCE_PASS
P5 = AUTHORIZED_AFTER_P4_LOCAL_ACCEPTANCE_PASS
P5_5 = NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
TERMINAL_OWNER_GATE = OWNER_REVIEW_C
```

## 1. Owner decision

Owner Review B approves the P1/P2 delivery after the bounded remediation on PR #498. The independently reviewed remediation closed the three required contract finding groups:

1. P0 Attention/replay field coverage;
2. exact seven-state/four-risk fail-closed schema semantics;
3. Scoreline READY=10,000 + explicit unconditional probability semantics.

PR #498 has been promoted to `main` at exact merge SHA:

```text
f14136f07d69ece09e61fec6b1dd546e67c0267c
```

This approval authorizes one continuous product-development segment:

```text
P3 — FINAL INTELLIGENCE WORKSPACE UI
↓ local acceptance; remediate in scope until PASS
P4 — VALIDATION + LEAGUE PERFORMANCE + FORWARD RECORDS + HISTORY/REPLAY
↓ local acceptance; remediate in scope until PASS
P5 — FULL-CHAIN TRUTHFULNESS + VISUAL + REPOSITORY ACCEPTANCE
↓
STOP — OWNER REVIEW C
```

There is **no Owner gate between P3, P4 and P5**. Codex must not stop merely because one numbered phase is implemented. It continues automatically after the phase-local acceptance gates pass.

## 2. Continuity / self-remediation rule for this execution segment

The purpose of this authorization is to reduce Owner relay and repeated prompt handoff.

For P3→P5, Codex must use the following loop:

```text
IMPLEMENT CURRENT PHASE
↓
RUN PHASE-LOCAL ACCEPTANCE
↓
FAIL + FIX IS INSIDE THIS AUTHORITY
    -> FIX
    -> RE-RUN AFFECTED + DEPENDENT GATES
    -> CONTINUE
PASS
    -> START NEXT AUTHORIZED PHASE WITHOUT OWNER MESSAGE
OUT-OF-SCOPE / PRODUCT-AUTHORITY CONFLICT
    -> STOP BLOCKED WITH EVIDENCE
P5 ALL GATES PASS
    -> STOP OWNER_REVIEW_C
```

Do not ask the Owner to relay ordinary test failures, TypeScript failures, E2E failures, responsive-layout defects, visual-regression defects, contract mismatches, copy violations, or other fixable defects that remain within the frozen P0/P1/P2 product contract. Fix them and continue.

## 3. Exact base and delivery shape

Start from the latest `origin/main`, which at this authorization is:

```text
EXPECTED_STARTING_MAIN = f14136f07d69ece09e61fec6b1dd546e67c0267c
```

Before implementation, fetch latest `origin/main` and `origin/context/current`. If main has moved, verify whether the movement is compatible and rebase cleanly; never silently discard newer evidence.

Preferred delivery shape:

- one clean implementation worktree/branch for P3→P5;
- one Draft PR may remain open and accumulate P3→P5 commits;
- normal PR Fast / Full CI may be rerun as needed;
- do not merge the P3→P5 implementation PR before Owner Review C unless a later explicit Owner authority says otherwise;
- P3/P4/P5 local completion must be recorded in the final Owner Review C packet.

## 4. P3 — Final Intelligence Workspace UI

### 4.1 Product authority

There is one public product only:

```text
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
```

The final Web UI must consume the P2 contract:

```text
GET /v1/dashboard/intelligence-workspace
SCHEMA = w2.dashboard-intelligence-workspace.v1
```

The Web product must not independently reconstruct recommendation/readiness/market/validation semantics from legacy endpoints when the unified P2 payload already supplies the required field.

Do not restore `BossDecisionView`, `RecommendationBoard`, `RecommendationCard`, old Boss L1/L2, old lock/recommendation ranking, or historical Step4/Post4 as a second public product.

### 4.2 Required final surfaces

Implement the approved Intelligence Workspace with these core surfaces:

1. compact global status/header + navigation;
2. Attention Feed;
3. Today Matches / Match Board;
4. Selected Match Inspector;
5. Market Radar;
6. Model Lab;
7. Scoreline Top 3 reference;
8. Validation;
9. League Performance;
10. Forward Validation Records + history/replay;
11. External Intelligence;
12. Data & Operations.

Required product facts include:

```text
W2 INTELLIGENCE
13 LEAGUES
SHADOW_ONLY
Candidate OFF
Formal OFF
Lock OFF
Production OFF
```

### 4.3 Match Board

Required row information:

- kickoff/time;
- league;
- fixture/matchup;
- W2 intelligence state;
- market main line fact;
- data/readiness state;
- next evaluation when available.

Market facts must never visually imply that the market "picked" Home/Away/Over/Under.

### 4.4 Selected Match Inspector

Required structure:

```text
MATCH IDENTITY
W2 ANALYSIS
MODEL VIEW
MARKET VIEW
MODEL / MARKET RELATION
FORMAL RECOMMENDATION = OFF + reason
DATA READINESS / RISK / NEXT EVALUATION
```

`ANALYSIS_REFERENCE`, `NOT_PROVEN`, and Formal OFF must remain visually explicit.

### 4.5 Attention Feed

Render only P2-bound evidence:

- exact seven-state intelligence state;
- fixture/kickoff;
- reason code(s);
- affected domain(s);
- factual summary;
- readiness context;
- exact four risks;
- next evaluation when present.

Attention is not a recommendation/opportunity ranking.

### 4.6 Market Radar

For AH and OU, render only real persisted P2 evidence:

- market identity;
- main/canonical selected line under W2 construction semantics;
- bookmaker count;
- two-sided prices/probabilities where present;
- snapshot count;
- observation count;
- freshness;
- actual discrete timeline;
- movement/reason codes.

Truth contract:

```text
0 snapshots = NO_TIMELINE_EVIDENCE -> no trend path
1 snapshot = ONE_OBSERVATION_NOT_A_TREND -> no trend path
2+ snapshots = DISCRETE_REAL_PATH -> actual persisted points only
```

No interpolation, smoothing invented as observation, copied point, synthetic path, fake flow/volume, bookmaker intent or funds-flow inference.

### 4.7 Model Lab

Clearly separate:

```text
W2 MODEL
MARKET
API-FOOTBALL PREDICTION = EXTERNAL_MODEL_BENCHMARK
```

API-Football Prediction currently remains `NOT_AVAILABLE` when not projected; do not call Provider on read.

Model/market statuses are diagnostic only. `MODEL_OUTSIDE_MARKET_RANGE` is not an opportunity/edge/value claim.

Frozen Phase 0.5 remains visible as appropriate:

```text
FINAL_VERDICT = NO_EDGE
HISTORICAL_INCREMENTAL_EDGE = NOT_PROVEN
V_CONTINUATION_GATE = FAIL
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

### 4.8 Scoreline Top 3

Consume the P2 scoreline contract only.

For READY:

```text
label = MODEL_SCORELINE_REFERENCE
proof_status = NOT_PROVEN
simulations_completed = 10000
top3[].sample_count = source count
top3[].unconditional_probability = source unconditional probability
```

No second simulation engine and no recomputation on Web/API read.

### 4.9 External Intelligence

Weather, News, Sentiment and Advanced xG remain:

```text
NOT_CONNECTED
```

Their absence is optional and must not make match data incomplete.

### 4.10 Data & Operations

Render real read-model source, domain freshness/status, degradation/system health, counts, Provider-budget status and runtime truth without secrets. Opening/refreshing the Web page must not cause Provider calls or business writes.

## 5. P4 — Validation + League Performance + Forward Records + History/Replay

P4 begins automatically after P3 local acceptance passes.

### 5.1 Primary validation hierarchy

Probability quality is primary:

- Brier Score;
- Log Loss;
- Calibration Error / ECE;
- Reliability bins/diagram;
- W2 vs market probability baseline where available;
- sample/cohort/checkpoint identity/status.

Do not recompute scoring in the Web read path.

### 5.2 Secondary directional hierarchy

Show as secondary evidence only:

- Correct;
- Wrong;
- PUSH;
- VOID;
- W2 Direction Accuracy;
- effective N;
- `MARKET_DIRECTION_BENCHMARK = NOT_DEFINED`.

Do not turn absolute hit rate into the dominant green KPI.

Settlement semantics are binding:

```text
PUSH = neutral settlement / 走水
VOID = invalid settlement
COHORT_EXCLUDED != PUSH
COHORT_EXCLUDED != VOID
```

### 5.3 League Performance

Required columns/values:

- League;
- Validation N;
- Decisive N;
- Correct;
- Wrong;
- PUSH;
- VOID when the P2 contract exposes it;
- W2 Direction Accuracy;
- Brier;
- Calibration;
- Statistical Status.

Statuses are `AVAILABLE`, `SAMPLE_BUILDING`, `INSUFFICIENT`.

Do not color leagues as good/bad purely from raw Direction Accuracy while the market direction benchmark is undefined.

### 5.4 Forward Validation Records / history/replay

Expose the existing P2 replay/records capability; do not build a second replay engine.

The final experience must answer from source-bound evidence:

- what was known at the selected date/time;
- what W2 judged;
- why/reason summary;
- readiness context;
- what happened afterward when outcome evidence exists;
- settlement/tracking status;
- card/evidence identity/hash checks;
- explicit replay gaps when evidence is incomplete.

Public label: `Forward Validation Records / 前向验证记录` is acceptable.

### 5.5 Public forbidden metrics

Final new workspace public reachability must be zero for:

```text
ROI
CLV
*_roi
*_clv
anonymous_live_odds_benchmark
value/edge/opportunity scoring
```

Legacy endpoints may remain until P5.5, but the new workspace cannot consume/render these fields.

## 6. P5 — Full-chain truthfulness + visual acceptance

P5 begins automatically after P4 local acceptance passes.

### 6.1 Mandatory truth scenarios

At minimum, test final UI + unified read model behavior for:

1. no matches / empty day;
2. 0 market snapshots;
3. 1 market snapshot;
4. 2+ real market snapshots;
5. lineup too early / not expected yet;
6. lineup expected but absent / provider-empty where represented;
7. injuries stale where represented;
8. market stale;
9. collection/provider incident or budget/degradation state where represented;
10. model not ready;
11. validation pending / insufficient;
12. `SAMPLE_BUILDING`;
13. External Intelligence `NOT_CONNECTED`;
14. history/replay with evidence;
15. history/replay with explicit gaps/incomplete evidence.

### 6.2 Mandatory negative truth assertions

```text
0_SNAPSHOT != TREND
1_SNAPSHOT != TREND
NO_INTERPOLATION
NO_SYNTHETIC_SIGNAL
NO_FAKE_BENCHMARK
NO_PUBLIC_CLV
NO_PUBLIC_ROI
NO_MARKET_AS_PICK
NO_ANONYMOUS_LIVE_ODDS_BENCHMARK
OPTIONAL_EXTERNAL_NOT_CONNECTED != DATA_INCOMPLETE
MODEL_MARKET_DISAGREEMENT != OPPORTUNITY
FORMAL_RECOMMENDATION = OFF
PUBLIC_DASHBOARD_AUTHORITY = NEW_INTELLIGENCE_WORKSPACE_ONLY
```

### 6.3 Visual authority

Target remains the Owner-approved dark-navy W2 Intelligence Workspace composition:

- left navigation;
- compact top status strip;
- Attention / Market Radar / External Intelligence upper region;
- Today Matches board;
- selected-match Inspector;
- Model Lab / Scoreline reference;
- Validation;
- League Performance / records;
- Data & Operations as defined by the approved product spec.

Deterministic golden viewport:

```text
1536x1024
DPR=1
fixed Chromium
fixed timezone/locale/font when test harness supports it
animations/transitions disabled for capture
scroll position = 0
```

Responsive acceptance also covers:

```text
1920x1080
1440x900
1366x768
```

No horizontal page scroll, core panel clipping, overlapping text/controls, missing core panel, duplicate public Dashboard, or unreadable layout.

If the original Owner reference binary is not repository-bound and cannot be resolved by Codex, **do not interrupt P3/P4 merely for that missing binary**. Implement the frozen product/geometry/semantic contract, generate deterministic P5 candidate screenshots and record `OWNER_REFERENCE_BINARY_NOT_REPO_BOUND` in the Owner Review C packet. This does not waive Owner visual acceptance; it defers the final pixel/reference comparison to Owner Review C instead of creating another midstream Owner relay.

When a repository-bound approved reference is available, add panel/full-page regression against it with tight deterministic tolerance.

### 6.4 P5 repository classification

Produce an evidence-backed classification only:

```text
KEEP
DELETE
DEPRECATE
RETAIN_FOR_EVIDENCE
```

for legacy Boss UI, old recommendation components/adapters/styles/tests/flags and other legacy assets.

**Do not delete them in P5.** Deletion authority remains P5.5 after Owner Review C approval.

## 7. Phase-local acceptance and automatic continuation

### P3 local acceptance before starting P4

All must pass:

- Web consumes `GET /v1/dashboard/intelligence-workspace` as final product data contract;
- one public workspace authority only;
- required P3 surfaces present;
- seven states/four risks rendered from P2 without reconstruction drift;
- 0/1/2+ timeline truth UI tests;
- Formal/Candidate/Lock/Production OFF presentation;
- Scoreline 10,000/unconditional semantics preserved;
- External NOT_CONNECTED non-blocking;
- no public ROI/CLV/value/edge/opportunity leakage;
- Web typecheck/build;
- focused unit/contract/E2E;
- no-call-on-read remains true;
- Repository Hygiene has no unexplained new dead assets.

If any fails inside authorized scope, fix and rerun. Do not stop for Owner.

### P4 local acceptance before starting P5

All must pass:

- Probability Validation primary hierarchy rendered from P2 values;
- Directional Outcome secondary hierarchy;
- League Performance truthful statistical status;
- Forward Validation Records + replay/decision/reason/outcome/gaps exposed;
- PUSH/VOID/excluded semantics correct;
- Market Direction Benchmark remains NOT_DEFINED;
- public ROI/CLV reachability remains zero;
- no new scoring/replay engine;
- focused unit/contract/E2E + Web build/typecheck PASS.

If any fails inside authorized scope, fix and rerun. Do not stop for Owner.

### P5 terminal acceptance

All must pass before Owner Review C:

- all mandatory truth scenarios;
- all mandatory negative assertions;
- semantic UI contract tests;
- deterministic geometry/layout tests;
- available visual regression/golden capture checks;
- responsive integrity at required viewports;
- no second/legacy public Dashboard route/entrypoint;
- full TypeScript/static checks;
- full unit/contract/integration/Web E2E required by repo;
- exact-head Full CI / `RELEASE_REQUIRED = PASS`;
- Repository Hygiene PASS;
- worktree clean;
- no Provider calls caused by Dashboard execution/testing unless an already-existing repository test fixture/mocking layer performs no real external call;
- no Scheduler/cadence/whitelist/model/threshold/authority changes.

Then stop at Owner Review C. Do not start P5.5.

## 8. Owner Review C packet requirements

Codex must write a single final packet containing at minimum:

```text
P3_RESULT
P4_RESULT
P5_RESULT
EXACT_STARTING_MAIN_SHA
EXACT_IMPLEMENTATION_BASE_SHA
EXACT_IMPLEMENTATION_HEAD_SHA
PR_NUMBER
PR_STATE
CHANGED_FILES
PUBLIC_ROUTE_AND_ENTRYPOINT_EVIDENCE
UNIFIED_READ_MODEL_CONSUMPTION_EVIDENCE
P3_SURFACE_ACCEPTANCE
P4_VALIDATION_ACCEPTANCE
P5_TRUTH_SCENARIO_MATRIX
FORBIDDEN_PUBLIC_FIELD_AND_COPY_SCAN
ZERO_ONE_TWO_PLUS_TIMELINE_EVIDENCE
SCORELINE_10000_UNCONDITIONAL_EVIDENCE
NO_CALL_ON_READ_EVIDENCE
VISUAL_TEST_ENVIRONMENT
GOLDEN/SCREENSHOT_ARTIFACT_PATHS_OR_REFERENCE_GAP
RESPONSIVE_ACCEPTANCE
TEST_COUNTS
CI_RUNS
RELEASE_REQUIRED
REPOSITORY_HYGIENE
KEEP_DELETE_DEPRECATE_RETAIN_FOR_EVIDENCE_MATRIX
UNRESOLVED_ITEMS
```

Also refresh `CODEX_EXECUTION_RECEIPT.md`, `CURRENT_STATE.yaml`, and `NEXT_ACTION.md` to the terminal state:

```text
P3 = PASS
P4 = PASS
P5 = COMPLETE_READY_FOR_OWNER_REVIEW_C
P5_5 = NOT_STARTED_NOT_AUTHORIZED
NEXT = OWNER_REVIEW_C
ROUND_4 = NOT_STARTED
```

## 9. Explicit stop / block conditions

Codex may stop before Owner Review C only if continuing would require an unapproved change to any of the following:

- frozen product semantics;
- new Provider call/purchase/cutover;
- Scheduler/cadence policy;
- exact 13 whitelist;
- model/factor/threshold/retraining;
- new migration/business write outside clearly necessary UI/read-only implementation and not already authorized;
- Phase 0.5 rerun;
- Round 4;
- Candidate/Formal/Lock/Production enablement;
- destructive legacy deletion;
- P5.5 cleanup authority.

Ordinary implementation defects are not Owner-block conditions.

## 10. Permanent boundaries

```text
POST_R3_PATH_A = CONTINUES_UNDER_EXISTING_RUNTIME_POLICY
DASHBOARD_WORK_MUST_NOT_CHANGE_PATH_A = true
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
P5_5 = NOT_AUTHORIZED
P6 = BLUEPRINT_ONLY_NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```
