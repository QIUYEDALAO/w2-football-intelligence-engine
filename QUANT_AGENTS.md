# W2 Football Quant Agent Instructions

Read from branch `context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `AI_QUANT_PROJECT_CONTEXT.md`

Context updates do not use PR or CI.

## Current state

```text
PHASE_0_5_STATUS = COMPLETE
FINAL_VERDICT = NO_EDGE
ACTIVE_NEXT_ACTION = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_ACTION = NONE_AUTHORIZED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

## Mandatory stop

Do not continue R3, R4 or R5. Do not open H. Do not retune the failed protocol using V/H outcomes.

Forbidden:

- changing the 3% PRE selection threshold;
- adding features based on V results;
- changing L2 grid, devig, market scope or split assignment;
- building Signal Ledger, Shadow positions, Portfolio, Risk, Kelly, Dashboard or 2×1;
- changing production models, V4, Scheduler, Provider allowlist or production DB;
- Provider calls, PR, CI, deployment or real-money work.

## Final evidence

```text
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32_PERCENT
V_CONTINUATION_GATE = FAIL
```

## Allowed future work

No code is currently authorized.

The recommended next product direction is:

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

A future quant experiment requires a new information source, a genuinely new model/edge hypothesis and a new pre-registered protocol. The current Phase 0.5 evidence cannot be reused for post-result tuning.

Wait for the owner decision.
