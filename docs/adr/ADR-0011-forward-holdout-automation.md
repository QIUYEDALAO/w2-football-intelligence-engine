# ADR-0011: Forward Holdout Automation

## Status

Accepted for Stage 7D. Real autorun and real networking remain disabled pending approval.

## Context

Stage 7B froze the national challenger and future holdout protocol. Stage 7C added a manually
operated forward cycle for lock audit, result settlement, market comparability, and Gate 4 power
tracking. Stage 7D adds the automation foundation needed to run that cycle safely later, without
starting live scheduling in this stage.

## Decision

W2 will model forward holdout operations as a small state machine plus an idempotent cycle service.
The cycle supports discovery, T-24h/T-1h phase locking, market snapshot capture, result settlement,
evaluation, and Gate audit reporting. The implementation is dry-run first:

- `W2_FORWARD_HOLDOUT_AUTORUN=false`
- `W2_FORWARD_HOLDOUT_NETWORK=false`
- no real Celery Beat entry is enabled by default
- unknown quota stops conservatively
- 401, 403, and 429 open a circuit breaker
- locked predictions are append-only and cannot be overwritten
- result events are append-only and idempotent

The persisted operational layer is additive:

- `forward_cycle_checkpoint`
- `forward_scheduler_run`
- `forward_state_transition`
- `forward_operational_alert`

## Consequences

The forward holdout process can be rehearsed and monitored without consuming API quota or creating
timed jobs. Gate 4 remains `PROVISIONAL_FORWARD_HOLDOUT_PENDING` until future holdout settlement
reaches the pre-registered sample and stability criteria. Stage 9 remains blocked.

No training, tuning, candidate generation, or recommendation generation is introduced.
