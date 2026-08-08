# W2 MI Round 3 Final Receipt

```text
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
RESULT = PASS_MARKET_RADAR_MODEL_LAB
COMPLETED_AT = 2026-08-08T18:37:52+08:00
NEXT = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
```

## Source, PR, CI and immutable release

```text
R3_BASE_MAIN_SHA = c241b877a4168659f465163108f7a53fb8fd82a5
R3_FINAL_MAIN_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
PR_NUMBER = 497
PR_FINAL_HEAD_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
PR_MERGE_SHA = f0fe9d332d05a84f1ef04be86fd9fb44b69d69e3
PR_FAST_RUN_ID = 31251369393_PASS
CONTEXT_ONLY_RUN_ID = 31251369519_PASS
RELEASE_CANDIDATE_RUN_ID = 31251401584_PASS
MAIN_PROMOTION_RUN_ID = 31251800708_PASS
DEPLOYED_SOURCE_SHA = 51ebbeabc5497ce48708b3587705e2922c4805da
DEPLOYED_SOURCE_TREE_SHA = 74bc040446b753449ca9ec567db208de3576f006
DEPLOYED_PYTHON_DIGEST = sha256:40f5443f2179776a20cf27695d361946aa63c7b6af83be23f996f93852ef8e7b
DEPLOYED_WEB_DIGEST = sha256:b74ae5aca38f82b3380d5f489f0fe03b317e645f1f56a8d3af39dac080fc9bb7
IMMUTABLE_DEPLOYMENT = PASS
HEALTH = PASS
READY = PASS
RELEASE_SYNC = PASS
```

The release script reported 429 seconds for full CI, 203 seconds for image
preheat and 41 seconds for the deployment switch. The deployed API and Web
both report the exact accepted source identity.

## A0 — exact active UI and legacy reachability

The pre-change exact-main audit used `c241b877a4168659f465163108f7a53fb8fd82a5`.

```text
ACTIVE_DASHBOARD_ROUTE = / and every non-/performance fallback
ACTIVE_PAGE_COMPONENT = DashboardPage
ACTIVE_INTELLIGENCE_COMPONENT = IntelligenceConsole
ACTIVE_CHAIN = apps/web/src/main.tsx -> App.tsx -> DashboardPage -> IntelligenceConsole
PERFORMANCE_ROUTE = /performance -> PerformancePage
LEGACY_RECOMMENDATION_COMPONENT_RUNTIME_REACHABILITY = 0
LEGACY_COMPONENTS = BossDecisionView, RecommendationBoard, RecommendationCard
R3_A0_EXACT_ACTIVE_UI_CHAIN_PROVEN = PASS
```

Legacy recommendation components remain only as compatibility/reference
assets. Contract tests prove that no public root import reaches them.

## A1 — real persisted timeline reality

The database contained exactly 124 fixture identities across the unchanged 13
active competitions. Current raw capture availability by fixture and market was:

```text
RAW_CAPTURE_DEPTH_ASIAN_HANDICAP = 0:58 / 1:37 / 2+:29 / MAX:15
RAW_CAPTURE_DEPTH_TOTALS = 0:58 / 1:37 / 2+:29 / MAX:15
```

The stricter accepted Round-3 eligibility plus canonical-mainline builder,
materialized for all 124 active-whitelist fixtures, produced:

```text
VALID_TIMELINE_DEPTH_ASIAN_HANDICAP = 0:73 / 1:29 / 2+:22 / MAX:12
VALID_TIMELINE_DEPTH_TOTALS = 0:64 / 1:31 / 2+:29 / MAX:12
```

The live public future DayView exposed 128 fixture-market diagnostics across
64 cards:

```text
PUBLIC_TIMELINE_DEPTH_COMBINED = 0:92 / 1:9 / 2+:27
INSUFFICIENT_NO_OR_SINGLE = 101
MOVEMENT_COMPARISON_ELIGIBLE = 27
```

For every public market with fewer than two valid snapshots, movement was
`INSUFFICIENT`, movement history was empty and fewer than two real points were
renderable. Every 2+ case contained at least two persisted points and a factual
movement state. Tests cover AH and OU at 0, 1 and 2+ snapshots.

```text
R3_A1_REAL_TIMELINE_DEPTH_AUDITED = PASS
R3_A1_ZERO_POINT_UI = PASS
R3_A1_SINGLE_POINT_UI = PASS
R3_A1_MULTI_POINT_UI = PASS
R3_A1_FAKE_OR_INTERPOLATED_TIMELINE_POINTS = 0
R3_A2_COLLECTION_CADENCE_EXPANDED_FOR_UI = false
```

## Real persisted public acceptance

The existing write-side materializer projected the accepted evidence into the
existing checkpoint model. No duplicate persistence model or read-time market
query path was introduced.

```text
FROZEN_PUBLIC_ARTIFACTS_WITH_ROUND3 = 378
SHADOW_READ_AUTHORITY_ARTIFACTS_WITH_ROUND3 = 69_OF_69
PUBLIC_DAYVIEW_CARD_COUNT = 64
PUBLIC_ACCEPTED_OBSERVATIONS = 14784
PUBLIC_REJECTED_OBSERVATIONS = 1521
PUBLIC_REJECTED_BY_REASON = UNSUPPORTED_MARKET:1521
PUBLIC_READ_SOURCE = analysis_card_checkpoint
PUBLIC_READ_ADDITIONAL_QUERY_COUNT = 0
PUBLIC_READ_PROVIDER_CALLS = 0
```

Radar and movement counts from the real public response:

```text
RADAR_READY = 36
RADAR_INSUFFICIENT = 92
MOVEMENT_INSUFFICIENT = 101
MOVEMENT_STABLE = 2
MOVEMENT_PRICE = 21
MOVEMENT_LINE = 0
MOVEMENT_LINE_AND_PRICE = 4
STATISTICAL_ANOMALY_CALIBRATION = NOT_CALIBRATED
ANOMALY_THRESHOLD_INVENTED = false
```

Model Lab truthfully remained non-ready for the current public evidence:

```text
MODEL_LAB_MARKET_NOT_READY = 125
MODEL_LAB_MODEL_NOT_READY = 2
MODEL_LAB_INSUFFICIENT_BOOKMAKER_DEPTH = 1
MODEL_LAB_COMPARABLE_WITHIN_MARKET_RANGE = 0
MODEL_LAB_MODEL_OUTSIDE_MARKET_RANGE = 0
MODEL_LAB_ACTION_AUTHORITY = NONE
```

No model-ready comparison was manufactured. The public contract and visual
copy treat an outside-range result as a sensor warning requiring model/data/
calibration/market-identity review, never as value or opportunity.

```text
R3_A3_MODEL_OUTSIDE_RANGE_POSITIVE_OPPORTUNITY_ENCODING = 0
FORBIDDEN_OPPORTUNITY_SCORE_KEYS = 0
FORBIDDEN_VALUE_SCORE_KEYS = 0
ATTENTION_ORDER = FROZEN_PRECEDENCE_THEN_KICKOFF_THEN_FIXTURE_ID
R3_A5_ATTENTION_FEED_USES_ONLY_FROZEN_PRECEDENCE = PASS
```

## Frozen Phase 0.5 context

Every public Model Lab block exposes the same frozen validation context:

```text
PHASE_0_5_FINAL_VERDICT = NO_EDGE
V_CONTINUATION_GATE = FAIL
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32%
HISTORICAL_INCREMENTAL_EDGE = NOT_PROVEN
H_RESULT_ACCESS = PERMANENTLY_CLOSED
PHASE_0_5_REEXECUTION = false
R3_A4_PHASE_0_5_FROZEN_NO_EDGE_CONTEXT_VISIBLE = PASS
```

## Gates

```text
FOCUSED_COMBINED = 147_PASSED
LATEST_FOCUSED = 36_PASSED
FULL_PYTEST = 2490_PASSED_13_SKIPPED
RUFF = PASS
MYPY = PASS_280_SOURCE_FILES
STAGE1_CONTRACTS = PASS
TRACKED_OUTPUTS = PASS
CHECK_W2_ALL = PASS
SECRET_SCAN = PASS
PROTECTED_BOSS_BASELINE = PASS
WEB_TYPECHECK_BUILD = PASS
RELEVANT_PLAYWRIGHT = 6_OF_6_PASS
PR_FAST = PASS
RELEASE_CANDIDATE = PASS
PROVIDER_CALLS_DURING_DEV_CI = 0
```

## Provider, bridge and product stop lines

Dashboard/API reads were measured at Provider request-log count 646 before and
646 after. Manual Provider calls for Round-3 acceptance were zero.

Restoring the already accepted bridge runtime from an unintended deployment
default of `OFF` to `SHADOW_ONLY` allowed two normal scheduler activations.
They used six accepted automatic calls in total (640 to 646), under the existing
cache/quota contract; they were not manual Round-3 probes. No cadence, endpoint
allowlist or scheduler was added or expanded.

```text
API_FOOTBALL_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
PROVIDER_HTTP_MAX_ATTEMPTS = 1
IDS_BATCHING = false
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
AUDIT_ONLY_RUNTIME_REACHABILITY = 0
RECOMMENDATION_ROWS = 0
RECOMMENDATION_LOCK_ROWS = 0
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
REAL_MONEY = NOT_AUTHORIZED
```

## Non-destructive rollback

The bridge was explicitly set to `OFF` for the rollback test. The runtime was
then switched from the Round-3 immutable images to the prior accepted
`c241b877…` images and restored to `51ebbeab…`.

The rollback-phase persisted fingerprint remained byte-for-byte count stable:

```text
RAW_PAYLOAD = 559_TO_559
ENDPOINT_CAPTURE = 490_TO_490
FIXTURE_IDENTITY = 124_TO_124
MARKET_OBSERVATION = 71698_TO_71698
PROVIDER_REQUEST_LOG = 643_TO_643
RECOMMENDATION = 0_TO_0
RECOMMENDATION_LOCK = 0_TO_0
ACTIVE_WHITELIST = 13_TO_13
ROLLBACK_TO_PREVIOUS_IMAGE = PASS
RESTORE_ROUND3_IMAGE = PASS
```

After the accepted `SHADOW_ONLY` bridge was restored, normal scheduler
collection advanced persisted evidence to `562 / 493 / 124 / 72614` for raw /
capture / identity / market observations. Final Provider log count was 646;
recommendations and locks remained zero.

## Repository hygiene

- `KEEP`: the pure Round-3 market intelligence builder, bounded persisted
  evidence query, write-side checkpoint integration, DayView/intelligence
  projection changes, public Web components/types/styles and their tests.
- `RETAIN_FOR_EVIDENCE`: canonical architecture checklist updates, this final
  receipt, CI/release/run IDs and immutable deployment/rollback evidence.
- `DELETE`: none. No one-off diagnostic script, duplicate DTO/model, scheduler,
  feature flag, tracked generated output or stale fixture was introduced.
- Legacy recommendation components remain compatibility/reference assets and
  are proven unreachable from the public runtime; this round does not authorize
  their deletion.

Ignored virtual environments, caches, Web build output and Playwright results
were not tracked.

```text
REPOSITORY_HYGIENE = PASS
DEAD_ASSETS_FOUND = 0
DEAD_ASSETS_DELETED = 0
OBSOLETE_CODE_LINES_REMOVED = 0
RETAINED_FOR_EVIDENCE = ROUND3_CONTRACTS_TESTS_CI_DEPLOYMENT_ROLLBACK_AND_FINAL_RECEIPT
UNRESOLVED_HYGIENE_ITEMS = 0
```

## Final state

```text
ROUND_3 = PASS_MARKET_RADAR_MODEL_LAB
ACTIVE_WHITELIST = 13_UNCHANGED
FREE_BRIDGE_MODE = SHADOW_ONLY
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
NEXT = AWAIT_OWNER_POST_R3_PRODUCT_DECISION
```
