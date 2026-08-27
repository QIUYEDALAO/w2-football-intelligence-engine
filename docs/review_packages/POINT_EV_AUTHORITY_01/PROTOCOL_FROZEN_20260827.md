# POINT-EV-AUTHORITY-01 — frozen protocol

Status: `FROZEN_BEFORE_ANY_RESULT` for sections 3 to 8. Section 2 records what was
already read while confirming the task was well posed, and says so.

Scope is point EV only. EV-SE is a separate line and is not touched here;
`alpha_age_per_day` and `beta_missing` stay `NULL`. This package does not implement
factor model V2 and does not authorise anything.

## 1. The reported problem

Fixture `1570340` (Real Madrid vs Real Sociedad, Under 3.5 @ `1.92`) is reported at
`74.8131%` model probability and `+43.6411%` EV, sourced from `BASELINE_PRIOR`, and
that unvalidated calibration reaches candidate and confirmation semantics.

## 2. What was already checked, disclosed

Two things were verified before this document existed and are stated rather than
presented as findings of a frozen run:

- **the EV arithmetic is correct.** `0.748131 x 0.92 - 0.251869 = 0.436412`, which
  matches the reported `+43.6411%` to the digit. Whatever is wrong, the five-state
  EV formula reproducing that number is not it;
- **the disagreement is with the whole market, not with one price.** `1.92` implies
  `52.08%` including vig, so the model sits `22.7` percentage points above it. An
  edge of that size against a liquid market is the signature of an uncalibrated
  probability, not of value.

## 3. The frozen regression sample and the chain to replay

Fixture `1570340` is the frozen sample. The replay must carry, and hash, every link:

1. the quote and its point-in-time inputs — bookmaker, price, line, capture time,
   quote identity hash;
2. the four-field xG and the windows behind it, with the as-of that selected them;
3. factor enablement state at that as-of;
4. `lambda_home`, `lambda_away`, `lambda_sigma_home`, `lambda_sigma_away`;
5. the score matrix;
6. the five-state settlement distribution;
7. `EV` and `EV_SE`;
8. the candidate decision and the notification decision.

Inputs are acquired read-only. Production reads run under
`BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY` and are rolled back;
no Provider call, no write, no deploy. Every extracted artefact is fingerprinted
with SHA-256 and frozen in this package. If a link cannot be reconstructed from
retained data, it is reported as unreconstructable rather than inferred.

## 4. Classification, and the rule for naming a root cause

Every defect found is placed in exactly one class:

- **formula** — the arithmetic from distribution to EV is wrong;
- **probability** — the model's probability is wrong given its inputs;
- **binding** — the probability's declared validity is not bound to what consumes it;
- **display** — the surface misrepresents an otherwise correct decision.

Exactly one defect is named the primary root cause, on the test that removing it
alone would prevent the reported outcome. Others are reported as independent
defects with their own class, and are not folded into the primary.

## 5. One calibration authority

The semantics are unified in a single module that every path imports. No consumer
may keep its own allowlist.

The authority answers one question — may this calibration status support a formal
recommendation — and the answer is yes only for statuses that record a completed
production validation. `READY` is a simulation-pipeline status, not a validation
verdict, and must not appear in the recommendation allowlist wherever it currently
does.

Unvalidated calibration stays fully available as **analysis evidence**: the
distribution, EV, EV_SE and the whole audit trail continue to be computed, stored
and displayed. What it may not do is form a candidate, a confirmation, a lock, or a
notification recommendation. Suppressing the evidence would be a different bug and
is prohibited.

## 6. What may not be changed

- the five-state settlement formula and its bindings;
- historical recommendations, historical settlements, and the outcome ledger;
- V1 probability parameters;
- the Dashboard changes already present in the main workspace, which this package
  works around in a separate worktree.

**No EV cap.** Capping EV would hide an uncalibrated probability behind a threshold
and would be fitting a number to this fixture. The calibration problem is addressed
as an authority problem or not at all.

**No reverse-tuning.** This fixture's final result may not be read, and the current
65 settled picks may not select any parameter, threshold, or conclusion.

## 7. Regression tests

All five are required, each as an executable test rather than a claim:

- (a) `BASELINE_PRIOR`, and any other unvalidated status, cannot produce a formal
  recommendation on any path;
- (b) an approved validated calibration still admits normally — the fix must not be
  a blanket denial;
- (c) the EV formula, line direction, odds format and five-state binding are
  unchanged, demonstrated by tests that fail if any of them moves;
- (d) fixture `1570340` under the current unvalidated model returns
  `NO_CANDIDATE` / `HOLD`;
- (e) analysis evidence for that fixture is still complete after the change.

## 8. Deliverables

Frozen protocol, input and output evidence with SHA-256, a root-cause report, a
status matrix, the local commit with its exact diff, the five regression tests with
their results, reproduction commands, and an independent view on how factor model V2
and V1/V2 dual-track settlement should be sequenced after this.

No deployment. Model-parameter fixes or production switches, if any are implied, are
submitted as proposals with evidence and are not self-authorised.
