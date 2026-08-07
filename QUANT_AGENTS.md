# W2 Football Quant Agent Instructions

Before any Phase 0.5 work, read in order from branch `context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `AI_QUANT_PROJECT_CONTEXT.md`

Context is updated directly on `context/current`; do not create a context PR or run context CI.

## Current task

```text
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
PROTOCOL_FROZEN = true
EXECUTION = AUTHORIZED_STAGEWISE
```

## Required flow

1. Revalidate the R1/R2 freeze pack and both V manifest hashes without V outcomes.
2. If any validation fails, keep V/H closed and stop.
3. If validation passes, open V results once.
4. Evaluate frozen model/L2 candidates and frozen OU 2.5 PRE selections only.
5. If V fails, permanently close H and stop with `NO_EDGE` or `INSUFFICIENT_EVIDENCE`.
6. If V passes, refit fixed final models on D+V, generate/freeze H prediction and PRE-selection manifests without H outcomes, then stop.

## Workspace and evidence

- use the existing canonical frozen RC3 pack and R1/R2 artifact directory;
- do not regenerate or silently replace frozen V manifests;
- recompute exact file-byte SHA-256 values before V unlock;
- record all result-column access;
- generated research artifacts remain outside tracked production paths;
- no PR, CI or deployment.

## Result-access discipline

```text
D = existing training data and conditional D+V refit
V = one-time access only after pre-unlock verification
H = closed throughout the current task
```

Never read H results. Never use V/H results to add features, models, markets, thresholds, devig methods or candidates.

## Frozen scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26
PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS_SOURCE = PINNACLE_ONLY
L2_GRID = 0.01,0.1,1.0,10.0
```

M4 PRE and CLOSE are independently trained and hashed. CLOSE information may not influence PRE selection.

## Statistical integrity

- `ev_se` is `EV_SCENARIO_SD`, not sampling standard error;
- use V only to select among the frozen L2 grid;
- predictive lift is `market_log_loss - model_log_loss`;
- line-moved orders remain in PRE ROI at original PRE line/price;
- same-line CLV is exploratory only;
- actual selected-order count determines economic power;
- M1/M3, AH economics, integer/quarter lines and individual leagues cannot independently trigger GO.

## Prohibited work

- no production code/model changes;
- no Provider calls;
- no production DB writes;
- no Signal Ledger, Portfolio, Risk, Kelly, Dashboard or 2×1;
- no changes to V4, Scheduler or Provider allowlist;
- no H result access;
- no real-money or automated betting.

## Current stop line

The current execution must end in one of two states:

### V gate fails

```text
H_RESULT_ACCESS = PERMANENTLY_CLOSED
FINAL_VERDICT = NO_EDGE | INSUFFICIENT_EVIDENCE
```

### V gate passes

```text
FINAL_MODELS = FROZEN
H_PREDICTION_MANIFEST_SHA256 = FROZEN
H_SELECTION_MANIFEST_SHA256 = FROZEN
H_RESULT_COLUMNS_READ = false
```

Do not automatically start the one-time H audit.
