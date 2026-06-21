# ADR-0010: Forward Holdout Operations

## Status

Accepted for W2 Stage 7C.

## Decision

Forward holdout operation runs a repeatable cycle: discover, lock eligible phases, settle completed
fixtures, evaluate, and report. It may synchronize provider results and captured market snapshots,
but it must not retrain, tune, or promote using the frozen Stage 7/8 audit set.

Gate 4 may stay pending, fail to outperform, or close only under the pre-registered future holdout
rules.

## Consequences

Stage 9 remains blocked unless Gate 4 is formally closed. Candidate and recommendation outputs are
forbidden.
