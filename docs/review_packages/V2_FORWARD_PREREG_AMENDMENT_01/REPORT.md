# V2-FORWARD-PREREG-AMENDMENT-01 result

Status: `READY_FOR_INDEPENDENT_ACCEPTANCE`

Protocol commit: `cb958902b2893adac44871cce0f324cf2f5ac307`

Base: `22dc0dbec9d5792f9cc5bd2c2c45ba38e7662b0b`

## 1. Outcome

The failed-model preregistration remains byte-for-byte unchanged. A new successor
contract is frozen for the Task 4 recovery candidate, but no V2 row is currently
allowed: actual collector activation is not authorised and the exact cohort start is
therefore unresolved.

This task does not pass Gate 1. Gate 1 remains
`FAIL_PENDING_PROSPECTIVE_CONFIRMATION`; Gate 2 remains `CLOSED`.

## 2. Old contract preservation

The old file remains:

```text
docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json
sha256 cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1
status SUPERSEDED_BEFORE_FIRST_SAMPLE
```

It was not edited, renamed or reused as the new identity. Its failed Gate 1 hashes
remain historical evidence.

The successor is:

```text
docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_RECOVERY_20260828.json
file sha256     5c6b13b50818587d381e361bafbce25f33bd7e7f52c3b090ccf02bd0def4c880
semantic sha256 bf2b539d77a532b7c8bf9e81d2644f6f3f760ddf549719613ee2643c8aac4e98
```

## 3. Zero-row evidence and its limit

Classification is `CONFIRMED_RECORD_NOT_LIVE_QUERIED`, not a fresh production count.

The accepted POINT-EV deployment report records release `ea557bb8`, schema
`0070_notification_delivery_routing`, and explicitly states that it was cut without
the unapproved V2 forward line or migration. Local inspection of the exact release
confirms it contains no `0070_factor_shadow_v2_gate0.py`. With no deployed V2 schema,
role, collector or timer, no proposed V2 forward row can exist.

Production reads/writes in this task were `0/0`. The report does not claim that a live
database query was performed.

## 4. Complete candidate binding

The successor binds the Task 4 semantic identities exactly:

| Component | Identity |
|---|---|
| split | `c45e1d4e...0d29` |
| preprocessing | `c6530ef5...029e` |
| features | `9e514a36...de92` |
| model | `665a0e58...d0c6` |
| calibration | `199ae9c2...4255` |
| score matrices | `4e9b94ca...6c66` |
| recovery evidence | `43ea7cd6...2555e` |

It also binds recovery protocol/result commits and records calibration authority as
`UNVALIDATED_NOT_ADMISSIBLE`. No `APPROVED_VALIDATED` state is inferred.

## 5. Cohort-start decision

The correct exact start cannot be named before actual activation. Inventing a future
timestamp would permit backfill if activation happened later. The frozen rule is:

```text
cohort_start = max(2026-08-27T16:10:59Z, activation_authority.effective_at)
```

The successor stores `production_capture_captured_at_not_before=null` and
`UNRESOLVED_NO_ROWS_ALLOWED`. Task 7 must atomically persist the resolved timestamp
and bind this preregistration hash before its first write. Missing or mismatched
activation authority fails closed; captures before the resolved start may never be
backfilled.

Rejected: set the start to the old `2026-08-22` date; pretend amendment freeze is the
activation time; or edit the successor after collection starts.

## 6. Base and lineup hierarchy

`BASE_PRE_LINEUP` is the only prospective primary variant, and only after activation
authority exists. `LINEUP_CONFIRMED` is a named child variant but has
`NO_ROWS_ALLOWED_UNTIL_SEPARATE_PREREGISTRATION`.

The lineup child cannot borrow base samples, power or admission. This is the smallest
contract that preserves the already accepted one-family/two-variant schema decision
without freezing a lineup coefficient or calibration identity that does not exist.

## 7. Pairing, denominator and POINT-EV epoch

The full denominator is `ALL_ELIGIBLE_SCHEDULED_OPPORTUNITIES`; neither-track output
is required for denominator membership. The strict paired numerator keeps the exact
existing name `fixtures_with_paired_v1_production_capture` and requires the same
fixture, market, checkpoint variant, quote and captured-at semantics.

Every row/report must carry `POINT_EV_FAIL_CLOSED` and release `ea557bb8`. Candidate
delivery is not a pairing requirement, because POINT-EV correctly suppresses current
`BASELINE_PRIOR` formal candidates while preserving analytical forecasts and EV.

## 8. One-look design

The successor freezes:

- one look no earlier than `2028-02-01T00:05:00Z`;
- at least `5,500` distinct completed strict pairs;
- LogLoss and RPS deltas strictly below zero;
- top-label 10-bin ECE delta no greater than zero;
- LogLoss improvement in at least two of three frozen history-depth strata;
- multiclass Brier reported but not used as a post-hoc extra gate; and
- 5,000 paired-fixture bootstrap resamples with a fixed seed.

The old failed-model HOLDOUT dispersion is labelled
`PLANNING_ONLY_CONTAMINATED_PRIOR_NOT_CONFIRMATION`. It supplies planning scale only;
it cannot confirm the new candidate. If either date or sample rule is unmet, no locked
metric may be read. A new date must be frozen before any metric inspection.

## 9. Verification

- validator `--check`: PASS;
- validator `--self-test-check`: PASS, 5/5 mutants caught;
- independent production canonical-serializer parity: PASS, same `bf2b539d...4e98`;
- focused validator plus package-matrix contracts: 7 passed;
- Ruff full repository: PASS;
- mypy `src apps`: 299 files, zero errors;
- strict mypy for the new validator: PASS; and
- final full pytest: `2,973 passed / 5 failed / 9 skipped`;
- all five failures are the same established baseline set from Task 4: two unavailable
  Docker Compose cases, one missing `python` executable and two rootless ownership
  cases; and
- the two new tests account for the increase from 2,971 to 2,973 passes.

The first full run exposed one task-induced package-matrix failure because the
governance validator imported `w2.domain`. A second run then correctly rejected a
stdlib canonical hash writer as a duplicate authority. The final validator now checks
the exact frozen file and semantic constants only; the production serializer supplies
the independent parity evidence. Both static authority guards pass, and the global
architecture matrix was not edited for a one-file documentation check.

Reproduction:

```bash
cd /Users/liudehua/.hermes/worktrees/w2-v2-integration-baseline
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/check_factor_v2_forward_prereg_amendment.py
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python scripts/check_factor_v2_forward_prereg_amendment.py --self-test-check
PYTHONPATH=src /Users/liudehua/.hermes/worktrees/w2-ev-se-offline-validation/.venv/bin/python -m pytest -q tests/unit/test_factor_v2_forward_prereg_amendment.py tests/contract/test_src_w2_package_matrix.py
```

## 10. Boundaries and next task

Provider 0; production reads/writes 0/0; GitHub/GHCR 0; model fitting/tuning/scoring
0; sealed/prospective metric reads 0; migration/collector/timer/deployment 0;
candidate/opportunity/outbox/Bark 0; alpha/beta remain `NULL`.

If independently accepted, the next local task is `V2-DUAL-TRACK-LEDGER-01`. It must
make `BASE_PRE_LINEUP`/`LINEUP_CONFIRMED` and the first-row preregistration lock hard
schema/identity inputs. This report does not authorise migration apply or deployment.
