# W2 Free-Tier Historical Capability

Date: 2026-07-07

This note records the sanitized result of the free-tier capability probe for the
W2 league whitelist historical proof phase. It is evidence for selecting a
historical audit season only; it does not enable any league and does not change
canonical profile seasons.

## Scope

- Provider calls in this probe: 3
- Endpoints probed: `status`, `leagues?id=39`, `leagues?id=71`
- Follow-up fixture-window probe: 2 provider requests,
  `fixtures?league=39&season=2024` and `fixtures?league=39&season=2023`
- Raw provider payloads: not committed
- Headers and keys: not recorded
- Output directory: `/tmp/w2_free_tier_capability_20260706T165210Z`
- User-observed official dashboard usage before this phase: 37 calls

## Result

The probe did not return provider `errors.plan` for either league metadata
request. Both control leagues returned one league record.

| control | league_id | country | response_count | chosen season |
| --- | ---: | --- | ---: | ---: |
| premier_league | 39 | England | 1 | 2024 |
| brasileirao_serie_a | 71 | Brazil | 1 | 2024 |

## Coverage Matrix

For the selected historical season `SEASON_FREE=2024`:

| control | fixtures events | fixture statistics | player statistics | lineups | odds |
| --- | --- | --- | --- | --- | --- |
| premier_league | true | true | true | true | false |
| brasileirao_serie_a | true | true | true | true | false |

## Fixture Window Probe

The follow-up fixtures probe confirmed that Premier League historical fixtures
are actually available to the current key:

| endpoint | season | response_count | errors.plan |
| --- | ---: | ---: | --- |
| `fixtures?league=39&season=2024` | 2024 | 380 | false |
| `fixtures?league=39&season=2023` | 2023 | 380 | false |

The earlier evidence-only failure was caused by the `next=5 + season` query
shape used for future fixtures, not by the 2024 historical fixtures window.

The same metadata shows that Premier League 2026 has coverage flags set to
false, while Brasileirao Serie A 2026 still advertises fixture/statistics/lineup
coverage. The prior 2026 evidence-only failures therefore should not be treated
as a completed free-tier historical proof.

## Decision

Use `SEASON_FREE=2024` for the historical free-tier control audit.

The next audit must use an explicit audit-season override such as
`--audit-season-override 2024` or `W2_AUDIT_SEASON_OVERRIDE=2024`. This override
is a per-run audit input only. It must not mutate
`provider_mapping.api_football_season` in the competition profiles.

## Safety

- provider_calls_capability_probe=3
- provider_calls_fixture_window_probe=2
- db_reads=0
- db_writes=0
- enabled_true=false
- staging_deploy=false
- production_deploy=false
- scheduler_restart=false
- raw_payload_committed=false
- key_or_header_committed=false
