# W2 Gate3 Baselight AH Walk-Forward Result

Generated at: `2026-06-24T02:20:00Z`

STATUS=PASS_LIMITED_WALK_FORWARD
SAMPLE_PATH=/Users/liudehua/.openclaw/workspace/w2_external_data/baselight_gate3_limited_ah/baselight_limited_ah.jsonl
ROW_COUNT=72082
FIXTURE_COUNT=502
BOOKMAKER_COUNT=13
LINE_BUCKET_COUNT=17
COMPETITION_COUNT=42
FOLD_COUNT=5
SAMPLE_SHA256=eb493d9f67e7ac672d40a37ecb14efb615b307f8bb5152429338d9c27158831b
candidate=false
formal_recommendation=false

## Resolved By Limited Backtest

- `HISTORICAL_AH_BASELINE_BACKTEST_MISSING`
- `AH_WALK_FORWARD_EVIDENCE_MISSING`

## Boundary

- No full Baselight data is committed.
- External sample remains outside Git.
- DATE-only collected_at cannot support T-1h, T-30m, T-10m, intraday movement, or exact closing timestamp.
- Gate3 remains PARTIAL unless closure checkers pass without blockers.

## Remaining Limitations

- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`
