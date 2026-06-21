# Forward Holdout Host Requirements

Stage 7G audits whether the local or staging machine is actually capable of
running the forward holdout cycle continuously.

## Required Host Capabilities

- A persistent process host for scheduler and worker processes.
- A durable runtime directory for checkpoints, lock ledgers, market snapshots,
  result events, and request audit files.
- The W2 provider key injected through the approved environment variable only.
- Network access limited to the configured provider base URL.
- No system-level daemon is installed by Stage 7G.

## Continuity Signals

- Scheduler and worker PID are visible.
- Heartbeat is recent.
- `last_cycle`, `next_cycle`, checkpoint hash, and cycle hash advance over time.
- No-overlap lock prevents concurrent cycles.
- Retry records and errors are persisted as operational audit data.

## Current Policy

When no persistent scheduler host is available, the correct status is
`PERSISTENT_SCHEDULER_HOST_REQUIRED`. The cycle may still be run manually as a
controlled audit, but it must not be described as live autorun.

Stage 7G does not train, tune, update calibration, create candidates, or emit
recommendations.
