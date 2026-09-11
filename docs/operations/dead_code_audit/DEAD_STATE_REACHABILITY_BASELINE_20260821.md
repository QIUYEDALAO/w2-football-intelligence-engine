# Dead-state reachability baseline — 2026-08-21

## Status

`PENDING_PRODUCTION_COVERAGE_WINDOW` until `2026-08-28T04:37:34Z`.

This phase intentionally does not remove enum members, status branches, schema constraints, or rendering labels. The active coverage window provides execution evidence; final reachability still requires static writer/transition analysis and Owner-intent review.

## Production baseline

Measured at `2026-08-21 04:39:38+00` on release `eab6dca7997a21a215b9929a3ac2a7365cf27631`:

- official opportunity states: `BLOCKED_BY_GATE=9`, `EVALUATED_CANDIDATE=49`, `EVALUATED_NO_EDGE=54`, `MISSED_CHECKPOINT=66`;
- official opportunities / attempts: `178 / 112`;
- checkpoint plan states measured before activation: `CAPTURED=696`, `FAILED=140`, `MISSED=133143`, `PLANNED=40443`, `PROVIDER_EMPTY=142`;
- public measurement status: `MEASURABLE`;
- invalid official binding, invalid latest-attempt binding, and cross-opportunity supersession: all `0`.

These values are a timestamped baseline, not a list of all reachable states. Absence from this snapshot is not evidence of deadness.

## Domains to resolve after the window

| Domain | Evidence to combine | Removal threshold |
|---|---|---|
| Matchday checkpoint plan states | coverage, repository transition graph, migration constraints, production distributions | No writer/transition/caller, no persisted row, no operational recovery meaning |
| Official opportunity states | coverage, opportunity writer transaction paths, plan-to-opportunity cardinality | No natural or authoritative MISSED path can emit the state |
| Evaluation and gate outcomes | coverage contexts, gate policy registry, persisted `original_state`/gate evidence | No enabled policy path can emit it; disabled future capability resolved by Owner |
| Candidate notification states | coverage, outbox transition methods, delivery audit | No producer or recovery transition and no retained delivery obligation |
| Outcome-ledger run states | coverage, run-state compare-and-set transitions, retry/recovery rules | No forward or recovery transition and no compatibility requirement |
| Capability and public measurement labels | coverage, capability manifest, API rendering contracts | Capability retired or label proven unreachable across enabled modes |

## Required final artifacts

1. Per-state matrix: definition, writer, transition predecessors/successors, capability owner, persisted row count, covered call sites, and classification.
2. `REACHABLE`, `DISABLED_BUT_RETAINED`, `RECOVERY_ONLY`, `STATIC_DEAD_CANDIDATE`, or `OWNER_DECISION_REQUIRED` classification for every state value.
3. Exact coverage raw-file manifest and combined JSON/HTML report hashes.
4. A deletion proposal only for state values that satisfy both dynamic and static criteria; no automatic schema or code deletion.
