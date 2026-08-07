# W2 Copilot / Codex Current Instructions

Before acting, read from `origin/context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `ROUND_1_CODEX_EXECUTION.md`
7. `ROUND_1_ACCEPTANCE_CRITERIA.md`
8. `AI_PROJECT_CONTEXT.md`
9. `AI_QUANT_PROJECT_CONTEXT.md`
10. `AGENTS.md`
11. `QUANT_AGENTS.md`

Use latest `origin/main` as the code baseline. When old context on `main` conflicts with `origin/context/current`, the current task authority is `origin/context/current`.

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

## Binding league correction

```text
ACTIVE_WHITELIST_BASELINE_COUNT = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Current 13 identities:

```text
chinese_super_league
allsvenskan
eliteserien
premier_league
la_liga
bundesliga
serie_a
ligue_1
brasileirao_serie_a
argentina_primera
mls
eredivisie
primeira_liga
```

The European `5 + 6` cohort is not a replacement whitelist. `Eredivisie` and `Primeira Liga` already exist in the 13 baseline. Future net-new candidates are only:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Future candidate union is `13 + 4 = 17`, but Round 1 must not add/register/enable/audit/call/schedule these four.

## Current work

Perform one bounded API/Web semantic refactor:

- recommendation-first -> intelligence-first;
- seven deterministic intelligence states;
- four independent event/data/model/collection risk dimensions;
- stable market/zero-alert days as valid results;
- V4 retained as diagnostic input, not public product authority;
- market facts independent from V4 pick/no-pick state;
- divergence forbidden from generating opportunity/edge/value/recommendation semantics;
- public shell: Market Overview / Match Intelligence / Data & Operations Summary;
- active whitelist remains exact 13.

Detailed implementation requirements are binding in `ROUND_1_CODEX_EXECUTION.md`.

All acceptance gates are binding in `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Use one clean worktree, one runtime PR, one final exact-head Full Release Candidate, one merge and one deployment. Stop after Round 1 acceptance.

Do not reopen Phase 0.5/H. Do not build Signal Ledger for execution, Portfolio, Risk/Kelly, 2x1, auto-betting or real-money workflows.
