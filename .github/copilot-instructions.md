# W2 Copilot / Codex Current Instructions

Use latest `origin/main` as code baseline and `origin/context/current` as task authority.

Read in order:

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
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_BRIDGE_CONTROLLED_RUNTIME_CLOSURE
OWNER_DECISION = APPROVED_EXECUTE_CONTINUOUSLY
API_FOOTBALL_PRO_RENEWAL = NOT_AUTHORIZED_NOW
ROUND_3 = NOT_STARTED
```

Do not stop after a sub-step. Review/fix PR #495, pass all gates, merge, add one bounded existing-scheduler Shadow integration PR if needed, pass release gates, deploy through normal immutable release procedure, prove rollback, activate `SHADOW_ONLY`, run bounded real Free-plan acceptance, execute repository hygiene, write the final receipt, then stop before Round 3.

For in-scope failures: fail closed at the gate, repair minimally, rerun and continue without requesting owner approval again.

Mandatory pre-merge correction: current PR #495 effectively limits Free bridge use to 60/day by subtracting a 20-call reserve from an 80 cap while the quota helper also protects reserve. Final semantics must be Provider 100/day, W2 max 80/day, at least 20 remaining; no double subtraction.

Quota accounting must be shared across all API-Football traffic using the same account/key and survive restart. Bridge-local accounting alone is forbidden.

Keep exact existing 13 whitelist, four audit-only leagues unreachable, no second scheduler daemon, no paid renewal, no new Provider, Candidate/Formal/Lock/Production OFF and Round 3 not started. `REPOSITORY_HYGIENE_POLICY.md` is mandatory before PASS.
