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

Do not use `scripts/run_stage14a_league_audit.py` as evidence for
`national_leagues`. That script is a top-five offline regression harness and does
not prove national league provider coverage. National league whitelist evidence
must come from `scripts/run_w2_league_whitelist_audit.py`.

P2 August validation planning uses the disabled top-five profiles as candidates
only. Planning documents must not be interpreted as runtime enablement; Changing
`enabled` from `false` to `true` requires a separate approved runtime PR with
quota, rollback, and staging evidence.

Coverage fields:

- `xg`: API-Football `/fixtures/statistics` availability.
- `lineups_injuries`: API-Football lineup and injury availability.
- `squad_value`: Transfermarkt dataset mapping availability.
- `bookmaker_depth`: future-refresh bookmaker coverage.
- `h2h`: internal historical fixture coverage.
- `settled_ah`: settled Asian handicap history coverage.
