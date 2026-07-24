# W2_SIMPLIFICATION_PLAN_V1

Generated at: 2026-07-20T12:51:47.425145Z  
Historical audit provenance: Git commit `22391c8`
State: `MANUAL_APPROVAL_REQUIRED`

## Gate

The generated V1 matrix referenced by the original plan exited Git under
`ARCH-HYGIENE-01`. Current gates and completion evidence are maintained in
`docs/operations/architecture_convergence/W2_ARCHITECTURE_CONVERGENCE_MASTER_CHECKLIST.md`.

## Consolidation A: scheduling, checkpoints, provider intake

1. Prove all runtime provider calls and scheduler tasks can route through `MatchdayEndpointCaptureV1`.
2. Make `config/policies/matchday_intake.v2.json` the only active checkpoint source.
3. Remove or hard-disable fallback checkpoint constants and obsolete `matchday_schedule.v1` semantics.
4. Add regression tests proving missed checkpoints are never backfilled and late captures stay unscheduled.
5. Run one approved staging read-only canary after source cleanup.

## Consolidation B: market, model evidence, recommendation state

1. Make `RecommendationDecisionV3.decision_hash` the single identity for API, Dashboard, frozen artifact, tracking and reporting.
2. Demote legacy `WATCH/SKIP` and reporting `FORMAL/LOCKED` states to display-only projections.
3. Ensure market probability is labelled as market baseline, not independent model evidence.
4. Keep `ANALYSIS_PICK` analysis-only and never lock-eligible.

## Consolidation C: F5/F8 and historical data

1. Add durable `W2DataAssetRegistryV1` implementation.
2. Add encrypted/object-store second copy for Football-Data private assets.
3. Execute restore drill: restore into test root, recompute SHA, rebuild identical manifest.
4. Import reviewed F5 facts into canonical runtime query path.
5. Select one reviewed as-of F8 authority and demote static snapshots.

## Consolidation D: scripts, config, docs, DB legacy

1. Classify every script as operational, audit, migration-only, one-time recovery, unsafe-without-approval, legacy or dead.
2. Remove obsolete env switches after replacement tests prove fail-closed behavior.
3. Bind each DB table to writer, reader, natural key, content hash, idempotency and retention.
4. Remove stale tracked generated outputs after source-of-truth reports replace them.

## Acceptance

- Every core concept has exactly one `ACTIVE_CANONICAL` authority.
- Every compatibility layer has a deletion condition.
- Provider, formal, lock and production cannot be enabled by one switch.
- Historical data assets have registry, hash, backup and restore proof.
- Runtime deployment SHA is captured and compared against source review SHA.
