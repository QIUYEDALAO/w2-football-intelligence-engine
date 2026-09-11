# V1 recalibration evidence — A1 PIT input freeze

This package freezes only pre-kickoff model inputs and market observations. No
results, score, goals, settlement, or outcome columns were queried or included.

## Join and filters

- Join: `matchday_market_observations.provider_fixture_id = team_xg_match.fixture_id`.
- Kickoff window: `2026-07-22` through `2026-08-30` (inclusive).
- Quotes: `captured_at < kickoff_at`, `live=false`, `suspended=false`, at least
  three distinct bookmakers; latest captured bucket retained per fixture.
- Snapshot path uses both teams' `team_xg_rolling_snapshot` rows keyed by
  `as_of_fixture_id`; otherwise the input is marked `rebuild`.

## Integrity

The JSON artifact records SHA-256 digests of each read-only CSV export and its
own digest. The export observed 24 eligible fixtures (17 snapshot, 7 rebuild),
not the 283 fixtures stated in the task brief. This is an evidence coverage
blocker, not a license to infer missing fixtures or read outcomes.

The artifact intentionally omits snapshot goal metadata and all result fields.
