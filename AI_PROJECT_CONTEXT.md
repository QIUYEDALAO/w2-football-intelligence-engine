# W2 AI Project Context

Current mutable context is maintained on branch `context/current`. Read:

- `CURRENT_CONTEXT.md`
- `CURRENT_STATE.yaml`
- `CURRENT_TASK_CHECKLIST.md`
- `NEXT_ACTION.md`
- `AI_QUANT_PROJECT_CONTEXT.md`
- `QUANT_AGENTS.md`

Context changes are direct replacements and do not use PR, CI, Release Candidate, image build or deployment.

## Current product decision

W2 is not continuing the Sporttery-specific direction. It also is not yet authorized to become a full quant platform.

The current program is a bounded feasibility gate:

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
RESEARCH = PINNACLE_CLOSING_MAINLINE_AH_AND_OU25
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R1_D_TRAIN_AND_V_MANIFEST
```

The deployed operational W2 V4, Dashboard and controlled Scheduler remain unchanged. Candidate, Formal, Lock and Production remain off.

## Decision logic

- No edge or insufficient evidence does not authorize a quant-platform build.
- Predictive increment only authorizes, at most, a later minimal forward Signal Ledger/Shadow measurement design.
- Only an `ECONOMIC_EDGE_CANDIDATE` authorizes drafting the complete W2 Football Quant Platform design.

## Current research scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26

PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS = PINNACLE_ONLY
```

Primary models are market-only M0, pure-goals per-division Dixon-Coles M2, and separately trained M4 PRE/CLOSE binary residual models. Cross-source M1/M3 are secondary and cannot gate the final conclusion.

## Staged outcome access

```text
R0: D/V/H closed, binding recheck.
R1: D outcomes only for training.
R2: freeze V prediction and selection manifests before V outcomes.
R2B: open V once and apply continuation gate.
R3: only after V pass, refit fixed final models on D+V.
R4: freeze H prediction and selection manifests before H outcomes.
R5: open H once and issue the final verdict.
```

V uses static train-D evaluation. H uses static D+V refit and no H outcome update.

## Immediate work

1. Recompute B1–B5 and relevant-code binding.
2. Unlock D results only.
3. Fit M2 for 20 divisions and train-only rho grid.
4. Fit all frozen M4 PRE/CLOSE L2 candidates independently.
5. Generate and freeze V candidate prediction and PRE-selection manifests.
6. Stop before reading V results.

## Hard boundaries

```text
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PROVIDER_CALLS = 0
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED

PERSISTENT_SCHEDULER = ON_CONTROLLED
CANDIDATE = OFF
FORMAL = OFF
LOCK = OFF
PRODUCTION = OFF
```

Current `ev_se` is lambda-scenario EV dispersion, not sampling standard error, and cannot be used as a confidence bound.
