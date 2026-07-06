# W2 League Whitelist Remediation Plan 2026-07-06

## Status

PR #183 corrected the league whitelist audit scope from the six
`national_leagues_in_season` competitions to the full 14-competition whitelist.
The final #183 acceptance state is:

- `full_scope=14`
- `completed_leagues_total=14`
- `partial_leagues=[]`
- `unstarted_leagues=[]`
- `can_enable=false` for all 14 competitions
- no `enabled=true` flips
- provider reports remained under `/tmp` and were not committed
- no staging deploy
- no production deploy
- no DB writes
- no scheduler restart
- no lock or settlement writes

This document is an offline remediation plan only. It does not call provider,
does not update runtime state, and does not enable any competition.

## Scope Inventory

The full whitelist scope is 14 competitions:

| Group | Competitions |
| --- | --- |
| Top five | `premier_league`, `la_liga`, `bundesliga`, `serie_a`, `ligue_1` |
| World | `world_cup_2026` |
| National leagues | `brasileirao_serie_a`, `argentina_primera`, `mls`, `chinese_super_league`, `allsvenskan`, `eliteserien`, `eredivisie`, `primeira_liga` |

The `national_leagues/` directory contains eight candidate profiles. The full
whitelist count is 14 because it also includes five `top_five/` profiles and
`world_cup_2026`.

## Blockers By Category

The #183 full-scope audit inventory keeps every competition blocked from
enablement. The common blocker categories are:

| Category | Current conclusion | Remediation owner |
| --- | --- | --- |
| `provider_mapping` | Failed or not safely confirmed for enablement | Profile mapping review |
| `season` | Audited/provider season evidence must be aligned with configured season intent | Profile mapping review |
| `fixtures` | Fixture query coverage did not prove the intended upcoming or active schedule | Fixture query review |
| `results` | Historical/result coverage must be confirmed before outcome tracking claims | Coverage review |
| `xg` | Statistics/xG coverage must be confirmed per provider league and season | Coverage review |
| `lineups_injuries` | Lineup and injury availability must be verified for the intended season | Coverage review |
| `bookmaker_depth` | AH/OU depth and line presence did not meet the whitelist contract | Odds market review |
| `squad_value` | No approved squad value mapping source is available yet | Data-source review |

None of these blockers should be converted into guessed config edits. A profile
change is allowed only after sanitized observed evidence identifies the exact
provider league, country, season, team count, fixture query behavior, and market
coverage that justify it.

## Provider Mapping And Season Remediation

Remediation candidates are investigative steps, not direct config changes:

1. Reconcile each configured `api_football_league_id` with sanitized observed
   provider values: league id, league name, country, season, and team count.
2. For leagues with season fallback warnings, separate "historical coverage
   exists" from "current configured season is enablement-ready".
3. Record whether the intended W2 competition should use the provider's current
   season, previous completed season, or a delayed season-start gate.
4. Keep profile edits in a separate review PR after evidence is captured.

The next provider audit must emit sanitized observed fields, including:

- `observed_provider_league_id`
- `observed_provider_league_name`
- `observed_provider_country`
- `observed_provider_season`
- `observed_provider_team_count`

## Fixture Query Remediation

Fixture coverage should be remediated before any enablement attempt:

1. Capture sanitized fixture query parameters for each competition.
2. Record fixture response counts for the intended season and audit window.
3. Distinguish off-season competitions from misconfigured provider season or
   league id mappings.
4. Require an explicit explanation when an active league returns no usable
   upcoming fixtures.
5. Keep query changes behind dry-run and audit-only commands until they pass the
   seven-item whitelist audit.

Required sanitized evidence:

- `observed_fixture_query_params`
- `observed_fixture_response_count`

## Bookmaker Depth And AH/OU Remediation

Bookmaker readiness must follow the tightened audit contract:

- minimum bookmaker depth is at least three bookmakers
- AH market must be observed
- OU market must be observed
- a usable line must be observed

The remediation path is:

1. Capture sanitized bookmaker counts per competition.
2. Capture sanitized AH/OU market names observed from the provider.
3. Confirm whether provider market names differ by league, country, or bookmaker.
4. Update market-name mapping only after sanitized observed market names support
   the change.
5. Re-run audit after mapping changes, still with `enabled=false`.

Required sanitized evidence:

- `observed_bookmaker_count`
- `observed_ah_ou_market_names`
- `observed_has_ah`
- `observed_has_ou`
- `observed_has_line`

## Squad Value Mapping Source Plan

`squad_value:CANNOT_VERIFY` remains an enablement blocker. The next remediation
step is to choose and document an approved source for squad value or an approved
temporary substitute policy.

The plan:

1. Define the accepted source of squad value or squad-strength proxy.
2. Define update cadence, licensing constraints, and stale-data handling.
3. Add a deterministic mapping from W2 competition/team ids to the source ids.
4. Add audit output that reports mapping coverage without committing licensed or
   raw third-party payloads.
5. Keep `can_enable=false` until squad value can pass or a formally approved
   substitute gate is documented.

## Next Provider Audit Prerequisites

Before another provider audit is allowed:

1. Provider usage reconciliation must be accepted for the intended account and
   dashboard.
2. A daily hard cap and reserve must be set before execution.
3. The audit command must use the full 14-competition scope, unless the PR
   explicitly states a smaller scoped purpose.
4. Sanitized observed evidence fields must be included in reports.
5. Raw provider payloads, provider keys, full headers, runtime files, and `/tmp`
   reports must not be committed.
6. The audit must stop on 429, quota warning, endpoint outside allowlist, DB write
   requirement, deploy requirement, scheduler restart requirement, or
   `enabled=true` requirement.

## Enablement Gate

No competition may flip to `enabled=true` until all seven audit items pass for
that competition:

1. provider mapping
2. fixtures
3. results
4. xG/statistics
5. lineups and injuries
6. bookmaker depth with AH/OU and line
7. squad value mapping

Passing one competition does not enable the group. Each competition needs its own
passing report, reviewer approval, and a separate runtime enablement PR with
quota, rollback, and staging evidence.

## Explicit Non-Goals

- no provider calls in this PR
- no `enabled=true` changes
- no staging deploy
- no production deploy
- no DB reads or writes
- no scheduler restart
- no lock or settlement writes
- no raw provider payloads committed
- no `/tmp` audit reports committed
- no profile value guesses from category-level blockers
