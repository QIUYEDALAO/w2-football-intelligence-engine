# V2-GATE1-CALIBRATION-RECOVERY-01 — frozen protocol

Status: `FROZEN_BEFORE_ANY_RECOVERY_RESULT`

Base commit: `cb8f5d22ded2857d09dfcabda3a159bee165bb5f`

This task is local development only. It cannot pass Gate 1, open Gate 2, admit a
model, amend the forward preregistration, apply a migration, start a collector,
call a Provider, read or write production, deploy, form a candidate, enqueue a
notification, or change EV-SE alpha/beta.

## 1. Objective and terminal status

Produce one new, frozen Factor V2 candidate identity using only the permitted
2024 TRAIN targets and the current local xG snapshot. Diagnose the already known
ECE failure mechanism, fit the minimum calibration layer justified by TRAIN-only
evidence, and emit independently hash-bound corpus, split, preprocessing,
feature, model, calibration, score-matrix and report artifacts.

The terminal programme state is fixed regardless of the observed TRAIN result:

```text
FACTOR_MODEL_V2_GATE1 = FAIL
FACTOR_MODEL_V2_GATE2 = CLOSED
RECOVERY_OUTPUT_ROLE = PROSPECTIVE_CANDIDATE_IDENTITY_ONLY
CONFIRMATION_AUTHORITY = FUTURE_ONE_LOOK_ONLY
```

No report from this task may say that calibration improved on VALIDATION,
HOLDOUT, forward data or production.

## 2. Frozen data roles

### Permitted development set

The sole outcome-visible development universe is the target set in semantic
split manifest
`01a4f593efc3814cf31b6d4a677320513cdc996baf006d59c4c4d029fda243ce`
whose split is `TRAIN`:

```text
kickoff interval = [2024-01-01T00:00:00Z, 2025-01-01T00:00:00Z)
target count = 3,118
historical old-snapshot scorable count = 2,684
```

The 3,118 targets are the denominator. A target that is missing, unjoinable or
unscorable under the current corpus remains in the denominator and in a
reason-coded exclusion manifest. It must not be silently removed.

### Sealed observed sets

```text
2025 VALIDATION targets = 4,520 = OBSERVED_CONFIRMATORY_CONTAMINATED
2026 HOLDOUT targets = 2,628 = OBSERVED_CONFIRMATORY_CONTAMINATED
```

Their fixture IDs may be read only to enforce exclusion. Their outcomes,
features, predictions, scores, calibration curves and aggregate metrics must not
be read by the recovery method or emitted by the result package. Existing
reports may be byte-hash checked as immutable historical failures only.

A self-test must mutate sealed-set outcome fields and prove every recovery
artifact remains byte-identical.

## 3. Frozen local inputs

The task may read these local frozen files and no database:

| Role | Path | File SHA-256 |
|---|---|---|
| target/history corpus | `/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/reports/factor_model_v2/gate1_history_backfill_20260822T055041929427Z/factor_history_corpus.json` | `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2` |
| coverage identity | `/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/reports/factor_model_v2/gate1_history_backfill_20260822T055041929427Z/factor_history_coverage.json` | `0404bb1a6b402e692a87e35f563d43e934230b952846b2d706d4be46f161e705` |
| split manifest bytes | `/Users/liudehua/.hermes/worktrees/w2-model-forecast-validation-ledger/reports/factor_model_v2/gate1_split_train_xg_pit_v4_20260822T055041929427Z/factor_v2_split_manifest.json` | `72cf04f3303f788c9fe5b66cb8e90f5bc9d77a28cc02318f17b14654eb458406` |
| old preprocessing bytes | same directory, `factor_v2_train_preprocessing.json` | `ac8eee965a35973ea13a30e62c194031281e2a27dc1ba0d129d4fd46f0e35269` |
| old normalized-feature bytes | same directory, `factor_v2_normalized_features.json` | `ac8cb1708a1355a621cf6cfb7823421985a63c38e96a6624d0583745961d9bdf` |
| old visibility bytes | same directory, `factor_v2_visibility.json` | `5dc6c4ca00110fb692f1f3488a67a1887099f6e18e0b85108e09e6cc6e67fc7c` |
| current xG transaction dump | `/Users/liudehua/.hermes/data/ev_se_drift_v2/team_xg_match.csv` | `84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909` |

The current xG dump contains `18,978` data rows / `9,489` fixtures between
literal `BEGIN` and `ROLLBACK` sentinels. It is not the old Gate 1 xG file
(`18,696` / `9,348`) and therefore defines a new experiment identity.

The dump omits opponent, goals and raw-payload hash columns. Reconstruction may
only exact-join fixture/team fields to the frozen history corpus or the old full
xG artifact. Missing, ambiguous or conflicting joins fail closed and remain in
the exclusion ledger. No name, time-tolerance or inferred identity join is
allowed.

## 4. New identity rule

Every output identity must include:

- this protocol file SHA-256;
- base commit `cb8f5d22`;
- current xG dump SHA-256 and row/fixture counts;
- source artifact file hashes;
- the unchanged semantic TRAIN membership hash;
- a new recovery schema/version label; and
- its immediate upstream artifact hashes.

The old Gate 1 package and hashes remain byte-for-byte unchanged and retain
status `FAIL`. Reusing an old output hash, overwriting an old report directory,
or describing the current corpus as a rerun of the old experiment is forbidden.

## 5. Frozen recovery method

### Factor model

- Active factors remain exactly `F3_REST_FITNESS` and
  `F7_STRENGTH_FORM`.
- `F6_H2H` remains `EXCLUDED_BY_PREREGISTERED_THRESHOLD`.
- Reuse the existing Poisson factor coefficient fitter and exact 13×13 score
  matrix authority; do not add a model family or feature.
- All coefficient fitting sees TRAIN targets only.
- Final candidate coefficients are fitted once on all currently scorable TRAIN
  targets; all 3,118 targets remain in denominator accounting.

### Calibration layer

Use one global scalar temperature `T` on the complete score matrix:

```text
q_ij(T) = p_ij^(1/T) / sum_ab p_ab^(1/T)
T bounds = [0.5, 2.0]
objective = mean multiclass 1X2 negative log likelihood
selection data = deterministic chronological forward OOF predictions within TRAIN
```

TRAIN is ordered by `(kickoff, fixture_id)` and divided into four contiguous
blocks without outcomes. Blocks 2–4 are predicted by coefficients fitted only
on preceding blocks; block 1 has no OOF predecessor and stays visible in the
denominator with reason `OOF_WARMUP_NOT_CALIBRATION_ELIGIBLE`. Fit `T` only on
the combined forward OOF predictions. Optimisation is deterministic bounded
scalar minimisation with fixed tolerance `1e-6`; no ECE bin or downstream Gate
metric may choose `T`.

The selected `T` is then applied to score matrices produced by the final
all-scorable-TRAIN coefficient fit. This creates the frozen prospective
candidate. It is not a claim of out-of-sample calibration.

### Mechanism diagnosis

The report must diagnose the known old failure (`ECE +0.004487` on former
VALIDATION and `+0.020344` on former HOLDOUT) without recomputing either sealed
metric. The diagnosis may use only TRAIN OOF reliability data and model
structure. It must distinguish class-confidence distortion from ranking/log-loss
effects and disclose ECE bin sensitivity.

### Rejected methods fixed before results

- no isotonic calibration: too flexible and not a single coherent 13×13 matrix;
- no classwise Platt, Dirichlet or league-specific calibration: unnecessary
  parameters and sparse subgroup overfit;
- no threshold, ECE-bin or feature tuning: not probability calibration and
  would create result-dependent degrees of freedom;
- no use of former VALIDATION/HOLDOUT: both are observed; and
- no uncalibrated `T=1` promotion merely because log loss previously improved.

## 6. Required artifacts

The result commit must add a new package without modifying this protocol:

- current canonical xG corpus and exact reconstruction/exclusion ledger;
- TRAIN-only target corpus and denominator ledger;
- recovery split identity;
- recovery preprocessing and feature identities;
- final model coefficients and model identity;
- temperature calibration artifact with OOF fold manifest;
- per-target candidate score-matrix hashes and aggregate score-matrix identity;
- `REPORT.md` with mechanism diagnosis, selected method, rejected alternatives,
  limitations and exact reproduction commands;
- `STATUS_MATRIX.md`; and
- machine-readable evidence with all source/output hashes and stop-line counts.

The package must explicitly state that confirmation requires
`V2-FORWARD-PREREG-AMENDMENT-01` before the first forward row and a later
one-look `V2-FORWARD-EVALUATION-01`.

## 7. Checks and stop lines

Required checks:

- deterministic rerun produces byte-identical artifacts;
- sealed-set outcome mutation produces byte-identical artifacts;
- any TRAIN outcome mutation changes at least the model or calibration identity;
- any source hash, split membership, current xG row or protocol mutation is
  detected;
- every matrix is finite, non-negative, exactly 13×13 and sums to 1 within
  `1e-9` after calibration;
- denominator accounting sums to 3,118; and
- old Gate 1 report bytes remain unchanged.

Stop lines:

```text
Provider calls = 0
production reads = 0
production writes = 0
GitHub/GHCR = 0
migration apply = 0
collector/timer start = 0
deployment = 0
candidate/opportunity/outbox/Bark = 0
forward metric reads = 0
VALIDATION/HOLDOUT outcome-visible reads = 0
Gate 1 = FAIL
Gate 2 = CLOSED
alpha = NULL
beta = NULL
```
