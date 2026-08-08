# W2 Copilot / Codex Current Instructions

Use latest `origin/main` as code baseline and `origin/context/current` as task authority.

Read in order:

```text
1. CURRENT_STATE.yaml
2. NEXT_ACTION.md
3. FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md
4. POST_R2_PROVIDER_ACCESS_ROOT_CAUSE.md
5. POST_R2_DATA_SOURCE_DECISION_MATRIX.md
6. ROUND_2_FINAL_RECEIPT.md
7. REPOSITORY_HYGIENE_POLICY.md
```

```text
PRODUCT = W2 Football Intelligence
ROUND_1 = PASS
ROUND_2 = PASS_WITH_TERMINAL_PROVIDER_PLAN_RESTRICTION
POST_R2_ACCESS_DECISION = PASS_FREE_PLAN_SEASON_RESTRICTION_CONFIRMED
ACTIVE_NEXT_ACTION = W2_MI_FREE_PLAN_FIXTURE_CENTRIC_BRIDGE
OWNER_DECISION = DO_NOT_RENEW_API_FOOTBALL_PRO_NOW
ROUND_3 = NOT_STARTED
```

Do not recommend or require API-Football Pro renewal for this task. First exhaust the zero-incremental-cost path using the existing active Free account (100/day).

Validate whether current-season data remains accessible without a season parameter through `fixtures?date`, `fixtures?live`, fixture ID(s), odds by fixture/date, and fixture-scoped injuries/statistics. Target 5-8 new Provider calls, hard max 12, no retries; do not rerun the 17-league season audit. Keep at least 20 daily requests in reserve.

If a useful current fixture-centric path is proven, one bounded bridge PR is authorized and must remain disabled by default. Reuse existing W2 raw payload, endpoint capture, fixture identity and market normalization contracts; add quota-aware planning/cache/deduplication and no idle polling.

If current fixture-centric access is also blocked, do not buy capacity. Produce the zero-cost/low-cost fallback decision defined by `FREE_PLAN_FIXTURE_CENTRIC_BRIDGE.md`; The Odds API Starter may be evaluated as an odds-only zero-dollar candidate, but soccer AH/OU coverage must be verified rather than assumed.

No Provider purchase/renewal, production cutover, Scheduler activation, persistent collection expansion, league enablement or Round 3 is authorized by validation alone.

`REPOSITORY_HYGIENE_POLICY.md` is mandatory before PASS.