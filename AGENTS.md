# W2 Repository Agent Instructions

Current authority is `origin/context/current`.

Read first:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_AUTHORIZATION.md
4. FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_ACCEPTANCE.md
5. FREE_PLAN_FIXTURE_CENTRIC_VALIDATION.md
6. FREE_PLAN_DAILY_CALL_BUDGET.md
7. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
OWNER_DECISION = APPROVED_EXECUTE_CONTINUOUSLY
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ROUND_3 = NOT_STARTED
```

Execute the entire authorized chain continuously. Do not stop after PR #495 review, one failing gate, merge, deployment or first shadow run. For bounded in-scope failures: fail closed, fix, rerun and continue.

Known mandatory pre-merge issue: PR #495 currently double-protects the Free reserve, making the effective bridge ceiling 60. Required semantics are provider limit 100, W2 max 80, remaining reserve at least 20. Fix and test before merge.

Shared API-Football quota truth must include all W2 traffic on the same key/account. A bridge-local counter alone is not acceptable. Existing scheduler/operations framework owns runtime; no second scheduler daemon.

Final runtime target is `SHADOW_ONLY`, exact existing 13 whitelist, no audit-only league promotion, no recommendation gates and no Round 3. `REPOSITORY_HYGIENE_POLICY.md` is mandatory before PASS.
