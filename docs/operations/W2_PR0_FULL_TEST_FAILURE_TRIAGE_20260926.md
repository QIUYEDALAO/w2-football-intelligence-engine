# PR-0 全量测试失败归因（2026-09-26）

工作分支 `codex/w2-authority-20260916`；起点 `b5fb9ece` 是当前 HEAD
`42a6e60b` 的祖先。此回执只处理本地测试，不代表发布或生产验收。

## 结论与证据边界

- 首轮 33 失败清单来自本任务连续执行时记录的失败摘要；首轮完整原始日志未保留。下表中两项新增失败的原因由代码和当时失败信息定位，不能把首轮摘要当成一份仍可重新读取的原始日志。
- `42a6e60b` 提交后的全量命令 `.venv/bin/python -m pytest -q --tb=short` 返回 **31 failed, 4021 passed, 67 skipped, 2 warnings**；提交回执后的最终复跑同样返回该结果。本地日志分别为 `/tmp/w2_pr0_pytest_20260926.txt` 和 `/tmp/w2_pr0_pytest_20260926_final.txt`，后者保存最终 31 项失败列表。
- 09-23 登记基线的分组计数由 Owner 提供：0051 迁移 24、staging runtime 2、SC18 等 5。当前逐项归因与这三个分组吻合；没有拿到 09-23 的原始节点 ID 清单，因此“逐条与旧日志完全同名”不能独立宣称已核验。
- 首轮多出的 **2 项已消失**。两项均非 09-23 基线；当前失败集为 31。未修改、跳过或放宽任何基线失败测试。

## 33 项逐项归因与基线对照

表中 `B` 表示归入 Owner 登记的 31 项基线分组，`N` 表示本次新增。迁移组的 24 项均在 SQLite Alembic `upgrade head` 时止于 `0051_apply_seven_day_collection_policy.py:30`：预期更新 14 行，实际更新 28 行，抛出 `COLLECTION_POLICY_UPDATE_COUNT_INVALID:28`；因此后续测试目的尚未执行到，不应解释成各自断言的业务失败。

| # | 测试（文件::测试名） | 归类 | 失败原因 |
|---:|---|:---:|---|
| 1 | `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking` | B | 子进程调用裸 `python`，当前 PATH 找不到该命令，`FileNotFoundError`。 |
| 2 | `tests/contract/test_src_w2_package_matrix.py::test_matrix_callers_entrypoints_and_classifications_are_complete` | B | 包矩阵声明 `tests:49`，实际扫描 `tests:48`，`direct_callers` 不符。 |
| 3 | `tests/integration/test_eval_01a_migration.py::test_0045_schema_and_fixture_identity_constraints` | B | 0051 迁移计数异常。 |
| 4 | `tests/integration/test_eval_01a_migration.py::test_0045_empty_downgrade_and_reupgrade` | B | 0051 迁移计数异常。 |
| 5 | `tests/integration/test_eval_01a_migration.py::test_0045_nonempty_downgrade_fails_closed` | B | 0051 迁移计数异常。 |
| 6 | `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid` | B | Docker 创建的目录在宿主路径不可见，预检返回 `MISSING`，预期为 `TARGET_UID_GID_CANNOT_WRITE`。 |
| 7 | `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime` | B | 同一目录映射问题，预检返回 `MISSING`，预期可写。 |
| 8 | `tests/integration/test_migrations.py::test_alembic_upgrade_and_downgrade_smoke` | B | 0051 迁移计数异常。 |
| 9 | `tests/integration/test_migrations.py::test_0060_projects_canonical_fixture_id_without_rewriting_capture` | B | 0051 迁移计数异常。 |
| 10 | `tests/integration/test_migrations.py::test_0061_versions_known_capture_batches_without_rewriting_payload` | B | 0051 迁移计数异常。 |
| 11 | `tests/integration/test_migrations.py::test_0052_drops_and_restores_empty_retired_checkpoint_plan` | B | 0051 迁移计数异常。 |
| 12 | `tests/integration/test_migrations.py::test_0052_refuses_nonempty_retired_checkpoint_plan` | B | 0051 迁移计数异常。 |
| 13 | `tests/integration/test_migrations.py::test_0053_backfills_reviewed_team_identity_and_retains_it` | B | 0051 迁移计数异常。 |
| 14 | `tests/integration/test_migrations.py::test_0054_backfills_and_database_guards_statistics_raw` | B | 0051 迁移计数异常。 |
| 15 | `tests/integration/test_migrations.py::test_0055_backfills_lead_time_without_mutating_ledger_payload_hashes` | B | 0051 迁移计数异常。 |
| 16 | `tests/integration/test_migrations.py::test_0053_rejects_partial_fixture_scope` | B | 0051 迁移计数异常。 |
| 17 | `tests/integration/test_migrations.py::test_arch_p1_01_drops_and_restores_system_metadata` | B | 0051 迁移计数异常。 |
| 18 | `tests/integration/test_migrations.py::test_arch_p1_01_drops_and_restores_all_evidence_backed_dead_tables` | B | 0051 迁移计数异常。 |
| 19 | `tests/integration/test_migrations.py::test_arch_p1_01_drops_and_restores_empty_fk_components` | B | 0051 迁移计数异常。 |
| 20 | `tests/integration/test_migrations.py::test_staging_state_stage9a_head_upgrades_to_future_refresh_head` | B | 0051 迁移计数异常。 |
| 21 | `tests/integration/test_migrations.py::test_arch_p1_08_drops_and_restores_empty_shadow_strategy_tables` | B | 0051 迁移计数异常。 |
| 22 | `tests/integration/test_migrations.py::test_arch_p1_02_drops_the_legacy_table_when_every_row_is_covered` | B | 0051 迁移计数异常。 |
| 23 | `tests/integration/test_migrations.py::test_0042_team_identity_provider_review_provenance` | B | 0051 迁移计数异常。 |
| 24 | `tests/integration/test_migrations.py::test_0043_drops_and_downgrade_recreates_legacy_identity_schema` | B | 0051 迁移计数异常。 |
| 25 | `tests/integration/test_migrations.py::test_0042_downgrade_keeps_transfermarkt_rows_it_does_not_own` | B | 0051 迁移计数异常。 |
| 26 | `tests/integration/test_migrations.py::test_0042_downgrade_keeps_foreign_row_that_existed_before_upgrade` | B | 0051 迁移计数异常。 |
| 27 | `tests/integration/test_migrations.py::test_0042_downgrade_keeps_unowned_row_with_matching_id_and_hash` | B | 0051 迁移计数异常。 |
| 28 | `tests/integration/test_migrations.py::test_0042_backfills_only_the_selected_valid_ready_authority_rows` | B | 0051 迁移计数异常。 |
| 29 | `tests/unit/test_analysis_card_xg_materialized.py::test_analysis_card_uses_materialized_xg_and_market_snapshots` | B | 卡片 `markets[*].reasons` 中未找到测试要求的 `F9_TRUE_XG:AS_OF_ROLLING_XG_DIFF`。 |
| 30 | `tests/unit/test_api_dashboard_day_view.py::test_intelligence_workspace_validation_is_lazy_and_excludes_replay` | N | Validation 响应新增 `validation_signals`，但 `extra="forbid"` 的 Pydantic 响应模型起初未声明它，导致响应校验失败。 |
| 31 | `scripts/quant/tests/test_f1r_b_production_factor_persistence.py::test_07_the_wiring_did_not_touch_a_forbidden_path` | N | 此测试读取 `git status --porcelain`；当时 API/strategy 等授权修改尚未提交，工作树脏路径被旧任务的禁改路径断言拦截。提交后工作树干净，测试通过。 |
| 32 | `scripts/quant/tests/test_f1r_b_production_recording_integration.py::test_03_the_version_authority_matches_the_executed_builder` | B | F5 `recent_ah_cover_factor` 当前源码 SHA256 与冻结的 builder 版本绑定不符。 |
| 33 | `scripts/quant/tests/test_f1r_b_production_recording_integration.py::test_19_the_pinned_builder_sources_are_still_the_frozen_f1_evidence` | B | `src/w2/features/team_factors.py` 当前 SHA256 与 F1 冻结源码哈希不符。 |

## 新增失败的处理 diff

1. `42a6e60b` 中 `src/w2/api/schemas.py` 给 `DashboardIntelligenceValidationResponse` 加入 `validation_signals: dict[str, Any] = Field(default_factory=dict)`，与 `src/w2/api/routers.py` 的新响应字段对齐。响应模型仍为 `extra="forbid"`；未放宽校验。
2. `42a6e60b` 将此前工作区改动提交在原分支；`test_07` 的工作树守卫在干净状态下不再把 API/strategy 授权改动误作未提交越界。该测试及其禁改路径规则未改动。

本 PR-0 回执没有对 31 项登记基线失败做伪修复或调整断言。后续若要清除基线失败，需单独判断迁移数据权威、Docker 文件共享路径、冻结 F1 哈希及其他合同的预期版本。
