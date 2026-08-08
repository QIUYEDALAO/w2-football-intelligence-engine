# W2 Current Context

Current mutable authority is `origin/context/current`.

## Current decision

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = W2_MI_POST_R2_PROVIDER_ACCESS_AND_DATA_SOURCE_DECISION
POST_R2_ACCESS_DECISION = AUTHORIZED_IN_PROGRESS
ROUND_3 = NOT_STARTED
```

Read current execution authority in this order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. POST_R2_PROVIDER_ACCESS_DATA_SOURCE_DECISION.md
4. ROUND_2_FINAL_RECEIPT.md
5. ROUND_2_FINAL_CAPABILITY_MATRIX.json
6. REPOSITORY_HYGIENE_POLICY.md
```

Round 2 is closed: 17/17 Provider rows are `PLAN_RESTRICTED`, 17/17 temporal evidence is insufficient, zero rows are promotion-authorized, and the runtime whitelist remains exact 13.

The current task is to determine the real cause of the Provider access block and choose the viable data-source architecture before Round 3. Up to 8 new read-only diagnostic Provider calls are authorized only if retained evidence and official current Provider documentation cannot distinguish the cause. No retry, business write, 17-league rebatch, purchase, Provider cutover, production Scheduler change, league enablement or Round 3 implementation is authorized.

If an internal W2 season/request/configuration defect is proven, one bounded fix PR is authorized. If the blocker is external entitlement/coverage/account scope, produce a current data-source decision matrix and one preferred recommendation plus fallback instead of making a fake code fix.

`REPOSITORY_HYGIENE_POLICY.md` remains mandatory before PASS.

Permanent guards remain: intelligence-first semantics; active whitelist 13 unless separately authorized; V4 diagnostic-only; no betting-edge/opportunity claim; Candidate/Formal/Lock/Production OFF; H permanently closed; no real-money execution; Round 3 not started.
