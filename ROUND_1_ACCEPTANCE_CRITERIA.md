# W2 MI Round 1 — Binding Acceptance Criteria

This file is the binding acceptance standard for:

```text
W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Owner instruction:

```text
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_RUNTIME_PR = 493
```

Round 1 is PASS only when **every mandatory gate below passes on the final exact PR head and the deployed public product**.

A failed gate means:

```text
DO_NOT_ADVANCE
REMEDIATE_IN_SAME_PR
REVALIDATE
CONTINUE_UNTIL_ALL_PASS
```

A failed gate does **not** mean the task is complete. No additional owner authorization is required for bounded Round 1 remediation inside PR #493.

Never bypass, weaken, skip, xfail, delete, rebaseline or falsify a required gate to obtain PASS.

---

## A. Current failure baseline and remediation target

The first Full RC attempt is permanent evidence:

```text
AUDITED_BASE_MAIN_SHA = 84e642f3ea26464574f75ee4d520b38bcf24073a
RUNTIME_PR_NUMBER = 493
FAILED_PR_HEAD_SHA = 5479e1f1f419e2fc15b69882aaa0c323c966ce1d
PR_FAST_RUN = 31151508691
PR_FAST_RESULT = SUCCESS
FAILED_FULL_RC_RUN = 31151557970
FAILED_FULL_RC_RESULT = FAILURE
FAILED_GATE = BOSS_CONSOLE_PROTECTED_BASELINE
FAILED_FILE = apps/web/src/components/DecisionCounts.tsx
EXPECTED_DECISION_COUNTS_SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
FAILED_DECISION_COUNTS_SHA256 = 4d16bdcede5cf96d17ecf346e1872b5db58139c470ef1227786a6667166a7d5a
MERGE = NOT_EXECUTED
DEPLOYMENT = NOT_EXECUTED
```

The final receipt must preserve this failed-attempt evidence and separately identify the final successful head/RC.

### A1. Protected baseline remediation — hard gate

Required before the next Full RC:

```text
apps/web/src/components/DecisionCounts.tsx
SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
```

Required:

```text
python3 scripts/check_boss_console_baseline.py = PASS
```

Forbidden remediation:

```text
MODIFY_BOSS_CONSOLE_VISUAL_AUTHORITY_HASHES = false
WEAKEN_BASELINE_CHECK = false
DELETE_PROTECTED_FILE = false
SKIP_BASELINE_CHECK = false
```

These files must not be modified merely to make the gate green:

```text
docs/ui/boss-console/BOSS_CONSOLE_VISUAL_AUTHORITY_V2.json
scripts/check_boss_console_baseline.py
```

### A2. Intelligence-only overview separation — hard gate

The new Market Overview must use a new intelligence-only component rather than changing the protected legacy `DecisionCounts.tsx`.

Acceptance evidence must prove:

```text
PUBLIC_INTELLIGENCE_ROOT_IMPORTS_LEGACY_DECISION_COUNTS = false
MARKET_OVERVIEW_HAS_INTELLIGENCE_ONLY_COMPONENT = true
```

The new intelligence overview component must expose the Round 1 overview metrics without changing the protected Boss Console authority.

---

## B. Source, PR and scope identity

Required final evidence:

```text
ORIGINAL_AUDITED_BASE_MAIN_SHA = 84e642f3ea26464574f75ee4d520b38bcf24073a
RUNTIME_PR_NUMBER = 493
RUNTIME_PR_COUNT = 1
FINAL_PR_HEAD_SHA = exact final accepted PR head
FINAL_SOURCE_TREE_SHA = exact tree of final accepted PR head
CHANGE_CLASS = runtime API/Web
```

If `main` advances before final merge, record the compatibility reconciliation separately. Do not erase the original audited baseline.

Fail if:

- a second runtime/remediation PR is created for Round 1;
- unrelated refactors are added;
- Round 2/3 work enters PR #493;
- context-only files are copied into PR #493 solely to change authority.

---

## C. Existing whitelist preservation — hard gate

Authoritative active whitelist before and after must be exactly 13.

Required identities:

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
NEW_LEAGUES_SCHEDULED_IN_R1 = 0
```

The European `5 + 6` grouping must not replace/reduce the current 13.

The four future net-new candidates remain not started:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union may remain documented as `13 + 4 = 17`, but Round 1 must not activate any of the four.

---

## D. Provider and Scheduler invariants — hard gate

Required code/config diff evidence:

```text
PROVIDER_POLICY_DIFF = EMPTY
PROVIDER_ALLOWLIST_DIFF = EMPTY
SCHEDULER_POLICY_DIFF = EMPTY
NEW_PROVIDER_ENDPOINTS = 0
NEW_PROVIDER_FREQUENCIES = 0
NEW_PROVIDER_RETRIES = 0
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
```

No Round 1 validation step may deliberately call Provider to prove UI/API semantics.

Do not modify:

- endpoint allowlist;
- scheduler cadence/concurrency;
- retry policy;
- quota policy;
- league scheduling;
- live collection enablement.

Required safety states:

```text
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

---

## E. Public authority switch — hard gate

Each public DayView/fixture intelligence projection must expose:

```text
intelligence_state
intelligence_reason_codes
risk_dimensions
recommendation_decision_v4_role
```

Required:

```text
recommendation_decision_v4_role = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

V4 and historical settlement/replay evidence remain available where required for diagnostics/history.

Fail if V4 outcome alone still determines any public product behavior below:

```text
card visibility
current/last-known market fact visibility
top-level intelligence state
Market Overview counters
public ranking/priority
public next-attention semantics
opportunity/recommendation wording
```

Regression test requirement:

Change only V4 outcome while keeping the underlying market/data/model/collection diagnostic facts identical. The canonical intelligence state must not change solely because the V4 outcome changed.

---

## F. Seven-state deterministic contract — hard gate

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

Automated tests must prove:

1. exactly one top-level state is emitted;
2. precedence is deterministic;
3. secondary reason codes are preserved;
4. reason-code ordering is deterministic;
5. no state depends on random ordering or browser-only inference;
6. Round 1 does not invent new Round 3 thresholds.

Required test fixtures must cover all seven states.

If real current production-shaped evidence does not support a certain market anomaly/movement event, synthetic/contract test data may validate the mapping, but no fake production data may be deployed.

---

## G. MARKET_STABLE and zero-alert behavior — hard gate

Required fixture test:

- valid real-shaped market/data inputs;
- no higher-precedence incident/warning;
- no material movement/anomaly/disagreement evidence.

Required output:

```text
intelligence_state = MARKET_STABLE
```

Required browser copy must clearly communicate a stable result, e.g.:

```text
市场稳定 / 未检测到显著异常
```

Zero material alerts must be a successful product result.

Fail if zero alerts causes:

- empty product shell when fixtures exist;
- error state;
- artificial alert generation;
- lowered threshold;
- recommendation placeholder.

Separate empty-day test:

A truly fixture-empty day must show a meaningful explicit empty-day state and must not fabricate `MARKET_STABLE` fixtures.

---

## H. Divergence guard — hard gate

Given model-market divergence evidence, canonical public projection must produce diagnostic semantics only.

Allowed examples:

```text
MODEL_MARKET_DISAGREEMENT
模型与市场存在分歧
模型校准需要复核
模型特征可能陈旧
市场信息尚未被模型解释
模型漂移/过度自信复核
```

Forbidden public derivations include any semantic equivalent of:

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
优势机会
```

This guard applies to:

```text
API/read-model projection
Web normalization/adapter
Market Overview counters
Match Intelligence labels
sort/ranking logic
tooltips
badges
empty/stable copy
browser-visible DOM
```

Fail if any divergence magnitude/status/`direction_allowed` threshold determines recommendation readiness or public opportunity priority.

Automated regression must explicitly use a large divergence (including a case that would have crossed the old threshold) and prove no opportunity/recommendation semantics appear.

---

## I. Market-fact visibility independent of V4 — hard gate

Regression cases:

1. real current/fresh market evidence + V4 `NOT_READY`;
2. real current/fresh market evidence + V4 `NO_EDGE`;
3. real current/fresh market evidence + no selected candidate/pick;
4. stale/reference-only market evidence + no pick.

Required:

- legitimate current facts remain visible when current/fresh;
- legitimate last-known/reference facts remain visible with explicit reference/stale semantics;
- stale/reference facts are never promoted to current/executable;
- current odds/market probabilities are not cleared merely because V4 has no pick;
- market identity/source/freshness truth remains auditable.

Fail if public market visibility is still gated by `decision_tier`, V4 selected candidate, or recommendation readiness.

---

## J. Four independent risk dimensions — hard gate

Every public fixture exposes:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Each dimension requires:

```text
dimension
status
reason_codes
human explanation
```

Minimum automated cases:

1. actual lineup/injury/event fact -> `EVENT_RISK`;
2. identity/xG/required quote/readiness problem -> `DATA_RISK`;
3. calibration/simulation/model-readiness/divergence -> `MODEL_RISK`;
4. Provider/Scheduler/schema/runtime failure -> `COLLECTION_RISK`;
5. data and collection risk simultaneously present -> remain separate;
6. `NOT_READY/BLOCKED` without event evidence -> must not become a high-risk match.

Fail if:

- risks collapse into one generic high/medium/low betting risk;
- data + collection are merged into one product dimension;
- any risk dimension implies a betting recommendation.

---

## K. Public product identity and information architecture — hard gate

Browser `<title>` and visible product brand must contain:

```text
W2 Football Intelligence
```

Root product must visibly and unambiguously contain three surfaces:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Chinese primary headings are allowed, but the product roles must be clear.

Legacy recommendation-first root page must no longer be the public `/` authority.

Navigation terminology must be compatible with intelligence-first product semantics.

---

## L. Market Overview counters — hard gate

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

The public Market Overview must not use these as primary KPIs:

```text
analysis picks
formal recommendations
lock eligible
NO_EDGE
opportunities
positive EV
```

Counter reconciliation tests must prove each displayed count equals the canonical DayView intelligence projection population used by the page.

Zero values must render as valid zeroes, not disappear or trigger threshold changes.

---

## M. Match Intelligence behavior — hard gate

At least one production-shaped real card must render without fabricated values.

Required:

- primary status comes from `intelligence_state`;
- fixture/competition/team/kickoff identity remains visible;
- current/last-known market facts are truthful;
- model diagnostics are labeled as diagnostics;
- four risk dimensions are visible or inspectable;
- evidence/reason codes remain inspectable;
- no fake odds/model probability is substituted for missing data.

Market/model probabilities may be shown where real and properly sourced.

Their difference must be described as model-market disagreement/diagnostic difference, never edge/value/opportunity.

The public main card/table must not use recommendation-first labels such as:

```text
分析建议
正式建议
今日重点决策
分析盘口
推荐方向
值得介入
```

Historical/technical content may remain under clearly labeled historical/diagnostic surfaces.

---

## N. Data & Operations Summary — hard gate

Must preserve real operational truth already available, including where applicable:

```text
page update time
latest confirmed odds time
next refresh/checkpoint
Provider status/budget
Scheduler/runtime status
stale/data incident count
collection incident count
release SHA/API-Web sync
```

Required safety status display:

```text
Candidate OFF
Formal OFF
Lock OFF
Production OFF
```

Do not claim Scheduler/Provider health from hardcoded UI text if the canonical API/read-model reports otherwise. UI must use available runtime truth or an explicit UNKNOWN/unavailable state.

---

## O. Historical compatibility — hard gate

Do not delete/rewrite historical V4, DecisionContract, settlement, replay, capture or validation identities merely to satisfy new product semantics.

Required historical/replay/settlement regression tests remain green.

If `/performance` or other historical performance/CLV/hit-rate views remain public, they must be clearly framed as historical/model diagnostics and not evidence of current betting edge.

The protected Boss Console visual authority must continue to pass unchanged unless a separate future owner-approved visual-authority change explicitly supersedes it.

---

## P. Local validation before every new Full RC

For every remediation head, Codex must run the focused checks implicated by the diff.

For the current protected-baseline remediation, mandatory local commands include:

```text
python3 scripts/check_boss_console_baseline.py
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
```

Also run changed-path Python/static/contract tests and repository-required format/lint checks.

Before requesting Full RC, report a compact local matrix showing PASS/FAIL and exact head SHA.

Do not request Full RC with a known local failure.

---

## Q. Automated API/Web acceptance matrix

At minimum the final test suite must prove:

1. `MARKET_STABLE` renders non-empty;
2. zero-alert day with fixtures is valid;
3. truly empty day is explicit and nonblank;
4. `MARKET_MOVEMENT` consumes existing movement evidence only;
5. `MARKET_ANOMALY` consumes existing explicit anomaly evidence only;
6. `MODEL_MARKET_DISAGREEMENT` cannot produce recommendation/opportunity language;
7. `DATA_INCOMPLETE` does not become high-risk match;
8. `MODEL_DIAGNOSTIC_WARNING` remains diagnostic;
9. `COLLECTION_INCIDENT` remains collection-specific;
10. four risk dimensions remain independent;
11. V4 role is diagnostic-only;
12. market facts survive V4 no-pick/not-ready/no-edge cases;
13. current real data cards still render;
14. public Market Overview count reconciliation passes;
15. protected Boss Console baseline passes;
16. public intelligence root does not consume protected legacy DecisionCounts;
17. API/Web release SHA sync logic remains correct;
18. Candidate/Formal/Lock/Production remain OFF;
19. active whitelist remains exact 13;
20. browser console errors = 0 after deployment acceptance.

---

## R. PR Fast and remediation loop — hard gate

PR #493 is the only runtime PR.

Every source-changing remediation creates a new exact head.

For each new head:

```text
PR_FAST_REQUIRED = SUCCESS
```

If PR Fast fails:

- do not run Full RC;
- inspect the failure;
- fix in PR #493;
- repeat until PR Fast passes.

No owner reauthorization is needed for an in-scope Round 1 correction.

---

## S. Full Release Candidate loop — hard gate

There may be multiple failed RC attempts while converging, but only the final successful exact-head RC qualifies the release.

Required final condition:

```text
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
FINAL_RC_SOURCE_SHA = FINAL_PR_HEAD_SHA
FINAL_RC_SOURCE_TREE_SHA = FINAL_SOURCE_TREE_SHA
```

Rules:

- a source change requires a new exact-head Full RC;
- do not rerun/reuse an old RC as evidence for a changed SHA;
- do not reuse manifest/image identity across different source SHAs;
- a failed RC must be retained in the final receipt;
- failure means remediate in the same PR, not merge/deploy;
- do not weaken a guard because it blocked the RC.

All required Full RC jobs must pass, including Web protected baseline, Web typecheck/build/E2E, static, unit, integration, migration, staging parity, predeploy, packaging, image smoke and manifest/release-required gates according to the repository workflow.

Required final artifacts:

```text
RC_SOURCE_SHA
RC_SOURCE_TREE_SHA
API_IMAGE_DIGEST
WEB_IMAGE_DIGEST
RELEASE_MANIFEST = VALID
RELEASE_REQUIRED = SUCCESS
```

---

## T. Merge acceptance — hard gate

Merge is forbidden until the final exact-head Full RC succeeds.

Required:

```text
MERGE_METHOD = MERGE_COMMIT
AUTO_MERGE = false
MERGED_PR = 493
MERGE_SOURCE_HEAD = FINAL_PR_HEAD_SHA
```

No squash/rebase.

If PR head changes after successful RC, the successful RC is invalidated and a new exact-head Full RC is required before merge.

---

## U. Deployment acceptance — hard gate

Deploy only release artifacts verified by the final successful RC.

Required:

```text
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
DEPLOYED_API_SOURCE_SHA = FINAL_PR_HEAD_SHA
DEPLOYED_WEB_SOURCE_SHA = FINAL_PR_HEAD_SHA
DEPLOYED_API_SHA = DEPLOYED_WEB_SHA
API_WEB_RELEASE_IDENTITY = SYNC
```

Do not rebuild a different release after merge and call it equivalent.

Do not alter Provider/Scheduler/whitelist/product switches during deployment.

If deployment activation/preflight/health fails:

- fail closed;
- do not proceed to public acceptance as PASS;
- diagnose and remediate only inside authorized Round 1 boundaries;
- run required exact-head validation again before a replacement deployment if source changes.

---

## V. Public API acceptance — hard gate

After deployment, perform read-only public acceptance against at least:

```text
/
/v1/health
/v1/version
/v1/dashboard/day-view
/v1/fixtures/{real_fixture_id}/analysis-card
```

Use a real visible fixture when available. Do not create Provider calls merely to obtain one.

Required API evidence:

- health/readiness consistent with deployed release;
- DayView exposes canonical intelligence fields;
- one real analysis card exposes diagnostic-only V4 role;
- market facts remain truthful;
- release identity matches Web;
- no fake/demo fallback on the production/public root unless explicitly requested by URL/config for demo.

---

## W. Public browser acceptance — hard gate

Perform browser acceptance on the deployed public root.

Required visible evidence:

```text
W2 Football Intelligence
Market Overview
Match Intelligence
Data & Operations Summary
```

Required behavioral checks:

1. stable fixture renders correctly if present;
2. zero intelligence alerts do not blank the page;
3. empty-day state is meaningful if no fixtures exist;
4. Match Intelligence renders real market facts without requiring V4 pick;
5. model-market disagreement uses diagnostic copy only;
6. four risk dimensions remain separate;
7. Safety switches show Candidate/Formal/Lock/Production OFF;
8. API/Web SHA or release identity shows synchronized source;
9. no browser-visible opportunity/recommendation semantics are derived from divergence;
10. no unexpected recommendation-first Boss Console is mounted as root product authority.

Required browser technical result:

```text
BROWSER_CONSOLE_ERRORS = 0
UNHANDLED_PAGE_ERRORS = 0
REQUIRED_API_REQUEST_FAILURES = 0
```

Take/store acceptance evidence according to existing repository release practice; do not add raw/private Provider payloads to Git.

If public browser acceptance fails, Round 1 remains IN_PROGRESS and must be remediated until PASS.

---

## X. No-scope-expansion verification — hard gate

Final diff/audit must confirm:

```text
ROUND_2_IMPLEMENTATION = NOT_STARTED
ROUND_3_IMPLEMENTATION = NOT_STARTED
OVERROUND_PERCENTILE_ALERT_MODEL = NOT_IMPLEMENTED
NEW_MARKET_RADAR_THRESHOLDS = 0
NEW_MODEL_EDGE_HYPOTHESIS = 0
H_RESULT_ACCESS = PERMANENTLY_CLOSED
SIGNAL_LEDGER_FOR_EXECUTION = NOT_IMPLEMENTED
PORTFOLIO = NOT_IMPLEMENTED
RISK_KELLY = NOT_IMPLEMENTED
TWO_LEG_PARLAY = NOT_IMPLEMENTED
REAL_MONEY = NOT_AUTHORIZED
```

---

## Y. Final receipt — mandatory complete evidence

The final Round 1 receipt must include at least:

```text
ORIGINAL_AUDITED_BASE_MAIN_SHA
RUNTIME_PR_NUMBER
FAILED_ATTEMPTS[]
  - head_sha
  - pr_fast_run/result
  - full_rc_run/result
  - failed_gate
FINAL_PR_HEAD_SHA
FINAL_SOURCE_TREE_SHA
FINAL_PR_FAST_RUN
FINAL_PR_FAST_RESULT
FINAL_FULL_RC_RUN
FINAL_FULL_RC_RESULT
RC_SOURCE_SHA
RC_SOURCE_TREE_SHA
API_IMAGE_DIGEST
WEB_IMAGE_DIGEST
RELEASE_MANIFEST_STATUS
MERGE_SHA
DEPLOYED_API_SHA
DEPLOYED_WEB_SHA
DEPLOYED_RELEASE_IDENTITY
PUBLIC_API_ACCEPTANCE
PUBLIC_BROWSER_ACCEPTANCE
BROWSER_CONSOLE_ERRORS
UNHANDLED_PAGE_ERRORS
ACTIVE_WHITELIST_BEFORE
ACTIVE_WHITELIST_AFTER
ACTIVE_WHITELIST_IDENTITY_DIFF
BOSS_CONSOLE_PROTECTED_BASELINE
PUBLIC_INTELLIGENCE_ROOT_LEGACY_DECISION_COUNTS_IMPORT
INTELLIGENCE_STATE_TESTS
STATE_PRECEDENCE_TESTS
DIVERGENCE_GUARD_TESTS
FOUR_RISK_DIMENSION_TESTS
MARKET_STABLE_ZERO_ALERT_TEST
MARKET_FACT_V4_INDEPENDENCE_TESTS
MARKET_OVERVIEW_COUNT_RECONCILIATION
REAL_CARD_TEST
EMPTY_DAY_TEST
HISTORICAL_COMPATIBILITY_TESTS
PROVIDER_POLICY_DIFF
PROVIDER_ALLOWLIST_DIFF
SCHEDULER_POLICY_DIFF
NEW_PROVIDER_CALLS_INITIATED_BY_R1
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
BOSS_CONSOLE_PROTECTED_BASELINE = PASS
PUBLIC_INTELLIGENCE_ROOT_LEGACY_DECISION_COUNTS_IMPORT = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
PUBLIC_BROWSER_ACCEPTANCE = PASS
ROUND_1 = PASS
```

Only after this complete state may Round 1 end.

After PASS, stop. Round 2 still requires a new explicit owner authorization/next action.
