# W2 Stage 6 Result

STAGE_6=COMPLETED
GATE_3=MARKET_BASELINE_ONLY
RECOMMENDATION_OUTPUT=false
NETWORK_USED=false
API_QUOTA_USED=0
HISTORICAL_AH=FORWARD_ONLY
THRESHOLDS=CALIBRATION_REQUIRED
PUSH_BLOCKED_NO_ORIGIN

WARN_ONLY:

- CALIBRATION_REQUIRED
- HISTORICAL_AH_FORWARD_ONLY
- STAGE4B_MARKET_MOVEMENT_SAMPLE_ONLY

BLOCKER:

- None

Notes:

- Stage 6 builds market baselines and market quality diagnostics only.
- UNKNOWN_PREMATCH_AGGREGATE and CLOSING sources are not used for phase movement backtests.
- No recommendation, staking, model edge, or AI output was generated.
