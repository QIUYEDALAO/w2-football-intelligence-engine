# W2_AUTHORITY_MAP_V3

- source_review_sha: `94ba834559c0beba5b38075bd358a8e92a434a51`
- audit_generator_sha: `22391c8a961bc94ee7dd748858d23e244e97827a`
- audit_output_commit_sha: `PENDING_COMMIT`
- artifact_sha: `c6360d455b530287ce767ac2e53191ea58594f717f3d5b304321b04e6f44ca72`
- generated_at: `2026-07-20T13:40:59.001913Z`
- finding_refs: `P0-DATA-ASSET-REGISTRY-MISSING, P0-PROVIDER-INTAKE-SPLIT, P0-CHECKPOINT-AUTHORITY-SPLIT, P0-RECOMMENDATION-STATE-SPLIT, P0-F5-RUNTIME-DATA-MISSING, P0-F8-RUNTIME-DATA-MISSING`

## Summary

- core_concept_count: `48`
- p0_count: `6`
- active_canonical: `5`
- active_compatibility: `37`
- conflicting_authority: `3`

## Entries

- `fixture_discovery`: `ACTIVE_COMPATIBILITY` refs=[]
- `team_identity`: `ACTIVE_COMPATIBILITY` refs=[]
- `player_identity`: `ACTIVE_COMPATIBILITY` refs=[]
- `competition_policy`: `ACTIVE_COMPATIBILITY` refs=[]
- `checkpoint_policy`: `CONFLICTING_AUTHORITY` refs=['P0-CHECKPOINT-AUTHORITY-SPLIT']
- `scheduler_dispatch`: `ACTIVE_COMPATIBILITY` refs=[]
- `celery_task`: `ACTIVE_COMPATIBILITY` refs=[]
- `provider_request`: `CONFLICTING_AUTHORITY` refs=['P0-PROVIDER-INTAKE-SPLIT']
- `endpoint_capture`: `ACTIVE_COMPATIBILITY` refs=[]
- `raw_payload`: `ACTIVE_COMPATIBILITY` refs=[]
- `odds_observation`: `ACTIVE_COMPATIBILITY` refs=[]
- `market_observation`: `ACTIVE_COMPATIBILITY` refs=[]
- `canonical_ah`: `ACTIVE_COMPATIBILITY` refs=[]
- `canonical_ou`: `ACTIVE_COMPATIBILITY` refs=[]
- `quote_identity`: `ACTIVE_CANONICAL` refs=[]
- `quote_freshness`: `ACTIVE_COMPATIBILITY` refs=[]
- `collection_freshness`: `ACTIVE_COMPATIBILITY` refs=[]
- `market_selection`: `ACTIVE_CANONICAL` refs=[]
- `market_probability`: `ACTIVE_COMPATIBILITY` refs=[]
- `model_probability`: `ACTIVE_COMPATIBILITY` refs=[]
- `analysis_direction`: `ACTIVE_COMPATIBILITY` refs=[]
- `market_movement`: `ACTIVE_COMPATIBILITY` refs=[]
- `lineup_policy`: `ACTIVE_CANONICAL` refs=[]
- `injury_policy`: `ACTIVE_COMPATIBILITY` refs=[]
- `xg_enrichment`: `ACTIVE_COMPATIBILITY` refs=[]
- `F5`: `DATA_DEPENDENCY_MISSING` refs=['P0-F5-RUNTIME-DATA-MISSING']
- `F8`: `DATA_DEPENDENCY_MISSING` refs=['P0-F8-RUNTIME-DATA-MISSING']
- `factor_registry`: `ACTIVE_CANONICAL` refs=[]
- `formal_readiness`: `ACTIVE_CANONICAL` refs=[]
- `formal_recommendation`: `ACTIVE_COMPATIBILITY` refs=[]
- `recommendation_decision_v3`: `CONFLICTING_AUTHORITY` refs=['P0-RECOMMENDATION-STATE-SPLIT']
- `recommendation_projection`: `ACTIVE_COMPATIBILITY` refs=[]
- `recommendation_identity`: `ACTIVE_COMPATIBILITY` refs=[]
- `lock`: `ACTIVE_COMPATIBILITY` refs=[]
- `settlement`: `ACTIVE_COMPATIBILITY` refs=[]
- `performance_cohort`: `ACTIVE_COMPATIBILITY` refs=[]
- `dashboard_projection`: `ACTIVE_COMPATIBILITY` refs=[]
- `api_read_model`: `ACTIVE_COMPATIBILITY` refs=[]
- `frozen_artifact`: `ACTIVE_COMPATIBILITY` refs=[]
- `tracking`: `ACTIVE_COMPATIBILITY` refs=[]
- `calibration`: `ACTIVE_COMPATIBILITY` refs=[]
- `baseline_prior`: `ACTIVE_COMPATIBILITY` refs=[]
- `team_value`: `ACTIVE_COMPATIBILITY` refs=[]
- `registered_roster`: `ACTIVE_COMPATIBILITY` refs=[]
- `data_asset_registry`: `DATA_DEPENDENCY_MISSING` refs=['P0-DATA-ASSET-REGISTRY-MISSING']
- `backup_restore`: `ACTIVE_COMPATIBILITY` refs=[]
- `script_registry`: `ACTIVE_COMPATIBILITY` refs=[]
- `config_flags`: `ACTIVE_COMPATIBILITY` refs=[]
