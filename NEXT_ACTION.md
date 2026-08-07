# NEXT ACTION

Current action:

```text
W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

## Required authorities

Read current authority from `origin/context/current` in this order:

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
12. `.github/copilot-instructions.md`

Use latest `origin/main` as code baseline. Use `origin/context/current` as current task/product authority when old `main` context conflicts.

## Binding league correction

Current active whitelist:

```text
ACTIVE_WHITELIST = 13
ROUND_1_WHITELIST_CHANGE = FORBIDDEN
```

Round 1 must preserve exactly these 13 identities:

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

The European `5 + 6` grouping is **not** the total whitelist.

The six Extended Radar names contain two existing whitelist competitions (`Eredivisie`, `Primeira Liga`) and only four net-new future candidates:

```text
Belgian Pro League
Turkish Super Lig
Greek Super League
Scottish Premiership
```

Therefore future Round 2 planning uses:

```text
13 EXISTING + 4 NET_NEW = 17 TOTAL CANDIDATES
```

Do not add the four new candidates in Round 1.

## Round 1 objective

Convert the public product from recommendation-first to intelligence-first while preserving the existing operational foundations.

Required outcomes:

1. Public identity becomes `W2 Football Intelligence`.
2. Implement the seven deterministic intelligence states and frozen precedence.
3. Implement four independent risk dimensions.
4. `MARKET_STABLE` and zero material alerts become valid non-empty results.
5. `RecommendationDecisionV4` is retained but becomes `DIAGNOSTIC_INPUT_NOT_PRODUCT_AUTHORITY`.
6. Model-market divergence cannot produce opportunity/value/edge/recommendation semantics anywhere in the public projection or browser UI.
7. Real market facts remain visible independently of V4 pick/no-pick state when their own data/freshness truth permits it.
8. Public page forms `Market Overview`, `Match Intelligence`, `Data & Operations Summary`.
9. Existing real cards, empty-day state, release SHA and operational health remain truthful.
10. Current 13 whitelist identities remain unchanged.

## Execution and acceptance

Codex execution authority:

```text
ROUND_1_CODEX_EXECUTION.md
```

Binding acceptance criteria:

```text
ROUND_1_ACCEPTANCE_CRITERIA.md
```

Do not substitute a self-invented task decomposition for those files.

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
ACTIVE_WHITELIST = 13_UNCHANGED
PROVIDER_POLICY_CHANGE = false
PROVIDER_ALLOWLIST_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2_CAPABILITY_AUDIT = NOT_STARTED
ROUND_3_MARKET_RADAR = NOT_STARTED

CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Use one bounded runtime PR, one final exact-head Full Release Candidate, one merge, one deployment and one public browser acceptance. Stop after Round 1 PASS; do not begin Round 2 automatically.
