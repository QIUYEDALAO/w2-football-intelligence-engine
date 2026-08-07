# W2 Repository Agent Instructions

Current task authority is `origin/context/current`.

Read before runtime work:

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
11. `QUANT_AGENTS.md`

Use latest `origin/main` as code baseline; use `origin/context/current` as current task authority.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
ACTIVE_RUNTIME_PR = 493
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
```

Phase 0.5 is closed with `NO_EDGE`; do not reopen H or retune the failed hypothesis.

Permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
RecommendationDecisionV4 = DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY
```

## League hard boundary

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
```

The 17 arithmetic is `13 existing + 4 net-new`; the European `5 + 6` cohort is not a replacement whitelist.

Round 1 must not add/register/enable/audit/call/schedule the four net-new candidates.

## Round 1

One bounded API/Web runtime refactor in the existing PR #493:

- intelligence-first public product;
- seven deterministic intelligence states;
- four independent risk dimensions;
- `MARKET_STABLE` and zero alerts as valid results;
- V4 diagnostic-only public product role;
- market facts independent from V4 pick/no-pick state;
- no model-divergence opportunity/recommendation semantics;
- current 13 whitelist unchanged;
- Provider/Scheduler policy unchanged.

Detailed execution: `ROUND_1_CODEX_EXECUTION.md`.

Explicit continuation authorization: `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`.

Acceptance: `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Delivery — binding interpretation

```text
ONE_RUNTIME_PR = PR_493_ONLY
PR_FAST_ATTEMPTS = AS_NEEDED_AFTER_SOURCE_HEAD_CHANGE
FULL_RC_ATTEMPTS = AS_NEEDED_UNTIL_FINAL_SUCCESS
FAILED_PR_FAST_OR_RC_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_RC_ON_FINAL_HEAD = true
ONE_MERGE_COMMIT = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

A failed gate means do not advance past that gate, **not** stop work and wait for owner.

For every bounded Round 1 failure:

```text
DIAGNOSE -> MINIMAL_FIX_IN_PR_493 -> LOCAL_VALIDATION -> NEW_HEAD_PR_FAST -> NEW_EXACT_HEAD_FULL_RC -> REPEAT_IF_NEEDED
```

No additional owner authorization is required for this remediation loop.

Do not merge or deploy until the final exact-head Full RC succeeds. Stop only after merge, same-source deployment, public API/browser acceptance and every Round 1 acceptance criterion pass.

## Hard stop

```text
LEAGUE_EXPANSION = false
NEW_PROVIDER_CALLS_INITIATED_BY_R1 = 0
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

No Signal Ledger for execution, Portfolio, Risk/Kelly, 2x1, auto-betting, real-money or betting-edge claim.

If a proposed remediation crosses a permanent stop line or expands outside Round 1, request owner authorization for that expansion. Ordinary PR #493 fixes, PR Fast re-runs and replacement exact-head Full RC attempts are already authorized.