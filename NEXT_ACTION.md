# NEXT ACTION

```text
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
OWNER_DECISION = APPROVED_EXECUTE_CONTINUOUSLY
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
FREE_FIXTURE_VALIDATION = FREE_FIXTURE_CENTRIC_CURRENT_DATA_WORKS
PR_495 = OPEN_MERGEABLE_FAST_CI_PASS
ROUND_3 = NOT_STARTED
```

Binding authorities:

```text
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_AUTHORIZATION.md
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_ACCEPTANCE.md
REPOSITORY_HYGIENE_POLICY.md
```

## Goal

Do not stop after one sub-step. Complete the entire chain:

```text
REFETCH
-> INDEPENDENTLY AUDIT PR #495
-> FIX QUOTA/OTHER IN-SCOPE DEFECTS
-> RUN ALL PRE-MERGE GATES
-> MERGE PR #495
-> REFETCH MAIN
-> ADD ONE BOUNDED EXISTING-SCHEDULER SHADOW INTEGRATION PR IF NEEDED
-> RUN PR/RC GATES
-> MERGE
-> DEPLOY THROUGH NORMAL IMMUTABLE RELEASE PATH
-> VERIFY ONE-STEP ROLLBACK
-> ACTIVATE FREE BRIDGE SHADOW_ONLY
-> RUN BOUNDED REAL FREE-PLAN ACCEPTANCE
-> REPOSITORY HYGIENE
-> FINAL RECEIPT
-> STOP BEFORE ROUND 3
```

For in-scope failures, fail closed at the failed gate, fix, rerun and continue. Do not ask the owner again merely because a test/CI/runtime acceptance failed.

## Known mandatory pre-merge fix

Independent review found PR #495 currently models:

```text
daily_hard_cap = 80
reserve = 20
```

but then computes capacity as `80 - 20 - actual`, while the shared quota helper also protects the reserve. This makes the effective W2 ceiling 60.

Required semantics are exactly:

```text
PROVIDER_DAILY_LIMIT = 100
W2_DAILY_CALL_CEILING = 80
MIN_PROVIDER_DAILY_REMAINING = 20
EFFECTIVE_W2_CEILING = 80_NOT_60
```

Fix and test this before PR #495 may merge.

## Other hard requirements

- quota accounting must reconcile all API-Football traffic sharing the same key, not only bridge calls;
- process restart must not reset daily usage truth;
- local ledger and Provider remaining/limit evidence must reconcile; stricter wins;
- Free defaults to single fixture ID; `fixtures?ids` stays disabled because it was plan-restricted;
- no idle polling, duplicate request keys or unnecessary fresh-cache calls;
- avoid redundant fixture-detail calls when discovery already provides canonical identity evidence;
- only existing 13 whitelist competitions may receive follow-up calls;
- four audit-only leagues remain runtime-unreachable;
- runtime owner must live in the existing scheduler/operations framework; no second daemon;
- collection states must cover discovery, prematch market, lineup window and postmatch statistics with deterministic quota priority;
- optional enrichment must yield before core market evidence on heavy days;
- bridge activation is `SHADOW_ONLY`;
- Candidate/Formal/Lock/Production remain OFF;
- no Round 3 work.

## Provider budget

```text
FREE_PROVIDER_LIMIT = 100/day
W2_MAX = 80/day
RESERVE = at least 20/day
TASK_NEW_REAL_ACCEPTANCE_CALLS <= 20
AUTOMATIC_RETRY = false
```

Use fewer calls when possible. No spending for the sake of consuming quota.

## Completion

Only stop successfully when `FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_ACCEPTANCE.md` is fully PASS and `FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_RECEIPT.md` exists.

Expected final state:

```text
FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME = PASS
FREE_BRIDGE_MODE = SHADOW_ONLY
API_FOOTBALL_PRO_RENEWAL = NOT_REQUIRED_NOW
ACTIVE_WHITELIST = 13_UNCHANGED
REPOSITORY_HYGIENE = PASS
ROUND_3 = NOT_STARTED
NEXT = AWAIT_OWNER_ROUND_3_OR_BIG_FIVE_COLLECTION_DECISION
```
