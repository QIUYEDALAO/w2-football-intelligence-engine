# W2 Gate3 Baselight AI Schema Probe

Generated at: `2026-06-23T20:49:41Z`

Source: user-provided Baselight AI schema/coverage result.

No full Baselight data was downloaded. No formal Gate3 backtest was built. No deployment, Stage7I recovery, `.env` read, W1 modification, candidate output, or formal recommendation output was performed.

## Dataset

- dataset: `@blt.ultimate_soccer_dataset`
- odds table: `match_betting_odds`
- match/result table: `matches`

## Coverage

- odds row count: `522058931`
- odds fixture count: `32260`
- bookmaker count: `20`
- match count: `278892`
- home_score/away_score non-null fixtures: `32172`

## Markets

- Match Winner
- Asian Handicap
- Goals Over/Under
- Asian Handicap First Half
- Goals Over/Under First Half
- Double Chance
- Exact Score

## Asian Handicap Coverage

- observation_count: `23109497`
- fixture_count: `10946`
- settled AH fixture_count: `10858`
- AH bookmaker count: `15`
- AH line bucket count: `150`
- competition count: `70`
- season count: `3`
- join failures: `0`

## Odds Semantics

- odds_type values: `pre_match only`
- collected_at column type: `TIMESTAMP`
- observed collected_at precision: `DATE_ONLY`
- intraday precision: unavailable

## License

- dataset-level license: `CC BY 4.0`
- platform export/retention policy: `UNVERIFIED`

## Decision

`baselight_status=CONDITIONAL_GATE3_CANDIDATE`

Baselight can potentially support:

- historical AH baseline
- fixture-level chronological walk-forward
- daily pre-match snapshot replay
- settled AH settlement testing

Baselight cannot support from this evidence alone:

- T-1h phase
- T-30m phase
- T-10m phase
- intraday odds movement
- exact closing timestamp

## Remaining Blockers

- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`

Gate3 remains `PARTIAL` until a limited AH extract and walk-forward backtest are built and pass.

candidate=false

formal_recommendation=false
