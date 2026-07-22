# W2_CONFIG_FLAG_MATRIX_V1

- Generated at: `2026-07-20T12:51:47.425145Z`
- Audit SHA: `94ba834559c0beba5b38075bd358a8e92a434a51`
- Provider calls: `0`
- DB writes: `0`
- Final state: `MANUAL_APPROVAL_REQUIRED`

配置、环境变量和开关矩阵。Live staging 值未做 SSH/DB 读取，因此标记为未验证。

## Flags

| variable | default | staging_value | affects_capability | possible_duplicate_switch | fail_closed |
| --- | --- | --- | --- | --- | --- |
| CELERY_WORKER_CONCURRENCY | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_AI_RECOMMENDATION_CARD_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | recommendation_surface | none_identified_static | UNKNOWN |
| W2_AI_RECOMMENDATION_INPUT_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | recommendation_surface | none_identified_static | UNKNOWN |
| W2_AI_RECOMMENDATION_OUTPUT_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | recommendation_surface | none_identified_static | UNKNOWN |
| W2_AI_RECOMMENDATION_VALIDATION_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | recommendation_surface | none_identified_static | UNKNOWN |
| W2_CANDIDATE_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | recommendation_surface | none_identified_static | YES_STATIC |
| W2_CELERY_BROKER_URL | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_CELERY_RESULT_BACKEND | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_DATABASE_URL | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_DEEPSEEK_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | YES_STATIC |
| W2_DEEPSEEK_ROLE_BOUNDARY_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_FOOTBALL_DATA_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | historical_data_asset | none_identified_static | UNKNOWN |
| W2_FORMAL_DECISION_REVIEW_TEMPLATE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_FORMAL_RECOMMENDATION_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_FORMAL_RECOMMENDATION_P0 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_FORMAL_TRACKING_REPORT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | UNKNOWN |
| W2_FORWARD_OUTCOME_RUNTIME_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | singular/plural competition id switches coexist | UNKNOWN |
| W2_FUTURE_FIXTURE_REFRESH_COMPETITION_IDS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | singular/plural competition id switches coexist | UNKNOWN |
| W2_FUTURE_FIXTURE_REFRESH_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | provider_intake | none_identified_static | YES_STATIC |
| W2_FUTURE_REFRESH_PERSISTENCE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_GIT_SHA | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_LINEUP_MULTI_MARKET_EXECUTION_PLAN_20260719 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | lineup_market_model | none_identified_static | UNKNOWN |
| W2_LINEUP_POLICY_PATH | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | lineup_market_model | none_identified_static | UNKNOWN |
| W2_MARKET_TIMELINE_MAX_FIXTURES | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | UNKNOWN |
| W2_MARKET_TIMELINE_REFRESH_ENABLED | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | YES_STATIC |
| W2_MARKET_TIMELINE_REFRESH_INTERVAL_SECONDS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | UNKNOWN |
| W2_MARKET_TIMELINE_RUNTIME_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | UNKNOWN |
| W2_MARKET_TIMELINE_WINDOW | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | market_timeline | none_identified_static | UNKNOWN |
| W2_P2_RELEASE_GOVERNANCE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_PRODUCTION_RELEASE | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | deployment_release_identity | none_identified_static | YES_STATIC |
| W2_PROVIDER_CALLS_DISABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_DAILY_HARD_CAP | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_DAILY_RESERVE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_ENDPOINT_ALLOWLIST | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_HTTP_MAX_ATTEMPTS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_PREFLIGHT_MIN_REMAINING | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_REFRESH_BATCH_SIZE | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_REFRESH_TICK_HARD_CAP | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_REQUEST_LEDGER_ENABLED | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_SCHEDULER_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_PROVIDER_TASK_KEY_DEDUP_TTL_SECONDS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_R1_RELEASE_GATE_MANIFEST_20260718 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_R2_RELEASE_GATE_MANIFEST_20260718 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_R3_READONLY_RELEASE_GATE_MANIFEST_20260718 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_R3_READONLY_STAGING_CANDIDATE_20260718 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | recommendation_surface | none_identified_static | UNKNOWN |
| W2_READINESS_RELEASE_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_RECOMMENDATION_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | recommendation_surface | none_identified_static | YES_STATIC |
| W2_REDIS_URL | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_RELEASE_AND_ROLLBACK_V1 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_RELEASE_ID | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_RUNTIME | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_RUNTIME_F5 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | historical_data_asset | none_identified_static | UNKNOWN |
| W2_RUNTIME_F5_NOT_READY | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_RUNTIME_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_STAGE15A_RELEASE_READINESS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | deployment_release_identity | none_identified_static | UNKNOWN |
| W2_STAGE7C_LOCK_AUDIT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_STAGE7F_LOCK_AUDIT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_STAGE7I_GLOBAL_LOCK | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_STAGE7I_RUNTIME_ROOT | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | runtime_infrastructure | none_identified_static | UNKNOWN |
| W2_STAGING_PROVIDER_DATA | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | provider_intake | policy/env/scheduler gate may overlap | YES_STATIC |
| W2_V3_07_AH_FORMAL_EVIDENCE_20260720 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_V3_07_AH_FORMAL_EVIDENCE_INPUT_20260720 | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | formal_recommendation | capability_manifest/formal_ah_approval/env may overlap | YES_STATIC |
| W2_XG_BACKFILL_ENABLED | fail_closed_or_false_in_tests/compose; live value not verified | static compose/config only; live not verified | xg_enrichment | none_identified_static | YES_STATIC |
| W2_XG_BACKFILL_INTERVAL_SECONDS | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | xg_enrichment | none_identified_static | UNKNOWN |
| W2_XG_BACKFILL_RECENT_MATCHES | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | xg_enrichment | none_identified_static | UNKNOWN |
| W2_XG_BACKFILL_REQUEST_BUDGET | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | xg_enrichment | none_identified_static | UNKNOWN |
| W2_XG_HISTORY_BACKFILL | UNKNOWN_STATIC_SCAN | static compose/config only; live not verified | xg_enrichment | none_identified_static | UNKNOWN |

Flag rows rendered: 70 of 70. Full list is in JSON.
