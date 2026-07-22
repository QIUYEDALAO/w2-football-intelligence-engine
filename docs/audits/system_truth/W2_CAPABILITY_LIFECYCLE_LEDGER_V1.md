# W2_CAPABILITY_LIFECYCLE_LEDGER_V1

- Generated at: `2026-07-20T12:51:47.425145Z`
- Audit SHA: `94ba834559c0beba5b38075bd358a8e92a434a51`
- Provider calls: `0`
- DB writes: `0`
- Final state: `MANUAL_APPROVAL_REQUIRED`

区分代码存在、数据具备、测试通过、已部署、已启用、可公开。

## Capabilities

| capability | code_exists | data_ready | deployed | enabled | publicly_available | blockers |
| --- | --- | --- | --- | --- | --- | --- |
| fixture_discovery | True | False | NOT_VERIFIED | NO | NO | P0-PROVIDER-INTAKE-SPLIT |
| checkpoint_policy | True | False | NOT_VERIFIED | NO | NO | P0-CHECKPOINT-AUTHORITY-SPLIT |
| endpoint_capture | True | True | NOT_VERIFIED | NO | NO | PROVIDER_CANARY_PENDING |
| historical_F5 | True | False | NOT_VERIFIED | NO | NO | W2_RUNTIME_F5_NOT_READY, W2_CANONICAL_IMPORT_NOT_EXECUTED |
| F8_team_value | True | False | NOT_VERIFIED | NO | NO | REVIEWED_ASOF_AUTHORITY_NOT_PROVEN |
| LMM_lineups | True | True | NOT_VERIFIED | NO | NO | UNLOCK_NOT_APPROVED |
| formal_AH | True | False | NOT_VERIFIED | NO | NO | CAPABILITY_DISABLED, HUMAN_APPROVAL_MISSING |
| recommendation_V3 | True | False | NOT_VERIFIED | NO | NO | LEGACY_STATE_SURFACES_ACTIVE |
| lock | True | False | NOT_VERIFIED | NO | NO | REQUIRES_FORMAL_RECOMMEND, LOCK_UNLOCK_NOT_APPROVED |
| settlement | True | False | NOT_VERIFIED | NO | NO | DECISION_HASH_BINDING_NOT_PROVEN |
| Dashboard_projection | True | False | NOT_VERIFIED | NO | NO | DASHBOARD_V3_SINGLE_SOURCE_NOT_PROVEN |
