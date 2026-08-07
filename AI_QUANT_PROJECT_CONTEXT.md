# W2 Football Quant — AI Handoff

Read first from branch `context/current`:

1. `CURRENT_CONTEXT.md`
2. `CURRENT_STATE.yaml`
3. `CURRENT_TASK_CHECKLIST.md`
4. `NEXT_ACTION.md`
5. `QUANT_AGENTS.md`

Context updates do not use PR, CI, Release Candidate, image build or deployment.

## Current decision

```text
PROGRAM = W2_FOOTBALL_QUANT_EDGE_EXISTENCE
PROTOCOL = W2_PHASE_0_5_AH_OU_EDGE_EXISTENCE_PROTOCOL_V1_RC3
PROTOCOL_FROZEN = true
ACTIVE_NEXT_ACTION = W2_PHASE_0_5_R2B_V_EVALUATION_AND_CONDITIONAL_H_MANIFEST_FREEZE
CURRENT_STATUS = R1_R2_FREEZE_REPORTED_PREUNLOCK_RECHECK_REQUIRED
```

Do not build the quant platform yet. The current decision is whether frozen D-trained models and PRE selection rules survive the V seasons.

## R1/R2 reported freeze

```text
D_TRAINING_ROWS = 21518
M2_DIVISIONS_FITTED = 20
V_CANDIDATE_PREDICTION_ROWS = 14909
V_PRE_SELECTION_CANDIDATE_ROWS = 59636

V_CANDIDATE_PREDICTION_MANIFEST_SHA256 =
591314c9f13fc3256ca51aef6c65953150f40912e776ff8d6347b1701d24033f

V_PRE_SELECTION_CANDIDATE_MANIFEST_SHA256 =
e582585aaa57ac5cac894a2fad071dfadfa6ad7890b84ba4c8b3d74e4bd3fe13
```

Receipt:

```text
/Users/liudehua/.hermes/workspace/w2-phase05-research/
r1_v_manifest_20260807/artifacts/R1_R2_FREEZE_RECEIPT.json
```

## Current result gate

```text
D = available for existing training and conditional final refit
V = one-time unlock only after freeze recheck passes
H = closed
```

## Immediate execution

### Step 1 — Pre-unlock recheck

Re-hash and validate the full R1/R2 freeze pack without V outcomes. Confirm:

- both frozen V SHA values;
- deterministic rerun identity;
- all 16 M4 candidates;
- M4 PRE visible CLOSE-field count = 0;
- PRE/CLOSE parameter and training isolation;
- V/H outcome reads = 0 during R1/R2;
- Provider, production write, PR, CI and deployment = 0.

Failure keeps V/H closed and stops.

### Step 2 — Open V once

After the precheck passes:

- calculate paired Log Loss, Brier, calibration and predictive lift for OU 2.5 and AH half-goal markets;
- settle frozen OU 2.5 PRE selections at original PRE line/price;
- evaluate all four frozen L2 values only;
- choose final L2 using V only;
- do not add features, markets, thresholds or candidates.

### Step 3 — Conditional continuation

If V fails:

```text
H_RESULT_ACCESS = PERMANENTLY_CLOSED
FINAL_VERDICT = NO_EDGE | INSUFFICIENT_EVIDENCE
```

Stop.

If V passes:

- refit final M2/M4 PRE/M4 CLOSE on D+V;
- freeze final model/training/feature/parameter hashes;
- generate and freeze H prediction and H PRE-selection manifests without H outcomes;
- calculate H selected-order count and design-side MDE;
- stop before H result access.

## Non-negotiable boundary

```text
H_RESULT_COLUMNS_READ = false
PROVIDER_CALLS = 0
PRODUCTION_CODE_CHANGE = false
PRODUCTION_MODEL_CHANGE = false
PRODUCTION_DB_WRITES = 0
SIGNAL_LEDGER_DEVELOPMENT = false
PORTFOLIO_DEVELOPMENT = false
PR_CREATED = false
CI_RUN = false
DEPLOYMENT_EXECUTED = false
REAL_MONEY = NOT_AUTHORIZED
```

Current `ev_se` is lambda-scenario dispersion, not sampling standard error. It may not be used as a confidence interval or admission gate.
