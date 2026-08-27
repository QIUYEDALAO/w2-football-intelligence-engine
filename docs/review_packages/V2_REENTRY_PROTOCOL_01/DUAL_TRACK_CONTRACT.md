# V2-REENTRY-PROTOCOL-01 — V1/V2 dual-track contract

Status: design only. No ledger, migration, collector or Dashboard is authorised.

## 1. Track and variant identity

Track is one of `V1_PRODUCTION_CAPTURE` and `V2_ANALYSIS_ONLY`.

V2 uses one model family and two forecast variants:

- `BASE_PRE_LINEUP`;
- `LINEUP_CONFIRMED`.

The lineup forecast is an immutable child of a base forecast. It never supersedes or
rewrites the base forecast.

Required forecast identity fields:

```text
fixture_id
competition_id
production_capture_identity_hash
checkpoint_variant
checkpoint/event identity
captured_at
feature_as_of
model_family + model_version
feature_registry_version + preprocessing_version
calibration_version
pit_input_identity_hash
parent_forecast_identity_hash
lineup_input_hash + lineup_captured_at
```

For `BASE_PRE_LINEUP`, parent and lineup fields are null. For `LINEUP_CONFIRMED`, all
three are non-null and the parent references the same fixture's base model family.
These are columns and hash inputs, not JSON-only annotations.

## 2. Same-opportunity pairing

A strict V1/V2 pair requires equality of:

```text
fixture identity
market
selection and exact line
checkpoint variant
scheduled checkpoint/event identity
quote_identity_hash
bookmaker/source observation
captured_at semantics
lineup_input_hash (for LINEUP_CONFIRMED)
authoritative settlement contract
```

It also requires one scorable V1 output and one scorable V2 output. The canonical
paired numerator remains `fixtures_with_paired_v1_production_capture`.

No looser fixture/date join may be reported as paired.

## 3. Full denominator

Both-output is not required for denominator membership. Every eligible scheduled
opportunity receives a terminal funnel row even if neither track produces a forecast.

Required stages:

```text
fixtures/opportunities eligible
V1 checkpoint CAPTURED or MISSED
V1 production forecast capture present
V2 forecast present
strict V1/V2 pair present
authoritative completed result present
both outputs scorable
exclusion/missingness reason
```

The supplied T-30m rate `34/40 = 85%` leaves 6/40 in the denominator as V1 checkpoint
missingness. An inner join is forbidden. Coverage and metric reports must show the
full denominator, strict paired numerator and attrition strata side by side.

## 4. Lineup semantics

V2 reuses V1 authority:

- event: `LINEUP_CONFIRMED`;
- identity: canonical `lineup_input_hash`;
- time: authoritative lineup event `captured_at`;
- quote gate: complete fresh exact quote captured at/after lineup confirmation.

The lineup V2 forecast and its V1 comparator bind the same lineup hash and exact quote.
If either is absent, the strict pair is missing and the denominator row remains.

Base-versus-lineup predictions generally use different chronological quotes. Their EV
difference is descriptive and not a causal lineup-effect estimate.

## 5. Settlement

- V1 and V2 use the same authoritative final result identity.
- Market grading uses the same five-state settlement rules and exact line.
- Each forecast/outcome remains append-only and independently hash-addressed.
- Historical replay and forward rows are permanently separated.
- V2 writes only its own analysis ledger.
- V2 may not write V1 capture, opportunity, attempt, outcome, candidate, outbox,
  notification or formal P&L authorities.
- Interim locked metrics remain unavailable until the preregistered one-look event.

## 6. POINT-EV epoch

Every row/report carries the active calibration-authority epoch:

- `PRE_POINT_EV` — historical V1 candidates were not authority-gated;
- `POINT_EV_FAIL_CLOSED` — V1 `BASELINE_PRIOR` continues as analysis evidence but is
  not a formal candidate; or
- an exact evidence-bound validated decision identity.

Candidate delivery is not a pairing requirement and candidate yield is never pooled
across epochs without stratification.

## 7. Schema rejection criteria

Reject the migration before apply if any of these are true:

- checkpoint variant or lineup identity is JSON-only;
- forecast uniqueness can collapse base and lineup rows;
- lineup can exist without a parent/base identity or confirmed event;
- an attempt can pair a different quote than V1;
- denominator misses have no durable terminal row/reason;
- V2 role can write V1 tables or outbox;
- admission lacks an exact variant/model/calibration identity; or
- the first-row preregistration lock is not enforced before the write transaction.

