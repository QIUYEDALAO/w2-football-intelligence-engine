# ADR-0008: Event-Driven Backtest

## Status

Accepted for W2 Stage 8.

## Decision

W2 uses an event-driven replay engine for evaluation. The engine reads only as-of data, builds
features, loads fixed model and calibration versions, emits probability snapshots, and evaluates
after match completion. It does not run candidate generation, recommendation strategy, staking, or
live execution.

Replay decisions are restricted to `NOT_READY`, `SKIP`, and `WATCH`.

## Consequences

Replay outputs are deterministic and checkpointable. Gate 4 cannot be re-promoted using the Stage 7
214 test rows; only untouched future or nested walk-forward evidence can close it.
