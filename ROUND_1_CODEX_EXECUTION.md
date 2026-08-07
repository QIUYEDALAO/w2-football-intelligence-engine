# W2 MI Round 1 — Codex Execution Authority

This file is the binding execution authority for Codex. It is maintained directly on branch `context/current` without PR/CI/deployment.

## 0. Owner authorization and completion rule

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = IN_PROGRESS_REMEDIATION
```

Round 1 is one bounded runtime API/Web refactor in the existing PR #493.

**Do not stop the task merely because an implementation check, PR Fast, Full Release Candidate, deployment preflight, or public browser acceptance fails.**

The binding meaning of fail-closed is:

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_THE_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1
```

For any failure that remains inside the authorized Round 1 scope:

1. preserve the failure evidence;
2. diagnose the exact root cause from code/logs/contracts;
3. make the smallest in-scope correction in the same PR #493;
4. rerun focused local checks;
5. obtain a new successful `PR_FAST_REQUIRED` for the new head;
6. run a new exact-head Full Release Candidate for that head;
7. repeat this remediation loop as necessary until every binding acceptance criterion passes.

No additional owner authorization is required for bounded Round 1 remediation attempts inside PR #493.

Owner authorization is required again only if the proposed fix would cross a permanent stop line, expand scope beyond Round 1, change Provider/Scheduler policy, alter the active whitelist, start Round 2/3, or weaken/bypass an acceptance guard.

Round 1 is complete only when:

```text
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
MERGE = SUCCESS
API_WEB_SAME_VERIFIED_SOURCE_DEPLOYMENT = SUCCESS
PUBLIC_BROWSER_ACCEPTANCE = PASS
ROUND_1_ACCEPTANCE_CRITERIA = ALL_PASS
ROUND_1 = PASS
```

Until then:

```text
ROUND_1 = IN_PROGRESS
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
```

## 1. Current failure receipt — authoritative starting point

The first Round 1 implementation attempt reached PR #493 and correctly failed closed at Full RC.

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
EXPECTED_SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
FAILED_ACTUAL_SHA256 = 4d16bdcede5cf96d17ecf346e1872b5db58139c470ef1227786a6667166a7d5a
MERGE = NOT_EXECUTED
DEPLOYMENT = NOT_EXECUTED
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
```

The failed RC showed that static-contract, unit-contract, integration, migration-schema, staging-parity, predeploy-e2e, compose-packaging, Python image build, Web image build and image-smoke passed. The Web job stopped before typecheck/build/E2E because `scripts/check_boss_console_baseline.py` rejected the protected `DecisionCounts.tsx` hash. The release manifest then correctly failed closed.

Treat this as a bounded compatibility defect, not as authority to redesign delivery gates.

## 2. Immediate mandatory remediation for PR #493

The protected Boss Console visual authority is historical/user-approved compatibility authority. Do not rewrite it merely to make CI pass.

### 2.1 Restore the protected file exactly

Restore:

```text
apps/web/src/components/DecisionCounts.tsx
```

to the exact content from Round 1 base/main:

```text
84e642f3ea26464574f75ee4d520b38bcf24073a
```

Required SHA-256 after restoration:

```text
c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
```

Do not modify, regenerate, weaken, delete or rebaseline:

```text
docs/ui/boss-console/BOSS_CONSOLE_VISUAL_AUTHORITY_V2.json
scripts/check_boss_console_baseline.py
```

Do not alter protected hashes to bless the new implementation.

### 2.2 Separate the new intelligence product from the protected legacy component

Create a new intelligence-only overview component, for example:

```text
apps/web/src/components/MarketOverviewCounts.tsx
```

Move the new Round 1 Market Overview metrics there:

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

`IntelligenceConsole.tsx` must consume the new intelligence-only component.

The public W2 Football Intelligence root must not consume `DecisionCounts.tsx` as its Market Overview authority.

Add a regression/static guard proving the intelligence root does not import or depend on the protected legacy `DecisionCounts` component.

### 2.3 Preserve the new product behavior

The remediation must not revert the already implemented Round 1 product contract:

```text
W2 Football Intelligence
Market Overview
Match Intelligence
Data & Operations Summary
```

and must preserve the seven-state intelligence contract, four risk dimensions, market-fact independence and V4 diagnostic-only role defined below.

## 3. Authority and source

Before any further edit:

```bash
git fetch origin main context/current --prune
```

Use PR #493 as the only Round 1 runtime PR. Do not create a replacement or remediation PR.

Use `origin/context/current` as current product/task authority. Read in order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_1_CODEX_EXECUTION.md`
7. `ROUND_1_ACCEPTANCE_CRITERIA.md`
8. `AI_PROJECT_CONTEXT.md`
9. `AI_QUANT_PROJECT_CONTEXT.md`
10. `AGENTS.md`
11. `QUANT_AGENTS.md`
12. `.github/copilot-instructions.md`

If old files on `main` conflict with `context/current`, `context/current` controls this current task. Do not copy these context files into PR #493 merely to synchronize context.

If `origin/main` advances while PR #493 remains open, rebase/merge-base handling must follow repository policy and preserve the one-PR boundary. Do not silently change the original audit baseline in the final receipt; record both original audited base and any required current-main compatibility reconciliation.

## 4. League correction — binding

The current active whitelist baseline is **13 competitions**, not 11.

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Exact identities:

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

The European `5 + 6` grouping is not a replacement whitelist.

Core Benchmark (already present):

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar cohort:

```text
Eredivisie                 # already present
Primeira Liga              # already present
Belgian Pro League         # future net-new candidate
Turkish Super Lig          # future net-new candidate
Greek Super League         # future net-new candidate
Scottish Premiership       # future net-new candidate
```

Future candidate union is:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

This is future planning only. Round 1 must not register, enable, call, audit or schedule any of the four net-new competitions.

## 5. Permanent product guard

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Do not delete V4, DecisionContract, settlement, historical replay or historical validation evidence.

V4 may remain visible to technical/history diagnostics, but it must no longer control the public product's:

```text
top-level intelligence state
card visibility
market-fact visibility
public ranking/priority
Market Overview counters
next attention reason
opportunity/recommendation language
```

## 6. Required public intelligence projection

Every public fixture/card projection must expose exactly one deterministic top-level state:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Frozen Round 1 precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Retain deterministic secondary reason codes so lower-precedence evidence is not lost.

Round 1 may only map existing explicit movement/anomaly evidence. Do not invent Round 3 thresholds, overround percentiles, persistence rules, bookmaker-confirmation formulas, alert scores or opportunity scores.

```text
MARKET_STABLE = VALID_SUCCESS_RESULT
ZERO_MATERIAL_ALERTS = VALID_SUCCESS_RESULT
```

Do not lower thresholds to manufacture content.

## 7. Four independent risk dimensions

Public product risk must expose four separate dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

Each dimension must contain deterministic status/reason codes/human explanation.

Rules:

- `NOT_READY` / `BLOCKED` are not high-risk matches;
- missing identity/xG/ratings/required quote/readiness -> data/model readiness evidence;
- Provider/Scheduler/schema/runtime failures -> collection evidence;
- actual lineup/injury/event facts -> event evidence;
- model readiness/calibration/feature staleness/divergence -> model evidence;
- do not merge data + collection back into one generic betting-risk score;
- no dimension implies a betting recommendation.

## 8. Market facts independent from V4 selection

Current market facts must not disappear merely because V4 is `NOT_READY`, `NO_EDGE`, has no selected candidate, or has no pick.

Where truth exists, preserve read-only display of:

```text
fixture/team/competition identity
AH and OU current or last-known market
line/price
bookmaker/confirmation evidence already available
captured_at
freshness
market probabilities where legitimately available
existing line/price movement evidence
lineup/data readiness
model probabilities/model diagnostics
evidence lineage/blockers
```

Never promote stale/reference-only quotes into current/executable quotes.

## 9. Public surfaces

The public root must visibly identify:

```text
W2 Football Intelligence
W2 Football Market Intelligence & Model Diagnostics
```

Minimum Round 1 structure:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Minimum Market Overview counters:

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

Optional additional intelligence counters:

```text
market anomalies
model-market disagreements
```

Do not use recommendation-first metrics as primary public KPIs:

```text
analysis picks
formal recommendations
lock eligible
NO_EDGE
opportunities
positive EV
```

Historical settlement/performance data may remain as clearly historical diagnostics. It must not be presented as proof of a current betting edge.

## 10. Divergence guard — machine and browser

Any model-market divergence may produce only diagnostic language such as:

```text
model-market disagreement
model calibration review required
model feature may be stale
market information not explained by model
model drift/overconfidence review
```

It must never generate public product semantics equivalent to:

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

No divergence magnitude/status/`direction_allowed` threshold may determine public recommendation readiness or public attention priority as an opportunity signal.

## 11. Hard Round 1 stop lines

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST_COUNT = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2_CAPABILITY_AUDIT = NOT_STARTED
ROUND_3_MARKET_RADAR = NOT_STARTED
DB_MIGRATION_EXPECTED = 0
MODEL_RECOMPUTE_EXPECTED = 0

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Do not reopen Phase 0.5 or H. Do not build Signal Ledger for execution, Portfolio, Kelly/Risk, 2x1, auto-betting or real-money workflows.

If a proposed remediation requires crossing any stop line, stop and request owner authorization instead of implementing it.

## 12. Required continuous delivery loop until PASS

Use exactly one runtime PR: **PR #493**.

There may be multiple failed validation/RC attempts while fixing the same PR, but there must be only:

```text
ONE_RUNTIME_PR = true
ONE_SUCCESSFUL_FINAL_RC_ON_FINAL_HEAD = true
ONE_MERGE = true
ONE_DEPLOYMENT = true
ONE_FINAL_PUBLIC_ACCEPTANCE = true
```

A failed RC is evidence, not completion.

For each remediation head:

1. run focused local checks relevant to the change;
2. run the protected Boss Console baseline locally if any Web path is touched;
3. run Web typecheck/build/E2E when Web is touched;
4. run required Python/static/contract tests for changed backend paths;
5. push to PR #493;
6. require `PR_FAST_REQUIRED = SUCCESS` on that exact head;
7. trigger a **new exact-head Full Release Candidate** for that exact head;
8. if Full RC fails, do not merge/deploy; return to root-cause remediation in the same PR;
9. repeat until Full RC succeeds.

Do not rerun an old failed RC after changing source. A source change requires a new exact-head RC.

Do not reuse an RC manifest or candidate image across different source SHAs.

Do not weaken, delete, skip, xfail, rebaseline or bypass a failing required guard simply to obtain green CI.

Once the final exact-head Full RC is successful:

1. freeze that PR head;
2. do not add source changes after the successful final RC;
3. merge once using merge commit only; no squash/rebase/auto-merge;
4. deploy only the immutable API/Web artifacts verified for that final source/release identity;
5. perform public browser/API acceptance;
6. if deployment or public acceptance fails, fail closed at that gate, remediate only within authorized Round 1 scope, and repeat the necessary exact-head validation/release sequence before another deployment attempt;
7. mark Round 1 PASS only when every criterion in `ROUND_1_ACCEPTANCE_CRITERIA.md` passes.

## 13. Completion receipt

The final report must include the complete evidence matrix required by `ROUND_1_ACCEPTANCE_CRITERIA.md`, including all failed RC attempts and the final successful RC.

Do not report `ROUND_1 = PASS` from local tests, PR Fast, a successful image build, or a partial RC.

Only the final deployed and browser-accepted exact-head release can close Round 1.
