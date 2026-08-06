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
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_FROZEN_ARTIFACT_RECOVERY
PROTOCOL_FROZEN = true
EXECUTION = BLOCKED_UNTIL_ARTIFACT_RECOVERY
```

## Workspace

- use a clean local research worktree based on the verified source head;
- recompute B1–B5 and the relevant-code manifest before result access;
- stop on any source, artifact, split or guard drift;
- keep generated data and reports outside tracked production paths;
- do not deploy.

## Result-access discipline

```text
R0: D/V/H closed.
R1: D training results only.
R2: freeze V candidate prediction and selection manifests while V remains closed.
R2B: V opens once; H remains closed.
R3/R4: refit D+V and freeze H manifests while H remains closed.
R5: H opens once; no model or selection change afterward.
```

Never read V or H results early. Never use H results for model fit, threshold choice, feature choice, market scope, devig choice or selection changes.

## Frozen research scope

```text
SOURCE = FOOTBALL_DATA_MMZ_ONLY
D = 2019_20,2020_21,2021_22
V = 2022_23,2023_24
H = 2024_25,2025_26

PRIMARY_PREDICTIVE = OU_2_5,AH_HALF_GOAL_LINES
PRIMARY_ECONOMIC = OU_2_5
ODDS_SOURCE = PINNACLE_ONLY
```

M2 and M4 parameters are fixed by `CURRENT_CONTEXT.md`. M4 PRE and CLOSE must be trained independently.

## Prohibited work

- no production code/model changes;
- no Provider calls;
- no Signal Ledger or product strategy implementation;
- no Portfolio, Risk, Kelly, Dashboard or 2×1;
- no changes to V4, Scheduler, Provider allowlist or production DB;
- no real-money or automated betting.

## Statistical integrity

- current `ev_se` is `EV_SCENARIO_SD`, not sampling standard error;
- use only the frozen two-stage bootstrap and Holm family;
- line-moved orders remain in PRE ROI at original PRE line and price;
- same-line CLV is exploratory only;
- individual-league and M1/M3 results cannot independently trigger GO;
- actual selected-order count, not eligible population, determines economic power.

## Current required stop

Finish R1/R2 with:

```text
V_CANDIDATE_PREDICTION_MANIFEST_SHA256 = frozen
V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 = frozen
V_RESULT_COLUMNS_READ = false
H_RESULT_COLUMNS_READ = false
PROVIDER_CALLS = 0
DEPLOYMENT_EXECUTED = false
```

Then stop for review.
