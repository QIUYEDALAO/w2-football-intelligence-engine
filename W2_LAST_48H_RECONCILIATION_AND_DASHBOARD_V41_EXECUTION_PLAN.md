# W2 Last-48-Hour Reconciliation and Dashboard V4.1 Execution Plan

```text
AUTHORITY = W2_LAST_48H_RECONCILIATION_AND_DASHBOARD_V41_EXECUTION_V1
OWNER_DATE = 2026-08-10
OWNER_DECISION = DASHBOARD_V41_OWNER_DESIGN_FREEZE_APPROVED
CONTINUOUS_IMPLEMENTATION = AUTHORIZED
BASE_MAIN = d2740a573c748cfaef38c66e951618e8782e09d0
CURRENT_DEPLOYED_SOURCE = 4370393be9b2593ec008d150daa9bf39ddbf265f
CURRENT_PUBLIC_SCHEMA = w2.dashboard-intelligence-workspace.v1
NEXT_TERMINAL_GATE = OWNER_DASHBOARD_V41_POSTDEPLOY_ACCEPTANCE
TRACK_A = TRACK_A_CLOSED_PASS
ROUND_4 = NOT_STARTED
P6 = NOT_AUTHORIZED
```

## 1. Reconciliation result

This document replaces an accumulated sequence of partial Dashboard task lists with one ordered authority. It distinguishes:

```text
CLOSED_RETAIN
CLOSED_SUPERSEDED_PRESENTATION
OPEN_REQUIRED
DEFERRED_NOT_AUTHORIZED
```

The reconciliation is based on merged PRs #494 through #505, current `main`, current `context/current`, the completed Track A and VPS receipts, and the Owner-approved V4.1 reference set.

### 1.1 Completed and retained

| Workstream | Evidence | Reconciled status | Binding decision |
|---|---|---|---|
| MI Round 2 audit foundation | PR #494 | CLOSED_RETAIN | Audit-only descriptors, provider identity, quota ledger and runtime isolation remain valid. |
| Free fixture bridge planner | PR #495 | CLOSED_RETAIN | Disabled-by-default fixture-centric planner and quota safety remain valid. |
| Free bridge SHADOW runtime | PR #496 | CLOSED_RETAIN | Scheduler/Celery integration remains SHADOW_ONLY on the exact existing 13 competitions. |
| Round 3 Market Radar / Model Lab | PR #497 | CLOSED_RETAIN | Persisted AH/OU evidence, sparse-safe timeline and diagnostic-only Model Lab remain the source foundation. |
| Unified Dashboard contracts and read model | PR #498 | CLOSED_RETAIN | `GET /v1/dashboard/intelligence-workspace`, no-call/no-write contract and unified schema remain the only public data authority. |
| P3/P4/P5 capability delivery | PR #499 | CLOSED_RETAIN_BACKEND_AND_SECONDARY_CAPABILITIES | Validation, league/tournament performance, forward records, replay and evidence contracts remain; the old first-screen composition is superseded. |
| Legacy Dashboard cleanup | PR #500 | CLOSED_RETAIN | Removed Boss/L1/L2/recommendation/performance public surfaces remain deleted; protected evidence remains protected. |
| Chinese-first and responsive remediation | PRs #501-#503 | CLOSED_RETAIN_TRUTH_FIXES / CLOSED_SUPERSEDED_PRESENTATION | Chinese labels, 13-inch truth, median price rendering and overflow fixes remain; the dense first-screen layout is superseded. |
| Canonical identity and collection semantics | PR #504 | CLOSED_RETAIN | Canonical competition aggregation, tournament separation, collection assessment, PRIOR_ONLY, football-day and only-record reasons remain mandatory. |
| Market truth consistency | PR #505 | CLOSED_RETAIN | Exact movement vocabulary/evidence, one public market readiness, stale Market Memory, quote counts, scoreline structure and Attention grouping remain mandatory. |
| VPS local OCI relay deployment | accepted receipt | CLOSED_RETAIN | GitHub/GHCR -> Owner local OCI relay -> VPS remains the only primary image transport. |
| Post-R3 Track A | closure report | TRACK_A_CLOSED_PASS | Natural evidence closure is complete; no recurring internal defect was proven. |
| Round4 readiness evidence | `ROUND4_READINESS_DECISION_PACKET.md` | EVIDENCE_FOUNDATION_RETAIN_PACKET_REFRESH_REQUIRED | The evidence conclusion is retained, but its exact release identity predates the V4.1 release and must be refreshed after V4.1 deployment. |

### 1.2 Completed but no longer the final product authority

The following claims are not to be reused as proof that the final Dashboard UX is complete:

```text
P3/P4/P5 old first-screen composition
PR #501 visual-parity acceptance
D13/D14/D15 terminal product-UX labels
same-render screenshot equality
no-overflow-only visual acceptance
```

They are historical technical milestones. Their source-truth fixes remain, but the public first-screen information architecture is replaced by V4.1.

### 1.3 Current code/deployment truth

```text
origin/main = d2740a573c748cfaef38c66e951618e8782e09d0
current deployed source = 4370393be9b2593ec008d150daa9bf39ddbf265f
PR #505 = MERGED
PR #505 RELEASE_REQUIRED = PASS
current deployed Dashboard = technically truthful D15 baseline, not final V4.1 UX
```

Therefore:

```text
CURRENT_BACKEND_FOUNDATION = COMPLETE
CURRENT_TRUTH_REMEDIATIONS = COMPLETE_AND_RETAINED
CURRENT_V41_DESIGN = OWNER_APPROVED
CURRENT_V41_PRODUCTION_IMPLEMENTATION = NOT_STARTED
CURRENT_V41_VPS_DEPLOYMENT = NOT_STARTED
OVERALL_DASHBOARD_V41 = NOT_COMPLETE
```

## 2. V4.1 Owner design freeze

The Owner has approved the latest V4.1 artifacts as the final information-architecture direction. They are:

```text
w2_v4_A_正常日(1).html
w2_v4_B_阻塞日(1).html
w2_v4_C_平静日(1).html
w2_v4_E_证据过期(1).html
w2_v4_F_空比赛日(1).html
w2_v4_base(1).html
W2_v41_A_正常日.png
W2_v41_B_阻塞日.png
W2_v41_C_平静日.png
W2_v41_D_窄屏1180.png
W2_v41_E_证据过期.png
W2_v41_F_空比赛日.png
```

### 2.1 Business modes

Only four day-level business modes are authorized:

```text
NORMAL  -> MATCH
BLOCKED -> GLOBAL_INCIDENT
CALM    -> DAY_SUMMARY
EMPTY   -> EMPTY_STATE
```

`E 证据过期` is not a fifth `day_mode`; it is `NORMAL + MATCH + market_evidence_status=STALE`.

`D 窄屏1180` is not a business state; it is a responsive presentation state.

### 2.2 Frozen first-screen hierarchy

```text
L1 TODAY SUMMARY
L2 PRIORITY SHORTLIST / GROUPS
L3 MODE-SPECIFIC PRIMARY FOCUS
L4 GLOBAL MODEL QUALITY SUMMARY
```

V4.1 is a football-intelligence review surface, not a betting recommendation surface.

### 2.3 Frozen truth rules

- Priority counts are grouped by `priority_reason_primary`; secondary reasons remain visible on the match.
- Default focus uses source-bound information usefulness, never EV/value/opportunity/recommendation semantics.
- A whole-day collection incident renders a global incident, not an arbitrary match.
- A calm day renders a day summary, not a forced match detail.
- An empty day never fills itself from another date.
- Historical stale market evidence remains visible but cannot be current model-comparison authority.
- Trend evidence and same-time cross-sectional comparison are separate concepts.
- Relative ages, countdowns and next-evaluation labels are derived from source timestamps, not authored strings.
- Scoreline Top 3 appears only when model READY, identity READY and exactly 10,000 existing simulations are proven.
- Global validation metrics render only from a valid checkpoint; missing/stale checkpoint fails closed.
- No external-intelligence empty cards are permanently present on the first screen.
- The first screen keeps only one compact immutable/read-only mode indicator and one system-status entry.

## 3. Ordered remaining execution plan

The following phases are one continuous authorized task. Codex must not stop between phases for ordinary implementation, test, layout or CI failures. In-scope failures must be fixed and revalidated before continuing.

### V41-0 — Materialize the approved design authority

1. Fresh-sync exact `origin/main` and `origin/context/current`.
2. Read the Owner-local `W2设计_v4/` artifacts and verify that the latest V4.1 files match the names and semantics above.
3. Copy sanitized editable HTML and PNG references into a repo-bound location such as:

```text
docs/ui/dashboard-v4.1/reference/
```

4. Record SHA-256 for every reference artifact.
5. Generate exact repo-bound targets at:

```text
1280x720
1180 responsive reference
1366x768
1512x982
1536x1024
```

6. Create:

```text
DASHBOARD_V41_DESIGN_SPEC.md
DASHBOARD_V41_STATE_MATRIX.md
DASHBOARD_V41_DESIGN_REVIEW_PACKET.md
REAL_SHAPE_DASHBOARD_V41_FIXTURES.json
```

7. Do not copy prototype CSS verbatim into production. The prototype is visual/product authority, not production architecture.

Acceptance:

```text
OWNER_V41_REFERENCE_SET_REPO_BOUND = PASS
REFERENCE_HASH_MANIFEST = PASS
DESIGN_STATE_MATRIX = PASS
NO_PRODUCT_CODE_CHANGED_YET = PASS
```

### V41-1 — Add the V4.1 read-model contract

Keep the existing endpoint. Add only source-bound, additive fields needed by V4.1.

Required contract:

```text
day_mode = NORMAL | BLOCKED | CALM | EMPTY
default_focus_type = MATCH | GLOBAL_INCIDENT | DAY_SUMMARY | EMPTY_STATE
default_focus_fixture_id = fixture id only for MATCH, otherwise null
```

Mandatory pair validation:

```text
NORMAL  <-> MATCH
BLOCKED <-> GLOBAL_INCIDENT
CALM    <-> DAY_SUMMARY
EMPTY   <-> EMPTY_STATE
```

Fail closed on impossible combinations, including:

```text
BLOCKED + MATCH
EMPTY + non-null fixture id
NORMAL + null focus fixture id
CALM + non-null fixture id
```

Add/derive, without Provider calls or business writes:

- `priority_reason_primary` and `priority_reason_secondary[]`;
- L1 counts grouped by primary reason, with no double counting;
- deterministic information-usefulness ordering and tie-breaks;
- source-bound global incident projection;
- source-bound calm-day summary projection;
- empty-day adjacent-day navigation evidence;
- market trend-evidence status separate from cross-sectional-comparison status;
- raw `generated_at`, `kickoff_utc`, `latest_snapshot_at`, `freshness_max_age_seconds`, `next_eval_at`;
- checkpoint availability/freshness for L4 global model quality;
- one model status/explanation authority;
- risk-dimension-specific reasons;
- public league status aligned with `only_record_reason`.

Do not create new recommendation, opportunity, EV, ROI, CLV or market-direction benchmark semantics.

Acceptance:

```text
V41_SCHEMA_ADDITIVE_AND_COHERENT = PASS
DAY_MODE_FOCUS_PAIR_FAIL_CLOSED = PASS
NO_DOUBLE_COUNT_PRIMARY_REASON = PASS
TIME_FIELDS_SOURCE_BOUND = PASS
NO_PROVIDER_CALL_ON_READ = PASS
NO_DB_BUSINESS_WRITE_ON_READ = PASS
```

### V41-2 — Replace the first-screen React/CSS composition

Implement one component system and one responsive layout from the frozen design.

Recommended production structure:

```text
DashboardV41Shell
DashboardV41Header
TodaySummary
PriorityShortlist
MatchFocus
GlobalIncidentFocus
CalmDayFocus
EmptyDayFocus
MarketEvidenceBlock
ThreeLayerMeaning
ModelDiagnosticSummary
GlobalModelQualityRail
SecondaryViewLinks
```

Requirements:

- only consume the unified workspace endpoint;
- use the read-model focus authority, not `matches[0]` and not a frontend first-match fallback;
- NORMAL renders the evidence-useful match focus;
- BLOCKED renders a global incident;
- CALM renders a day summary;
- EMPTY renders an empty-day state;
- STALE Market Memory remains visible with comparison paused;
- conditional Scoreline Top 3 is compact and disappears when not qualified;
- date navigation, Today and Refresh remain read-only actions;
- full validation, league/tournament performance, replay, external intelligence and Data/Ops remain secondary destinations;
- preserve every D13/D14/D15 truth behavior;
- replace, split or comprehensively rewrite the current patch-layered CSS;
- remove superseded selectors instead of appending another override block;
- preserve protected evidence assets and public-authority guards.

Acceptance:

```text
ONE_PUBLIC_DASHBOARD = PASS
NO_MATCHES_ZERO_DEFAULT_POLICY = PASS
ONE_COMPONENT_SYSTEM = PASS
NO_APPEND_ONLY_CSS_PATCH = PASS
NO_LEGACY_BOSS_RESTORE = PASS
ZH_CN_PRIMARY_COPY = PASS
```

### V41-3 — Truth, responsive, accessibility and visual acceptance

Create deterministic production-shape fixtures for:

```text
NORMAL_MATCH_RICH_EVIDENCE
BLOCKED_GLOBAL_INCIDENT
CALM_DAY_SUMMARY
NORMAL_MATCH_STALE_MARKET_MEMORY
EMPTY_DAY
NORMAL_1180_RESPONSIVE
```

Required contract tests:

- day-mode/focus impossible combinations fail closed;
- production and E2E use the same default-focus policy;
- primary-reason counts do not double-count a match with secondary reasons;
- `generated_at - latest_snapshot_at` is calculated correctly across timezone/day boundaries;
- a past `next_eval_at` is never labelled next;
- stale threshold boundary is exact;
- STALE and READY do not coexist for the same public market;
- one time snapshot cannot imply movement;
- same line/same price plus bookmaker-count change is stable;
- trend evidence may be insufficient while cross-sectional comparison is available;
- lineup before the expected window is not Attention;
- empty day cannot borrow another date;
- L4 checkpoint absent/stale fails closed;
- Scoreline reference requires exact 10,000 simulations and identity/model readiness;
- reads preserve `provider_calls=0`, `db_writes=0`, `would_write_checkpoint=false`.

Required visual/accessibility acceptance:

```text
1280x720
1180 responsive
1366x768
1512x982
1536x1024
200% browser zoom
keyboard-only navigation
visible focus state
normal text contrast >= 4.5:1
no horizontal page overflow
no nested-scroll requirement for primary content at <=1200px
```

The visual gate must compare against approved stored targets with real image diff / Playwright `toHaveScreenshot` or equivalent. Same-render equality may remain only as a determinism check.

### V41-4 — Full repository closure for the implementation

Run and pass:

```text
focused Python/unit/contract tests
full unit/contract/integration suite
Ruff
strict MyPy
Web typecheck
Web production build
full Web E2E
all V4.1 visual baselines
staging parity
migration/predeploy checks
secret scan
tracked-output checks
protected-evidence checks
Repository Hygiene
git diff --check
Exact-head Full CI
RELEASE_REQUIRED
```

Remove dead V4.1-transition selectors, fixtures and test helpers only when proven unreachable. Do not delete protected historical evidence.

### V41-5 — Merge and VPS deployment

After exact-head acceptance, merge automatically and deploy through:

```text
GitHub/GHCR
-> Owner local computer
-> scripts/relay_immutable_images_via_local.sh
-> exact OCI archive
-> SCP
-> VPS digest verification/import
-> existing warm-switch deployment
```

Forbidden:

```text
VPS direct GHCR bulk pull as primary transport
floating image tags
local rebuild of accepted release images
threshold relaxation
runtime-policy hotfix
```

### V41-6 — Real postdeploy acceptance

Require:

```text
WEB_AND_API_EXACT_SOURCE_MATCH
HEALTH_PASS
READY_PASS
RELEASE_SYNC_PASS
GET_/v1/dashboard/intelligence-workspace_PASS
PUBLIC_AUTHORITY_NEW_INTELLIGENCE_WORKSPACE_ONLY
V41_SCHEMA_AND_FOCUS_FIELDS_PRESENT
READ_PROVIDER_CALLS_0
READ_DB_WRITES_0
NO_CALL_ON_READ_TRUE
EXACT_13_COMPETITIONS
SHADOW_ONLY
CANDIDATE_FORMAL_LOCK_PRODUCTION_OFF
CURRENT_REAL_DAY_MODE_RENDERED_CORRECTLY
13_INCH_OWNER_DEVICE_SMOKE_READY
NO_STAGING_SEED_OR_SYNTHETIC_PRODUCTION_FALLBACK
```

Production acceptance checks the naturally current day mode only. Other modes are proven through deterministic source-bound fixtures; do not fabricate production data to force them.

Terminal gate:

```text
OWNER_DASHBOARD_V41_POSTDEPLOY_ACCEPTANCE
```

### V41-7 — Refresh the Round4 decision packet, but do not start Round4

After V4.1 postdeploy acceptance, refresh `ROUND4_READINESS_DECISION_PACKET.md` with:

- exact final V4.1 main and deployed identities;
- current stop lines;
- Track A CLOSED_PASS evidence reference;
- current no-call/no-write proof;
- current Dashboard release identity.

This is a packet refresh only.

```text
ROUND_4 = NOT_STARTED
ROUND_4_EXECUTION_AUTHORITY = NOT_GRANTED
```

## 4. Continuous-execution and remediation policy

Codex is authorized to execute V41-0 through V41-7 continuously.

Do not stop after V41-0, V41-1, V41-2, V41-3, V41-4 or merge merely to ask the Owner to relay another instruction.

For ordinary in-scope failures:

```text
fix -> rerun focused checks -> rerun full required gate -> continue
```

Stop early only for:

- a migration proven unavoidable;
- a required product semantic not covered by V4.1 authority;
- a requested Provider/Scheduler/whitelist/model/threshold/runtime-policy change;
- inability to obtain or verify the Owner reference artifacts;
- a critical deployment failure after automatic rollback;
- a security or data-integrity conflict outside current scope.

## 5. Terminal classifications

```text
DASHBOARD_V41_POSTDEPLOY_READY_FOR_OWNER_ACCEPTANCE
DASHBOARD_V41_DEPLOYMENT_ROLLED_BACK
DASHBOARD_V41_SCOPE_BLOCKED_OWNER_DECISION_REQUIRED
```

No terminal classification authorizes Round4.

## 6. Permanent stop lines

```text
NEW_PROVIDER_OR_PLAN = NOT_AUTHORIZED
MANUAL_PROVIDER_PROBE = FORBIDDEN
SCHEDULER_OR_CADENCE_CHANGE = NOT_AUTHORIZED
ACTIVE_WHITELIST_CHANGE = NOT_AUTHORIZED
MODEL_FACTOR_THRESHOLD_CHANGE = NOT_AUTHORIZED
MODEL_RETRAINING = NOT_AUTHORIZED
MARKET_DIRECTION_BENCHMARK_DEFINITION = NOT_AUTHORIZED
EXTERNAL_INTELLIGENCE_ACTIVATION = NOT_AUTHORIZED
PHASE_0_5_REEXECUTION = FORBIDDEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
ROUND_4_START = NOT_AUTHORIZED
P6_EXECUTION = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
READ_PROVIDER_CALLS = 0_REQUIRED
READ_DB_BUSINESS_WRITES = 0_REQUIRED
VPS_DIRECT_GHCR_BULK_IMAGE_PULL = FORBIDDEN_AS_PRIMARY_TRANSPORT
IMAGE_TRANSPORT = LOCAL_OCI_RELAY_PRIMARY
DELETE_PROTECTED_HISTORICAL_EVIDENCE = FORBIDDEN
```