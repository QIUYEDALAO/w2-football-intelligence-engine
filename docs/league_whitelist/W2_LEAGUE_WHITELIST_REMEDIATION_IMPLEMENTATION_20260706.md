# W2 League Whitelist Remediation Implementation 2026-07-06

## Summary

This PR implements offline remediation support after the full-scope whitelist
coverage inventory:

- 14/14 whitelist competitions have coverage-inventory reports.
- 14/14 remain `can_enable=false`.
- No profile is enabled.
- No provider call is made in this PR.
- No deployment, DB access, scheduler restart, lock write, or settlement write is
  part of this PR.

## What Was Implemented Offline

### Profile validation

`league_profile_validation` checks configured profile values against sanitized
observed provider evidence. If evidence is missing, it returns
`NEEDS_PROVIDER_EVIDENCE` and does not mutate the profile.

It validates:

- provider league id
- provider league name
- provider country
- provider season
- provider team count

### Fixture query diagnostics

The audit now distinguishes fixture-empty states:

- `FIXTURES_EMPTY_OFF_SEASON`
- `FIXTURES_EMPTY_CONFIGURED_SEASON`
- `FIXTURES_QUERY_REVIEW_REQUIRED`

Coverage inventory may use recent results as evidence for deeper sampling, but
empty future fixtures are never treated as enablement-ready.

### Odds market mapping

`odds_market_mapping` normalizes common AH/OU market names:

- Asian Handicap
- Handicap Result
- Asian Handicap First Half
- Goals Over/Under
- Over/Under
- Total Goals
- Match Goals

The bookmaker depth contract remains strict:

- at least three bookmakers
- AH observed
- OU observed
- line observed

### Squad value blocker

The squad value requirement remains blocked by `SQUAD_VALUE_SOURCE_MISSING`.
This PR adds documentation for the source contract but does not invent or
approve a data source.

### Readiness CLI

`scripts/check_w2_league_remediation_readiness.py` is a no-provider, no-DB
readiness check. It reports:

- profile validation status
- fixture query status
- odds market mapping status
- squad value source status
- `ready_for_provider_reaudit`
- safety counters

## What Still Requires The Next Provider Audit

The next provider audit must capture sanitized observed evidence before any
profile value changes:

- observed provider league id
- observed provider league name
- observed country
- observed season
- observed team count
- observed fixture query params
- observed fixture response count
- observed bookmaker count
- observed AH/OU market names
- observed line presence

Do not guess league id, season, team count, or bookmaker mappings from blocker
categories alone.

## Enablement Rule

No competition may become `enabled=true` until all seven items pass:

1. provider mapping
2. fixtures
3. results
4. xG/statistics
5. lineups and injuries
6. bookmaker depth with AH/OU and line
7. squad value mapping

Passing one league does not enable the group. Each league needs its own PASS
report, reviewer approval, and a separate runtime enablement PR.

## Safety

- provider_calls=0
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- no lock or settlement writes
- no `/tmp` audit reports committed
- no raw provider payload committed
