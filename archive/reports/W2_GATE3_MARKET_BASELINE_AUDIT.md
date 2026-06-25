# W2 Gate3 Market Baseline Closure Audit

Generated at: `2026-06-25T00:00:00Z`

## Decision

Gate3 status remains `PARTIAL`.

Stage6 implementation is complete as a market-analysis layer, but Gate3 is a production readiness gate. Baselight limited AH evidence now resolves the historical AH baseline/walk-forward blocker. Gate3 still does not close because Baselight is `DATE_ONLY`, precise intraday phase claims remain unavailable, 1X2 prices are `UNKNOWN_PREMATCH_AGGREGATE`, OU evidence is a limited `CLOSING` subset, and Baselight export/retention policy remains unverified.

## Scope And Boundaries

- No provider calls were made.
- No API quota was consumed.
- No deployment, restart, migration, model tuning, strategy threshold tuning, candidate output, or formal recommendation output was performed.
- `docs/W2_MASTER_ROADMAP.md` was not modified.

## Requirement Audit

### G3-1-1X2_CONSENSUS_DEVIG_REPRODUCIBLE

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_1X2_BACKTEST.json`, `src/w2/markets/devig.py`, `src/w2/markets/consensus.py`
- Metrics: `{"devig_methods": ["LOGARITHMIC", "POWER", "PROPORTIONAL", "SHIN"], "method_selection_policy": "train_validation_only_test_final_report", "sample_count": 1074, "selected_method": "POWER", "test_brier": 0.484818, "test_ece": 0.059862, "test_log_loss": 0.817356, "test_rps": 0.156605}`
- Limitations: 1X2 source semantics are UNKNOWN_PREMATCH_AGGREGATE, so this supports aggregate or closing-like baseline only, not early phase market movement.
- Blockers: None
### G3-2-AH_CONSENSUS_PRICING_SETTLEMENT

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_MARKET_QUALITY.json`, `src/w2/markets/poisson.py`, `src/w2/domain/odds.py`, `reports/W2_STAGE5B_MARKET_COVERAGE.json`, `reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json`, `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json`, `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md`
- Metrics: `{"historical_ah_fabricated": false, "historical_ah_status": "BASELIGHT_LIMITED_WALK_FORWARD_PASS", "historical_build_status": "PASS_LIMITED_WALK_FORWARD", "baselight_fixture_count": 502, "baselight_fold_count": 5, "baselight_bookmaker_count": 13, "baselight_line_bucket_count": 17, "baselight_competition_count": 42, "matrix_pricing_available": true, "quarter_settlement_available": true}`
- Limitations: AH mechanics are implemented and functionally validated; historical AH walk-forward is supported by Baselight limited `DATE_ONLY` sample. Intraday phase and exact closing claims remain unsupported.
- Blockers: None
### G3-3-OU_CONSENSUS_DEVIG_REPRODUCIBLE

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_OU_BACKTEST.json`, `src/w2/markets/devig.py`, `src/w2/markets/poisson.py`
- Metrics: `{"fit_failures": 0, "lines_used": ["0.5", "1.5", "2.5", "3.5", "4.5"], "sample_count": 128, "snapshot_semantics": "CLOSING"}`
- Limitations: OU evidence is a W1 historical World Cup closing subset, not a multi-phase captured-at dataset.
- Blockers: None
### G3-4-COMPLETE_OU_LADDER_FITTING_BACKTEST

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_OU_BACKTEST.json`, `scripts/run_stage6_market_backtest.py`
- Metrics: `{"ab_winner": "MEDIAN_LINE", "fit_failures": 0, "fixture_diagnostic_count": 128, "ladder_mean_absolute_under25_error": 0.491762, "median_line_mean_absolute_under25_error": 0.485559, "sample_count": 128}`
- Limitations: Ladder implementation and residual reports exist; A/B result does not establish broader production readiness because evidence is limited to closing World Cup subset.
- Blockers: None
### G3-5-STRICT_SPLIT_OR_WALK_FORWARD_EVIDENCE

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_1X2_BACKTEST.json`, `reports/W2_STAGE6_OU_BACKTEST.json`, `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json`, `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md`
- Metrics: `{"one_x_two_split_policy": "chronological_plus_walk_forward", "ou_walk_forward": {"fold_count": 96, "initial_train_size": 32}, "ah_walk_forward_status": "PASS_LIMITED_WALK_FORWARD", "baselight_fixture_count": 502, "baselight_fold_count": 5, "baselight_bookmaker_count": 13, "baselight_line_bucket_count": 17, "baselight_competition_count": 42}`
- Limitations: 1X2 and OU have split/walk-forward evidence under their documented source semantics; AH walk-forward is supported by Baselight limited `DATE_ONLY` sample. Captured-at phase backtest limitations are tracked under G3-6.
- Blockers: None
### G3-6-DATA_SOURCE_AND_SNAPSHOT_SEMANTICS_CLEAR

- Status: `PARTIAL`
- Evidence: `reports/W2_STAGE6_1X2_BACKTEST.json`, `reports/W2_STAGE6_OU_BACKTEST.json`, `reports/W2_STAGE5B_MARKET_COVERAGE.json`, `docs/adr/ADR-0006-market-baseline.md`
- Metrics: `{"closing_odds_not_used_for_early_phase": true, "one_x_two_snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE", "ou_snapshot_semantics": "CLOSING"}`
- Limitations: Semantics are explicit but insufficient to close a production gate for early phase market movement. Baselight `DATE_ONLY` precision cannot support T-1h/T-30m/T-10m or exact closing timestamp claims, and export/retention policy remains unverified.
- Blockers: UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS, CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS, CAPTURED_AT_PHASE_BACKTEST_RESULTS_MISSING, BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE, PRECISE_PHASE_COVERAGE_UNAVAILABLE, EXPORT_AND_RETENTION_POLICY_UNVERIFIED
### G3-7-REPRODUCIBLE_RESULTS

- Status: `PASS`
- Evidence: `scripts/run_stage6_market_backtest.py`, `scripts/check_w2_stage6_market.py`, `reports/W2_STAGE6_1X2_BACKTEST.json`, `reports/W2_STAGE6_OU_BACKTEST.json`
- Metrics: `{"api_quota_used": 0, "network_used": false, "stage6_checker": "PASS under make verify"}`
- Limitations: Reproducibility depends on checked-in W2 reports and read-only W1 historical source paths captured by Stage5B manifests.
- Blockers: None
### G3-8-LEAKAGE_GUARDS

- Status: `PASS`
- Evidence: `reports/W2_STAGE5B_MARKET_COVERAGE.json`, `docs/markets/W2_MARKET_MOVEMENT_FEATURES_V1.md`, `src/w2/markets/movement.py`
- Metrics: `{"closing_odds_not_used_for_early_phase": true, "non_captured_at_guard": ["MOVEMENT_DISABLED_FOR_NON_CAPTURED_AT"]}`
- Limitations: Leakage guards pass for the audited reports; they do not replace missing captured-at historical market coverage.
- Blockers: None
### G3-9-NO_RECOMMENDATION_OR_INDEPENDENT_ADVANTAGE_CLAIM

- Status: `PASS`
- Evidence: `reports/W2_STAGE6_RESULT.md`, `reports/W2_STAGE6_MARKET_QUALITY.json`, `docs/adr/ADR-0006-market-baseline.md`
- Metrics: `{"candidate": false, "formal_recommendation": false, "recommendation_output": false}`
- Limitations: None
- Blockers: None

## Closure Rule Evaluation

Gate3 cannot be `CLOSED` while any of the following remains true:

- Historical AH Baselight limited walk-forward passed: `true`.
- Stage4B single forward snapshot is no longer the only AH market validation: `false`.
- 1X2 semantics are `UNKNOWN_PREMATCH_AGGREGATE`: `true`.
- OU semantics are `CLOSING` subset only: `true`.
- Baselight intraday timestamp precision is unavailable: `true`.
- Baselight export/retention policy is unverified: `true`.
- Recommendation output is disabled: `true`.

## WARN_ONLY

- `CALIBRATION_REQUIRED`
- `STAGE4B_MARKET_MOVEMENT_SAMPLE_ONLY`
- `OU_CLOSING_SUBSET_ONLY`
- `ONE_X_TWO_UNKNOWN_PREMATCH_AGGREGATE`
- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`

## BLOCKER

- `CAPTURED_AT_PHASE_BACKTEST_RESULTS_MISSING`
- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `CLOSING_ONLY_HISTORICAL_OU_BACKTEST_LIMITATION`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`

## Recommendation

Keep Master Phase 6 implementation evidence as `COMPLETE`, but keep Gate3 as `PARTIAL`. Historical AH blockers are resolved by Baselight limited walk-forward evidence; do not allow Gate3 closure until retained `DATE_ONLY`, precise phase, OU closing-subset, 1X2 aggregate, and export/retention limitations are resolved and all mandatory requirements pass closure mode.


## Historical Market Evidence Build Update

Generated at: `2026-06-23T17:01:02Z`

The historical market build discovered and normalized existing internal/W1 market assets without provider calls or runtime mutation.

- Source inventory: `reports/W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json`
- Phase coverage: `reports/W2_GATE3_PHASE_COVERAGE.json`
- AH walk-forward: `reports/W2_GATE3_AH_WALK_FORWARD.json`
- Build result: `reports/W2_GATE3_HISTORICAL_MARKET_BUILD_RESULT.md`

Results:

- Source count: `55`
- Captured-at phase coverage status: `CAPTURED_AT_AVAILABLE`
- Closing leakage into early phases: `0`
- AH walk-forward status: `NO_USABLE_INTERNAL_HISTORICAL_AH_DATA`
- Gate3 status after build: `PARTIAL`

The build resolves the earlier lack of captured-at market coverage inventory, but it does not close Gate3 because captured-at observations do not yet have sufficient settled phase-specific backtest evidence and historical AH remains without usable settled internal data.

## Baselight Closure Reconciliation

Generated at: `2026-06-25T00:00:00Z`

Baselight limited AH evidence has since reached the minimum sample thresholds
for an AH historical walk-forward reconciliation:

- Extract manifest:
  `reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json`
- Walk-forward result:
  `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json`
- Human-readable result:
  `reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD_RESULT.md`
- Rows: `72082`
- Fixtures: `502`
- Folds: `5`
- Bookmakers: `13`
- Line buckets: `17`
- Competitions: `42`
- Candidate: `false`
- Formal recommendation: `false`

Resolved blockers:

- `HISTORICAL_AH_BASELINE_BACKTEST_MISSING`
- `AH_WALK_FORWARD_EVIDENCE_MISSING`
- `EXTERNAL_HISTORICAL_AH_SOURCE_DECISION_REQUIRED`

Retained blockers:

- `CAPTURED_AT_PHASE_BACKTEST_RESULTS_MISSING`
- `CLOSING_ONLY_HISTORICAL_OU_BACKTEST_LIMITATION`
- `BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE`
- `PRECISE_PHASE_COVERAGE_UNAVAILABLE`
- `EXPORT_AND_RETENTION_POLICY_UNVERIFIED`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`

Checker expectations:

- Audit mode: `PASS`
- Closure mode: expected failure while Gate3 remains `PARTIAL` with retained
  limitations.
