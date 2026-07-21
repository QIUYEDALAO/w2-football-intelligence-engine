# W2 Analysis Recommendation Closure Report

Generated: 2026-07-21

## Status

```text
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

## GitHub / Staging Sync

- PR: #370
- Latest pushed head used for final staging probe: `301e8c2`
- Staging server: `118.196.30.136`
- Staging scheduler: `W2_PROVIDER_SCHEDULER_ENABLED=false`
- Provider calls after execution: `W2_PROVIDER_CALLS_DISABLED=true`
- Recommendation writes: `0`
- Lock writes: `0`
- OFFICIAL/lock event writes: `0`

## What Was Fixed

1. `run_xg_history_backfill` now supports controlled competition selection via
   `W2_XG_BACKFILL_COMPETITION_ID`.
2. F9 rolling xG snapshot generation now includes already persisted `team_xg_match`
   rows instead of using only rows fetched in the current run.
3. Captured odds payloads can be materialized into canonical market observations
   without another provider call.
4. Read model projection now maps fixture-scoped provider-team xG snapshots back to
   W2 canonical team ids.
5. H2H readiness is surfaced from canonical evidence instead of being hard-coded false.

## Staging Execution Evidence

### Provider and Data Materialization

- Allsvenskan provider-primary team identities: `16`
- Canonical match history rows: `102`
- Teams with canonical history: `16`
- Rating snapshots: `16`
- Total `team_xg_match` rows after backfill: `104`
- Total rolling xG snapshots after backfill: `28`
- Smoke fixture rolling xG snapshots: `4`
- Smoke fixture H2H: `5` matches each
- Fresh odds provider capture during final odds refresh:
  - `fixtures`: `1`
  - `odds`: `8`
  - `status`: `1`
- Fresh odds quota remaining from run audit: `7277`
- Fresh odds materialized from captured payloads:
  - Fixture `1494218`: `315` observations
  - Fixture `1494224`: `325` observations

### Fixture `1494218`

- Decision: `ANALYSIS_PICK`
- Simulation status: `READY`
- xG: `READY`
- xG match counts: home `11`, away `4`
- xG snapshot count: `2`
- H2H: `READY`, `5` matches
- Market observations: `315`
- Bookmakers: `10`
- Lineups: `NOT_REQUESTED` / advisory only

AH:

- Line: `0.75`
- Quote: `COMPLETE`, captured `2026-07-21T03:21:11Z`
- HOME model probability: `0.359416`
- HOME market probability: `0.489418`
- HOME delta: `-0.130002`
- HOME EV: `-0.19167709828675417`
- HOME uncertainty: `null`
- HOME status: `NO_EDGE`
- AWAY model probability: `0.833762`
- AWAY market probability: `0.510582`
- AWAY delta: `0.32318`
- AWAY EV: `0.5963187023085054`
- AWAY uncertainty: `null`
- AWAY status: `READY`

OU:

- Line: `2.5`
- Quote: `COMPLETE`, captured `2026-07-21T03:21:11Z`
- OVER model probability: `0.634411`
- OVER market probability: `0.543478`
- OVER delta: `0.090933`
- OVER EV: `0.06581088116338281`
- OVER uncertainty: `null`
- OVER status: `READY`
- UNDER model probability: `0.365589`
- UNDER market probability: `0.456522`
- UNDER delta: `-0.090933`
- UNDER EV: `-0.26882247757545574`
- UNDER uncertainty: `null`
- UNDER status: `NO_EDGE`

### Fixture `1494224`

- Decision: `ANALYSIS_PICK`
- Simulation status: `READY`
- xG: `READY`
- xG match counts: home `9`, away `6`
- xG snapshot count: `2`
- H2H: `READY`, `5` matches
- Market observations: `325`
- Bookmakers: `9`
- Lineups: `NOT_REQUESTED` / advisory only

AH:

- Line: `-1.25`
- Quote: `COMPLETE`, captured `2026-07-21T03:21:10Z`
- HOME model probability: `0.361028`
- HOME market probability: `0.5`
- HOME delta: `-0.138972`
- HOME EV: `-0.2227166444882719`
- HOME uncertainty: `null`
- HOME status: `NO_EDGE`
- AWAY model probability: `0.071503`
- AWAY market probability: `0.5`
- AWAY delta: `-0.428497`
- AWAY EV: `-0.8072245386583266`
- AWAY uncertainty: `null`
- AWAY status: `NO_EDGE`

OU:

- Line: `3.5`
- Quote: `COMPLETE`, captured `2026-07-21T03:21:10Z`
- OVER model probability: `0.379408`
- OVER market probability: `0.424084`
- OVER delta: `-0.044676`
- OVER EV: `-0.16530157707606033`
- OVER uncertainty: `null`
- OVER status: `NO_EDGE`
- UNDER model probability: `0.620592`
- UNDER market probability: `0.575916`
- UNDER delta: `0.044676`
- UNDER EV: `0.005358434028735343`
- UNDER uncertainty: `null`
- UNDER status: `NO_EDGE`

## Remaining Data / Governance Issues

These do not block analysis-only `ANALYSIS_PICK`, but they still block formal
recommendations, locks, and production release:

- F5 historical AH for Allsvenskan remains unavailable from reviewed source/crosswalk.
- F8 squad value remains incomplete because reviewed as-of artifact is not present.
- LMM/lineups remain advisory only; no published lineup baseline was requested or required.
- Uncertainty is currently `null` because the active model reports
  `lambda_uncertainty_method=none`; formal use needs an approved uncertainty method.
- Calibration is still `BASELINE_PRIOR`, not validated calibration.
- Staging API container remains pre-existing `unhealthy`/503 and was not remediated in this task.
- Production deployment was not attempted.

## Verification

- `uv run ruff check src/w2/api/repository.py scripts/probe_analysis_chain.py scripts/materialize_captured_matchday_odds.py src/w2/ingestion/xg_backfill.py tests/unit/test_xg_backfill_materialization.py`
- `uv run pytest tests/unit/test_analysis_card_xg_materialized.py tests/unit/test_feature_inputs_independent_sources.py tests/unit/test_dashboard_recommendation_loop.py tests/unit/test_xg_backfill_materialization.py -q`
- Result: `47 passed`
