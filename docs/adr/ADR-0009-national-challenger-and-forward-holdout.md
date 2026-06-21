# ADR-0009: National Challenger And Forward Holdout

## Status

Accepted for W2 Stage 7B.

## Decision

Stage 7B freezes the Stage 7/8 214-row test set as `AUDIT_ONLY`, builds a national challenger
manifest, and establishes a true forward holdout protocol. The frozen audit set cannot be used for
tuning, method choice, feature choice, or promotion.

Gate 4 remains pending until future locked predictions accumulate completed results under the frozen
protocol.

## Consequences

Stage 9 remains blocked. Stage 7B may produce `NOT_READY`, `SKIP`, or `WATCH` decisions only. It
does not generate candidates or recommendations.
