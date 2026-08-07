# W2 Current Task Checklist

This is the complete current task order for W2. It is maintained directly on branch `context/current`; context updates do not use PR or CI. Runtime changes continue to use the guarded PR / Release Candidate / deployment process.

## Program status

```text
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
PRODUCT = W2 Football Intelligence
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_TASK = AWAIT_OWNER_ROUND_2_AUTHORIZATION
NEXT_CODE_TASK = NONE_AUTHORIZED
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = PASS
```

Execution authority:

```text
ROUND_1_CODEX_EXECUTION.md
```

Acceptance authority:

```text
ROUND_1_ACCEPTANCE_CRITERIA.md
```

Permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

---

## MI-00 — Phase 0.5 closeout

```text
STATUS = DONE
FINAL_VERDICT = NO_EDGE
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Do not reopen, retune, or build execution products around the failed hypothesis.

---

## MI-R1 — Product semantics and status reframe

```text
STATUS = PASS
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
CHANGE_CLASS = RUNTIME_API_AND_WEB
ONE_RUNTIME_PR = true
ACTIVE_RUNTIME_PR = 493
MULTIPLE_FAILED_VALIDATION_ATTEMPTS_ALLOWED = true
ONE_SUCCESSFUL_FINAL_RC_ON_FINAL_HEAD = true
ONE_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

### R1.0 Completion semantics — hard boundary

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1
```

If a required gate fails but the fix is still inside authorized Round 1 scope, Codex must:

1. retain the failed evidence;
2. identify the exact root cause;
3. make the smallest correction in the same PR #493;
4. rerun local affected checks;
5. obtain new exact-head PR Fast success;
6. run new exact-head Full RC;
7. repeat until all acceptance gates pass.

No additional owner authorization is required for an in-scope Round 1 remediation.

Owner authorization is required only for scope expansion or stop-line changes.

Round 1 completion conditions, now satisfied:

```text
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
MERGE = SUCCESS
API_WEB_SAME_VERIFIED_SOURCE_DEPLOYMENT = SUCCESS
PUBLIC_API_ACCEPTANCE = PASS
PUBLIC_BROWSER_ACCEPTANCE = PASS
ROUND_1_ACCEPTANCE_CRITERIA = ALL_PASS
ROUND_1 = PASS
```

### R1.1 Historical failed attempt — retained evidence

```text
AUDITED_BASE_MAIN_SHA = 84e642f3ea26464574f75ee4d520b38bcf24073a
RUNTIME_PR_NUMBER = 493
FAILED_HEAD_SHA = 5479e1f1f419e2fc15b69882aaa0c323c966ce1d
PR_FAST_RUN = 31151508691
PR_FAST_RESULT = SUCCESS
FAILED_FULL_RC_RUN = 31151557970
FAILED_FULL_RC_RESULT = FAILURE
FAILED_GATE = BOSS_CONSOLE_PROTECTED_BASELINE
FAILED_FILE = apps/web/src/components/DecisionCounts.tsx
EXPECTED_SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
FAILED_ACTUAL_SHA256 = 4d16bdcede5cf96d17ecf346e1872b5db58139c470ef1227786a6667166a7d5a
MERGE = NOT_EXECUTED
DEPLOY = NOT_EXECUTED
```

Completed remediation:

- restored protected `DecisionCounts.tsx` exactly to the base/main authority;
- preserved protected manifest hashes and the baseline checker;
- created the intelligence-only Market Overview counter component;
- made `IntelligenceConsole` consume the intelligence-only component;
- added the legacy DecisionCounts import regression guard;
- preserved the intelligence-first public implementation;
- passed final PR Fast, exact-head Full RC, merge, deployment and public acceptance.

Complete evidence: `ROUND_1_FINAL_RECEIPT.md`.

### R1.2 League baseline correction — hard boundary

The current active whitelist is **13**, not 11.

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Baseline identities:

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

The European `5 + 6` grouping is a future market-role cohort, not a replacement whitelist.

Of the six Extended Radar names, `Eredivisie` and `Primeira Liga` are already in the 13 baseline. Only four are net-new:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union after owner-authorized Round 2 planning:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Round 1 must leave all 13 unchanged and must not register/enable/call/schedule the four new candidates.

### R1.3 Source and scope

- continue only PR #493;
- task authority from `origin/context/current`;
- preserve Scheduler, Provider policy, current 13 whitelist, V4 calculations and historical settlement/replay;
- no new Provider calls initiated by Round 1;
- no Round 2/3 implementation;
- no second remediation PR;
- no bypass of protected CI/visual authority.

### R1.4 Product identity

Public product identity:

```text
W2 Football Intelligence
W2 Football Market Intelligence & Model Diagnostics
```

Top-level product questions:

```text
what is happening in the market?
is the data fresh and complete?
is the model behaving reliably?
what needs attention?
```

### R1.5 Intelligence states

Each public fixture/read-model card exposes exactly one:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Frozen precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Preserve secondary deterministic reason codes.

Do not invent Round 3 alert thresholds in Round 1.

### R1.6 Four risk dimensions

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

- `NOT_READY/BLOCKED` is not high betting risk;
- identity/xG/quote/readiness problems -> data/model readiness;
- Provider/Scheduler/schema/runtime -> collection;
- actual lineup/injury/event facts -> event;
- model calibration/simulation/feature staleness/divergence -> model;
- do not collapse data + collection into one generic risk;
- no dimension implies a recommendation.

### R1.7 Public authority switch

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

Do not delete V4 or settlement/history.

Public card state, visibility, market facts, priority, counters and wording must no longer be controlled by V4 recommendation outcome alone.

### R1.8 Permanent divergence guard

Model-market divergence may produce diagnostic disagreement/model-review language only.

It may not produce or rank:

```text
value opportunity
positive edge
market mispricing
recommended side
high-confidence pick
价值机会
正 EV 机会
推荐方向
值得介入
```

Remove the public chain where divergence status/magnitude/direction_allowed determines recommendation readiness/opportunity priority.

### R1.9 Market fact independence

Real current/last-known AH/OU facts must not disappear merely because V4 is `NOT_READY`, `NO_EDGE`, has no selected candidate or no pick.

Never promote stale/reference-only quote evidence to current/executable.

### R1.10 MARKET_STABLE

```text
MARKET_STABLE = VALID_SUCCESS_RESULT
ZERO_MATERIAL_ALERTS = VALID_SUCCESS_RESULT
```

Stable fixtures render non-empty. Do not lower thresholds to manufacture alerts.

A truly fixture-empty day remains a real empty-day state; do not fabricate stable fixtures.

### R1.11 Public page structure

Minimum public shell:

```text
Market Overview
Match Intelligence
Data & Operations Summary
```

Minimum overview counters:

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

Do not use analysis picks, formal recommendations, lock eligible, NO_EDGE, opportunity or positive EV as primary Market Overview KPIs.

### R1.12 Protected compatibility

Required:

```text
BOSS_CONSOLE_PROTECTED_BASELINE = PASS
PUBLIC_INTELLIGENCE_ROOT_LEGACY_DECISION_COUNTS_IMPORT = false
```

The old protected Boss Console can remain for compatibility/reference, but the public intelligence root must not depend on changing its protected DecisionCounts component.

### R1.13 Tests and acceptance

Every item in `ROUND_1_ACCEPTANCE_CRITERIA.md` is mandatory.

At minimum prove:

1. active whitelist exact 13 with identity diff empty;
2. protected Boss Console baseline PASS;
3. public intelligence root no longer imports legacy DecisionCounts;
4. `MODEL_MARKET_DISAGREEMENT` never produces recommendation/opportunity language;
5. `NOT_READY/BLOCKED` maps to data/model/collection semantics, not high-risk match;
6. `MARKET_STABLE` renders valid non-empty state;
7. four risk dimensions remain independent;
8. market facts remain visible independently of V4 pick state;
9. Market Overview counter reconciliation passes;
10. current real cards still render;
11. empty-day behavior remains explicit and nonblank;
12. API/Web release SHA sync remains correct;
13. Candidate/Formal/Lock/Production remain OFF;
14. Provider/Scheduler policy and whitelist remain unchanged;
15. browser console errors = 0;
16. final public API/browser acceptance PASS.

### R1.14 Delivery loop until accepted

For every remediation head:

- run affected focused local tests;
- run protected Web baseline if Web is touched;
- Web typecheck/build/E2E when Web is touched;
- required Python/static/contract tests for backend changes;
- push only to PR #493;
- require exact-head `PR_FAST_REQUIRED = SUCCESS`;
- run a new exact-head Full RC;
- if RC fails, do not merge/deploy; remediate and repeat.

A source change invalidates the previous RC as final release evidence.

Multiple failed validation/RC attempts are allowed and must be retained in the final receipt.

Only one successful final RC on the final head may authorize merge/deploy.

After final RC PASS:

- freeze final head;
- merge once using merge commit only;
- deploy the verified immutable API/Web release identity;
- run public API acceptance;
- run public browser acceptance;
- if deployment/browser acceptance fails, remain IN_PROGRESS and remediate within Round 1 until PASS;
- stop only after complete Round 1 acceptance.

Round 1 completion state:

```text
PRODUCT_SEMANTICS = INTELLIGENCE_FIRST
ACTIVE_WHITELIST = 13_UNCHANGED
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
BOSS_CONSOLE_PROTECTED_BASELINE = PASS
MODEL_MARKET_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
PUBLIC_BROWSER_ACCEPTANCE = PASS
MARKET_RADAR_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
MODEL_LAB_FULL_ANALYTICS = NOT_YET_IMPLEMENTED
ROUND_1 = PASS
```

---

## MI-R2 — Provider capability audit

```text
STATUS = BLOCKED_UNTIL_OWNER_AUTHORIZED
TASK = W2_MI_R2_FIRST_DIVISION_PROVIDER_CAPABILITY_AUDIT
MODE = READ_ONLY_CONTROLLED
DURATION = 14_DAYS
TARGET_CANDIDATE_UNION = 17
```

Round 2 target is the union of the existing 13 whitelist competitions and four net-new European first-division candidates, not a replacement 11-league whitelist.

The `5 + 6` European cohort remains a product-analysis lens inside the wider 17-candidate universe.

No competition is promoted merely by membership in the target pool.

Do not begin Round 2 automatically.

---

## MI-R3 — Market Radar and Model Lab

```text
STATUS = BLOCKED_UNTIL_MI_R2_CAPABILITY_DECISION
AUTHORIZED_LEAGUES = ROUND_2_PROMOTED_ONLY
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Round 3 freezes exact market alert thresholds only after Round 2 live distributions exist.

No opportunity score.

---

## Permanent stop lines

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
