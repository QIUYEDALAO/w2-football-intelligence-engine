# W2 Lineup Value Features V1

The pipeline compares confirmed XI with the as-of expected XI, including role-specific replacement deltas, continuity, formation/position disruption, captain/goalkeeper changes and mapping/valuation coverage. Future valuations are excluded, and unresolved replacements return `ROLE_REPLACEMENT_UNRESOLVED` rather than zero.

Result: `LINEUP_CHANGE_FEATURES_PASS`. Model effect remains advisory: AH, totals and lambda adjustments are all `0.0`.
