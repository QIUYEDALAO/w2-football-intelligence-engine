# V2-REENTRY-PROTOCOL-01 — factor and data-role matrix

## Historical target sets

Authority: frozen split manifest canonical hash
`01a4f593efc3814cf31b6d4a677320513cdc996baf006d59c4c4d029fda243ce`.

| Set | Exact definition | Count | Already observed/use | New role |
|---|---|---:|---|---|
| TRAIN | manifest rows `split=TRAIN`, kickoff `[2024-01-01,2025-01-01)` | 3,118 | preprocessing, fit and development | `DEVELOPMENT_ONLY` |
| TRAIN xG-scorable | old Gate 1 coefficient-fit subset | 2,684 | fitted | development diagnostic only |
| VALIDATION | manifest rows `split=VALIDATION`, kickoff `[2025-01-01,2026-01-01)` | 4,520 | metrics inspected | `OBSERVED_CONFIRMATORY_CONTAMINATED` |
| HOLDOUT | manifest rows `split=HOLDOUT`, kickoff `[2026-01-01,2026-08-21T19:18:10.674088Z)` | 2,628 | metrics inspected | `OBSERVED_CONFIRMATORY_CONTAMINATED` |
| prospective successor | exact bounds to be frozen after new model identity | 0 now | unseen | future confirmation only |

Task 2 may fit and select only within the 3,118 frozen TRAIN identities. Internal
folds do not turn any part of that set into independent validation. VALIDATION and
HOLDOUT may be used only for blind reproducibility checks that do not expose new
metrics to the developer.

## xG corpus identities

| Snapshot | File SHA | Rows/fixtures | Role |
|---|---|---:|---|
| Gate 1 | `09d921ffb7b39a88dd67ad5043d0102941b7357effb54487a700c83dc2399d9b` | 18,696 / 9,348 | frozen old experiment |
| later local extract | `84ef81e90377014cb9ea9abc93276aebed65e1c63b9d4e5dfa18d47443634909` | 18,978 / 9,489 | candidate new-corpus input; not live authority |

Comparison:

| Category | Rows | Fixtures |
|---|---:|---:|
| common and field-identical | 18,696 | 9,348 |
| added | 282 | 141 |
| removed | 0 | 0 |
| added before old historical cutoff | 108 | 54 |
| added at/after old cutoff | 174 | 87 |

All 282 additions were captured after the old Gate 1 snapshot. Replacing the old CSV
therefore creates a new corpus identity; it is not an in-place reproduction.

## Factor roles

| Factor/output | Historical development | Historical confirmation | Forward role | Decision |
|---|---|---|---|---|
| F3 rest/fitness | allowed on TRAIN with PIT contract | old 2025/2026 already observed | base variant | retain subject to new identity |
| F7 strength/form | allowed on TRAIN with PIT contract | old 2025/2026 already observed | base variant | retain subject to new identity |
| F6 H2H | old coverage/stability gate failed | not admissible | excluded unless separately preregistered | keep excluded |
| base xG | allowed as declared method input | old metrics observed | both variants' parent | re-freeze corpus/method hash |
| confirmed lineup | no accepted historical paired set | none | forward-only | separate checkpoint variant |
| market quote | never a fitted outcome surrogate | same exact quote required for pair | pairing/EV evidence | identity input, not football factor |
| V1 candidate state | not model data | authority discontinuity | not a pair requirement | never use as scientific denominator |

## Contamination rules

- Any method, coefficient, threshold or calibration chosen after seeing 2025/2026
  Gate 1 metrics is contaminated for those sets.
- Adding later xG source fixtures does not make the old target outcomes unseen.
- Calibration recovery may report fit convergence and internal TRAIN diagnostics, but
  cannot claim Gate improvement.
- The new identity's first confirmation is prospective and one-look.
- Lineup coverage, coefficients and calibration are forward-only until separately
  accepted; missing lineup never receives a default/proxy value.

## Successor preregistration requirements

Before its first row, freeze:

- exact new model/feature/preprocessing/calibration/checkpoint-variant hashes;
- actual `production_capture_captured_at_not_before` no earlier than freeze/activation;
- full eligible opportunity denominator;
- strict paired numerator named `fixtures_with_paired_v1_production_capture`;
- base and lineup cohorts either separately powered or explicitly hierarchical;
- primary metrics, strata, power basis, one-look time and insufficient-sample rule;
- POINT-EV authority epoch field; and
- permanent `relaxation_forbidden_after_first_sample=true`.

