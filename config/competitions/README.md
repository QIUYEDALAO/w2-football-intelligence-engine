# Competitions Config

This directory is the W2 competition whitelist. Each competition profile records:

- `competition_id`
- `season`
- `enabled`
- `coverage_profile`

Only profiles with `enabled=true` can drive live collection, analysis-card output,
or forward-run fixture selection. As of U0, only `world_cup_2026` is enabled.
Top-five and selected national leagues stay disabled until their Stage14 coverage
audit passes.

Coverage fields:

- `xg`: API-Football `/fixtures/statistics` availability.
- `lineups_injuries`: API-Football lineup and injury availability.
- `squad_value`: Transfermarkt dataset mapping availability.
- `bookmaker_depth`: future-refresh bookmaker coverage.
- `h2h`: internal historical fixture coverage.
- `settled_ah`: settled Asian handicap history coverage.
