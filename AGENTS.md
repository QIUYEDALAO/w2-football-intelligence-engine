# W2 Repository Agent Instructions

For current W2 work, read branch `context/current` in this order:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `AI_QUANT_PROJECT_CONTEXT.md`
6. `QUANT_AGENTS.md`

Context updates are direct replacements on `context/current`; do not create a context PR or run context CI. Runtime code, tests, migrations, workflows and deployment changes still require the normal delivery process.

## Current program

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R1_D_TRAIN_AND_V_MANIFEST
```

The current work is a local, stage-gated AH/OU edge-existence study. It is not quant-platform implementation.

## Required start procedure

- verify the source head and clean worktree;
- recompute B1–B5 and the relevant-code manifest before reading results;
- keep D/V/H result access physically separated;
- stop on any artifact, source, split or guard drift.

## Result-access rules

```text
D = training-only after R0 recheck
V = closed until V candidate prediction and selection manifests are frozen
H = closed until final H prediction and selection manifests are frozen
```

Never use V/H outcomes before the corresponding gate. Never change the frozen protocol after observing V or H results.

## Frozen scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26
PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS_SOURCE = PINNACLE_ONLY
```

## Hard stops

- no production code/model change;
- no Provider call;
- no Signal Ledger, strategy product, Portfolio, Risk, Kelly, Dashboard or 2×1;
- no modification to V4, Scheduler, Provider allowlist or production DB;
- no deployment or real-money action;
- Candidate, Formal, Lock and Production remain off.

## Statistical integrity

- `ev_se` is scenario dispersion, not sampling standard error;
- PRE and CLOSE residual models are trained separately;
- one primary selection per fixture/market;
- line-moved orders stay in PRE ROI at the original PRE line/price;
- same-line CLV and individual-league results are exploratory only;
- actual selected-order count determines economic power;
- use only the frozen bootstrap, seed, metrics and Holm family.

## Current required stop point

```text
V_CANDIDATE_PREDICTION_MANIFEST_SHA256 = frozen
V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 = frozen
V_RESULT_COLUMNS_READ = false
H_RESULT_COLUMNS_READ = false
```

Stop and report at that point.
