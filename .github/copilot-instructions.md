# W2 Copilot / Codex Current Instructions

Use latest `origin/main` as code baseline and `origin/context/current` as task authority.

Read in order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
4. ROUND_2_FINAL_RECEIPT.md
5. ROUND_2_FINAL_CAPABILITY_MATRIX.json
6. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
ROUND_3 = NOT_STARTED
```

Execute the post-R2 root-cause/data-source decision now. Determine whether 17/17 `PLAN_RESTRICTED` is caused by Provider entitlement, season mapping, Provider coverage, account/key entitlement, request/client behavior, multiple causes, or remains unresolved.

Use current official Provider documentation/account evidence. If necessary, at most 8 new read-only diagnostic Provider calls are authorized, with no retry and zero business/checkpoint writes. Do not rerun the 17-league batch.

A bounded fix PR is authorized only if an internal W2 defect is proven. Otherwise produce a decision matrix covering current API-Football, upgrade, alternate full Provider, dedicated odds Provider, and hybrid paths; give one preferred path and one fallback with current cost/coverage/licensing/engineering evidence.

Do not buy/upgrade anything, change credentials, cut over Provider, change production Scheduler/collection, enable leagues, or start Round 3 without new owner authority.

`REPOSITORY_HYGIENE_POLICY.md` is mandatory before PASS.
