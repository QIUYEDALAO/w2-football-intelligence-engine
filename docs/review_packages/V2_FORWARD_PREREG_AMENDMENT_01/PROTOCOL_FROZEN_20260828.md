# V2-FORWARD-PREREG-AMENDMENT-01 frozen protocol

Frozen at: `2026-08-27T16:10:59Z`

Base: `22dc0dbec9d5792f9cc5bd2c2c45ba38e7662b0b`

## 1. Objective

Preserve the failed-model preregistration byte-for-byte and freeze one successor
prospective contract for the candidate produced by
`V2-GATE1-CALIBRATION-RECOVERY-01`, before any V2 forward row exists.

This task does not activate collection and cannot pass Gate 1 or open Gate 2.

## 2. Frozen inputs

- old preregistration file:
  `docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json`;
- old file SHA-256:
  `cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1`;
- recovery protocol commit: `577c4cc45b9d1675aa96d7e5836b39543b76775c`;
- recovery result commit: `22dc0dbec9d5792f9cc5bd2c2c45ba38e7662b0b`;
- recovery evidence identity:
  `43ea7cd64ff369191317ada071136ecdc0173d48a929e09688a3c6f32322555e`;
- split, preprocessing, feature, model and calibration identities are read only
  from the frozen recovery artifacts; and
- POINT-EV production authority epoch begins at release
  `ea557bb8ff64e06add91bbe32814fe073ec64642`.

No VALIDATION, HOLDOUT, prospective outcome, current recommendation, P&L or match
result may be inspected while choosing this contract.

## 3. Zero-row authority

The zero-row condition is `CONFIRMED_RECORD / NOT_LIVE_QUERIED`:

- the accepted POINT-EV release contains and runs Alembic revision
  `0070_notification_delivery_routing`;
- that exact release does not contain
  `0070_factor_shadow_v2_gate0.py`;
- the accepted deployment report records no V2 migration, role, collector or timer;
  and
- prior Task 4 used production reads/writes `0/0` and started no collector.

Therefore no deployed schema capable of storing the proposed V2 row exists. This task
must not turn that record evidence into a claim of a fresh production query.

## 4. Required successor contract

The result must add a new file; it must not edit, rename or replace the old file. The
successor must bind:

1. all recovery semantic identities and their evidence/protocol identities;
2. `BASE_PRE_LINEUP` as the only row-admissible variant;
3. `LINEUP_CONFIRMED` as an explicitly hierarchical child with
   `NO_ROWS_ALLOWED_UNTIL_SEPARATE_PREREGISTRATION`;
4. the full eligible-opportunity denominator and strict paired numerator named
   `fixtures_with_paired_v1_production_capture`;
5. the `POINT_EV_FAIL_CLOSED` authority epoch and exact release identity;
6. one-look metrics, power basis, sample rule, evaluation time and insufficient-sample
   action fixed without prospective outcomes; and
7. `relaxation_forbidden_after_first_sample=true`.

## 5. Cohort start

Actual activation is not authorised and its timestamp is unknowable in this task.
The successor therefore freezes this deterministic rule:

```text
cohort_start = max(amendment_frozen_at, activation_authority.effective_at)
```

The activation authority must persist the exact resolved timestamp and successor file
hash before the first write transaction. A missing/mismatched activation authority,
or any attempt to backfill a capture before the resolved timestamp, must fail closed.
No later task may edit the preregistration to insert a convenient earlier timestamp.

## 6. Statistical decision

The base variant retains a two-sided `alpha=0.05`, `power=0.80` planning design,
minimum `5,500` distinct completed strict pairs and one look no earlier than
`2028-02-01T00:05:00Z`. The old observed HOLDOUT dispersion is planning input only,
not confirmation of the new candidate. The primary comparison is the successor
`B2_FACTOR_V2` versus same-engine `B0` on strict pairs.

The one look must report LogLoss, RPS, multiclass Brier and 10-bin top-label ECE with
paired-fixture intervals and the complete denominator/attrition strata. If either the
date or minimum sample is unmet, no metric is read. A later date may be frozen only
before inspecting any locked metric.

The lineup child receives no borrowed sample, effect estimate or admission from the
base variant. Its later preregistration must be independently powered or add an
explicit multiplicity-controlled hierarchy before its first row.

## 7. Required checks and deliverables

- successor preregistration JSON with canonical and file SHA-256 identities;
- immutable old-file hash check;
- validator/self-test proving hash, identity, zero-row evidence classification,
  cohort-start rule, denominator, variants, one-look lock and stop lines;
- `REPORT.md`, `STATUS_MATRIX.md`, artifact manifest and reproduction commands;
- Ruff, mypy and focused tests; full-suite result compared with base failures; and
- two commits: this protocol first, then all results without rewriting this file.

## 8. Stop lines

- Provider calls `0`; production reads/writes `0/0`; GitHub/GHCR `0`.
- Model fitting/tuning/scoring and VALIDATION/HOLDOUT/prospective metric reads `0`.
- Migration apply, role creation, collector/timer start and deployment `0`.
- V1/V2 ledger, candidate, opportunity, outbox, Bark and formal P&L writes `0`.
- Gate 1 stays `FAIL`; Gate 2 stays `CLOSED`; alpha/beta stay `NULL`.
- The old preregistration and the Task 4 frozen package remain byte-for-byte unchanged.
