# National League Whitelist Candidates

Candidate competition profiles for national top-flight leagues beyond `top_five/`
and `world_cup_2026`. Same schema as `top_five/`. All profiles here are
`enabled=false`.

Per the parent `config/competitions/README.md` governance: flipping `enabled`
false→true requires a passed Stage14 coverage audit plus a separate approved
runtime PR with quota, rollback, and staging evidence. Creating a profile is NOT
enablement.

## Selection criteria

- Top division only (match manipulation concentrates in lower divisions).
- Coverage-capable on API-Football (`/fixtures/statistics` xG, lineups, odds depth).
- Deep, liquid betting markets.
- `provider_mapping.api_football_league_id` values are best-known and carry
  `provider_mapping_status=STAGE14_VERIFICATION_REQUIRED` — Stage14 must confirm
  each id before enablement.

## `activation_plan`

- `AUDIT_THEN_STAGING_ENABLE_NOW_IN_SEASON` — league is in season now (July 2026);
  target: pass audit, enable in staging first (staging = policy A), start
  accumulating `outcome_tracked` samples.
- `AUDIT_THEN_ENABLE_AT_SEASON_START_2026_08` — product-core European league,
  off-season until August; placeholder now, enable when the season opens.

## Profiles

| competition_id | league | in season (Jul 2026) | api_football id (verify) | activation |
|---|---|---|---|---|
| eredivisie | Eredivisie (NL) | no | 88 | Aug season start |
| primeira_liga | Primeira Liga (PT) | no | 94 | Aug season start |
| brasileirao_serie_a | Brasileirao Serie A (BR) | yes | 71 | staging now |
| argentina_primera | Liga Profesional (AR) | yes | 128 | staging now |
| allsvenskan | Allsvenskan (SE) | yes | 113 | staging now |
| eliteserien | Eliteserien (NO) | yes | 103 | staging now |
| mls | Major League Soccer (US/CA) | yes | 253 | staging now |
| chinese_super_league | Chinese Super League (CN) | yes | 169 | staging now |

## Per-league notes for Stage14

- `argentina_primera`: unusual format (single table ~28 teams, relegation by
  averages, split tournaments) — confirm team count, season mapping, and the
  correct API-Football competition id (multiple Argentine competitions exist).
- `mls`: multi-timezone; 2026 World Cup is hosted in US/Canada/Mexico, so summer
  fixture scheduling is disrupted — verify fixture calendar before staging enable.
- `chinese_super_league`: added by product decision; carries heavier historical
  integrity baggage — pair with a per-match integrity gate (odds anomaly / dead
  rubber) before any lock-eligible treatment.
- Top-five (`../top_five/`) and `../world_cup_2026.v1.json` are managed
  separately; only `world_cup_2026` is enabled today.
