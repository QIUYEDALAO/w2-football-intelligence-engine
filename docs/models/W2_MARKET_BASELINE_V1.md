# W2 Market Baseline V1

Stage 6 creates a market baseline, not a recommendation engine.

## Inputs

- Stage 5B national 1X2 rows: `UNKNOWN_PREMATCH_AGGREGATE`.
- W1 World Cup historical OU rows: `CLOSING`.
- Stage 4B live smoke snapshot: functional validation for AH and bookmaker coverage.

## Components

- `MarketConsensusBuilder`: bookmaker filtering, weights, staleness, dispersion, outliers, coherence.
- Devig methods: proportional, Shin-style, power, and logarithmic normalization.
- OU ladder fitter: least-squares fit of total-goal `mu` from all available lines.
- Dixon-Coles market baseline: 1X2 plus OU ladder to home/away scoring rates and a score matrix.
- Market quality: liquidity, bookmaker coverage, freshness, dispersion, conflict.

## Outputs

- 1X2 log loss, RPS, Brier, ECE, reliability bins, and strata.
- OU line residuals and aggregate fit error.
- Derived 1X2, OU, AH, BTTS, and exact-score log score.
- Market quality status: `READY`, `WATCH_ONLY`, or `BLOCKED`.

No output from this layer is a recommendation.
