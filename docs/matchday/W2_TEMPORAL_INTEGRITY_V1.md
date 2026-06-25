# W2 Temporal Integrity V1

Every valuation records:

- `source_snapshot_id`
- `source_captured_at`
- `source_phase`
- `kickoff_utc`
- `valuation_generated_at`
- `projector_generated_at`
- `locked_before_kickoff`
- `recomputed_after_kickoff`
- `temporal_status`

`source_captured_at` must be earlier than kickoff for prematch use. If the
valuation runs after kickoff using locked prematch data, it is marked
`POSTMATCH_RECOMPUTED_FROM_LOCKED_PREMATCH` and is not displayed as a current
actionable direction.
