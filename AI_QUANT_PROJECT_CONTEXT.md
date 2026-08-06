# W2 Football Quant — AI Handoff

Read first:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`

These files on branch `context/current` are the current mutable authority. Context updates do not use PR, CI, Release Candidate, image build or deployment.

## Current decision

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
EXECUTION = AUTHORIZED_STAGEWISE
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R1_D_TRAIN_AND_V_MANIFEST
CURRENT_STATUS = READY_R1_AFTER_EXACT_ARTIFACT_RECOVERY
```

Do not build a quant platform yet. First determine whether W2 has out-of-sample predictive or economic edge in Pinnacle AH/OU markets.

## Current scope

```text
CONFIRMATORY_SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26

PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
PINNACLE_ONLY = true
```

Primary models:

```text
M0_PRE / M0_CLOSE = Pinnacle market-only
M2 = pure-goals Dixon-Coles per division, train-only rho grid
M4_PRE / M4_CLOSE = separately trained binary market-residual models
M1 / M3 = secondary, cross-source, not gating
```

## Current outcome-access gate

```text
D = training-only for R1
V = closed until all V candidate prediction/selection manifests are frozen
H = closed until final H prediction/selection manifests are frozen
```

V and H use static evaluation:

```text
V = train D; no V-outcome model update
H = refit D+V; no H-outcome model update
```

## Immediate handoff

The next execution must:

1. Bind R1 to the recovered read-only RC3 pack.
2. Unlock D results only.
3. Fit M2 for 20 divisions and 41 rho candidates per division.
4. Fit all frozen M4 PRE and M4 CLOSE L2 candidates independently.
5. Generate V candidate prediction and PRE-selection manifests without reading V outcomes.
6. Freeze both V SHA-256 values.
7. Stop and report before opening V results.

## Non-negotiable boundaries

```text
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PROVIDER_CALLS = 0
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED
```

Do not modify V4, production rho, Scheduler, Provider allowlist, production DB or Dashboard.

Current `ev_se` is lambda-scenario EV dispersion, not sampling standard error. It must not be used as a confidence interval or statistical admission gate.

## Final decision mapping

```text
INSUFFICIENT_EVIDENCE
→ no edge claim; consider a new evidence protocol only.

NO_EDGE
→ stop quant-platform development.

PREDICTIVE_INCREMENT_ONLY
→ at most design a minimal forward Signal Ledger and fixed-unit Shadow measurement.

ECONOMIC_EDGE_CANDIDATE
→ authorize the full W2 Football Quant Platform total-design document; still no real money.
```
