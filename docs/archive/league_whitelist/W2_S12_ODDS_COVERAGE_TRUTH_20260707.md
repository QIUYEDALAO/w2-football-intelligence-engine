# W2 S12 Odds Coverage Truth And August Readiness

Date: 2026-07-07

Status: `READ_ONLY_PROBE_COMPLETED`

This report records a read-only odds coverage probe after the Pro day-1 data
sprint. It does not enable any league, deploy staging or production, write DB
rows, change canonical seasons, restart scheduler loops, write checkpoints, or
write lock/settlement records.

Raw provider payloads, headers, and keys are not included in this document.
Sanitized probe artifacts were written only under:

```text
/tmp/w2_s12_odds_probe_20260707/
```

## Probe Scope

The immediate question was whether the `odds` / `bookmaker_depth` failures in
the 14-league inventory were true coverage failures, or whether the audit
selected the wrong fixture. The current inventory uses the first fixture in the
provider fixture response; that can be a settled historical fixture or a fixture
outside the useful odds publication window.

Read-only probes:

- Brazil Serie A, league `71`, season `2026`
- MLS, league `253`, season `2026`
- Chinese Super League, league `169`, season `2026`
- Premier League, league `39`, season `2024`, one historical finished fixture

Provider calls made by this S12 probe: `2`.

Most in-season checks reused the Pro day-1 local cache. The two live calls were
for the Premier League 2024 historical fixture check.

## In-Season Window Result

The requested five-day upcoming window was evaluated from
`2026-07-07T00:00:00Z`.

| league | selected fixtures <=5d | 1X2 | AH | OU | max bookmakers | W2 AH/OU usable | classification |
| --- | ---: | --- | --- | --- | ---: | --- | --- |
| brasileirao_serie_a | 0 | no | no | no | 0 | no | no fixture in 5-day window |
| mls | 0 | no | no | no | 0 | no | no fixture in 5-day window |
| chinese_super_league | 3 | yes | yes | yes | 10 | yes | audit probed wrong fixture/window |

Brazil and MLS had no fixture inside the five-day window, so they cannot be
classified from that narrow window alone.

## Nearest-Future Cache Scan

To avoid misclassifying a league simply because it had no fixture inside five
days, the existing local cache was scanned for nearest future fixtures without
making new provider calls.

| league | future odds payloads checked | payloads with any odds | W2 AH/OU usable payloads | nearest usable kickoff | max bookmakers | classification |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| brasileirao_serie_a | 202 | 10 | 10 | 2026-07-16T22:30:00Z | 3 | audit probed wrong fixture/window |
| mls | 292 | 0 | 0 | none observed | 0 | true odds coverage thin or unavailable in cached season |
| chinese_super_league | 104 | 8 | 8 | 2026-07-10T11:35:00Z | 10 | audit probed wrong fixture/window |

Brazil and China both have future fixtures with 1X2, Asian Handicap, Goals
Over/Under, line values, and enough bookmaker depth. Their inventory failures
are therefore not proof of missing league coverage; they are caused by the
fixture selection strategy.

MLS had zero non-empty odds payloads across the cached 2026 future fixtures.
For W2's AH/OU engine, this should be treated as a real coverage blocker unless
a later provider re-check proves otherwise.

## Big-5 August Readiness Probe

The Premier League 2024 historical fixture probe did not confirm historical odds
availability:

| league | season | fixture type | 1X2 | AH | OU | max bookmakers | conclusion |
| --- | --- | --- | --- | --- | --- | ---: | --- |
| premier_league | 2024 | one finished historical fixture | no | no | no | 0 | historical odds not retained or not available through this endpoint |

This does not prove that August 2026 Premier League odds will be unavailable.
It only means historical odds retention was not confirmed by this one-fixture
probe. Big-5 August readiness should be confirmed with a fresh near-kickoff
future fixture probe when the season enters the provider's odds publication
window.

## Odds Availability Matrix

| competition | 1X2 | AH | OU | bookmaker depth | W2 AH/OU engine usable | conclusion |
| --- | --- | --- | --- | ---: | --- | --- |
| brasileirao_serie_a | yes | yes | yes | 3 | yes | inventory should probe nearest odds-window fixture |
| mls | no | no | no | 0 | no | needs secondary odds source or later re-check |
| chinese_super_league | yes | yes | yes | 10 | yes | inventory should probe nearest odds-window fixture |
| premier_league historical 2024 | no | no | no | 0 | unknown for August | re-check with future 2026 fixture near kickoff |

## Recommendation

1. Fix the audit probe strategy before using `odds` / `bookmaker_depth` as a
   staging blocker for in-season leagues. The audit should evaluate the nearest
   upcoming fixture inside the odds publication window, not the first fixture in
   the season response.
2. Treat Brazil and China as `AUDIT_PROBED_WRONG_FIXTURE_WINDOW`, not true odds
   coverage failures.
3. Treat MLS as `TRUE_AH_OU_COVERAGE_THIN_OR_UNAVAILABLE` for now; document it
   as a secondary odds provider candidate in
   `docs/providers/SECONDARY_ODDS_PROVIDER_DECISION.md` before any MLS staging
   action.
4. Treat Big-5 August readiness as `NOT_CONFIRMED_BY_HISTORICAL_ODDS`. The
   correct confirmation point is a near-kickoff 2026 fixture once the August
   season is inside the provider's odds publication window.

## Safety

- provider_calls_this_probe=2
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- checkpoint_write=false
- lock_capture_write=false
- settlement_write=false
- canonical_season_changed=false
- raw_payload_committed=false
- key_or_header_committed=false
