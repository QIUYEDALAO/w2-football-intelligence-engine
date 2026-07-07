# W2 Daily Matchday V1

The daily matchday cycle discovers fixture snapshots for a target date, verifies
snapshot integrity, evaluates readiness, builds DecisionCard-shaped fixture
cards, and writes read-only reports or dry-run outputs unless a later approved
operation explicitly enables side effects.

The current product entrypoint is `w2-matchday`. It does not mean "production
deployment" by itself: provider calls, DB writes, scheduler loops, lock capture,
settlement, staging enablement, and production enablement all remain separate
approval gates.

Decision output follows Decision Contract V2:

- `ANALYSIS_PICK` is analysis-only and must be labelled `分析参考·非稳赢`.
- `RECOMMEND` is the only production-actionable tier.
- `WATCH`, `SKIP`, and `NOT_READY` must carry non-pick reasons, action, and next
  evaluation metadata.
- Dashboard, replay, audit, and reports render this upstream DecisionCard
  surface; they must not infer a different tier from legacy fields.

Fixture states include `UPCOMING_ELIGIBLE`, `PREMATCH_PHASE_PENDING`,
`PREMATCH_LOCKED`, `KICKED_OFF`, `SETTLEMENT_PENDING`, `SETTLED`,
`BLOCKED_DATA`, and `MISSED_PREMATCH_WINDOW`.

Every card includes 1X2, Asian handicap, totals, and BTTS rankings when those
markets exist in the source snapshot.
