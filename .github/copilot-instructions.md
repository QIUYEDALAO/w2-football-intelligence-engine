# W2 Copilot / Codex Current Instructions

Read from branch `context/current` before acting:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `AI_QUANT_PROJECT_CONTEXT.md`
6. `QUANT_AGENTS.md`

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PHASE_0_5_STATUS = COMPLETE
FINAL_VERDICT = NO_EDGE
ACTIVE_NEXT_ACTION = OWNER_DECISION_REQUIRED_AFTER_NO_EDGE
NEXT_CODE_ACTION = NONE_AUTHORIZED
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

## Evidence

```text
OU_CLOSE_BEST_PREDICTIVE_LIFT = -0.0000758
AH_CLOSE_BEST_PREDICTIVE_LIFT = -0.0006467
OU_PRE_BEST_FROZEN_SELECTIONS = 7566
OU_PRE_BEST_FROZEN_STRATEGY_ROI = -5.32_PERCENT
V_CONTINUATION_GATE = FAIL
```

## Mandatory stop

Do not:

- run R3, R4 or R5;
- open H results;
- change threshold, features, L2 grid, devig method, market scope or split assignment and rerun;
- build Signal Ledger, Shadow, Portfolio, Risk, Kelly, 2×1 or Quant Dashboard;
- change production code/models, V4, Scheduler, Provider allowlist or production DB;
- call Providers, create PR/CI, deploy or perform real-money work.

No code is authorized until the owner chooses the next product direction.

Recommended direction:

```text
W2_FOOTBALL_MARKET_INTELLIGENCE_AND_MODEL_DIAGNOSTICS
```

A future quant experiment requires a new information source, a new edge/model hypothesis and a new pre-registered protocol.

Context updates on `context/current` do not use PR or CI. Runtime changes still require the normal guarded delivery process.
