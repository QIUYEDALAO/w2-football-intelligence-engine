# W2 MI Round 1 — Acceptance Criteria

This file is the binding acceptance standard for `W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME`.

Round 1 is PASS only when all required items below pass on the final exact PR head and the deployed public product.

## A. Source and scope identity

Required evidence:

```text
AUDITED_BASE_MAIN_SHA = exact origin/main used for implementation
RUNTIME_PR_NUMBER = one PR only
FINAL_PR_HEAD_SHA = exact final PR head
CHANGE_CLASS = runtime API/Web
```

Fail if Round 1 is split across multiple runtime PRs or multiple deployments.

## B. Existing whitelist preservation — hard gate

Before and after runtime change, collect the authoritative active-whitelist identity set.

Required baseline count:

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
```

Required baseline identities:

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

Acceptance:

```text
ACTIVE_WHITELIST_BEFORE = 13
ACTIVE_WHITELIST_AFTER = 13
ACTIVE_WHITELIST_IDENTITY_DIFF = EMPTY
NEW_LEAGUES_REGISTERED_IN_R1 = 0
NEW_LEAGUES_ENABLED_IN_R1 = 0
```

The European 5+6 grouping must not replace or reduce the existing 13.

The four future net-new candidates — Belgian Pro League, Turkish Super Lig, Greek Super League, Scottish Premiership — must remain **not started** in Round 1.

## C. Provider and Scheduler invariants — hard gate

Required:

```text
PROVIDER_POLICY_DIFF = EMPTY
PROVIDER_ALLOWLIST_DIFF = EMPTY
SCHEDULER_POLICY_DIFF = EMPTY
NEW_PROVIDER_CALLS_FROM_R1 = 0
```

No new endpoint frequency, retry policy, quota rule, competition scheduling, or Provider enablement may be introduced.

Candidate/Formal/Lock/Production must remain OFF.

## D. Public authority switch

Each public DayView/fixture intelligence projection must expose:

```text
intelligence_state
intelligence_reason_codes
risk_dimensions
recommendation_decision_v4_role
```

Required role:

```text
recommendation_decision_v4_role = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

V4 objects and historical settlement evidence remain available where required for diagnostics/history.

Fail if V4 outcome alone still controls:

- card visibility;
- market fact visibility;
- public top-level state;
- public ranking/priority;
- opportunity/recommendation semantics;
- public product counters.

## E. Seven-state deterministic contract

Required states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Required precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Tests must prove deterministic precedence and stable reason-code ordering.

Round 1 must not introduce new Round 3 market-alert thresholds.

## F. MARKET_STABLE and zero-alert behavior — hard gate

Construct/retain a valid fixture/day with no material alert.

Required result:

```text
intelligence_state = MARKET_STABLE
```

Browser must show a meaningful stable-state message such as:

```text
市场稳定 / 未检测到显著异常
```

A day with zero material alerts must not become blank, error, degraded solely because alert count is 0, or trigger lower thresholds to manufacture content.

A truly fixture-empty day remains an explicit empty-day state and must not fabricate stable fixtures.

## G. Divergence guard — hard gate

Given model-market divergence evidence, the canonical public projection must produce diagnostic semantics only.

Allowed examples:

```text
MODEL_MARKET_DISAGREEMENT
模型与市场存在分歧
模型校准需要复核
模型特征可能陈旧
市场信息尚未被模型解释
模型漂移/过度自信复核
```

The public projection, Web adapters, counters, labels, tooltips, ranking and live DOM must not derive from divergence any meaning equivalent to:

```text
value opportunity
positive edge
market mispricing
recommended side
high-confidence pick
worth entering
价值机会
正 EV 机会
市场错误定价
推荐方向
高置信度选择
值得介入
```

Fail if any divergence magnitude/status/direction_allowed threshold still determines recommendation readiness or public priority.

## H. Market fact visibility independence

Regression case:

- real, legitimate market evidence exists;
- V4 is `NOT_READY`, `NO_EDGE`, or has no selected candidate/pick.

Required:

- legitimate current market facts remain visible if current/fresh;
- legitimate last-known/reference facts remain visible with explicit stale/reference labeling;
- stale/reference facts are never promoted to current/executable;
- current odds/market probabilities are not cleared merely because there is no V4 pick.

## I. Four independent risk dimensions

Every public fixture exposes four distinct dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Tests must cover at least:

1. lineup/injury/event fact -> event evidence;
2. identity/xG/quote/readiness problem -> data evidence;
3. calibration/simulation/model-readiness/divergence -> model evidence;
4. Provider/Scheduler/schema/runtime failure -> collection evidence.

Fail if:

- `NOT_READY/BLOCKED` is presented as a high-risk match;
- data + collection are collapsed into one product risk;
- a risk dimension implies a betting recommendation.

## J. Public product identity and structure

Browser `<title>` and visible brand must use:

```text
W2 Football Intelligence
```

The root product must clearly contain:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Chinese labels may be primary, but these three product roles must be unambiguous.

## K. Market Overview counters

Required public counters:

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

Optional:

```text
market anomalies
model-market disagreements
```

The root Market Overview must not use these as primary product KPIs:

```text
analysis picks
formal recommendations
lock eligible
NO_EDGE
opportunities
positive EV
```

## L. Match Intelligence behavior

At least one production-shaped real card must render without fabricated values.

Card primary state is `intelligence_state`, not `decision_tier`.

Market/model probabilities may be shown where real and properly sourced.

Their difference must be described as model-market disagreement/diagnostic difference, never value/edge/opportunity.

Public main card/table must not use recommendation-first labels such as:

```text
分析建议
正式建议
今日重点决策
分析盘口
推荐方向
```

Historical/technical details may remain under clearly diagnostic/history surfaces.

## M. Data & Operations Summary

Must preserve real operational truth including, where already available:

```text
page update time
latest confirmed odds time
next refresh/checkpoint
Provider status/budget
Scheduler/runtime status
stale/data incidents
collection incidents
release SHA/API-Web sync
```

Must show safety switches remain OFF:

```text
Candidate OFF
Formal OFF
Lock OFF
Production OFF
```

## N. Historical compatibility

Do not delete or rewrite historical V4/settlement/replay identities merely for product semantics.

Existing historical settlement and replay tests must remain green.

If historical performance/CLV/hit-rate views remain public, they must be clearly historical diagnostics and not presented as evidence of current betting edge.

## O. API/Web tests

Required automated coverage at minimum:

1. `MARKET_STABLE` renders non-empty.
2. `MARKET_MOVEMENT` uses existing movement evidence only.
3. `MARKET_ANOMALY` uses existing explicit anomaly evidence only.
4. `MODEL_MARKET_DISAGREEMENT` cannot produce recommendation/opportunity language.
5. `DATA_INCOMPLETE` does not become high-risk match.
6. `MODEL_DIAGNOSTIC_WARNING` remains diagnostic.
7. `COLLECTION_INCIDENT` remains collection-specific.
8. four risk dimensions remain independent.
9. V4 role is diagnostic-only.
10. market facts survive V4 no-pick/not-ready cases.
11. current real data cards still render.
12. empty-day remains explicit and nonblank.
13. API/Web release SHA sync remains correct.
14. Candidate/Formal/Lock/Production remain OFF.
15. active whitelist remains exact 13.
16. browser console errors = 0.

## P. Delivery acceptance

Required sequence:

```text
ONE_RUNTIME_PR = true
PR_FAST_REQUIRED = SUCCESS
ONE_FINAL_EXACT_HEAD_FULL_RC = SUCCESS
MERGE_METHOD = MERGE_COMMIT
AUTO_MERGE = false
ONE_DEPLOYMENT = true
API_WEB_SAME_VERIFIED_SOURCE = true
PUBLIC_BROWSER_ACCEPTANCE = PASS
```

The final Full Release Candidate must be bound to the final PR head SHA. Do not reuse an RC from another SHA.

## Q. Final receipt

The final Round 1 receipt must include:

```text
AUDITED_BASE_MAIN_SHA
RUNTIME_PR_NUMBER
FINAL_PR_HEAD_SHA
PR_FAST_RUN
PR_FAST_RESULT
FULL_RC_RUN
FULL_RC_RESULT
RC_SOURCE_SHA
RC_SOURCE_TREE_SHA
API_IMAGE_DIGEST
WEB_IMAGE_DIGEST
MERGE_SHA
DEPLOYED_API_SHA
DEPLOYED_WEB_SHA
PUBLIC_BROWSER_ACCEPTANCE
BROWSER_CONSOLE_ERRORS
ACTIVE_WHITELIST_BEFORE
ACTIVE_WHITELIST_AFTER
ACTIVE_WHITELIST_IDENTITY_DIFF
INTELLIGENCE_STATE_TESTS
DIVERGENCE_GUARD_TESTS
FOUR_RISK_DIMENSION_TESTS
MARKET_STABLE_ZERO_ALERT_TEST
REAL_CARD_TEST
EMPTY_DAY_TEST
PROVIDER_POLICY_DIFF
PROVIDER_ALLOWLIST_DIFF
SCHEDULER_POLICY_DIFF
NEW_PROVIDER_CALLS
CANDIDATE
FORMAL
LOCK
PRODUCTION
ROUND_2
ROUND_3
```

Expected final state:

```text
PRODUCT = W2 Football Intelligence
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
ACTIVE_WHITELIST = 13_UNCHANGED
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
NEW_PROVIDER_CALLS = 0
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
ROUND_1 = PASS
```

After PASS, stop. Round 2 requires a new explicit owner authorization/next action.
