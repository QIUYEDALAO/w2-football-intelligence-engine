# V2-GATE1-CALIBRATION-RECOVERY-01 result

Status: `PROSPECTIVE_CANDIDATE_IDENTITY_ONLY`

Protocol commit: `577c4cc45b9d1675aa96d7e5836b39543b76775c`

Protocol SHA-256: `4f01820d83536bcf2b024478b6f8259623fb108bf3e345898b41e83d491da10b`

Base: `cb8f5d22ded2857d09dfcabda3a159bee165bb5f`

## 1. Binding conclusion

This task produced one new, deterministic candidate identity. It did not and
cannot pass Gate 1: `FACTOR_MODEL_V2_GATE1` remains `FAIL`, Gate 2 remains
`CLOSED`, and no candidate, notification, migration, collector or deployment
was produced.

The candidate requires a frozen `V2-FORWARD-PREREG-AMENDMENT-01` before the
first forward row and a later one-look `V2-FORWARD-EVALUATION-01`. No historical
VALIDATION, HOLDOUT or production result can authorise it.

## 2. Current corpus reconstruction

The current transaction dump contains 18,978 rows / 9,489 fixtures. Exact,
non-inferential reconstruction admitted 18,802 rows / 9,401 fixtures:

- 18,696 rows matched the prior full xG artifact by exact fixture/team key and
  exact kickoff/xG/source values;
- 106 rows matched the frozen history corpus by exact fixture/team key; and
- 176 rows / 88 fixtures lacked opponent, goals and raw-payload hash authority
  and were excluded without filling any missing field.

All 176 excluded rows are paired two-team rows from 2026, with kickoff range
`2026-08-16T19:00:00Z` to `2026-08-25T19:00:00Z`. None precedes the end of
TRAIN. The 106 newly reconstructed rows are also all in 2026. Therefore the
current 18,978-row corpus has a new experiment identity, but its additions do
not alter any 2024 TRAIN rolling-xG input.

TRAIN denominator accounting is 3,118 targets: 2,684 scorable and 434 explicit
`ROLLING_XG_UNAVAILABLE` exclusions. Missing targets remain in the denominator.

## 3. Recovery method and result

The model kept only preregistered F3/F7, reused the existing Poisson fitter and
exact 13x13 score matrix, and continued to exclude F6. Four chronological TRAIN
blocks yielded 2,133 forward-OOF predictions; block 1 remained visible but was
not calibration-eligible.

One global complete-matrix temperature was selected only by TRAIN forward-OOF
1X2 negative log loss:

| Result | Value |
|---|---:|
| selected temperature | `0.928709586` |
| OOF NLL at T=1 | `1.013115115` |
| OOF NLL at selected T | `1.012871556` |
| final coefficient fit rows | `2,684` |
| final score matrices | `2,684` |

The selected temperature is below one, so it sharpens the complete probability
matrix. That slightly improves the proper NLL selection score, but does not
establish calibration recovery.

## 4. ECE mechanism diagnosis

The old immutable report recorded B2-minus-B0 ECE of `+0.004487` on former
VALIDATION and `+0.020344` on former HOLDOUT. Those metrics were not recomputed.

TRAIN-only forward OOF shows the mechanism directly: likelihood fitting can
improve ranking/log loss while distorting confidence. The selected `T < 1`
sharpens probabilities and made ECE worse at every descriptive bin count:

| bins | ECE T=1 | ECE selected T |
|---:|---:|---:|
| 5 | `0.010206320` | `0.012050398` |
| 10 | `0.010628638` | `0.013063272` |
| 15 | `0.018820640` | `0.020456878` |

This is not a new Gate measurement. It is TRAIN-only mechanism evidence. It
also demonstrates ECE's sensitivity to binning: absolute values change with
the bin count even though the direction is stable here. NLL-selected
temperature cannot be represented as proof that historical ECE improved.

## 5. Why this method and not the alternatives

The global temperature was retained because it is the smallest coherent layer
that preserves one complete 13x13 probability authority for 1X2, AH and OU,
uses a proper scoring rule, and can be selected with chronological TRAIN-only
OOF predictions.

Rejected before results:

- isotonic calibration: too flexible and does not directly preserve one
  coherent score matrix;
- classwise Platt, Dirichlet or league-specific calibration: unnecessary
  parameters for the available TRAIN OOF support;
- ECE-bin, threshold or feature tuning: result-dependent degrees of freedom,
  not probability calibration;
- former VALIDATION/HOLDOUT: both have already been observed; and
- promotion of uncalibrated `T=1`: prior log-loss improvement is not admission
  evidence.

The small NLL delta and worse descriptive TRAIN OOF ECE are limitations of the
candidate, not reasons to switch methods after seeing the result.

## 6. Frozen identities

| Artifact | Semantic identity |
|---|---|
| recovery split | `c45e1d4efcd3d59e9ef21c6ae36e1639a84faedf9e90356eb67e6830f6120d29` |
| preprocessing | `c6530ef565383c454bba40e5213ece7101289c4c30c0f8d5792a9e03af70029e` |
| features | `9e514a36d08b6fe94ec6dd17057f24d384cc781abf94ef5c3988b2af5d69de92` |
| model | `665a0e58bdb4369ab0a04501a3c14caaa6818f0340137de33b6d0217d9bfd0c6` |
| temperature calibration | `199ae9c24b4aca04a0058967dda259461544a23baf45c8f0ab84154277564255` |
| score-matrix set | `4e9b94ca624fff556775af508bebb9ac26722de87f0f15d442dd986f455a6c66` |
| evidence | `43ea7cd64ff369191317ada071136ecdc0173d48a929e09688a3c6f32322555e` |

Source file hashes are recorded in `artifacts/EVIDENCE.json`. Physical output
file hashes are frozen in `ARTIFACT_MANIFEST.md`; semantic identities remain
the decision authority. The old Gate 1 package was not modified and remains
`FAIL`.

## 7. Verification

The runner proves:

- deterministic recomputation is byte-identical;
- a sealed VALIDATION/HOLDOUT outcome mutation leaves all artifacts
  byte-identical;
- a scorable TRAIN outcome mutation changes the model or calibration identity;
- all authority files are exact-hash guarded;
- every calibrated matrix has 169 finite, non-negative cells and sums to one
  within `1e-9`; and
- the denominator sums to 3,118.

Static and regression verification:

- Ruff full repository: PASS;
- mypy `src apps`: 299 files, zero errors;
- strict mypy for the new runner: zero errors;
- focused recovery/ablation tests: 11 passed; and
- full suite: `2,971 passed / 5 failed / 9 skipped`;
- the five remaining full-suite failures are byte-for-byte the same test IDs
  reproduced at `cb8f5d22` (two unavailable Docker Compose cases, one missing
  `python` executable, and two rootless ownership cases).

Reproduction:

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v2-integration-baseline
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/run_factor_v2_gate1_calibration_recovery.py --check
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/run_factor_v2_gate1_calibration_recovery.py --self-test-check
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python -m pytest -q tests/unit/test_factor_v2_gate1_calibration_recovery.py
```

## 8. Stop lines

Provider 0; production reads/writes 0/0; GitHub/GHCR 0; migration apply 0;
collector start 0; deployment 0; candidate/opportunity/outbox/Bark 0;
VALIDATION/HOLDOUT metric reads 0; alpha/beta remain `NULL`.
