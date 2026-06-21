# ADR-0007: Independent Probability Models

## Status

Accepted for W2 Stage 7.

## Context

Stage 6 established market baselines. Stage 7 needs odds-free independent models so W2 can compare
football probabilities against market benchmarks without contaminating the core model with market
inputs.

## Decision

W2 adds an independent modeling layer under `src/w2/models`.

- National and club tracks use separate parameter state.
- Core features are produced strictly as-of from previous matches.
- Odds, market probabilities, lines, prices, and bookmaker fields are forbidden by a static allowlist.
- Calibration is selected on validation only; test is evaluated once.
- Market residual research is isolated from independent model training and is never named as a
  recommendation signal.
- AH remains `BLOCKED_FORWARD_ONLY`.

## Consequences

Gate 4 can close only when an independent national model beats the Stage 6 market benchmark with
paired bootstrap support, no leakage, no calibration degradation, and no concentration in a small
slice. Otherwise the result remains `PROVISIONAL_NOT_PROMOTED`.
