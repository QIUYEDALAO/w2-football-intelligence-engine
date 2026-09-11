# Empty-table classification — 2026-08-21

## Scope and evidence

- Authority: production VPS database, schema `0069_outcome_ledger_run_state`.
- Measurement clock: `2026-08-21 03:59:04.913344+00` (database UTC).
- Result: 27 empty tables out of 71 public base tables; their allocated size is 768 KiB.
- Static evidence: migrations, ORM models, repository read/write methods, non-test call sites, capability manifest, and foreign keys at local HEAD `c9e23864a1703b4cfc139dfd993369046cc66b74`.
- This document is an inventory, not deletion authorization. “Static dead candidate” still requires migration replay and the production coverage window before removal.

## Classification summary

| Class | Count | Meaning |
|---|---:|---|
| Static dead candidate | 11 | No non-test constructor or writer call path found; superseded by current authorities. Existing readers must still be retired with the table. |
| Pending activation | 5 | A real writer exists and is reachable through an event-driven or manual capability that is intentionally not always exercised. |
| Owner disposition recorded | 11 | Owner has resolved retain-versus-retire intent; all tables remain physically retained during the coverage window. |

## Static dead candidates

| Table | Write path found | Capability owner / replacement | Current conclusion |
|---|---|---|---|
| `competitions` | None outside migrations/tests/model declaration | Legacy relational fixture chain; replaced by `league_profile` / `league_season` | Static dead candidate |
| `seasons` | None outside migrations/tests/model declaration | Legacy relational fixture chain; replaced by `league_season` | Static dead candidate |
| `stages` | None outside migrations/tests/model declaration | Legacy relational fixture chain; current matchday identity is authoritative | Static dead candidate |
| `teams` | None outside migrations/tests/model declaration | Legacy relational fixture chain; replaced by `canonical_teams` | Static dead candidate |
| `venues` | None outside migrations/tests/model declaration | Legacy relational fixture chain | Static dead candidate |
| `referees` | None outside migrations/tests/model declaration | Legacy relational fixture chain | Static dead candidate |
| `fixtures` | None outside migrations/tests/model declaration | Legacy relational fixture chain; replaced by `matchday_fixture_identities` | Static dead candidate |
| `forward_market_snapshot` | No writer; `src/w2/audit_export/tables.py::_db_market_timeline_snapshots()` still reads it | Replaced by matchday market observations and current projection | Static dead candidate; a future retirement migration must remove or replace the audit-export reader in the same change |
| `ingestion_runs` | None outside migrations/tests/model declaration | Replaced by provider request/quota ledgers and current run-state authorities | Static dead candidate |
| `model_runs` | None outside migrations/tests/model declaration | Replaced by `model_forecast_*` authorities | Static dead candidate |
| `predictions` | None outside migrations/tests/model declaration | Replaced by dynamic evaluations / official opportunity-attempt ledger | Static dead candidate |

The legacy chain remains internally connected by foreign keys, but no current non-test code constructs rows for any table in that chain. It must be retired as one dependency-aware migration, not as isolated table drops.

Read-side recheck at `c9e23864`: `forward_market_snapshot` is the only one of these 11 tables with a non-test runtime reader. Exact ORM-class and raw-SQL scans found no corresponding reader for the other 10 tables; persistence-package re-exports are model registration, not row reads. This correction does not change the no-writer classification.

## Pending activation

| Table | Real write path | Capability owner / trigger | Current conclusion |
|---|---|---|---|
| `matchday_checkpoint_plan_reschedules` | `src/w2/matchday/repository.py` writes a reschedule audit row during checkpoint-plan upsert | Matchday Scheduler; only when a redatable fixture kickoff changes | Retain: rare event-driven writer |
| `team_value_asof_artifacts` | `scripts/materialize_team_value_asof.py --write` → `FahDataFoundationRepository.write_team_value_artifacts` | `lineup_value_enrichment`; feature enabled, public/production disabled | Retain: manual materialization path |
| `stage7i_lifecycle_run` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |
| `stage7i_lifecycle_heartbeat` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |
| `stage7i_lifecycle_event` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |

## Owner disposition recorded

| Table | Existing write surface | Capability owner / blocker | Owner disposition |
|---|---|---|---|
| `historical_market_source_snapshots` | Repository import method in `src/w2/historical/fah_repository.py`; no non-test caller found | Private/manual FAH import; formal AH disabled | Retain with the historical AH pair |
| `canonical_historical_ah_facts` | Repository import method in `src/w2/historical/fah_repository.py`; no non-test caller found | Private/manual FAH import; formal AH disabled | Retain with source snapshots |
| `registered_roster_snapshots` | Repository import writer exists; no non-test caller found | Future roster provenance / team-value enrichment | Retirement list after the coverage window; migrate only with the other dependency-aware retirements |
| `player_club_membership_observations` | Repository import writer exists; no non-test caller found | Future roster provenance / team-value enrichment | Retirement list after the coverage window; migrate only with the other dependency-aware retirements |
| `gate_a_run_reservations` | Connected one-shot canary path in `src/w2/operations/gate_a.py` | Signed or Owner-authorized Gate A run only | Retain the governed canary |
| `gate_a_provider_calls` | Connected one-shot canary path in `src/w2/operations/gate_a.py` | Signed or Owner-authorized Gate A run only | Retain the governed canary |
| `gate5_recommendation_lock_event` | `src/w2/strategy/lock_ledger.py` | `recommendation_lock` disabled | Retain with the formal recommendation chain |
| `recommendations` | No current marker writer found | Formal recommendation capability disabled | Retain with the formal recommendation chain |
| `recommendation_locks` | Lock snapshot writers exist but require a formal recommendation marker | Formal/lock capabilities disabled | Retain with the formal recommendation chain |
| `settlements` | Guarded settlement path exists and requires explicit confirmation | Formal/lock/settlement capabilities disabled | Retain with the formal recommendation chain |
| `t30_validation_snapshots` | `freeze_t30_snapshot()` exists in `src/w2/prematch/repository.py`; no non-test caller found | T-30 is active through the newer official opportunity/evaluation path | Retirement list after the coverage window; migrate only with the other dependency-aware retirements |

No table is dropped during the active coverage window. After the window closes, the two roster-provenance tables and `t30_validation_snapshots` may be handled together with the 11 static dead candidates in one dependency-aware migration; that future migration requires separate Owner authorization.

## Dependency notes

- `fixtures` is referenced by the legacy `predictions`, `recommendations`, and lock chain; deletion order must follow the foreign-key graph.
- `canonical_historical_ah_facts` depends on `historical_market_source_snapshots`.
- `gate_a_provider_calls` depends on `gate_a_run_reservations`; `future_refresh_task_audit` also has an inbound optional reference to Gate A reservations and must be proven null before any migration.
- `matchday_checkpoint_plan_reschedules` depends on `matchday_checkpoint_plans` and is not a dead-table candidate.

## Exit criteria before any drop migration

1. Seven-day production coverage window completes and is archived with exact release/digest and timestamps.
2. Migration replay passes from an empty database and from a production-shaped backup.
3. Foreign-key and application-reference scans are rerun at the exact migration HEAD.
4. The Owner dispositions recorded above are preserved; any future retirement migration receives separate authorization.
5. Backup/restore drill and rollback migration are documented; no existing raw, capture, outcome, opportunity, or attempt data is modified.
