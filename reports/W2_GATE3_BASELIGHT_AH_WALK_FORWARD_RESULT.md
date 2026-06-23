# W2 Gate3 Baselight AH Walk-Forward Result

Generated at: `2026-06-23T22:58:13Z`

STATUS=INSUFFICIENT_SAMPLE
EXTRACTION_METHOD=MATCH_SEED_PLUS_ODDS_MICRO_BATCH_NO_JOIN
MICRO_BATCH_V2_STATUS=BASELIGHT_SINGLE_FIXTURE_QUERY_PENDING
SAMPLE_PATH=/Users/liudehua/.openclaw/workspace/w2_external_data/baselight_gate3_limited_ah/baselight_limited_ah.jsonl
SAMPLE_SHA256=3fb354f40dd286652ded0f703e01575f8c66924774c53dfebf055a89ad599edb
ROW_COUNT=750
FIXTURE_COUNT=15
BOOKMAKER_COUNT=4
LINE_BUCKET_COUNT=11
COMPETITION_COUNT=15
FOLD_COUNT=5
candidate=false
formal_recommendation=false

## Result

The MCP probe remained healthy, but Baselight micro-batch v2 could not expand beyond the existing external sample. Matches seed queries completed, while the first single-fixture AH odds query remained pending/timeout under bounded polling. The external sample remains insufficient for Gate3 AH closure.

## Remaining Blockers

- `BASELIGHT_LIMITED_AH_SAMPLE_TOO_SMALL`
- `BASELIGHT_BOOKMAKER_COVERAGE_INSUFFICIENT`
- `BASELIGHT_MICRO_BATCH_PARTIAL_SAMPLE_INSUFFICIENT`
- `BASELIGHT_SINGLE_FIXTURE_QUERY_PENDING`

## Remaining Limitations

- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`
