# W2 Copilot / Codex Current Instructions

Read from branch `context/current` before acting:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `AI_PROJECT_CONTEXT.md`
7. `AI_QUANT_PROJECT_CONTEXT.md`
8. `QUANT_AGENTS.md`

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

## Current work

Perform one bounded API/Web semantic refactor:

- recommendation-first to intelligence-first;
- deterministic intelligence states;
- separate event/data/model/collection risk dimensions;
- stable market/zero-alert days as valid output;
- V4 retained as diagnostic input, not public product authority;
- model/market divergence forbidden from generating opportunity, edge, value or recommendation language.

Required states:

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

## Round 1 boundaries

```text
LEAGUE_EXPANSION = false
PROVIDER_POLICY_CHANGE = false
SCHEDULER_POLICY_CHANGE = false
NEW_PROVIDER_CALLS = 0
ROUND_2 = NOT_STARTED
ROUND_3 = NOT_STARTED
```

Use one clean worktree, one runtime PR, one exact-head full validation and one deployment. Stop after Round 1 acceptance.

## Future design guard

Round 3 Market Radar must use:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Higher overround is a market-thinness/noise condition, not a value signal. High-overround isolated moves should normally be `THIN_MARKET_NOISE` unless persistence or independent bookmaker confirmation supports a stronger alert. Exact thresholds wait for the Round 2 live capability audit.

## Permanent stop

Do not build Signal Ledger for execution, Portfolio, Risk/Kelly, 2×1 or real-money workflows. Do not claim betting edge. Candidate, Formal, Lock and Production remain off.

Context updates on `context/current` do not use PR or CI. Runtime changes still require the normal guarded delivery process.
