# W2 Gate3 Market Baseline Closure Audit

Generated at: `2026-06-23T16:41:27Z`

## Decision

Gate3 status remains `PARTIAL`.

Stage6 implementation is complete as a market-analysis layer, but Gate3 is a production readiness gate. The audited evidence does not close Gate3 because historical AH baseline/backtest evidence is absent, 1X2 prices are `UNKNOWN_PREMATCH_AGGREGATE`, OU evidence is a limited `CLOSING` subset, and movement thresholds remain `CALIBRATION_REQUIRED`.

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

- Status: `PARTIAL`
- Evidence: `reports/W2_STAGE6_MARKET_QUALITY.json`, `src/w2/markets/poisson.py`, `src/w2/domain/odds.py`, `reports/W2_STAGE5B_MARKET_COVERAGE.json`
- Metrics: `{"historical_ah_fabricated": false, "historical_ah_status": "FORWARD_ONLY", "matrix_pricing_available": true, "quarter_settlement_available": true}`
- Limitations: AH mechanics are implemented and functionally validated, but historical AH dataset/backtest is absent and remains FORWARD_ONLY.
- Blockers: HISTORICAL_AH_BASELINE_BACKTEST_MISSING
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

- Status: `PARTIAL`
- Evidence: `reports/W2_STAGE6_1X2_BACKTEST.json`, `reports/W2_STAGE6_OU_BACKTEST.json`
- Metrics: `{"one_x_two_split_policy": "chronological_plus_walk_forward", "ou_walk_forward": {"fold_count": 96, "initial_train_size": 32}}`
- Limitations: 1X2 and OU have split/walk-forward evidence; AH historical baseline has no backtest.
- Blockers: AH_WALK_FORWARD_EVIDENCE_MISSING
### G3-6-DATA_SOURCE_AND_SNAPSHOT_SEMANTICS_CLEAR

- Status: `PARTIAL`
- Evidence: `reports/W2_STAGE6_1X2_BACKTEST.json`, `reports/W2_STAGE6_OU_BACKTEST.json`, `reports/W2_STAGE5B_MARKET_COVERAGE.json`, `docs/adr/ADR-0006-market-baseline.md`
- Metrics: `{"closing_odds_not_used_for_early_phase": true, "one_x_two_snapshot_semantics": "UNKNOWN_PREMATCH_AGGREGATE", "ou_snapshot_semantics": "CLOSING"}`
- Limitations: Semantics are explicit but insufficient to close a production gate for early phase market movement or historical AH.
- Blockers: UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS, CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS
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

- Historical AH baseline/backtest does not exist: `true`.
- Stage4B single forward snapshot is the only AH market validation: `true`.
- 1X2 semantics are `UNKNOWN_PREMATCH_AGGREGATE`: `true`.
- OU semantics are `CLOSING` subset only: `true`.
- Movement thresholds require calibration: `true`.
- Recommendation output is disabled: `true`.

## WARN_ONLY

- `CALIBRATION_REQUIRED`
- `STAGE4B_MARKET_MOVEMENT_SAMPLE_ONLY`
- `OU_CLOSING_SUBSET_ONLY`
- `ONE_X_TWO_UNKNOWN_PREMATCH_AGGREGATE`

## BLOCKER

- `AH_WALK_FORWARD_EVIDENCE_MISSING`
- `CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS`
- `HISTORICAL_AH_BASELINE_BACKTEST_MISSING`
- `UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS`

## Recommendation

Keep Master Phase 6 implementation evidence as `COMPLETE`, but keep Gate3 as `PARTIAL`. Do not allow Gate3 closure until historical AH and broader as-of market evidence are available and all mandatory requirements pass closure mode.


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
