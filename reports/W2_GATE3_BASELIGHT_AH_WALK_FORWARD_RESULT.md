# W2 Gate3 Baselight AH Walk-Forward Result

Generated at: `2026-06-23T23:37:36Z`

STATUS=INSUFFICIENT_SAMPLE
EXTRACTION_METHOD=ODDS_DATE_WINDOW_THEN_MATCHES_METADATA_NO_JOIN
MICRO_BATCH_V3_STATUS=ODDS_DATE_WINDOW_PARTIAL_SAMPLE_INSUFFICIENT
SAMPLE_PATH=/Users/liudehua/.openclaw/workspace/w2_external_data/baselight_gate3_limited_ah/baselight_limited_ah.jsonl
SAMPLE_SHA256=001b422b53cdcb849c6ede39da1e8ec4eff79ab0cb1767b8ce078eaf053122e8
ROW_COUNT=2538
FIXTURE_COUNT=27
BOOKMAKER_COUNT=12
LINE_BUCKET_COUNT=17
COMPETITION_COUNT=18
FOLD_COUNT=5
candidate=false
formal_recommendation=false

## Result

The MCP probe remained healthy. Odds date-window v3 avoided joins and match_id odds filters, appended additional external sample rows, and improved coverage to 27 fixtures, 12 bookmakers, 17 line buckets, and 18 competitions. The sample still misses the >=500 fixture threshold, so Gate3 AH walk-forward remains insufficient.

## Remaining Blockers

- `BASELIGHT_LIMITED_AH_SAMPLE_TOO_SMALL`
- `BASELIGHT_MICRO_BATCH_PARTIAL_SAMPLE_INSUFFICIENT`
- `BASELIGHT_ODDS_DATE_WINDOW_PARTIAL_SAMPLE_INSUFFICIENT`

## Remaining Limitations

- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`
