# W2 S13 Odds Probe Fix And True Matrix

Date: 2026-07-07

Status: `READ_ONLY_AUDIT_PROBE_FIXED`

This report records the S13 fix for the league whitelist odds/bookmaker-depth
probe. The change is intentionally narrow: audit fixture selection now prefers
the nearest future fixture inside the odds publication window instead of the
first fixture returned by the season fixture response.

No league was enabled. No staging or production deploy was performed. No DB,
checkpoint, lock, or settlement writes were performed.

## Code Change

Changed:

- `src/w2/competitions/league_whitelist_audit.py`
- `scripts/run_w2_pro_day1_sprint.py`
- `tests/unit/test_league_whitelist_audit.py`

The audit now selects the odds probe fixture in this order:

1. nearest future fixture inside the odds probe window,
2. nearest future fixture if no window candidate exists,
3. first fixture id only as a final compatibility fallback.

The implementation uses a 14-day window. S12 showed Brazil had usable AH/OU
odds roughly 10 days out, so a strict 7-day ceiling would still create false
negatives. This is a deliberate "about one to two weeks" odds-window guard for
audit evidence, not a staging action window.

## Threshold Evaluation

`MIN_BOOKMAKER_DEPTH` remains `3`.

Reason: Brazil passed with exactly 3 bookmakers and complete AH/OU/line
evidence. Raising the threshold above 3 would recreate a false negative for a
league that has usable W2 AH/OU market coverage.

The hard bookmaker-depth gate remains:

- bookmaker_count >= 3
- AH present
- OU present
- line values present

## S13 True Odds Matrix

Command output was sanitized and stored under:

```text
/tmp/w2_s13_odds_window_audit_20260707T011240Z/
```

Provider calls made by the S13 re-audit: `1`.

| competition | odds fixture | odds | bookmaker_depth | bookmakers | AH | OU | line | conclusion |
| --- | --- | --- | --- | ---: | --- | --- | --- | --- |
| premier_league | 1557367 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| la_liga | 1570335 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| bundesliga | 1575140 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| serie_a | 1550095 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| ligue_1 | 1552729 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| world_cup_2026 | 1576804 | PASS | PASS | 13 | yes | yes | yes | usable inventory evidence |
| brasileirao_serie_a | 1492291 | PASS | PASS | 3 | yes | yes | yes | previous failure was probe-selection false negative |
| argentina_primera | 1493014 | FAIL | FAIL | 0 | no | no | no | watchlist; re-check or secondary source if repeated |
| mls | 1490325 | FAIL | FAIL | 0 | no | no | no | secondary odds provider candidate |
| chinese_super_league | 1523195 | PASS | PASS | 10 | yes | yes | yes | previous failure was probe-selection false negative |
| allsvenskan | 1494206 | PASS | PASS | 11 | yes | yes | yes | usable inventory evidence |
| eliteserien | 1494694 | PASS | PASS | 12 | yes | yes | yes | usable inventory evidence |
| eredivisie | 1552117 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |
| primeira_liga | 1575446 | FAIL | FAIL | 0 | no | no | no | August near-kickoff 2026 re-check required |

## Staging Candidate Signal

The fixed probe produced inventory candidates with provider mapping, fixtures,
odds, and bookmaker depth all passing:

- `world_cup_2026`
- `brasileirao_serie_a`
- `chinese_super_league`
- `allsvenskan`
- `eliteserien`

This is not an enablement approval. It only means the odds/bookmaker-depth
inventory signal is no longer blocked by the old first-fixture false negative.
The full 7-item whitelist audit and separate user approval are still required
before any `enabled=true` change.

## Secondary Odds Source Note

MLS remains empty across the cached future odds set and the S13 fixed probe.
It is now marked as a secondary odds provider candidate in:

```text
docs/providers/SECONDARY_ODDS_PROVIDER_DECISION.md
```

Argentina Primera also failed this S13 probe. It is not yet promoted to a hard
secondary-source decision, but it should be re-checked near kickoff or added to
the same secondary-provider track if repeated.

## Big-5 August Readiness

The five major European leagues still require August near-kickoff 2026 probes.
Historical odds retention was not confirmed by S12, and the current season
fixtures are not yet useful for a final August staging decision. The correct
readiness checkpoint is a near-kickoff future fixture once each league enters
the provider odds publication window.

## Safety

- provider_calls_this_reaudit=1
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
