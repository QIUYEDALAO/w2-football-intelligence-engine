# W2 Data Layer Policy V1

W2 separates data into four layers:

```text
RAW -> NORMALIZED -> FEATURE -> PREDICTION_STRATEGY
```

RAW is represented by immutable `RawPayloadReference` records:

- provider
- object_uri
- sha256
- captured_at
- immutable=true

NORMALIZED contains domain entities such as teams, fixtures, players, lineups,
weather, odds observations, and provider mappings.

FEATURE contains `FeatureSnapshot` records with a required `as_of_time`. Result
fields are forbidden from feature payloads.

PREDICTION_STRATEGY contains predictions, recommendations, locks, settlements,
and audit events. Stage 3 only creates the model shape; it does not implement a
strategy engine or real recommendation capability.

