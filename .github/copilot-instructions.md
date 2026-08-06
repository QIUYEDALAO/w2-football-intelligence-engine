# W2 Copilot / Codex Current Instructions

Read the following files from branch `context/current` before acting:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `AI_QUANT_PROJECT_CONTEXT.md`
6. `QUANT_AGENTS.md`

Do not use the obsolete Sporttery-specific context as current authority.

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R1_D_TRAIN_AND_V_MANIFEST
```

## Current work only

- recheck B1–B5 and relevant code binding;
- open D outcomes for training only;
- fit per-division pure-goals Dixon-Coles M2 with train-only rho grid;
- fit independently parameterized M4 PRE and M4 CLOSE L2 candidates;
- generate and freeze V prediction and PRE-selection manifests;
- stop before reading V outcomes.

## Result gates

```text
D = training-only after R0 recheck
V = closed until V manifests are frozen
H = closed until final H manifests are frozen
```

No V/H early read, no threshold/feature/market/devig change after protocol freeze.

## Frozen scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26
PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS = PINNACLE_ONLY
```

## Hard stop

Do not modify production code, production models, V4, Scheduler, Provider allowlist, production DB or Dashboard. Do not call Providers, deploy, build Signal Ledger, Portfolio, Risk, Kelly, 2×1 or any real-money workflow.

`ev_se` is scenario sensitivity, not sampling standard error, and must not be used as a confidence bound.

Context updates on `context/current` do not use a PR or CI. Runtime changes still use the normal guarded delivery process.
