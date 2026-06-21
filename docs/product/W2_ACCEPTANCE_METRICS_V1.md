# W2 Acceptance Metrics V1

Model metrics: Log Loss, Ranked Probability Score, Brier Score, Expected Calibration Error, Reliability Curve, Exact Score Log Score, Incremental Log Loss vs Market, Incremental RPS vs Market, calibration by competition/market/phase.

Strategy metrics: Candidate Coverage, Recommendation Coverage, Skip Rate, Watch-to-Recommend Conversion, Closing Line Value, stability by competition/market/odds band/phase, maximum consecutive misses, fixed-unit drawdown, post-recommendation market direction, threshold sensitivity.

System metrics: provider request success, ingestion success, freshness, task failure, quota utilization, latency, lock success, result sync completeness, fixture mapping conflicts, duplicate odds observations, closing snapshot coverage, reproducibility pass rate.

Hard invariants are not calibration thresholds: no prematch leakage, complete provenance for locked cards, deterministic card hash for same input/version, immutable raw payloads, failed recommendations retained, postmatch cannot alter prematch probability, no forced recommendations, RECOMMEND requires counterargument and invalidation conditions. Edge, hit rate, CLV, odds, bookmaker count, and promotion deltas are CALIBRATION_REQUIRED.
