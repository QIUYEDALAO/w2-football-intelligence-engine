# A-150 Legacy AH Cleanup Execution Record

## Scope

- Runtime: 43.155.208.138
- Release SHA: f15f28c3c4af138339881864b03c1085fc9d60a0
- Operation: classify legacy non-full-time Asian Handicap rows out of the full-time AH mainline pool.
- Provider calls: 0
- Lock writes: 0
- Settlement writes: 0

## Backup

- Backup path: `/opt/w2/backups/a150_legacy_ah_cleanup_20260704T013314Z/staging_db.dump`
- Backup size: 185M
- SHA256: `b43252535022e88713f1b9353d68039b33c1472230199c0d721ad26ba0c4c89e`
- Migration plan path: `/opt/w2/backups/a150_legacy_ah_cleanup_20260704T013314Z/migration_plan.jsonl`
- Migration plan rows: 117901

## Table Touch List

Touched:

- `future_market_observation.canonical_market`

Not touched:

- `recommendation_locks`
- `settlements`
- `audit_events`

Rollback evidence:

- Original `raw_market_label` remains in `future_market_observation`.
- Migration plan preserves `observation_id`, prior `canonical_market`, raw label, target classification, bookmaker, selection, line, odds, captured_at, and provider_last_update.

## Write Reconciliation

Pre-write dry-run:

- scanned: 214595
- would_update: 117901
- ASIAN_HANDICAP: 96694
- CARDS_ASIAN_HANDICAP: 14472
- CORNERS_ASIAN_HANDICAP: 32494
- FIRST_HALF_ASIAN_HANDICAP: 70935

Write result:

- updated: 117901
- ASIAN_HANDICAP: 96694
- CARDS_ASIAN_HANDICAP: 14472
- CORNERS_ASIAN_HANDICAP: 32494
- FIRST_HALF_ASIAN_HANDICAP: 70935

Post-write dry-run:

- scanned: 96694
- would_update: 0
- updated: 0

## Sample Inspection

- Sample size: 50
- Mismatch count: 0
- Sample classes: CARDS_ASIAN_HANDICAP=8, CORNERS_ASIAN_HANDICAP=17, FIRST_HALF_ASIAN_HANDICAP=25

Note: the legacy half-period bucket name is `FIRST_HALF_ASIAN_HANDICAP`; it currently isolates both first-half and second-half AH labels out of the full-time AH pool.

## Materialization And Page Validation

Post-cleanup materialization:

- `window=today`, checkpoint `T-3h`, write_artifacts=true
- provider_calls: 0
- written: 6
- immutable_conflicts: 0
- Colombia vs Ghana AH line: -1.25

Public page validation:

- Renderer watermark: `w2.html_dashboard.v6` count 2
- Forbidden terms: 0
- Colombia vs Ghana visible with market line -1.25
- Argentina vs Cape Verde Islands visible with stale-mainline review marker
- Closing snapshot label visible

Audit export:

- status: PASS
- read_only: true
- provider_calls: 0
- db_writes: 0

