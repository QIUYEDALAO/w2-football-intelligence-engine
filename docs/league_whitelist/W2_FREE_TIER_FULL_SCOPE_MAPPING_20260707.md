# W2 Free-Tier Full-Scope Mapping Evidence

Date: 2026-07-07

This document records the free-tier historical evidence-only audit after
`--audit-season-override 2024` was corrected to use completed fixtures
(`status=FT`). The purpose is to verify provider mapping and fixture coverage
without enabling any league, deploying, or using paid provider features.

## Scope

- Audit mode: `EVIDENCE_ONLY`
- Group: `all_whitelist_competitions`
- Audit season override: `2024`
- Initial output directory: `/tmp/w2_free_tier_full_scope_mapping_20260706T173638Z`
- Initial provider requests: 41
- Initial status: `PROVIDER_AUDIT_COMPLETED`
- Raw provider payloads: not committed
- Provider headers and key: not committed
- DB reads/writes: 0
- Deploys: 0
- `enabled=true` flips: 0

## Initial Result

The corrected historical fixture path validated annual-league fixtures on the
free tier. Bookmaker depth remains expectedly blocked by missing free odds
depth.

| competition | provider_mapping | fixtures | fixture_count | bookmaker_depth | note |
| --- | --- | --- | ---: | --- | --- |
| premier_league | PASS | PASS | 380 | FAIL | odds depth unavailable |
| la_liga | PASS | PASS | 380 | FAIL | odds depth unavailable |
| bundesliga | PASS | PASS | 308 | FAIL | odds depth unavailable |
| serie_a | PASS | PASS | 380 | FAIL | odds depth unavailable |
| ligue_1 | PASS | PASS | 307 | FAIL | odds depth unavailable |
| brasileirao_serie_a | ADVISORY_MISMATCH | PASS | 380 | FAIL | provider name is `Serie A` |
| argentina_primera | ADVISORY_MISMATCH | PASS | 378 | FAIL | provider name is `Liga Profesional Argentina`; team_count absent |
| mls | ADVISORY_MISMATCH | PASS | 512 | FAIL | provider country is `USA` |
| chinese_super_league | ADVISORY_MISMATCH | PASS | 240 | FAIL | provider name is `Super League` |
| allsvenskan | PASS | PASS | 242 | FAIL | odds depth unavailable |
| eliteserien | PASS | PASS | 242 | FAIL | odds depth unavailable |
| eredivisie | PASS | PASS | 317 | FAIL | odds depth unavailable |
| primeira_liga | PASS | PASS | 308 | FAIL | odds depth unavailable |
| world_cup_2026 | SEASON_EXCEPTION | FAIL | 0 | FAIL | 2024 is not a World Cup tournament season |

## Provider Mapping Contract

Provider identity is now anchored on API-Football `league_id`. A matching
`league_id` is the hard gate for `provider_mapping=PASS`; observed `name`,
`country`, `season`, and `team_count` are advisory evidence. Advisory
mismatches are recorded so profiles can be cleaned up, but cosmetic display
differences and annual team-count changes do not block mapping.

Fixtures returning data for the configured `league_id` is treated as additional
identity evidence for annual leagues. The 2024 sweep therefore verifies 13/13
annual whitelist competitions by ID plus fixture availability. World Cup is
excluded from that 2024 annual sweep because it requires a tournament season,
such as 2022, for historical proof.

Observed sanitized fields are written into the evidence-only result payloads
payloads and summarized here in a persistent, sanitized path:

| competition | configured league_id | observed name | observed country | observed team_count | advisory note |
| --- | ---: | --- | --- | ---: | --- |
| premier_league | 39 | Premier League | England | 20 | none |
| la_liga | 140 | La Liga | Spain | 20 | none |
| bundesliga | 78 | Bundesliga | Germany | 18 | none |
| serie_a | 135 | Serie A | Italy | 20 | none |
| ligue_1 | 61 | Ligue 1 | France | 18 | none |
| brasileirao_serie_a | 71 | Serie A | Brazil | 20 | display-name advisory |
| argentina_primera | 128 | Liga Profesional Argentina | Argentina | 0 | display-name / team-count advisory |
| mls | 253 | Major League Soccer | USA | 15 | country advisory |
| chinese_super_league | 169 | Super League | China | 16 | display-name advisory |
| allsvenskan | 113 | Allsvenskan | Sweden | 16 | none |
| eliteserien | 103 | Eliteserien | Norway | 16 | none |
| eredivisie | 88 | Eredivisie | Netherlands | 18 | none |
| primeira_liga | 94 | Primeira Liga | Portugal | 18 | none |

## Evidence-Based Profile Changes

No `api_football_league_id` value was changed because the failing annual
competitions already returned fixtures with the configured IDs. The failures
were caused by strict comparison against advisory display names, country
spellings, or annual team-count metadata. The profile aliases below are retained
so advisory evidence is precise, but they no longer decide PASS/FAIL.

| competition | api_football_league_id | provider league name | provider country | change |
| --- | ---: | --- | --- | --- |
| brasileirao_serie_a | 71 | Serie A | Brazil | add provider name/country alias |
| argentina_primera | 128 | Liga Profesional Argentina | Argentina | add provider name/country alias |
| mls | 253 | Major League Soccer | USA | add provider name/country alias |
| chinese_super_league | 169 | Super League | China | add provider name/country alias |

The provider audit still records:

- `provider_mapping.api_football_league_name` when present
- `provider_mapping.api_football_country` when present
- profile `name` / `country` as fallback
- advisory mismatches for `name`, `country`, `season`, and `team_count`

Argentina Primera no longer fails mapping when API-Football omits or changes
`team_count`; the mismatch is advisory unless the configured `league_id` fails.

## Rerun Status

After applying the alias changes, a targeted rerun began with
`brasileirao_serie_a`. It stopped after 2 provider requests because provider
headers reached the local quota warning threshold:

```text
stopped_reason=QUOTA_WARNING
quota_remaining=10
```

Output directory:

```text
/tmp/w2_free_tier_mapping_fix_rerun_20260706T174528Z/brasileirao_serie_a
```

The second request returned 380 fixtures, but the script correctly stopped
before completing the report. Because `QUOTA_WARNING` is a hard stop condition,
no additional provider requests were made.

## World Cup Exception

`world_cup_2026` cannot be validated with `--audit-season-override 2024`
because 2024 is not a World Cup tournament season. This is not evidence that
league id `1` is wrong. It requires a tournament-season audit override, such as
the last completed World Cup season, in a separate approved provider step.

## Decision

- Annual league fixture coverage is verified on the free tier for 13/13 annual
  competitions in the full whitelist scope.
- Annual league provider IDs are the hard identity anchor and do not need
  changes from this evidence.
- Four annual profiles now record provider-specific alias fields so future
  advisory evidence compares against API-Football observed values.
- `world_cup_2026` remains a season-scope exception for 2024 and must not be
  "fixed" by guessing a different league id.
- The only expected remaining provider-backed blocker for annual leagues is
  bookmaker depth / AH-OU odds coverage.

## Safety

- provider_calls_full_scope_initial=41
- provider_calls_targeted_rerun=2
- provider_calls_this_step=43
- db_reads=0
- db_writes=0
- enabled_true_flips=0
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- checkpoint_write=false
- lock_capture_write=false
- settlement_write=false
- raw_payload_committed=false
- key_or_header_committed=false
