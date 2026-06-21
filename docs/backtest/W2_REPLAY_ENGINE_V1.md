# W2 Replay Engine V1

The replay flow is:

1. Read data available at `event_time`.
2. Build features.
3. Load fixed model and calibration artifacts.
4. Generate probabilities.
5. Evaluate after result confirmation.
6. Write replay ledger and manifest hashes.

All times are UTC. Same-time events are ordered by sequence, fixture, type, and event id. Replays are
idempotent and checkpoint recovery must match a complete run.
