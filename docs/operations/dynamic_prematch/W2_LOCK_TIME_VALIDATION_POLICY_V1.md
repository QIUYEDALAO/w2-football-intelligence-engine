# W2 Lock-Time Validation Policy V1

The only validation snapshot is selected around kickoff minus 30 minutes with a ±5-minute tolerance. Selection uses time proximity, capture time and capture ID only—never EV or best price. Incomplete, stale, unfrozen, outside-window and post-kickoff observations are rejected. Persistence permits one active validation snapshot per fixture.

Result: `LOCK_TIME_VALIDATION_PASS`. This is a validation snapshot contract; recommendation lock remains disabled.
