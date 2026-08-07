# NEXT ACTION

Current action:

```text
W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Current runtime vehicle and owner authorization:

```text
ACTIVE_RUNTIME_PR = 493
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
OWNER_AUTHORIZATION_ID = W2_MI_R1_CONTINUE_UNTIL_ACCEPTED_20260807
ROUND_1_STATUS = IN_PROGRESS_REMEDIATION
```

## Explicit owner continuation authorization

Read and obey:

```text
ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md
```

The owner explicitly authorizes:

```text
允许在 PR #493 上提交 Round 1 修复，
重新运行 PR Fast，
并以新 final head 触发替代性的 exact-head Full RC；
失败的 run 31151557970 不计作最终 RC。
```

This permission is not limited to a single replacement attempt. For every bounded in-scope Round 1 source correction:

```text
ALLOW_NEW_PR_FAST_AFTER_SOURCE_CHANGE = true
ALLOW_REPLACEMENT_EXACT_HEAD_FULL_RC_AFTER_FAILED_RC = true
ALLOW_REPEAT_PR_FAST_AND_FULL_RC_UNTIL_FINAL_SUCCESS = true
FAILED_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
```

Therefore a failed PR Fast or Full RC is retained as evidence but does not exhaust the owner authorization or final successful delivery slot.

## Binding completion instruction

Codex must continue Round 1 in the **same PR #493** until every gate in `ROUND_1_ACCEPTANCE_CRITERIA.md` passes.

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_FAILED_GATE
FAIL_CLOSED != STOP_WORK_AND_WAIT_FOR_OWNER
```

For an in-scope Round 1 failure:

```text
DIAGNOSE -> MINIMAL_FIX_IN_PR_493 -> LOCAL_VALIDATION -> NEW_EXACT_HEAD_PR_FAST -> NEW_EXACT_HEAD_FULL_RC -> REPEAT_IF_NEEDED
```

No new owner authorization is required for bounded remediation inside the already approved Round 1 scope.

Do not create another Round 1 runtime PR.

Do not merge or deploy while any required gate is failing.

Round 1 ends only after:

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

## Current failure to remediate first

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
```

Mandatory first remediation:

1. restore `apps/web/src/components/DecisionCounts.tsx` exactly to base/main protected content and expected SHA-256;
2. do not edit `BOSS_CONSOLE_VISUAL_AUTHORITY_V2.json` or weaken `check_boss_console_baseline.py`;
3. move Round 1 Market Overview counters to a new intelligence-only component such as `MarketOverviewCounts.tsx`;
4. make `IntelligenceConsole` consume the new intelligence-only component;
5. add a regression guard proving the public intelligence root does not import the protected legacy `DecisionCounts` component;
6. preserve all Round 1 intelligence-first behavior;
7. push the fix to PR #493, obtain a new PR Fast success on the new head, then trigger a replacement exact-head Full RC on that new head;
8. if that replacement RC fails for another in-scope reason, repeat without requesting owner authorization.

Full implementation and remediation authority:

```text
ROUND_1_CODEX_EXECUTION.md
```

Binding acceptance authority:

```text
ROUND_1_ACCEPTANCE_CRITERIA.md
```

## Required authority read order

Read current authority from `origin/context/current` in this order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`
7. `ROUND_1_CODEX_EXECUTION.md`
8. `ROUND_1_ACCEPTANCE_CRITERIA.md`
9. `AI_PROJECT_CONTEXT.md`
10. `AI_QUANT_PROJECT_CONTEXT.md`
11. `AGENTS.md`
12. `QUANT_AGENTS.md`
13. `.github/copilot-instructions.md`

Use PR #493 / its current head as the active Round 1 implementation. Use `origin/context/current` as current task/product authority when old `main` context conflicts.

## Binding league correction

```text
ACTIVE_WHITELIST = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Exact current identities:

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

The European `5 + 6` grouping is not the total whitelist.

The only future net-new candidates are:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future Round 2 candidate union remains:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Do not add the four new candidates in Round 1.

## Round 1 objective

Required outcomes remain:

1. public identity = `W2 Football Intelligence`;
2. seven deterministic intelligence states with frozen precedence;
3. four independent risk dimensions;
4. `MARKET_STABLE` and zero material alerts are valid results;
5. `RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY`;
6. model-market divergence cannot produce opportunity/value/edge/recommendation semantics;
7. real market facts remain visible independently of V4 pick/no-pick state when their own data/freshness truth permits it;
8. public root contains `Market Overview`, `Match Intelligence`, `Data & Operations Summary`;
9. existing real cards, empty-day state, release identity and operational health remain truthful;
10. active whitelist remains exact 13;
11. protected legacy Boss Console visual authority remains PASS;
12. final public browser console errors = 0.

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
ROUND_2_CAPABILITY_AUDIT = NOT_STARTED
ROUND_3_MARKET_RADAR = NOT_STARTED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Multiple failed PR Fast/Full RC attempts are permitted as remediation evidence. Every source-changing attempt requires a new exact-head validation. Only the **final successful exact-head RC on the final PR head** qualifies for merge/deployment.

After Round 1 PASS, stop. Do not begin Round 2 automatically.
