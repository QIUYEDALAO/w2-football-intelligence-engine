# W2 Market Intelligence Agent Instructions

Read current authority from `origin/context/current` before acting.

Required execution files:

```text
CURRENT_CONTEXT.md
CURRENT_STATE.yaml
CURRENT_PRODUCT_DESIGN.md
CURRENT_TASK_CHECKLIST.md
NEXT_ACTION.md
ROUND_1_CODEX_EXECUTION.md
ROUND_1_ACCEPTANCE_CRITERIA.md
```

Current task:

```text
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

The Phase 0.5 hypothesis is closed with `NO_EDGE`. Do not reopen H or retune the failed model family.

Permanent guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

## League boundary

```text
ACTIVE_WHITELIST = 13_UNCHANGED_IN_ROUND_1
FUTURE_CANDIDATE_UNION = 17_NOT_STARTED
```

The European `5 + 6` cohort is not the whitelist. Future arithmetic is 13 existing + 4 net-new. Round 1 performs no league expansion and no new Provider calls.

## Round 1 scope

- intelligence-first public product;
- seven deterministic intelligence states;
- four independent event/data/model/collection risk dimensions;
- `MARKET_STABLE`/zero-alert result is valid;
- V4 remains diagnostic input, not public product authority;
- market facts remain independent of V4 selection;
- divergence never creates opportunity/value/edge/recommendation meaning;
- preserve the existing 13 whitelist, Provider policy and Scheduler behavior.

Detailed implementation is binding in `ROUND_1_CODEX_EXECUTION.md`.

Acceptance is binding in `ROUND_1_ACCEPTANCE_CRITERIA.md`.

## Prohibited Round 1 work

```text
league expansion
new Provider calls
Provider allowlist/policy changes
Scheduler policy changes
full Market Radar scoring
full Model Lab analytics
Signal Ledger for execution
Portfolio
Risk/Kelly
2x1
real money
betting-edge claims
```

Candidate, Formal, Lock and Production remain OFF.

Use one runtime PR, one final exact-head Full Release Candidate, one merge and one deployment; stop after public acceptance.
