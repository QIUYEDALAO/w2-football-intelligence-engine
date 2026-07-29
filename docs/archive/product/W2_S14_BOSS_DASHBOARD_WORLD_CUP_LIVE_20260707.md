# W2 S14 Boss Dashboard World Cup Live Proof

Date: 2026-07-07

Status: Draft PR evidence. This is a staging-only visible-product proof, not a production enablement or betting-quality claim.

## Scope

S14 replaces the dashboard first screen with a boss-view L1 decision page backed by DayView / DecisionCard fields.

The legacy dashboard components remain available in collapsed L2 diagnostics drawers. They are not the default first-screen experience.

## World Cup Live Probe

Only the already enabled `world_cup_2026` profile was used.

Sanitized output directory:

`/tmp/w2_s14_worldcup_live_20260707T024707Z`

Provider summary:

| Field | Value |
| --- | --- |
| provider_calls_actual | 15 |
| hard_cap | 20 |
| fixtures_found | 4 |
| matchday_decision_card_count | 4 |
| raw_payload_written | false |
| db_writes | 0 |
| enabled_changes | 0 |
| staging_deploy | false |
| production_deploy | false |

Fixture coverage:

| Fixture | Status | Odds | AH | OU | xG | Lineups |
| --- | --- | --- | --- | --- | --- | --- |
| Portugal vs Spain | FT | yes | yes | yes | yes | yes |
| USA vs Belgium | FT | yes | yes | yes | yes | yes |
| Argentina vs Egypt | NS | yes | yes | yes | pending | pending |
| Switzerland vs Colombia | NS | yes | yes | yes | pending | pending |

## DecisionCard / DayView Result

DayView cards: 4

Counts:

| Field | Value |
| --- | --- |
| analysis_pick | 4 |
| recommend | 0 |
| watch | 0 |
| not_ready | 0 |
| skip | 0 |
| lock_eligible | 0 |
| partial | 4 |
| outcome_tracked | 4 |

All four cards are staging analysis references. None are production-lockable.

The model caveat must remain visible:

> World Cup output is shown conservatively in staging. The current fitted model was validated on big-five club data and has not completed independent validation for international tournaments.

## L1 Rendering Proof

Screenshot:

`/tmp/w2_s14_worldcup_live_20260707T024707Z/s14_l1_worldcup_dashboard.png`

Screenshot checks:

| Check | Result |
| --- | --- |
| First screen shows World Cup matches | PASS |
| First screen shows DecisionCard-derived counts | PASS |
| First screen shows human tier labels | PASS |
| First screen shows model caveat | PASS |
| Internal enum leak on L1 | PASS, none found |
| L2 diagnostics default collapsed | PASS |
| Global diagnostics default collapsed | PASS |

Forbidden visible strings checked on first-screen text:

`ANALYSIS_PICK`, `NOT_READY`, `RECOMMEND`, `PARTIAL`, `BLOCKED`, `LINEUPS_PENDING`, `ASIAN_HANDICAP`, `provider_request_hash`, `raw_payload`.

No forbidden string was found.

## Safety

No production action was performed.

Safety summary:

| Field | Value |
| --- | --- |
| provider_calls | 15 |
| provider_hard_cap | 20 |
| db_writes | 0 |
| checkpoint_write | false |
| staging_deploy | false |
| production_deploy | false |
| scheduler_restart | false |
| lock_capture_write | false |
| settlement_write | false |
| new_enabled_leagues | 0 |
| raw_payload_committed | false |
| key_or_header_committed | false |

## Notes

This proof shows the visible product path:

provider live probe -> matchday dry-run -> DecisionCard -> DayView -> boss-view L1 dashboard.

It does not claim that World Cup recommendations are calibrated or production-ready.
