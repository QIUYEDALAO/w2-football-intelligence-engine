# W2 Repository Agent Instructions

Current mutable authority is `origin/context/current`.

Read first:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md
4. FREE_PLAN_DAILY_CALL_BUDGET.md
5. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
ACTIVE_NEXT_ACTION = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
FREE_BRIDGE_MODE = SHADOW_ONLY
ACTIVE_WHITELIST = 13_UNCHANGED
ROUND_3 = NOT_STARTED
```

The runtime-closure authorization is consumed. Do not repeat Provider
acceptance, modify deployment, change the whitelist, purchase/cut over a
Provider, enable recommendation gates or start Round 3 without new owner
authority.

The deployed bridge is data infrastructure only. It is owned by the existing
scheduler, uses the shared persistent quota ledger and canonical evidence
contracts, and must preserve Provider 100 / W2 maximum 80 / minimum remaining
20 with no automatic retries.

For any future implementation or code modification in this project, invoke the
project Ponytail skill when available and use it as a minimum-change constraint
plus final simplification review. Correctness, safety, compatibility, tests and
governance remain higher priority than brevity.

Permanent boundaries:

```text
PROVIDER_PURCHASE_OR_RENEWAL = NOT_AUTHORIZED_NOW
PROVIDER_CUTOVER = NOT_AUTHORIZED
ACTIVE_WHITELIST = EXACT_EXISTING_13
AUDIT_ONLY_PROMOTION = NOT_AUTHORIZED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
ROUND_3 = NOT_STARTED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
BETTING_EDGE_CLAIM = FORBIDDEN
REAL_MONEY = NOT_AUTHORIZED
```
