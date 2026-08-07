# W2 MI Round 1 — Owner Continuation Authorization

This file is the explicit owner authorization for continuing Round 1 after failed validation attempts. It is maintained directly on `context/current` without PR/CI/deployment.

## Binding authorization

```text
OWNER_AUTHORIZATION_ID = W2_MI_R1_CONTINUE_UNTIL_ACCEPTED_20260807
OWNER_DECISION = APPROVED_CONTINUE_UNTIL_ACCEPTED
ACTIVE_RUNTIME_PR = 493
AUTHORIZED_SCOPE = ROUND_1_BOUNDED_REMEDIATION_ONLY
```

The owner explicitly authorizes the following actions **without requesting another owner approval**, provided every change remains inside the already approved Round 1 scope and permanent stop lines:

```text
ALLOW_REMEDIATION_COMMITS_IN_PR_493 = true
ALLOW_NEW_PR_FAST_AFTER_SOURCE_CHANGE = true
ALLOW_REPLACEMENT_EXACT_HEAD_FULL_RC_AFTER_FAILED_RC = true
ALLOW_REPEAT_PR_FAST_AND_FULL_RC_UNTIL_FINAL_SUCCESS = true
FAILED_VALIDATION_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_RC_ATTEMPTS_CONSUME_FINAL_SUCCESS_SLOT = false
FAILED_RUN_31151557970_IS_FINAL_RC = false
ONE_SUCCESSFUL_FINAL_RC_REQUIRED = true
```

In plain language, the owner authorizes:

> 允许在 PR #493 上提交 Round 1 修复；每次 source head 改变后重新运行 PR Fast，并在该新 head 的 PR Fast 成功后触发新的替代性 exact-head Full RC；失败的 run `31151557970` 只保留为失败证据，不计作最终成功 RC。只要修复仍属于 Round 1 范围，就继续按相同流程修复、重新验证和触发新的 exact-head Full RC，直到最终成功并完成全部验收，不需要再次申请 owner 授权。

## Meaning of the delivery-count constraints

The historical wording `one PR Fast` or `one final exact-head Full RC` must **not** be interpreted as a lifetime attempt limit.

The binding interpretation is:

```text
ONE_RUNTIME_PR = exactly one Round 1 runtime PR (#493)
ONE_SUCCESSFUL_FINAL_RC = exactly one successful Full RC on the final accepted PR head
ONE_MERGE = exactly one final merge
ONE_ACCEPTED_DEPLOYMENT = exactly one final accepted deployment
```

The following may occur multiple times while the same PR is being remediated:

```text
PR_FAST_ATTEMPTS = AS_NEEDED_AFTER_EACH_SOURCE_HEAD_CHANGE
FULL_RC_ATTEMPTS = AS_NEEDED_AFTER_EACH_PR_FAST_GREEN_CANDIDATE_HEAD
LOCAL_VALIDATION_ATTEMPTS = AS_NEEDED
```

Failed attempts are retained as evidence and do not satisfy or consume the final-success requirement.

## Required remediation loop

For every in-scope failure:

```text
PRESERVE_FAILURE_EVIDENCE
-> DIAGNOSE_ROOT_CAUSE
-> MINIMAL_FIX_IN_PR_493
-> LOCAL_AFFECTED_VALIDATION
-> NEW_HEAD_PR_FAST_REQUIRED_SUCCESS
-> NEW_EXACT_HEAD_FULL_RC
-> IF_FAILED_REPEAT
```

If source changes, the previous RC cannot be used as release evidence for the new head.

If the source head does not change and the failure is demonstrably transient infrastructure/external failure, a repository-policy-compliant retry of the failed validation may be performed without additional owner authorization. The retry must not bypass or weaken any guard.

## Current failed attempt

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
```

The required next action is to remediate that failure in PR #493, then run PR Fast on the new head and trigger a replacement exact-head Full RC.

## Never authorized by this continuation

This continuation does not authorize:

```text
SECOND_ROUND_1_RUNTIME_PR
ROUND_2
ROUND_3
LEAGUE_EXPANSION
PROVIDER_POLICY_CHANGE
PROVIDER_ALLOWLIST_CHANGE
SCHEDULER_POLICY_CHANGE
NEW_PROVIDER_CALLS_INITIATED_BY_ROUND_1
PHASE_0_5_RERUN
H_ACCESS
SIGNAL_LEDGER_FOR_EXECUTION
PORTFOLIO
RISK_KELLY
TWO_LEG_PARLAY
REAL_MONEY
BETTING_EDGE_CLAIMS
BYPASS_OR_WEAKEN_REQUIRED_GATES
REBASELINE_PROTECTED_HASHES_ONLY_TO_GET_GREEN
AUTO_MERGE
```

Candidate, Formal, Lock and Production remain OFF.

## Completion condition

Codex must continue until all of the following are true:

```text
FINAL_PR_FAST_REQUIRED = SUCCESS
FINAL_EXACT_HEAD_FULL_RC = SUCCESS
FINAL_RC_SOURCE_SHA = FINAL_PR_HEAD_SHA
FINAL_RC_SOURCE_TREE_SHA = ISSUED_AND_VERIFIED
FINAL_API_IMAGE_DIGEST = ISSUED_AND_VERIFIED
FINAL_WEB_IMAGE_DIGEST = ISSUED_AND_VERIFIED
MERGE = SUCCESS
MERGE_METHOD = MERGE_COMMIT
API_WEB_SAME_VERIFIED_SOURCE_DEPLOYMENT = SUCCESS
PUBLIC_API_ACCEPTANCE = PASS
PUBLIC_BROWSER_ACCEPTANCE = PASS
BROWSER_CONSOLE_ERRORS = 0
ROUND_1_ACCEPTANCE_CRITERIA = ALL_PASS
ROUND_1 = PASS
```

Until those conditions are all true:

```text
ROUND_1 = IN_PROGRESS_REMEDIATION
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
```

If a proposed fix requires crossing a permanent stop line or expanding beyond the approved Round 1 product/runtime scope, stop and request owner authorization for that scope expansion. Ordinary bounded remediation, PR Fast re-runs and replacement exact-head Full RC attempts do not require another owner authorization.