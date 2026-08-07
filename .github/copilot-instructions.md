# W2 Copilot / Codex Current Instructions

Before acting, read from `origin/context/current`:

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

Use current PR #493 as the only Round 1 runtime implementation. Use `origin/context/current` as current task/product authority when old context on `main` conflicts.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
ACTIVE_RUNTIME_PR = 493
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ROUND_1_STATUS = IN_PROGRESS_REMEDIATION
```

## Binding completion behavior

Do not treat a failed required check as completion.

```text
FAIL_CLOSED = DO_NOT_ADVANCE_PAST_THE_FAILED_GATE
FAIL_CLOSED != ABANDON_ROUND_1
```

For any failure that remains within the approved Round 1 scope:

```text
DIAGNOSE
-> MINIMAL_FIX_IN_PR_493
-> LOCAL_VALIDATION
-> NEW_EXACT_HEAD_PR_FAST
-> NEW_EXACT_HEAD_FULL_RC
-> REPEAT_IF_NEEDED
```

No new owner authorization is required for bounded Round 1 remediation inside PR #493.

Do not create another Round 1 PR.

Do not merge/deploy until the final exact-head Full RC is successful.

If deployment or public browser acceptance fails, Round 1 remains IN_PROGRESS and must be remediated within the same authorized boundaries until the final deployed product passes all acceptance criteria.

Round 1 can stop only when:

```text
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
MERGE = SUCCESS
API_WEB_SAME_VERIFIED_SOURCE_DEPLOYMENT = SUCCESS
PUBLIC_API_ACCEPTANCE = PASS
PUBLIC_BROWSER_ACCEPTANCE = PASS
ROUND_1_ACCEPTANCE_CRITERIA = ALL_PASS
ROUND_1 = PASS
```

## Current first remediation

The first Full RC failed at the protected Boss Console baseline:

```text
FAILED_HEAD = 5479e1f1f419e2fc15b69882aaa0c323c966ce1d
FAILED_FULL_RC = 31151557970
FAILED_FILE = apps/web/src/components/DecisionCounts.tsx
EXPECTED_SHA256 = c1b3f940587c1a25610c5e762f955c12541a7da40f006e9ce7818e5d376c9d6e
FAILED_ACTUAL_SHA256 = 4d16bdcede5cf96d17ecf346e1872b5db58139c470ef1227786a6667166a7d5a
```

Mandatory remediation:

- restore `DecisionCounts.tsx` exactly to protected base/main content;
- do not change `BOSS_CONSOLE_VISUAL_AUTHORITY_V2.json` to bless the new hash;
- do not weaken `check_boss_console_baseline.py`;
- create an intelligence-only Market Overview counter component;
- make the public `IntelligenceConsole` consume the intelligence-only component;
- add a guard that the public intelligence root does not import protected legacy DecisionCounts;
- preserve all intelligence-first Round 1 behavior.

## Binding league correction

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Current 13 identities:

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

The European `5 + 6` cohort is not a replacement whitelist. `Eredivisie` and `Primeira Liga` already exist in the 13 baseline. Future net-new candidates are only:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union is `13 + 4 = 17`, but Round 1 must not add/register/enable/audit/call/schedule these four.

## Current product work

Maintain and finish the bounded API/Web semantic refactor:

- recommendation-first -> intelligence-first;
- seven deterministic intelligence states;
- four independent event/data/model/collection risk dimensions;
- stable market/zero-alert days as valid results;
- V4 retained as diagnostic input, not public product authority;
- market facts independent from V4 pick/no-pick state;
- divergence forbidden from generating opportunity/edge/value/recommendation semantics;
- public shell: Market Overview / Match Intelligence / Data & Operations Summary;
- active whitelist remains exact 13;
- protected legacy Boss Console visual authority remains PASS.

Detailed implementation/remediation requirements are binding in `ROUND_1_CODEX_EXECUTION.md`.

Every acceptance gate is binding in `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Multiple failed validation/RC attempts are permitted while remediating PR #493. Every source-changing attempt must use the new exact head. Do not reuse old RC evidence across SHAs.

Only one successful final exact-head RC may authorize the one merge and final accepted deployment.

Do not reopen Phase 0.5/H. Do not build Signal Ledger for execution, Portfolio, Risk/Kelly, 2x1, auto-betting or real-money workflows.
