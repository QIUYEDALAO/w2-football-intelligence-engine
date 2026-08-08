# W2 Repository Agent Instructions

Current task authority is `origin/context/current`.

Read first:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. ROUND_2_FINAL_RECEIPT.md
4. ROUND_2_FINAL_CAPABILITY_MATRIX.json
5. ROUND_2_TERMINAL_CLOSURE_AUTHORIZATION.md
6. ROUND_2_ACCEPTANCE_CRITERIA.md
7. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
ACTIVE_NEXT_ACTION = AWAIT_OWNER_POST_R2_CAPABILITY_DECISION
ROUND_3 = NOT_STARTED
```

Round 2 is closed: 17/17 Provider rows are `PLAN_RESTRICTED`, all temporal
evidence is insufficient, promotion rows are zero, active whitelist is the
unchanged 13, and repository hygiene passed.

Do not resume R2-B, recreate its heartbeat, start Round 3, enable leagues, add
persistent collection or change Provider/Scheduler policy without new owner
authority. Every future task must satisfy `REPOSITORY_HYGIENE_POLICY.md`
before PASS.

Permanent guards:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
BETTING_EDGE_CLAIM = FORBIDDEN
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
H_RESULT_ACCESS = PERMANENTLY_CLOSED
REAL_MONEY = NOT_AUTHORIZED
```
