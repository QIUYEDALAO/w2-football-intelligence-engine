# PRO_REOPEN_OWNER_DECISION_PACKET

Status: OWNER_DECISION_REQUIRED

This packet does not authorize a Pro purchase or renewal. The current decision remains
`NOT_PURCHASED_NOT_RENEWED` until the Owner explicitly changes it.

## Free-mode model validation proof

- Terminal: `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`
- MODEL_ELIGIBLE_COUNT: `9`
- MODEL_FORECAST_CAPTURE_COUNT: `9`
- MODEL_FORECAST_SETTLED_COUNT: `1`
- PROBABILITY_METRICS_SAMPLE_COUNT: `1`
- SHADOW_CANDIDATE_COUNT: `40`
- RAW_STATISTICS_RESTORE_HASH_MATCH: `true`
- raw Statistics count/hash: `141 / 7f3fc61fe64ae8b98b71fa1e123847eff3ec712d7aa7f870c6fd7bab34718243`
- rebuilt team_xg_match count/hash: `140 / 325085b337f2977b118cf88b083b5044e3a36e17ffcad0a857909ae311d63e33`
- rebuilt rolling snapshot count/hash: `72 / 937b9a809ed43687e3e9dd12d23da483077c2e00a6c35686d0e1b3697c3dcde8`

## Owner choices

1. Keep Free mode and continue natural ModelForecast accumulation.
2. Reopen a separately bounded Pro backfill decision using a fresh net-request budget.

Formal, Lock, Production, real money, Round 4, new Statistics calls, cadence changes,
model-threshold changes, and league deletion remain outside this packet.
