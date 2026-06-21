# ADR-0006: Market Baseline And Analysis Layer

## Status

Accepted for W2 Stage 6.

## Context

Stage 6 needs a market-derived benchmark before any recommendation or staking layer exists. The
available historical data has mixed semantics: Stage 5B national 1X2 prices are
`UNKNOWN_PREMATCH_AGGREGATE`, W1 OU rows are `CLOSING`, and Stage 4B provides one real captured
snapshot for functional validation.

## Decision

W2 implements a standalone market layer under `src/w2/markets`.

- Bookmaker consensus is configurable and reports input quality instead of fabricating consensus.
- Devig supports `PROPORTIONAL`, `SHIN`, `POWER`, and `LOGARITHMIC` through one interface.
- Stage 5B national 1X2 is used only as an aggregate or closing-like market baseline.
- W1 historical OU closing rows use full ladder fitting and are compared to the old median-line
  shortcut.
- Dixon-Coles style Poisson baselines are market reproduction tools only. W1 rho remains a reference
  candidate, not an asserted independent advantage.
- AH historical backtest status is `FORWARD_ONLY`; Stage 4B validates only parsing, settlement, and
  matrix pricing mechanics.
- Movement features are enabled only for `CAPTURED_AT`; thresholds remain `CALIBRATION_REQUIRED`.

## Consequences

Stage 6 can report market reproduction residuals, market quality, and movement diagnostics without
creating `RECOMMEND`. Test data is not used for method selection. No network calls or API quota are
allowed in this stage.
