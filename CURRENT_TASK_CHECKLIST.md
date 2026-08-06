# W2 Current Task Checklist

This is the complete current task order for W2. Context updates are made directly on branch `context/current`; no pull request or CI is required for this file.

## Program status

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
EXECUTION = AUTHORIZED_STAGEWISE
ACTIVE_TASK = Q05-R1-D-TRAIN-AND-V-MANIFEST
```

No task below authorizes production changes, Provider calls, deployment, Signal Ledger, strategy productization, portfolio construction or real-money execution.

---

## Q05-00 — Context reset

```text
STATUS = DONE
```

- Stop the Sporttery-specific implementation direction.
- Preserve only the final Sporttery research findings as research evidence; old Sporttery context is not current authority.
- Set W2 Phase 0.5 AH/OU edge existence as the only active workstream.
- Preserve the deployed operational W2 system unchanged.

---

## Q05-01 — Outcome-blind source inventory

```text
STATUS = DONE_REPORTED
FREEZE_0A = PASS
```

Completed facts:

- 156/156 source downloads succeeded.
- 20 mmz divisions × 7 seasons = 140 complete division-season units.
- `new/` cumulative series has no usable Pinnacle AH/OU pairs for this protocol.
- Outcome-blind negative test passed: semantic projection unchanged when result values changed.
- Result-field access attempts fail closed.
- Existing fuzzy/result-dependent join was not used.

Accepted population authority:

```text
AH_HALF_CLOSING_PREDICTIVE = 10816
AH_HALF_PRE_ECONOMIC = 10693
AH_HALF_SAME_LINE_CLV = 6479
OU25_CLOSING_PREDICTIVE = 46483
OU25_PRE_ECONOMIC = 46313
OU25_SAME_LINE_CLV = 46301
SAME_LINE = 31905
LINE_MOVED = 19053
```

---

## Q05-02 — Freeze 0B machine binding

```text
STATUS = PASS_EXACT_ARTIFACT_RECOVERY_RECHECK
```

Before reading any result column, recompute and require PASS:

- B1 `ARTIFACT_SHA_BINDING`
- B2 `COVERAGE_AND_MUTUAL_EXCLUSIVITY`
- B3 `NO_COMPETITION_SEASON_SPANS_SPLITS`
- B4 `RELEVANT_CODE_MANIFEST_BINDING`
- B5 `RESULT_COLUMNS_CLOSED`

Required output:

```text
B1_TO_B5 = PASS
CURRENT_RELEVANT_CODE_MANIFEST_SHA256 = <recomputed>
CURRENT_REPOSITORY_HEAD = <observed>
D_RESULT_ACCESS = CLOSED
V_RESULT_ACCESS = CLOSED
H_RESULT_ACCESS = CLOSED
```

Stop immediately if any artifact, code blob, split membership or result-access guard differs from the frozen protocol.

---

## Q05-R1 — D training and candidate construction

```text
STATUS = NEXT
RESULT_ACCESS = D_ONLY
```

### R1.1 Unlock D only

- Permit result columns only for `2019/20`, `2020/21`, `2021/22`.
- Keep every V and H result column inaccessible.
- Record the exact D source-file and training-population hashes.

### R1.2 Fit M2

For each of the 20 divisions:

- build the pure-goals training population from exact football-data rows;
- fit Dixon-Coles attack/defence and home baseline;
- search train-only `rho = -0.20 ... +0.20`, step `0.01`;
- emit fitted-match count, training cutoff, parameters and model hash;
- fail closed for insufficient training data.

Required artifacts:

```text
M2_DIVISION_MODEL_MANIFEST.json
M2_TRAINING_POPULATION_MANIFEST.json
M2_MODEL_HASHES.json
```

### R1.3 Fit M4 CLOSE candidates

Use D results and CLOSE-only inputs. For each pre-registered L2 value:

```text
0.01
0.1
1.0
10.0
```

fit:

```text
logit(p_final) = logit(p_market) + beta0 + beta1 * (logit(p_M2) - logit(p_market))
```

Generate separate model/training/feature/parameter hashes.

### R1.4 Fit M4 PRE candidates

Repeat independently with PRE-only inputs. Do not share fitted parameters with M4 CLOSE. No CLOSE column may be visible to the PRE training or selection path.

### R1.5 R1 stop conditions

R1 must finish with:

```text
D_RESULT_COLUMNS_READ = true
V_RESULT_COLUMNS_READ = false
H_RESULT_COLUMNS_READ = false
PROVIDER_CALLS = 0
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
```

---

## Q05-R2 — Freeze V candidate predictions and selections

```text
STATUS = BLOCKED_UNTIL_R1_COMPLETE
V_RESULTS = CLOSED
```

Using only D-fitted candidates and V market/identity fields, generate for every candidate:

### V candidate prediction manifest

- fixture natural identity;
- division and season;
- market and line;
- PRE/CLOSE Pinnacle prices;
- M0 probability;
- M2 probability;
- each M4 PRE/CLOSE candidate probability;
- model, parameter, feature and source hashes.

### V PRE selection candidate manifest

For OU 2.5 only:

- calculate OVER and UNDER predicted EV from M4 PRE and PRE odds;
- select the higher side only when predicted EV is at least 3%;
- exact tie => `NO_SELECTION_TIE`;
- lower than 3% => `NO_SELECTION`;
- maximum one primary selection per fixture/market;
- fixed one-unit stake;
- no CLOSE inputs.

Freeze:

```text
V_CANDIDATE_PREDICTION_MANIFEST_SHA256
V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256
```

Then stop. Do not read V results in this task.

---

## Q05-R2B — One-time V evaluation

```text
STATUS = BLOCKED_UNTIL_V_MANIFESTS_FROZEN
H_RESULTS = CLOSED
```

### R2B.1 Unlock V once

After both V manifest hashes are frozen, open V results once.

### R2B.2 Evaluate candidate models

For OU 2.5 and AH half-goal prediction populations:

- paired Log Loss;
- Brier score;
- calibration diagnostics;
- `PREDICTIVE_LIFT = market_log_loss - model_log_loss`;
- paired fixture-level diagnostics;
- coverage and exclusion matrices.

### R2B.3 Select L2 only from frozen grid

- choose the L2 candidate using V only;
- do not add features, models or thresholds;
- do not change market scope, devig or split assignment.

### R2B.4 Evaluate V PRE economic proxy

- settle the already frozen OU 2.5 PRE selections at original PRE line/price;
- fixed one unit;
- line movement remains included in ROI;
- same-line CLV remains exploratory only.

### R2B.5 Apply V gate

If V does not meet the frozen continuation gate:

```text
H_RESULT_ACCESS = PERMANENTLY_CLOSED
```

Issue either:

```text
NO_EDGE
or
INSUFFICIENT_EVIDENCE
```

and stop.

If V passes, continue to R3 without changing the protocol.

---

## Q05-R3 — Final D+V refit

```text
STATUS = BLOCKED_UNTIL_V_GATE_PASS
```

Refit on D+V using the fixed algorithm and V-selected hyperparameters:

- final per-division M2 models;
- final M4 PRE model;
- final M4 CLOSE model.

Freeze:

```text
FINAL_M2_MODEL_HASHES
FINAL_M4_PRE_MODEL_HASH
FINAL_M4_CLOSE_MODEL_HASH
FINAL_TRAINING_POPULATION_HASH
FINAL_FEATURE_MANIFEST_HASH
FINAL_PARAMETER_MANIFEST_HASH
```

No H result may be read.

---

## Q05-R4 — Freeze H predictions and selections

```text
STATUS = BLOCKED_UNTIL_R3_COMPLETE
H_RESULTS = CLOSED
H_EVALUATION_MODE = STATIC_REFIT_D_PLUS_V_NO_H_OUTCOME_UPDATE
```

Using the final D+V models and H market/identity fields only:

- generate all H predictions;
- generate the frozen OU 2.5 PRE selections;
- record selected and no-selection reasons;
- calculate actual selected-order count without reading results;
- calculate the design-side economic MDE from the selected count;
- do not update the model between 2024/25 and 2025/26.

Freeze:

```text
H_PREDICTION_MANIFEST_SHA256
H_SELECTION_MANIFEST_SHA256
```

Then stop before reading any H result.

If selected-order count is too small for the frozen economic test, pre-register:

```text
ECONOMIC_RESULT = INSUFFICIENT_EVIDENCE
```

Prediction evaluation may still proceed.

---

## Q05-R5 — One-time H audit

```text
STATUS = BLOCKED_UNTIL_H_MANIFESTS_FROZEN
```

### R5.1 Unlock H once

Only after both H manifest hashes are frozen.

### R5.2 Predictive evaluation

For OU 2.5 and AH half-goal:

- market-only vs M4 CLOSE paired Log Loss;
- Brier and calibration;
- two-stage competition-season/fixture bootstrap;
- 20,000 resamples, seed `2026080601`;
- Holm correction across the two primary prediction tests;
- minimum practical predictive lift `0.002` nats/fixture.

### R5.3 Economic evaluation

For frozen OU 2.5 PRE selections:

- fixed-unit realized ROI;
- point estimate threshold at least 3%;
- 95% bootstrap lower bound greater than zero;
- report achieved MDE using actual selected-order count;
- line-moved orders remain included at their original PRE line and price.

### R5.4 Stability and concentration

Required:

- leave-one-season-out;
- leave-one-tier/group-out;
- top 5% fixture profit contribution;
- competition-season and fixture clustering;
- model coverage and exclusion bias;
- market score on model-included subset vs full eligible universe.

Individual leagues remain exploratory and cannot independently reverse the pooled verdict.

### R5.5 Prohibitions after H opens

```text
H_MODEL_REFIT = FORBIDDEN
H_SELECTION_CHANGE = FORBIDDEN
H_THRESHOLD_CHANGE = FORBIDDEN
H_LEAGUE_SCOPE_CHANGE = FORBIDDEN
H_DEVIG_CHANGE = FORBIDDEN
```

---

## Q05-R6 — Final verdict and next program

```text
STATUS = BLOCKED_UNTIL_R5_COMPLETE
```

### `INSUFFICIENT_EVIDENCE`

- no claim that edge is absent;
- do not build the quant platform;
- decide whether a new forward-data protocol is worth starting.

### `NO_EDGE`

- stop the quant-platform build;
- preserve W2 as operational data, analysis and market-monitoring infrastructure;
- do not create Signal Ledger, Portfolio, Risk or Quant Dashboard.

### `PREDICTIVE_INCREMENT_ONLY`

- authorize only a minimal forward immutable Signal Ledger and fixed-unit Shadow measurement design;
- no portfolio, Kelly, risk engine or full quant Dashboard;
- require a new forward protocol.

### `ECONOMIC_EDGE_CANDIDATE`

- authorize drafting `W2_FOOTBALL_QUANT_PLATFORM_TOTAL_DESIGN_V1`;
- design Signal Ledger, Strategy Registry, fixed-unit Shadow, settlement, attribution, portfolio and risk in later separately authorized phases;
- still no real money, auto betting, Candidate, Formal, Lock or Production.

---

## Q05-HYGIENE — Execution hygiene

Applies to every task:

- use a clean local research worktree based on the verified source head;
- no Provider calls or production DB writes;
- no release images or deployment;
- no runtime output, source data, database dump or generated report committed to main;
- store artifacts locally with exact SHA-256 manifests;
- delete failed/temp artifacts that are not part of the frozen evidence package;
- do not revive old Sporttery implementation context;
- do not change production rho or V4 during Phase 0.5;
- current `ev_se` is diagnostic scenario dispersion only and cannot be used as statistical standard error.

## Current handoff

```text
NEXT = Q05-R1
STOP_POINT = V_CANDIDATE_PREDICTION_MANIFEST_SHA256_FROZEN
EXPECTED_REPORT = R1_COMPLETE_R2_MANIFESTS_FROZEN_V_RESULTS_UNREAD
```
