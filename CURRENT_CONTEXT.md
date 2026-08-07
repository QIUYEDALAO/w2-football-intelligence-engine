# W2 Current Context

This is the mutable current authority for W2. It is maintained directly on branch `context/current` without a pull request, CI, Release Candidate, image build or deployment.

## Read order

1. `CURRENT_STATE.yaml`
2. `CURRENT_PRODUCT_DESIGN.md`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`
6. `ROUND_1_CODEX_EXECUTION.md`
7. `ROUND_1_ACCEPTANCE_CRITERIA.md`
8. `ROUND_1_FINAL_RECEIPT.md`

## Owner product decision

```text
PRODUCT_NAME = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
OWNER_AUTHORIZATION_ID = W2_MI_R1_CONTINUE_UNTIL_ACCEPTED_20260807
ACTIVE_NEXT_ACTION = AWAIT_OWNER_ROUND_2_AUTHORIZATION
ACTIVE_RUNTIME_PR = 493
ROUND_1_STATUS = PASS
ROUND_2_STATUS = NOT_STARTED
```

W2 has been repositioned from a recommendation-first public shell into a football market-intelligence and model-diagnostics platform while preserving the existing data, identity, odds, model, Scheduler, replay and Dashboard foundations.

Final delivery and public-acceptance evidence is recorded in
`ROUND_1_FINAL_RECEIPT.md`. No Round 2 work is authorized.

## Historical continuation and delivery-count interpretation

`ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md` was the explicit owner authority for continuing PR #493 until acceptance. It is retained as history and no longer authorizes new runtime work after Round 1 PASS.

```text
ALLOW_REMEDIATION_COMMITS_IN_PR_493 = true
ALLOW_NEW_PR_FAST_AFTER_SOURCE_CHANGE = true
ALLOW_REPLACEMENT_EXACT_HEAD_FULL_RC_AFTER_FAILED_RC = true
ALLOW_REPEAT_PR_FAST_AND_FULL_RC_UNTIL_FINAL_SUCCESS = true
FAILED_VALIDATION_OR_RC_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_RUN_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
```

The historical phrase `one PR Fast` or `one final exact-head Full RC` must not be read as a one-attempt lifetime cap. It means one **successful final RC** on the final accepted head and one final merge/deployment.

For an in-scope Round 1 failure:

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1_OR_WAIT_FOR_OWNER
DIAGNOSE
-> MINIMAL_FIX_IN_PR_493
-> LOCAL_VALIDATION
-> NEW_EXACT_HEAD_PR_FAST
-> NEW_EXACT_HEAD_FULL_RC
-> REPEAT_IF_NEEDED
```

No new owner authorization is required for bounded remediation commits, replacement PR Fast runs, or replacement exact-head Full RC attempts inside the already approved Round 1 scope.

A new owner authorization is required only if a proposed correction would expand scope or cross a permanent stop line.

Round 1 is complete only when:

```text
FINAL_PR_FAST_REQUIRED = SUCCESS
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
FINAL_RC_SOURCE_SHA = FINAL_PR_HEAD_SHA
MERGE = SUCCESS
API_WEB_SAME_VERIFIED_SOURCE_DEPLOYMENT = SUCCESS
PUBLIC_API_ACCEPTANCE = PASS
PUBLIC_BROWSER_ACCEPTANCE = PASS
BROWSER_CONSOLE_ERRORS = 0
ROUND_1_ACCEPTANCE_CRITERIA = ALL_PASS
ROUND_1 = PASS
```

All Round 1 completion conditions are satisfied. Round 2/3 remain `NOT_STARTED`.

## Historical failed attempt

The first Full RC is retained as failure evidence and does not count as the final successful RC:

```text
AUDITED_BASE_MAIN_SHA = 84e642f3ea26464574f75ee4d520b38bcf24073a
RUNTIME_PR_NUMBER = 493
FAILED_HEAD_SHA = 5479e1f1f419e2fc15b69882aaa0c323c966ce1d
PR_FAST_RUN = 31151508691
PR_FAST_RESULT = SUCCESS
FAILED_FULL_RC_RUN = 31151557970
FAILED_FULL_RC_RESULT = FAILURE
FAILED_FULL_RC_COUNTS_AS_FINAL_SUCCESS = false
FAILED_GATE = BOSS_CONSOLE_PROTECTED_BASELINE
FAILED_FILE = apps/web/src/components/DecisionCounts.tsx
EXPECTED_SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
FAILED_ACTUAL_SHA256 = 4d16bdcede5cf96d17ecf346e1872b5db58139c470ef1227786a6667166a7d5a
MERGE = NOT_EXECUTED
DEPLOYMENT = NOT_EXECUTED
```

The final successful remediation completed the binding work:

- restored protected `DecisionCounts.tsx` exactly to the base/main user-approved authority;
- preserved the protected visual hashes and baseline checker;
- moved Market Overview counters into a separate intelligence-only component;
- made the public intelligence root independent of protected legacy DecisionCounts;
- preserved all Round 1 intelligence-first semantics;
- passed the new-head PR Fast and replacement exact-head Full RC;
- merged, deployed and passed public API/browser acceptance.

## Evidence boundary

Phase 0.5 is complete and closed:

```text
FINAL_VERDICT = NO_EDGE
H_RESULT_ACCESS = PERMANENTLY_CLOSED
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

Do not reopen H or retune the failed model family with V/H outcomes.

## Public product states

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

Round 1 precedence:

```text
COLLECTION_INCIDENT
> DATA_INCOMPLETE
> MODEL_DIAGNOSTIC_WARNING
> MARKET_ANOMALY
> MODEL_MARKET_DISAGREEMENT
> MARKET_MOVEMENT
> MARKET_STABLE
```

Risk dimensions:

```text
EVENT_RISK
DATA_RISK
MODEL_RISK
COLLECTION_RISK
```

`NOT_READY/BLOCKED` is not a betting-risk conclusion.

## League baseline correction

The current active whitelist is **13 competitions** and Round 1 must preserve it exactly.

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

The European `5 + 6` grouping is not a replacement whitelist.

Core Benchmark 5 are already within the baseline 13:

```text
Premier League
La Liga
Bundesliga
Serie A
Ligue 1
```

Extended Radar cohort 6 contains two existing baseline leagues plus four net-new future candidates:

```text
Eredivisie              EXISTING
Primeira Liga           EXISTING
Belgian Pro League      NET_NEW
Turkish Super Lig       NET_NEW
Greek Super League      NET_NEW
Scottish Premiership    NET_NEW
```

Future candidate union after explicit Round 2 authorization:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Round 1 performs zero league registration/enablement/audit/scheduling/provider expansion calls.

## Product authority

```text
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

V4 and historical settlement/replay evidence remain preserved. Public intelligence state, market-fact visibility, ranking, counters and wording must not be controlled by V4 recommendation outcome alone.

## Round 1

```text
TASK = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
STATUS = PASS
ACTIVE_RUNTIME_PR = 493
ONE_RUNTIME_PR = true
PR_FAST_ATTEMPTS = AS_NEEDED_AFTER_SOURCE_HEAD_CHANGE
FULL_RC_ATTEMPTS = AS_NEEDED_UNTIL_FINAL_SUCCESS
MULTIPLE_FAILED_VALIDATION_ATTEMPTS_ALLOWED = true
MULTIPLE_FAILED_RC_ATTEMPTS_ALLOWED = true
FAILED_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_RC = true
ONE_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
PUBLIC_ACCEPTANCE_REQUIRED = true
PUBLIC_API_ACCEPTANCE = PASS
PUBLIC_BROWSER_ACCEPTANCE = PASS
BROWSER_CONSOLE_ERRORS = 0
ACTIVE_WHITELIST = 13_UNCHANGED
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
```

Explicit owner continuation authority: `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`.

Detailed execution authority: `ROUND_1_CODEX_EXECUTION.md`.

Binding acceptance authority: `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Later rounds

Round 2 is blocked until Round 1 acceptance and a new explicit owner authorization. Its future candidate universe is the 17-competition union, not an 11-competition replacement whitelist.

Round 3 is blocked until Round 2 capability decisions and must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Exact Market Radar formulas wait for Round 2 live distributions.

## Permanent hard boundary

```text
BETTING_EDGE_CLAIM = FORBIDDEN
MODEL_DIVERGENCE_AS_OPPORTUNITY = FORBIDDEN
SIGNAL_LEDGER_FOR_EXECUTION = NOT_AUTHORIZED
PORTFOLIO = NOT_AUTHORIZED
RISK_KELLY = NOT_AUTHORIZED
TWO_LEG_PARLAY = NOT_AUTHORIZED
REAL_MONEY = NOT_AUTHORIZED

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```
