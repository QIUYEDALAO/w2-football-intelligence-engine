# Owner Review C Packet — Unified Intelligence Workspace P3–P5

```text
AUTHORITY = W2_OWNER_REVIEW_C_PACKET_V1
STATUS = READY_FOR_OWNER_REVIEW_C
P3_RESULT = PASS
P4_RESULT = PASS
P5_RESULT = COMPLETE_READY_FOR_OWNER_REVIEW_C
EXACT_STARTING_MAIN_SHA = f14136f07d69ece09e61fec6b1dd546e67c0267c
EXACT_IMPLEMENTATION_BASE_SHA = f14136f07d69ece09e61fec6b1dd546e67c0267c
EXACT_IMPLEMENTATION_HEAD_SHA = e9fda39783b7e0ce80cff635e9e2d61dd51bf73f
EXACT_CONTEXT_BASE_SHA = 6183c1d7ede344b48ab14b02c250521068cf2f37
PR_NUMBER = 499
PR_STATE = OPEN_DRAFT
PR_URL = https://github.com/QIUYEDALAO/w2-football-intelligence-engine/pull/499
P5_5 = NOT_STARTED_NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```

## Executive acceptance

P3, P4 and P5 are complete on the single Draft PR. The public Web product now
uses one final Intelligence Workspace and consumes the P2 unified read model.
The delivery reuses existing Round 3 Intelligence, Attention, Market Radar,
Model Lab, Scoreline, Replay, Forward Validation and Performance/Calibration
capabilities; it does not rebuild legacy Boss L1/L2 or create a second replay,
scoring or simulation engine.

Exact-head Full CI run
[31277321425](https://github.com/QIUYEDALAO/w2-football-intelligence-engine/actions/runs/31277321425)
completed successfully, including `RELEASE_REQUIRED = PASS`.

## Changed files

1. `apps/web/src/App.tsx`
2. `apps/web/src/components/DashboardPage.tsx`
3. `apps/web/src/components/IntelligenceConsole.tsx`
4. `apps/web/src/intelligence.css`
5. `apps/web/src/lib/intelligenceWorkspaceApi.ts`
6. `apps/web/src/types/intelligenceWorkspace.ts`
7. `apps/web/e2e/decision-contract.spec.ts`
8. `apps/web/e2e/performance.spec.ts`
9. `apps/web/playwright.config.ts`
10. `tests/unit/test_formal_card_copy.py`
11. `docs/ui/intelligence-workspace/P3_P5_ACCEPTANCE.md`
12. `docs/ui/intelligence-workspace/golden/intelligence-workspace-1536x1024.png`
13. `docs/ui/intelligence-workspace/golden/intelligence-workspace-1920x1080.png`
14. `docs/ui/intelligence-workspace/golden/intelligence-workspace-1440x900.png`
15. `docs/ui/intelligence-workspace/golden/intelligence-workspace-1366x768.png`

Diff summary: 15 files, 2,207 insertions, 809 deletions.

## Public route and entrypoint evidence

- `App.tsx` maps the public root and non-development routes to
  `DashboardPage`.
- `DashboardPage.tsx` fetches only the unified workspace endpoint through
  `fetchIntelligenceWorkspace`.
- `intelligenceWorkspaceApi.ts` issues
  `GET /v1/dashboard/intelligence-workspace?date=...&window=today&timezone=Asia%2FShanghai`.
- The public `/performance` path no longer exposes a second dashboard.
- The protected development-only Boss reference route remains solely for
  retained evidence and its protected visual baseline.
- Public authority renders `NEW_INTELLIGENCE_WORKSPACE_ONLY`.

## Unified read-model consumption

```text
SCHEMA = w2.dashboard-intelligence-workspace.v1
ENDPOINT = GET /v1/dashboard/intelligence-workspace
LEGACY_DAY_VIEW_FALLBACK = NONE
PROVIDER_CALLS_ON_READ = 0
DB_WRITES_ON_READ = 0
WOULD_WRITE_CHECKPOINT = false
NO_CALL_ON_READ = true
```

The UI renders source-bound fields and does not independently reconstruct
recommendation, readiness, timeline, validation, replay or scoreline authority.

## P3 surface acceptance

| Surface | Result | Contract evidence |
| --- | --- | --- |
| Global status/navigation | PASS | 13 leagues, SHADOW_ONLY, Candidate/Formal/Lock/Production OFF |
| Attention | PASS | state, reasons, affected domains, factual summary, readiness context, four risks, next evaluation |
| Match Board | PASS | kickoff, league, fixture, state, market fact, readiness, next evaluation |
| Match Inspector | PASS | analysis/model/market/relation separated; Formal OFF |
| Market Radar | PASS | AH/OU persisted snapshot, observation, freshness, movement and reason evidence |
| Model Lab | PASS | W2 model, market and optional external benchmark remain distinct |
| Scoreline Top3 | PASS | 10,000 simulations, unconditional probability and sample count |
| External Intelligence | PASS | Weather/News/Sentiment/Advanced xG remain NOT_CONNECTED and non-blocking |
| Data & Operations | PASS | read source, freshness, degradation, counts, health and budget status |

The exact seven intelligence states and exact
`EVENT_RISK/DATA_RISK/MODEL_RISK/COLLECTION_RISK` axes are rendered without
semantic promotion.

## P4 validation acceptance

- Probability Validation: Brier, Log Loss, ECE/calibration, reliability bins,
  W2-versus-market values, status, cohort and checkpoint metadata.
- Directional Outcome: Correct, Wrong, PUSH, VOID, effective N and W2 Direction
  Accuracy, with `MARKET_DIRECTION_BENCHMARK = NOT_DEFINED`.
- League Performance: validation/decisive N, settlement counts, accuracy,
  Brier, calibration and AVAILABLE/SAMPLE_BUILDING/INSUFFICIENT state.
- Forward Validation Records/history/replay: known-at facts, decision summary,
  reason summary, readiness, outcomes, hashes and explicit replay gaps.
- No new scoring or replay engine; no ROI/CLV/value/edge/opportunity public
  reachability.

## P5 truth-scenario matrix

| # | Scenario | Result |
| ---: | --- | --- |
| 1 | Empty football day | PASS: no fabricated match |
| 2 | Zero snapshots | PASS: NO_TIMELINE_EVIDENCE, no path |
| 3 | One snapshot | PASS: ONE_OBSERVATION_NOT_A_TREND |
| 4 | Two-plus snapshots | PASS: persisted DISCRETE_REAL_PATH only |
| 5 | Lineup too early | PASS: expectation explicit, not incident promotion |
| 6 | Lineup expected/provider-empty | PASS: explicit readiness reason |
| 7 | Injuries stale | PASS: source freshness and reason visible |
| 8 | Market stale | PASS: stale state remains factual |
| 9 | Collection/provider degradation | PASS: incident/budget state visible |
| 10 | Model not ready | PASS: blocked without invented output |
| 11 | Validation insufficient | PASS: insufficient state explicit |
| 12 | SAMPLE_BUILDING | PASS: sample-building state explicit |
| 13 | External NOT_CONNECTED | PASS: optional and non-blocking |
| 14 | Replay with evidence | PASS: known-at/decision/outcome/hash evidence |
| 15 | Replay with gaps | PASS: gaps remain explicit |

## Negative semantic acceptance

```text
0_SNAPSHOT_NOT_TREND = PASS
1_SNAPSHOT_NOT_TREND = PASS
NO_INTERPOLATION = PASS
NO_SYNTHETIC_SIGNAL = PASS
NO_FAKE_BENCHMARK = PASS
NO_PUBLIC_CLV = PASS
NO_PUBLIC_ROI = PASS
NO_MARKET_AS_PICK = PASS
NO_ANONYMOUS_LIVE_ODDS_BENCHMARK = PASS
OPTIONAL_EXTERNAL_NOT_CONNECTED_NOT_DATA_INCOMPLETE = PASS
MODEL_MARKET_DISAGREEMENT_NOT_OPPORTUNITY = PASS
FORMAL_RECOMMENDATION_OFF = PASS
PUBLIC_DASHBOARD_AUTHORITY_NEW_WORKSPACE_ONLY = PASS
```

## Scoreline and timeline evidence

- Scoreline READY appears only when `simulations_completed === 10000`.
- Every displayed Top3 item binds `unconditional_probability` and
  `sample_count`; no generic probability alias is used.
- Web/API read performs no simulation.
- Timeline UI has three discrete states: zero, one and two-plus. It renders only
  P2 `timeline_points`, without interpolation, smoothing or copied points.

## Test and CI evidence

```text
FOCUSED_BACKEND_WORKSPACE = 27 PASS
FOCUSED_P3_P5_PLAYWRIGHT = 19 PASS
FULL_WEB_E2E = 37 PASS
SOURCE_CONTRACT = 6 PASS
UNIT_CONTRACT_SHARDS = 20 + 763 + 566 + 992 PASS
INTEGRATION_SHARDS = 12 + 71 PASS
STAGING_PARITY = PASS
PREDEPLOY_E2E_AND_CONTRACT = PASS
COMPOSE_PACKAGING = PASS
MIGRATION_SCHEMA = PASS
STATIC_CONTRACT_RUFF_STRICT_MYPY_SECRET_SCAN = PASS
PROTECTED_BOSS_BASELINE = PASS
PR_FAST_RUN = 31277287625
PR_FAST_REQUIRED = PASS
FULL_CI_RUN = 31277321425
EXACT_HEAD_CHECKOUT = e9fda39783b7e0ce80cff635e9e2d61dd51bf73f
RELEASE_REQUIRED = PASS
FAILED_FULL_CI_JOBS = 0
```

The first Full CI attempt exposed only cross-operating-system font rasterization
differences in four macOS-authored PNG comparisons. The bounded correction keeps
the committed Owner evidence and verifies byte-identical repeated screenshots
within the same fixed Chromium runtime plus semantic and geometry assertions.
The corrected exact head passed the Ubuntu Web job and the final aggregate gate.

## Visual and responsive acceptance

```text
FIXED_BROWSER = Chromium
DPR = 1
LOCALE = en-GB
TIMEZONE = Asia/Shanghai
FIXED_CLOCK = 2026-08-09T06:00:00Z
ANIMATIONS_TRANSITIONS = disabled
SCROLL_POSITION = 0
VIEWPORTS = 1536x1024; 1920x1080; 1440x900; 1366x768
HORIZONTAL_PAGE_OVERFLOW = 0
CORE_SURFACES_VISIBLE = PASS
OWNER_REFERENCE_BINARY = NOT_REPO_BOUND
```

Golden paths are the four PNG files listed under Changed files. Final pixel
comparison against the missing original Owner binary is intentionally carried
to Owner Review C; no substitute is represented as Owner approval.

## Repository Hygiene

| Asset group | Classification | Result |
| --- | --- | --- |
| Unified workspace runtime/types/API/CSS | KEEP | public runtime chain |
| P3–P5 contract/E2E tests | KEEP | exact behavior gates |
| Four workspace screenshots | RETAIN_FOR_EVIDENCE | deterministic Owner packet evidence |
| Protected Boss fixture/baseline | RETAIN_FOR_EVIDENCE | existing protected contract |
| Legacy Boss/Recommendation UI | DEPRECATE | no public authority; retained pending P5.5 authorization |
| Legacy performance presentation | DEPRECATE | no second public route |
| Destructive deletions | DELETE: NONE | P5.5 not authorized |

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 112
UNRESOLVED_HYGIENE_ITEMS = 0
IMPLEMENTATION_WORKTREE_CLEAN = PASS
```

## Frozen controls and stop line

```text
PROVIDER_CALLS = 0
DB_BUSINESS_WRITES = 0
SCHEDULER_OR_CADENCE_CHANGED = false
ACTIVE_WHITELIST = EXACT_EXISTING_13
WHITELIST_CHANGED = false
MODEL_FACTOR_THRESHOLD_RETRAINING_CHANGED = false
PHASE_0_5_REEXECUTED = false
H_RESULT_ACCESS = PERMANENTLY_CLOSED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
P5_5 = NOT_STARTED_NOT_AUTHORIZED
ROUND_4 = NOT_STARTED
```

## Owner Review C decision requested

Review Draft PR #499 at the exact head above, the four candidate screenshots,
the P3–P5 acceptance evidence, and the repository-unbound Owner reference gap.
No merge, P5.5 cleanup, legacy deletion or Round 4 work has been performed or
authorized by this packet.
