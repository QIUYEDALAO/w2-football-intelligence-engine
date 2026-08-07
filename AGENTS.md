# W2 Repository Agent Instructions

For current W2 work, read branch `context/current` in this order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_PRODUCT_DESIGN.md`
4. `CURRENT_TASK_CHECKLIST.md`
5. `NEXT_ACTION.md`
6. `AI_PROJECT_CONTEXT.md`
7. `AI_QUANT_PROJECT_CONTEXT.md`
8. `QUANT_AGENTS.md`

Context updates are direct replacements on `context/current`; do not create a context PR or run context CI. Runtime code, tests, migrations, workflows and deployments still require the normal guarded delivery process.

## Current program

```text
PRODUCT = W2 Football Intelligence
PROGRAM = W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
OWNER_DECISION = APPROVED
ACTIVE_NEXT_ACTION = W2_MI_R1_PRODUCT_SEMANTICS_AND_STATUS_REFRAME
```

Phase 0.5 ended with `NO_EDGE`; H is permanently closed under that protocol. Do not retune the failed hypothesis on V/H outcomes.

Permanent product guard:

```text
MODEL_MARKET_DIVERGENCE != MARKET_OPPORTUNITY
```

## Current runtime task

Round 1 is a single bounded API/Web semantic refactor:

- recommendation-first to intelligence-first;
- deterministic market/model/data/collection states;
- separate event/data/model/collection risk dimensions;
- stable market/zero alerts as a valid result;
- V4 retained as diagnostic evidence input, not public product authority;
- no league, Provider or Scheduler expansion.

## Required Round 1 states

```text
MARKET_STABLE
MARKET_MOVEMENT
MARKET_ANOMALY
MODEL_MARKET_DISAGREEMENT
DATA_INCOMPLETE
MODEL_DIAGNOSTIC_WARNING
COLLECTION_INCIDENT
```

## Round 1 delivery

- latest trusted `origin/main`;
- one clean worktree;
- one bounded runtime PR;
- one exact-head full validation;
- one merge and one deployment;
- stop after public acceptance.

## Prohibited Round 1 work

- no new leagues;
- no new Provider calls/allowlist changes;
- no Scheduler policy changes;
- no full Market Radar or Model Lab analytics yet;
- no Signal Ledger, Shadow, Portfolio, Risk, Kelly or 2×1;
- no edge/profit/recommendation claim;
- Candidate, Formal, Lock and Production remain off.

## Future Market Radar guard

Round 3 must require:

```text
OVERROUND_PERCENTILE = REQUIRED_ALERT_COVARIATE
```

Higher overround is a thin-market/noise condition, not a value signal. An isolated move in a high-overround context should normally be `THIN_MARKET_NOISE` unless persistence or independent bookmaker confirmation supports a stronger alert.

## Operational safety

All existing fail-closed, identity, canonical serialization, Provider ledger, migration, deployment and production safety rules remain in force. Runtime changes must not weaken any existing guard.
