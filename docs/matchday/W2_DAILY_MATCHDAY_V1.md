# W2 Daily Matchday V1

The daily matchday cycle discovers fixture snapshots for a target date, verifies
snapshot integrity, builds full-market research cards, and writes read-only
reports. It never trains, tunes, or emits recommendations.

Fixture states include `UPCOMING_ELIGIBLE`, `PREMATCH_PHASE_PENDING`,
`PREMATCH_LOCKED`, `KICKED_OFF`, `SETTLEMENT_PENDING`, `SETTLED`,
`BLOCKED_DATA`, and `MISSED_PREMATCH_WINDOW`.

Every card includes 1X2, Asian handicap, totals, and BTTS rankings when those
markets exist in the source snapshot.
