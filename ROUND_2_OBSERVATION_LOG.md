# W2 MI Round 2 — R2-B Read-only Observation Log

```text
ROUND2_OBSERVATION_START_UTC = 2026-08-08T01:53:55.509495+00:00
ROUND2_OBSERVATION_END_UTC = 2026-08-22T01:53:55.509495+00:00
R2_B = ACTIVE
ROUND_3 = NOT_STARTED
```

This log records read-only observations only. It does not authorize Provider
calls, production writes, persistent polling, threshold selection or league
enablement.

## Snapshot 1 — 2026-08-08

Read-only public endpoints:

```text
GET /v1/health
GET /v1/version
GET /v1/dashboard/day-view?date=2026-08-08&window=future&timezone=Asia/Shanghai
```

Operational envelope:

```text
HTTP_STATUS = 200
API_GIT_SHA = 602665885a2cbaf87e5f6c6ceb8c73926244e471
DATA_PROFILE = real-db
DATA_SOURCE = read_model_checkpoint
DATABASE_READY = true
READ_MODEL_FIXTURE_COUNT = 69
DAYVIEW_CARD_COUNT = 64
DAYVIEW_PROVIDER_CALLS = 0
DAYVIEW_DB_WRITES = 0
DAYVIEW_WOULD_WRITE_CHECKPOINT = false
PUBLIC_SNAPSHOT_GENERATED_AT = 2026-08-08T02:17:09.560956Z
```

DayView coverage:

| Competition | Cards | BLOCKED | DATA_INCOMPLETE | Current odds | Last-known reference |
|---|---:|---:|---:|---:|---:|
| allsvenskan | 16 | 16 | 16 | 0 | 2 |
| brasileirao_serie_a | 20 | 20 | 20 | 0 | 8 |
| chinese_super_league | 15 | 15 | 15 | 0 | 7 |
| eliteserien | 13 | 13 | 13 | 0 | 3 |
| **Total** | **64** | **64** | **64** | **0** | **20** |

The other nine existing runtime-whitelist competitions and all four audit-only
candidates had no cards in this snapshot. The four audit-only candidates remain
outside DayView by design.

Market evidence boundary:

```text
FRESH_QUOTES = 0
MARKET_COMPLETE_FIXTURES = 0
LAST_KNOWN_REFERENCE_FIXTURES = 20
LAST_KNOWN_AH_ROWS = 20
LAST_KNOWN_OU_ROWS = 20
LAST_KNOWN_DISTINCT_CAPTURE_TIMESTAMPS = 20
ODDS_LAST_CONFIRMED_AT = 2026-08-03T06:55:28Z
WITHIN_WINDOW_QUOTE_ROWS = 0
MOVEMENT_STATUS_INSUFFICIENT = 64
```

All last-known quotes were captured on 2026-08-03, before the R2-B observation
window. They are reference-only baseline context and must not be counted as
within-window temporal evidence.

Pre-window descriptive overround context:

| Competition | Market | Fixtures | Timestamp count | Distinct bookmakers | Mean overround | Range |
|---|---|---:|---:|---:|---:|---:|
| allsvenskan | AH | 2 | 2 | 2 | 0.073422 | 0.055556–0.091288 |
| allsvenskan | OU | 2 | 2 | 2 | 0.086184 | 0.081081–0.091288 |
| brasileirao_serie_a | AH | 8 | 8 | 3 | 0.092592 | 0.036269–0.234990 |
| brasileirao_serie_a | OU | 8 | 8 | 3 | 0.063175 | 0.055556–0.084656 |
| chinese_super_league | AH | 7 | 7 | 4 | 0.066672 | 0.042374–0.095899 |
| chinese_super_league | OU | 7 | 7 | 4 | 0.070866 | 0.049934–0.089991 |
| eliteserien | AH | 3 | 3 | 2 | 0.061552 | 0.047149–0.089926 |
| eliteserien | OU | 3 | 3 | 3 | 0.063427 | 0.044735–0.089991 |

These figures are descriptive only. They are not a readiness conclusion,
percentile threshold, value signal or information score. Bookmaker counts are
distinct names across the league-market snapshot, not per-fixture depth claims.

Missing-field counts across the 64 cards:

```text
lineups = 64
ratings = 64
team_value = 64
xg = 60
odds = 44
market = 43
```

Local workspace database check:

```text
PATH = .local/w2.db
LAST_MODIFIED = 2026-07-20T10:09:39+0800
competitions = 0
fixtures = 0
odds_observations = 0
future_market_observation = 0
provider_request_logs = 0
raw_payload = 0
league_readiness_audit = 0
LOCAL_DB_TEMPORAL_EVIDENCE = INSUFFICIENT
```

Snapshot status:

```text
R2_B_WINDOW_COMPLETE = false
R2_B_TEMPORAL_EVIDENCE_STATUS = OPEN_ZERO_WITHIN_WINDOW_QUOTE_ROWS
FINAL_17_ROW_CAPABILITY_MATRIX = NOT_DUE
PROMOTION_AUTHORIZED = false
```

### Public readiness and timeline inventory

Additional read-only endpoints inspected during the same snapshot:

```text
GET /v1/leagues
GET /v1/leagues/{competition_id}/readiness for all 17 audit IDs
GET /v1/data-health
GET /v1/providers/status
GET /v1/fixtures/{fixture_id}/odds-timeline for one fixture per displayed league
```

```text
PUBLIC_LEAGUE_READINESS_ROWS = 5
PUBLIC_LEAGUE_READINESS_404_ROWS = 12
PUBLIC_READINESS_EXISTING_WHITELIST_ROWS = 5
PUBLIC_READINESS_AUDIT_ONLY_ROWS = 0
PUBLIC_RESULTS_READY_ROWS = 5
PUBLIC_AH_MISSING_ROWS = 5
PUBLIC_OU_PARTIAL_ROWS = 5
PUBLIC_TIMELINE_MISSING_ROWS = 5
PUBLIC_READINESS_MANUAL_REVIEW_ROWS = 5
DATA_HEALTH_STATUS = SYSTEM_DEGRADED
DATA_HEALTH_REASON = DATA_HEALTH_PROJECTION_NOT_READY
PROVIDER_STATUS = SYSTEM_DEGRADED
PROVIDER_CREDENTIAL_STATUS = UNKNOWN
PROVIDER_REMAINING_QUOTA = null
PROVIDER_STATUS_BLOCKER = PROVIDER_STATUS_PROJECTION_NOT_READY
SAMPLED_ODDS_TIMELINES = 4
SAMPLED_ODDS_TIMELINES_WITH_ITEMS = 0
```

The five readiness rows were limited to `premier_league`, `la_liga`,
`bundesliga`, `serie_a` and `ligue_1`. Their rollover payloads contained
synthetic-pattern team identifiers such as `<competition>-<season>-home-<n>` and
empty retained-team sets. They therefore cannot prove real Provider identity,
team or fixture capability for Round 2.

The DayView showed four different existing leagues whose readiness endpoints
returned 404. This is a truthful read-model coverage mismatch, not evidence that
those leagues are absent from the runtime whitelist.

```text
PUBLIC_READ_MODEL_COVERAGE_STATUS = MISMATCHED_AND_INSUFFICIENT
PUBLIC_READINESS_PROVENANCE_STATUS = NOT_ACCEPTABLE_AS_REAL_CAPABILITY_PROOF
WITHIN_WINDOW_TIMELINE_ITEMS_OBSERVED = 0
```
