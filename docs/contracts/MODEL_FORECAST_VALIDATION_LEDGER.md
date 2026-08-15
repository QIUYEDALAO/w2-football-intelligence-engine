# ModelForecast validation ledger contract

## Capture policy

`capture_policy = FIRST_ELIGIBLE_FREEZE_IMMUTABLE`.

A fixture is frozen the first time it becomes model-eligible before kickoff. The stored capture is
append-only and is never refreshed as kickoff approaches. The current uniqueness key is
`(fixture_id, model_family, model_version)`.

If a future policy permits repeated forecasts for one fixture, every forecast must be appended as
a distinct capture identity and settled independently. Existing captures must never be overwritten.

## Lead-time strata

Every capture and outcome stores `lead_time_seconds = kickoff_utc - captured_at` and one bucket:

- `LT_6H`: less than 6 hours
- `H6_TO_LT_24H`: at least 6 hours and less than 24 hours
- `D1_TO_D3`: at least 24 hours and at most 72 hours
- `GT_3D`: more than 72 hours

Brier, LogLoss, and RPS means are reported only within these buckets. Cross-bucket probability
metric averages are prohibited because they mix forecasts made at materially different horizons.
