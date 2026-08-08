# W2 Round 3 — Dashboard Reality & Visual Semantics Binding Addendum

```text
AUTHORITY = BINDING_ADDENDUM_TO_ROUND_3
TASK = W2_MI_R3_MARKET_RADAR_AND_MODEL_LAB
OWNER_DECISION = APPROVED
ROUND_1 = CLOSED_PASS_DO_NOT_REOPEN
ROUND_3 = AUTHORIZED_IN_PROGRESS
```

This addendum is binding with, and narrows where necessary, `ROUND_3_OWNER_AUTHORIZATION.md`, `ROUND_3_CODEX_EXECUTION.md`, and `ROUND_3_ACCEPTANCE_CRITERIA.md`.

It exists to prevent two classes of product error:

1. designing a rich market timeline before proving the persisted timeline depth actually exists;
2. visually presenting model-vs-market divergence as an opportunity signal even when the product text says otherwise.

## A0 — Exact-main active UI reality gate

Before changing Dashboard UI, re-fetch exact latest `origin/main` and prove the active page/component chain from code and tests.

The Round-3 authorization baseline is:

```text
MAIN_SHA_AT_AUTHORIZATION = c241b877a4168659f465163108f7a53fb8fd82a5
```

At that exact main, the repository contains `apps/web/src/components/IntelligenceConsole.tsx`, whose public surfaces are already:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Round 1 is therefore historical PASS and MUST NOT be reopened or restated as unimplemented.

Codex must still prove the live route/entry chain from exact current main before editing. If main has moved since authorization, record the new exact SHA and the actual active chain.

Do not write a spec that assumes a component exists merely because an old plan or local worktree says it does. Conversely, do not delete or replace a current intelligence surface based on a stale local worktree.

Required evidence:

```text
ACTIVE_DASHBOARD_ROUTE
ACTIVE_PAGE_COMPONENT
ACTIVE_INTELLIGENCE_COMPONENT
LEGACY_RECOMMENDATION_COMPONENT_RUNTIME_REACHABILITY
EXACT_MAIN_SHA
```

The public root must remain intelligence-first. Legacy recommendation components may remain for compatibility only if they are not public product authority.

## A1 — Timeline reality gate before chart design

Storage capability is not sufficient proof that a useful timeline exists.

Before rendering a line/path chart, audit the real persisted data available to the Round-3 read path for eligible existing-whitelist fixtures and AH/OU markets.

Measure at minimum:

```text
fixture_id
competition_id
canonical_market
canonical_line
valid_snapshot_count
distinct_captured_at_count
earliest_captured_at
latest_captured_at
bookmaker_count_by_snapshot
same_line_comparable_snapshot_count
raw_payload_lineage_complete
endpoint_capture_lineage_complete
```

Use code, models/migrations and real persisted evidence. Do not infer multi-snapshot depth from table schema alone.

Historical W2 evidence has previously shown a real baseline with zero fixtures having 2+ timeline snapshots. Therefore multi-point coverage must be re-proven for the current Round-3 data, not assumed.

### Required sparse timeline semantics

If the repository already has canonical equivalent reason/status codes, reuse them. Otherwise Round 3 must expose explicit product/read-model states equivalent to:

```text
0 comparable snapshots -> INSUFFICIENT_NO_TIMELINE_EVIDENCE
1 comparable snapshot  -> INSUFFICIENT_SINGLE_SNAPSHOT
2+ comparable snapshots -> MOVEMENT_COMPARISON_ELIGIBLE
```

For 0 or 1 point:

- render a deliberate empty/single-observation state;
- show the latest verified market fact if one exists;
- explain that movement cannot be inferred;
- do not draw a fake line segment;
- do not interpolate;
- do not duplicate one point to create a visual path;
- do not label STABLE merely because movement cannot be measured.

`STABLE`, `PRICE_MOVEMENT`, `LINE_MOVEMENT`, and `LINE_AND_PRICE_MOVEMENT` require sufficient comparable real observations under the final accepted evidence contract.

Tests MUST cover 0, 1, and 2+ valid comparable snapshots for AH and OU.

## A2 — Current collection-policy reality

The deployed Free bridge is checkpoint/cache driven, not an unlimited fixed-frequency odds poller.

Round 3 must preserve:

```text
API_FOOTBALL_PLAN = FREE
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
AUTOMATIC_RETRY = false
FREE_BRIDGE_MODE = SHADOW_ONLY
NO_IDLE_POLLING = true
```

Do not increase Provider cadence merely to make a prettier chart.

If existing normal Shadow collection naturally provides only one snapshot for a fixture/market, the UI must show the truthful single-snapshot state. Round 3 may improve read models; it does not authorize quota-wasting collection expansion for visualization.

## A3 — Model Lab must use monitoring/sensor semantics

A model point outside the real bookmaker de-vig probability band is a diagnostic warning, not a discovery/opportunity visual.

The visual metaphor must be:

```text
MARKET_RANGE = REFERENCE/OBSERVED ENVELOPE
MODEL_OUTSIDE_RANGE = INVESTIGATE MODEL / DATA / CALIBRATION
```

It must NOT visually imply:

```text
MODEL_FOUND_HIDDEN_VALUE
MODEL_BEATS_MARKET
BETTING_EDGE
OPPORTUNITY
```

### Forbidden positive encoding for disagreement

For `MODEL_OUTSIDE_MARKET_RANGE`, do not use visual treatment whose ordinary product meaning is positive opportunity, including:

- green success emphasis;
- profit/value badges;
- upward gain arrows;
- "edge", "value", "机会", "优势" copy;
- CTA styling associated with action or purchase/bet.

Use neutral/attention/warning treatment.

Required explanatory copy must communicate the semantic equivalent of:

```text
模型超出市场区间表示需要优先检查模型校准、特征时效、盘口身份和数据质量；不代表市场机会。
```

## A4 — Frozen historical model-validation context must be visible with Model Lab

When Model Lab displays model-market disagreement diagnostics, the same diagnostic surface must expose the frozen historical validation context for the model/edge research lineage so the visual cannot be read as an opportunity detector.

Bind, without recomputation or reopening Phase 0.5:

```text
PHASE_0_5_PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
FINAL_VERDICT = NO_EDGE
V_CONTINUATION_GATE = FAIL
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32%
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

This may be a compact always-visible line plus expandable details, but the public diagnostic must make the core fact obvious:

```text
HISTORICAL_INCREMENTAL_EDGE = NOT_PROVEN
```

Do not rerun Phase 0.5. Do not use current Round-3 data to reinterpret its frozen verdict.

## A5 — Cockpit information architecture within Round 3

Do not reopen Round 1. Round 1 already established the intelligence-first product shell.

Round 3 may refine the existing intelligence UI into a cockpit hierarchy while implementing Market Radar / Model Lab.

Recommended hierarchy:

```text
1. TODAY / MARKET OVERVIEW
   - monitored/today fixtures
   - market movement
   - model disagreement
   - data incidents
   - collection incidents
   Maximum five primary top counters.

2. ATTENTION FEED
   Sort by frozen seven-state precedence first, kickoff second.
   Attention != recommendation.

3. MATCH INTELLIGENCE
   - Market Radar
   - Model Lab
   - four independent risk dimensions
   - evidence/reason details on demand

4. DATA & OPERATIONS
   Compact health strip on primary view; detailed operational evidence expandable or secondary.
```

If the two-PR Round-3 allowance is used, the preferred split is:

```text
PR1 = truth/read-model/timeline reality + Model Lab semantic isolation + API contracts
PR2 = cockpit visual hierarchy / charts / attention feed / compact Ops
```

This is a Round-3 implementation split, NOT a reopening of Round 1.

## A6 — Attention Feed semantics

Ranking may use only the frozen intelligence-state precedence and deterministic tie-breakers.

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Then sort by kickoff and stable fixture ID.

Do not create a hidden composite opportunity score, betting score, edge score, or value score.

The feed answers:

```text
WHAT NEEDS INVESTIGATION FIRST
```

not:

```text
WHAT SHOULD I BET FIRST
```

## A7 — Market anomaly remains uncalibrated unless evidence proves otherwise

Round 3 must not manufacture anomaly thresholds to fill the cockpit.

If current persisted evidence cannot support a preregistered/calibrated anomaly rule:

```text
STATISTICAL_ANOMALY_CALIBRATION = NOT_CALIBRATED
```

is a valid PASS state.

Do not use high overround, large movement, or model divergence as a proxy for anomaly/value/opportunity without an independently justified contract.

## A8 — Acceptance additions

The existing `ROUND_3_ACCEPTANCE_CRITERIA.md` remains binding. Add these hard gates:

```text
R3_A0_EXACT_ACTIVE_UI_CHAIN_PROVEN = PASS
R3_A1_REAL_TIMELINE_DEPTH_AUDITED = PASS
R3_A1_ZERO_POINT_UI = PASS
R3_A1_SINGLE_POINT_UI = PASS
R3_A1_MULTI_POINT_UI = PASS
R3_A1_FAKE_OR_INTERPOLATED_TIMELINE_POINTS = 0
R3_A2_COLLECTION_CADENCE_EXPANDED_FOR_UI = false
R3_A3_MODEL_OUTSIDE_RANGE_POSITIVE_OPPORTUNITY_ENCODING = 0
R3_A4_PHASE_0_5_FROZEN_NO_EDGE_CONTEXT_VISIBLE = PASS
R3_A4_PHASE_0_5_REEXECUTION = false
R3_A5_ATTENTION_FEED_USES_ONLY_FROZEN_PRECEDENCE = PASS
R3_A7_ANOMALY_THRESHOLD_INVENTED = false
```

Public-read Provider calls remain zero.

Repository hygiene remains mandatory before Round-3 PASS.

## Stop line

This addendum does not authorize:

- Provider purchase/renewal;
- higher collection cadence merely for chart density;
- whitelist expansion;
- audit-only league promotion;
- Phase 0.5 reopening;
- Candidate/Formal/Lock/Production;
- betting/value/opportunity semantics;
- real-money behavior.
