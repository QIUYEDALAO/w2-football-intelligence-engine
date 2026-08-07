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
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
```

## Current work

- re-hash and verify the R1/R2 freeze pack before any V outcome access;
- open V outcomes once only after the precheck passes;
- evaluate only the frozen model/L2 candidates and frozen OU 2.5 PRE selections;
- if V fails, keep H permanently closed and stop;
- if V passes, refit final D+V models, freeze H predictions and H PRE selections, then stop before H outcomes.

## Result gates

```text
D = existing training and conditional D+V refit
V = one-time access after pre-unlock verification
H = closed throughout this task
```

No H read. No feature, threshold, market, devig or candidate change after protocol freeze.

## Frozen scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26
PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS = PINNACLE_ONLY
L2 = 0.01,0.1,1.0,10.0
```

## Hard stop

Do not modify production code, production models, V4, Scheduler, Provider allowlist, production DB or Dashboard. Do not call Providers, deploy, create PR/CI, build Signal Ledger, Portfolio, Risk, Kelly, 2×1 or real-money workflows.

`ev_se` is scenario sensitivity, not sampling standard error, and must not be used as a confidence bound.

Context updates on `context/current` do not use PR or CI. Runtime changes still use the normal guarded delivery process.
