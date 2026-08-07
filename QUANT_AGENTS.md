# W2 Market Intelligence Agent Instructions

Read current authority from `origin/context/current` before acting.

Required execution files:

```text
CURRENT_CONTEXT.md
CURRENT_STATE.yaml
CURRENT_PRODUCT_DESIGN.md
CURRENT_TASK_CHECKLIST.md
NEXT_ACTION.md
ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md
ROUND_1_CODEX_EXECUTION.md
ROUND_1_ACCEPTANCE_CRITERIA.md
ROUND_1_FINAL_RECEIPT.md
```

Current task:

```text
ACTIVE_NEXT_ACTION = AWAIT_OWNER_ROUND_2_AUTHORIZATION
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ACTIVE_RUNTIME_PR = 493
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ROUND_1_STATUS = PASS
ROUND_2_STATUS = NOT_STARTED
```

The Phase 0.5 hypothesis is closed with `NO_EDGE`. Do not reopen H or retune the failed model family.

All later Round 1 remediation language is historical only. PR #493 is merged;
do not resume it or begin Round 2 without a new explicit owner action.

Permanent guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

## League boundary

```text
ACTIVE_WHITELIST = 13_UNCHANGED_IN_ROUND_1
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
```

The European `5 + 6` cohort is not the whitelist. Future arithmetic is 13 existing + 4 net-new. Round 1 performs no league expansion and no new Provider calls.

## Round 1 scope

- intelligence-first public product;
- seven deterministic intelligence states;
- four independent event/data/model/collection risk dimensions;
- `MARKET_STABLE`/zero-alert result is valid;
- V4 remains diagnostic input, not public product authority;
- market facts remain independent of V4 selection;
- divergence never creates opportunity/value/edge/recommendation meaning;
- preserve the existing 13 whitelist, Provider policy and Scheduler behavior.

Detailed implementation is binding in `ROUND_1_CODEX_EXECUTION.md`.

Explicit continuation authorization is binding in `ROUND_1_OWNER_CONTINUATION_AUTHORIZATION.md`.

Acceptance is binding in `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Delivery — failure attempts do not consume the final slot

```text
ONE_RUNTIME_PR = PR_493_ONLY
PR_FAST_ATTEMPTS = AS_NEEDED_AFTER_SOURCE_HEAD_CHANGE
FULL_RC_ATTEMPTS = AS_NEEDED_UNTIL_FINAL_SUCCESS
FAILED_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_FULL_RC_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_EXACT_HEAD_FULL_RC = true
ONE_FINAL_MERGE = true
ONE_FINAL_ACCEPTED_DEPLOYMENT = true
```

`one final exact-head Full Release Candidate` means the one **successful** RC on the final accepted head, not a one-attempt limit.

For every bounded in-scope failure:

```text
DIAGNOSE -> MINIMAL_FIX_IN_PR_493 -> LOCAL_VALIDATION -> NEW_EXACT_HEAD_PR_FAST -> NEW_EXACT_HEAD_FULL_RC -> REPEAT_IF_NEEDED
```

No additional owner authorization is required for PR #493 remediation commits, replacement PR Fast runs or replacement exact-head Full RC attempts.

Do not merge/deploy while any required gate is failing.

Stop only after final RC success, merge commit, same-source API/Web deployment, public API/browser acceptance and all Round 1 acceptance criteria PASS.

## Prohibited Round 1 work

```text
league expansion
new Provider calls initiated by Round 1
Provider allowlist/policy changes
Scheduler policy changes
full Market Radar scoring
full Model Lab analytics
Signal Ledger for execution
Portfolio
Risk/Kelly
2x1
real money
betting-edge claims
```

Candidate, Formal, Lock and Production remain OFF.
