# Empty-table classification — 2026-08-21

## Scope and evidence

- Authority: production VPS database, schema `0069_outcome_ledger_run_state`.
- Measurement clock: `2026-08-21 03:59:04.913344+00` (database UTC).
- Result: 27 empty tables out of 71 public base tables; their allocated size is 768 KiB.
- Static evidence: migrations, ORM models, repository write methods, non-test call sites, capability manifest, and foreign keys at local HEAD `742d547adc8107aeacbf1388d5eae0dac5fd109a`.
- This document is an inventory, not deletion authorization. “Static dead candidate” still requires migration replay and the production coverage window before removal.

## Classification summary

| Class | Count | Meaning |
|---|---:|---|
| Static dead candidate | 11 | No non-test constructor or writer call path found; superseded by current authorities. |
| Pending activation | 5 | A real writer exists and is reachable through an event-driven or manual capability that is intentionally not always exercised. |
| Owner decision required | 11 | Retention depends on a future/formal capability or on reconnect-versus-retire product intent. |

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
| `forward_market_snapshot` | None outside migrations/tests/model declaration | Replaced by matchday market observations and current projection | Static dead candidate |
| `ingestion_runs` | None outside migrations/tests/model declaration | Replaced by provider request/quota ledgers and current run-state authorities | Static dead candidate |
| `model_runs` | None outside migrations/tests/model declaration | Replaced by `model_forecast_*` authorities | Static dead candidate |
| `predictions` | None outside migrations/tests/model declaration | Replaced by dynamic evaluations / official opportunity-attempt ledger | Static dead candidate |

The legacy chain remains internally connected by foreign keys, but no current non-test code constructs rows for any table in that chain. It must be retired as one dependency-aware migration, not as isolated table drops.

## Pending activation

| Table | Real write path | Capability owner / trigger | Current conclusion |
|---|---|---|---|
| `matchday_checkpoint_plan_reschedules` | `src/w2/matchday/repository.py` writes a reschedule audit row during checkpoint-plan upsert | Matchday Scheduler; only when a redatable fixture kickoff changes | Retain: rare event-driven writer |
| `team_value_asof_artifacts` | `scripts/materialize_team_value_asof.py --write` → `FahDataFoundationRepository.write_team_value_artifacts` | `lineup_value_enrichment`; feature enabled, public/production disabled | Retain: manual materialization path |
| `stage7i_lifecycle_run` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |
| `stage7i_lifecycle_heartbeat` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |
| `stage7i_lifecycle_event` | `src/w2/monitoring/stage7i_supervision.py` | Stage 7I manual operations / observer | Retain: manual operations ledger |

## Owner decision required

| Table | Existing write surface | Capability owner / blocker | Decision needed |
|---|---|---|---|
| `historical_market_source_snapshots` | Repository import method in `src/w2/historical/fah_repository.py`; no non-test caller found | Private/manual FAH import; formal AH disabled | Keep for an approved import, or retire with the historical AH pair |
| `canonical_historical_ah_facts` | Repository import method in `src/w2/historical/fah_repository.py`; no non-test caller found | Private/manual FAH import; formal AH disabled | Keep for an approved import, or retire with source snapshots |
| `registered_roster_snapshots` | Repository import writer exists; no non-test caller found | Future roster provenance / team-value enrichment | Reconnect an importer, or retire |
| `player_club_membership_observations` | Repository import writer exists; no non-test caller found | Future roster provenance / team-value enrichment | Reconnect an importer, or retire |
| `gate_a_run_reservations` | Connected one-shot canary path in `src/w2/operations/gate_a.py` | Signed or Owner-authorized Gate A run only | Retain the governed canary, or formally retire Gate A |
| `gate_a_provider_calls` | Connected one-shot canary path in `src/w2/operations/gate_a.py` | Signed or Owner-authorized Gate A run only | Retain the governed canary, or formally retire Gate A |
| `gate5_recommendation_lock_event` | `src/w2/strategy/lock_ledger.py` | `recommendation_lock` disabled | Retain for future lock activation, or retire |
| `recommendations` | No current marker writer found | Formal recommendation capability disabled | Retain future formal chain, or retire it as a unit |
| `recommendation_locks` | Lock snapshot writers exist but require a formal recommendation marker | Formal/lock capabilities disabled | Retain future formal chain, or retire it as a unit |
| `settlements` | Guarded settlement path exists and requires explicit confirmation | Formal/lock/settlement capabilities disabled | Retain future formal chain, or retire it as a unit |
| `t30_validation_snapshots` | `freeze_t30_snapshot()` exists in `src/w2/prematch/repository.py`; no non-test caller found | T-30 is active through the newer official opportunity/evaluation path | Reconnect the snapshot contract, or retire this superseded table |

## Dependency notes

- `fixtures` is referenced by the legacy `predictions`, `recommendations`, and lock chain; deletion order must follow the foreign-key graph.
- `canonical_historical_ah_facts` depends on `historical_market_source_snapshots`.
- `gate_a_provider_calls` depends on `gate_a_run_reservations`; `future_refresh_task_audit` also has an inbound optional reference to Gate A reservations and must be proven null before any migration.
- `matchday_checkpoint_plan_reschedules` depends on `matchday_checkpoint_plans` and is not a dead-table candidate.

## Exit criteria before any drop migration

1. Seven-day production coverage window completes and is archived with exact release/digest and timestamps.
2. Migration replay passes from an empty database and from a production-shaped backup.
3. Foreign-key and application-reference scans are rerun at the exact migration HEAD.
4. Owner resolves every row in “Owner decision required”.
5. Backup/restore drill and rollback migration are documented; no existing raw, capture, outcome, opportunity, or attempt data is modified.
