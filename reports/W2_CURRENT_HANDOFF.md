# W2 Football Intelligence Engine — Current Handoff

> **跨会话权威交接文件。** 新会话必须先读本文件，再规划、修改、部署或验收。
> 本文件只保留当前有效状态；详细历史以所引用的阶段报告和决策文件为准。

## 0. 机器可读摘要

```yaml
handoff_version: 41
handoff_correction: RELEASE_TRAIN_3A_R3B_RETRY_ROLLBACK_RECORDED
state_captured_on: 2026-06-25
handoff_operating_protocol_updated_on: 2026-07-20
handoff_operating_protocol: SOL_STAGE_PLAN_CODEX_EXECUTION_STAGE_REVIEW
project: W2 Football Intelligence Engine
workspace: /Users/liudehua/.openclaw/workspace/w2-football-intelligence-engine
legacy_project: W1
legacy_policy: frozen_read_only
master_roadmap_path: docs/W2_MASTER_ROADMAP.md
master_roadmap_version: 1
roadmap_status_path: reports/W2_ROADMAP_STATUS.json
roadmap_status_relation: current as of containing commit
active_stage_package: Release Train 3A-R3B staging retry deployment
active_execution_package: Release Train 3A-R3B staging retry deployment
execution_package_is_not_master_phase: true

gate0_status: PARTIAL
gate0_audit_path: reports/W2_GATE0_LEGACY_CLOSURE_AUDIT.md
gate0_manifest_path: reports/W2_GATE0_W1_SHA256_MANIFEST.json
gate0_classification_path: reports/W2_GATE0_W1_ASSET_CLASSIFICATION.json
gate0_blockers:
  - EXPECTED_W1_PATH_NOT_FOUND
  - W1_TAG_W1_LEGACY_FINAL_MISSING
  - W1_WORKTREE_NOT_CLEAN
  - W1_LEGACY_STATUS_UNTRACKED
  - W1_CURRENT_HEAD_DIFFERS_FROM_LEGACY_BASELINE_HEAD
  - FULL_W1_BACKUP_NOT_VERIFIED

gate3_status: PARTIAL
gate3_audit_path: reports/W2_GATE3_MARKET_BASELINE_AUDIT.md
gate3_decision_path: reports/W2_GATE3_MARKET_BASELINE_DECISION.json
gate3_historical_source_inventory_path: reports/W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json
gate3_phase_coverage_path: reports/W2_GATE3_PHASE_COVERAGE.json
gate3_ah_walk_forward_path: reports/W2_GATE3_AH_WALK_FORWARD.json
gate3_historical_build_result_path: reports/W2_GATE3_HISTORICAL_MARKET_BUILD_RESULT.md
gate3_historical_data_status: NO_USABLE_INTERNAL_HISTORICAL_AH_DATA
gate3_external_source_requirements_path: docs/data/W2_HISTORICAL_MARKET_SOURCE_REQUIREMENTS_V1.md
gate3_external_source_comparison_path: reports/W2_GATE3_EXTERNAL_SOURCE_COMPARISON.json
gate3_external_source_decision_path: reports/W2_GATE3_EXTERNAL_SOURCE_DECISION.md
gate3_external_source_status: FORWARD_ONLY_ACCUMULATION_SELECTED
gate3_acquisition_authorized: false
gate3_checker_mode: audit
gate3_data_route: FORWARD_ONLY_WITH_BASELIGHT_HISTORICAL_SUPPLEMENT
gate3_baselight_probe_status: CONDITIONAL_GATE3_CANDIDATE
gate3_baselight_observed_source: BASELIGHT_DATASET_VIA_MCP
gate3_baselight_settlement_validation: PASS
gate3_baselight_time_series_status: NO_REPEATED_ECONOMIC_KEY_ACROSS_DATES
gate3_baselight_license_status: DATASET_CC_BY_4_0_PLATFORM_EXPORT_UNVERIFIED
gate3_baselight_actual_query_completed: true
gate3_baselight_ai_schema_probe_path: reports/W2_GATE3_BASELIGHT_AI_SCHEMA_PROBE.json
gate3_baselight_odds_table: match_betting_odds
gate3_baselight_match_table: matches
gate3_baselight_settled_ah_fixture_count: 10858
gate3_baselight_collected_at_precision: DATE_ONLY
gate3_baselight_next_action: RETAIN_GATE3_PARTIAL_UNTIL_DATE_ONLY_PHASE_OU_1X2_EXPORT_LIMITATIONS_RESOLVE
gate3_baselight_limited_extract_status: ODDS_DATE_WINDOW_SAMPLE_READY
gate3_baselight_limited_extract_manifest_path: reports/W2_GATE3_BASELIGHT_LIMITED_AH_EXTRACT_MANIFEST.json
gate3_baselight_ah_walk_forward_status: PASS_LIMITED_WALK_FORWARD
gate3_baselight_ah_walk_forward_path: reports/W2_GATE3_BASELIGHT_AH_WALK_FORWARD.json
gate3_baselight_sample_sha256: eb493d9f67e7ac672d40a37ecb14efb615b307f8bb5152429338d9c27158831b
gate3_baselight_sample_row_count: 72082
gate3_baselight_sample_fixture_count: 502
gate3_baselight_sample_bookmaker_count: 13
gate3_baselight_sample_line_bucket_count: 17
gate3_baselight_sample_competition_count: 42
gate3_baselight_extraction_method: ODDS_DATE_WINDOW_THEN_MATCHES_METADATA_NO_JOIN
gate3_baselight_micro_batch_v3_status: PASS_LIMITED_WALK_FORWARD
gate3_baselight_mcp_probe_status: PASS
gate3_baselight_mcp_probe_path: reports/W2_BASELIGHT_MCP_PROBE.json
gate3_baselight_mcp_sql_tool_detected: true
gate3_baselight_mcp_sql_tool_name: baselight_sdk_query_execute
gate3_baselight_mcp_odds_limit_query_status: PASS
gate3_baselight_mcp_matches_limit_query_status: PASS
gate3_baselight_api_key_required: true
gate3_baselight_full_extract_status: NOT_STARTED
gate3_baselight_resolved_by_limited_backtest:
  - HISTORICAL_AH_BASELINE_BACKTEST_MISSING
  - AH_WALK_FORWARD_EVIDENCE_MISSING
gate3_ah_historical_status: BASELIGHT_LIMITED_WALK_FORWARD_PASS
gate3_ah_blockers_resolved:
  - HISTORICAL_AH_BASELINE_BACKTEST_MISSING
  - AH_WALK_FORWARD_EVIDENCE_MISSING
gate3_external_source_decision_blocker_resolved: true
gate3_closure_audit_checker: PASS
gate3_closure_checker: EXPECTED_FAIL_REMAINING_LIMITATIONS
gate3_closure_reconciliation_status: COMPLETED_PARTIAL_DECISION
gate3_baselight_remaining_limitations:
  - BASELIGHT_INTRADAY_TIMESTAMP_UNAVAILABLE
  - PRECISE_PHASE_COVERAGE_UNAVAILABLE
  - EXPORT_AND_RETENTION_POLICY_UNVERIFIED
  - CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS
  - UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS

stage7i_status: BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP
stage7i_final_observation_audit_path: reports/W2_STAGE7I_FINAL_OBSERVATION_AUDIT.md
stage7i_final_observation_decision_path: reports/W2_STAGE7I_FINAL_OBSERVATION_DECISION.json
stage7i_final_reconciliation_path: reports/W2_STAGE7I_FINAL_AUDIT_RECONCILIATION.md
stage7i_successor_fixture_id: 1489404
stage7i_successor_kickoff_utc: 2026-06-23T17:00:00Z
stage7i_successor_runtime_dir: /opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404
stage7i_successor_started_at_utc: 2026-06-23T09:59:44.331436Z
stage7i_successor_expected_end_utc: 2026-06-24T09:59:44.331436Z
stage7i_successor_run_status: BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP
stage7i_final_observer_historical_pid: 1435421
stage7i_final_observer_historical_pgid: 1435396
stage7i_final_observer_process_alive_after_window: false
stage7i_final_observer_completed_marker: true
stage7i_final_observer_summary_exists: true
stage7i_final_observer_completed_at_utc: 2026-06-24T10:01:11.955864Z
stage7i_final_observer_sample_count: 289
stage7i_final_observer_coverage_seconds: 86487.295089
stage7i_final_observer_max_gap_seconds: 300.338218
stage7i_final_observer_revision_stable: true
stage7i_final_lifecycle_collector_active: false
stage7i_final_lifecycle_gap: true
stage7i_historical_lifecycle_blocker: STAGE7I_LIFECYCLE_COLLECTOR_INACTIVE
stage7i_final_lifecycle_fixture_evidence_count: 1
stage7i_final_lifecycle_market_evidence_count: 2
stage7i_final_lifecycle_result_evidence_count: 0
stage7i_final_lifecycle_request_audit_count: 7
stage7i_final_actual_kickoff_status: ACTUAL_KICKOFF_SOURCE_UNAVAILABLE
stage7i_final_actual_kickoff_utc: null
stage7i_final_closing_status: PENDING_ACTUAL_KICKOFF
stage7i_final_closing_observation_utc: null
stage7i_final_result_status: MISSING
stage7i_final_settlement_evaluation_status: NOT_RUN_NO_RESULT
stage7i_final_shadow_db_audit: PENDING
stage7i_final_checker_result: FAIL
stage7i_final_checker_blocker: final status must be COMPLETED
stage7i_final_gate5_eligible: false
stage7i_recovery_or_successor_requires_explicit_approval: true

server_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
alembic_head: 0017_create_stage9a_shadow_strategy
deployment_freeze: ACTIVE
release_train_3a_deployment_record_path: reports/W2_RELEASE_TRAIN_3A_DEPLOYMENT.json
release_train_3a_result_path: reports/W2_RELEASE_TRAIN_3A_RESULT.md
release_train_3a_status: ROLLED_BACK_CONTRACT_FAILURE
release_train_3a_target_revision: fcfba08824f42917d30bc8d0742ea99d2fc18349
release_train_3a_previous_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_failure: FUTURE_REFRESH_SCHEDULER_DISPATCH_DISABLED
release_train_3a_rollback_completed: true
release_train_3a_post_rollback_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_migration_executed: false
release_train_3a_stage10e_deployed: false
release_train_3a_stage7i_successor_started: false
release_train_3a_env_content_read: false
release_train_3a_repair_result_path: reports/W2_RELEASE_TRAIN_3A_REPAIR_RESULT.md
release_train_3a_repair_status: IMPLEMENTED_PENDING_RETRY_DEPLOYMENT
release_train_3a_repair_root_cause: STAGING_SCHEDULER_ENABLE_FLAG_NOT_WIRED
release_train_3a_repair_paths:
  - infra/compose/compose.staging.yml
  - infra/compose/staging-lite.override.yml
future_refresh_scheduler_enablement: EXPLICIT_STAGING_ONLY
release_train_3a_r1_deployment_record_path: reports/W2_RELEASE_TRAIN_3A_R1_DEPLOYMENT.json
release_train_3a_r1_result_path: reports/W2_RELEASE_TRAIN_3A_R1_RESULT.md
release_train_3a_r1_status: ROLLED_BACK_CONTRACT_FAILURE
release_train_3a_r1_target_revision: 2d80e04b52af2b6ec957c554968c2c60a3a0cec0
release_train_3a_r1_failure: FUTURE_REFRESH_POLICY_INVALID
release_train_3a_r1_rollback_completed: true
release_train_3a_r1_post_rollback_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r1_dispatch_status: NOT_ATTEMPTED_HEALTH_CONTRACT_FAILED
release_train_3a_r1_task_audit_status: NOT_CREATED
release_train_3a_r2_repair_result_path: reports/W2_RELEASE_TRAIN_3A_R2_REPAIR_RESULT.md
release_train_3a_r2_repair_status: IMPLEMENTED_PENDING_RETRY_DEPLOYMENT
release_train_3a_r2_repair_root_cause: VERSIONED_POLICY_NOT_AVAILABLE_IN_STAGING_CONTAINERS
release_train_3a_r2_repair_policy_mount_target: /app/config/policies
release_train_3a_r2_repair_policy_mount_mode: read_only
release_train_3a_r2_repair_scheduler_worker_policy_mount: true
release_train_3a_r2_repair_api_web_policy_mount: false
release_train_3a_r2_repair_static_checker: PASS
release_train_3a_r2_repair_targeted_tests: PASS
release_train_3a_r2_repair_staging_revision_unchanged: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r2_deployment_record_path: reports/W2_RELEASE_TRAIN_3A_R2_DEPLOYMENT.json
release_train_3a_r2_result_path: reports/W2_RELEASE_TRAIN_3A_R2_RESULT.md
release_train_3a_r2_status: ROLLED_BACK_CONTRACT_FAILURE
release_train_3a_r2_target_revision: 371a9cb8618e7f47324e6ea9a2c9be35ca63199e
release_train_3a_r2_previous_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r2_policy_contract_ready: true
release_train_3a_r2_dispatch_status: QUEUED
release_train_3a_r2_manual_tick_called: false
release_train_3a_r2_worker_registered_task: true
release_train_3a_r2_worker_task_status: FAILED_PERMISSION_DENIED
release_train_3a_r2_task_audit_status: NOT_CREATED
release_train_3a_r2_failure: FUTURE_REFRESH_RUNTIME_PERMISSION_DENIED
release_train_3a_r2_runtime_mount_source: /opt/w2/releases/371a9cb8618e7f47324e6ea9a2c9be35ca63199e/infra/compose/runtime
release_train_3a_r2_runtime_mount_permissions: drwxr-xr-x root root
release_train_3a_r2_rollback_completed: true
release_train_3a_r2_post_rollback_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r2_post_rollback_health: PASS
release_train_3a_r3_repair_result_path: reports/W2_RELEASE_TRAIN_3A_R3_REPAIR_RESULT.md
release_train_3a_r3_repair_status: IMPLEMENTED_PENDING_RETRY_DEPLOYMENT
release_train_3a_r3_root_cause: STANDALONE_COMPOSE_RUNTIME_SOURCE_RESOLVED_INSIDE_INFRA_COMPOSE
future_refresh_runtime_mount: RELEASE_ROOT_SHARED_RUNTIME_SYMLINK
release_train_3a_r3_standalone_runtime_source: ../../runtime
release_train_3a_r3_lite_runtime_source: ./runtime
release_train_3a_r3_worker_runtime_healthcheck: NO_SIDE_EFFECT_WRITABILITY_CONTRACT
release_train_3a_r3_static_checker: PASS
release_train_3a_r3_targeted_tests: PASS
release_train_3a_r3_staging_revision_unchanged: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r3_deployment_record_path: reports/W2_RELEASE_TRAIN_3A_R3_DEPLOYMENT.json
release_train_3a_r3_result_path: reports/W2_RELEASE_TRAIN_3A_R3_RESULT.md
release_train_3a_r3_status: ROLLED_BACK_CONTRACT_FAILURE
release_train_3a_r3_target_revision: 5e1179f2502e6fe78c7a0a58c81dcacf9341dc53
release_train_3a_r3_previous_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r3_failure: SHARED_RUNTIME_NOT_WRITABLE_FOR_NON_ROOT_WORKER
release_train_3a_r3_target_scheduler_started: false
release_train_3a_r3_provider_called: false
release_train_3a_r3_worker_uid: 10001
release_train_3a_r3_worker_is_root: false
release_train_3a_r3_runtime_source: /opt/w2/releases/5e1179f2502e6fe78c7a0a58c81dcacf9341dc53/runtime
release_train_3a_r3_runtime_source_resolved: /opt/w2/shared/runtime
release_train_3a_r3_worker_runtime_writable: false
release_train_3a_r3_rollback_completed: true
release_train_3a_r3_post_rollback_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
release_train_3a_r3_post_rollback_health: PASS
release_train_3a_r3_next_action_requires_user_approval: true
pending_staging_deployment: true
pending_deployment_reason: choose approved shared runtime writability strategy for non-root worker before next retry
future_refresh_deployment_status: ROLLED_BACK_CONTRACT_FAILURE
stage10e_deployed: false

gate5: OPEN
candidate: false
formal_recommendation: false

github_repository: QIUYEDALAO/w2-football-intelligence-engine
github_remote: github-w2
repository_main_branch: main
github_default_branch_observed: chore/stage7i-24h-observation
repository_parent_before_reconciliation: f6cb856eeaafdfafe0fd314c390d14faafe8e486
repository_head_relation: handoff is current as of containing commit
latest_ci_run_id: 28122483166
latest_ci_workflow: W2 Stage 2 CI
latest_ci_result: success

stage7i_final_no_provider_calls: true
stage7i_final_no_runtime_writes: true
stage7i_final_no_signal_sent: true
stage7i_final_no_deploy_or_restart: true
stage7i_final_no_env_read: true
stage7i_final_w1_modified: false
stage7i_final_candidate: false
stage7i_final_formal_recommendation: false

original_workspace_last_known_dirty:
  - M scripts/extract_w2_gate3_baselight_limited_ah.py
  - M tests/unit/test_stage10a_read_api.py
  - ?? tests/unit/test_baselight_extract_resume.py
original_workspace_dirty_files_included_in_stage7i_final_commit: false
```

## 0.1 权威文件层级

1. `docs/W2_MASTER_ROADMAP.md`
   - 项目总目标、阶段、Gate 和禁止事项。
2. `reports/W2_ROADMAP_STATUS.json`
   - 各阶段与 Gate 的动态进度。
3. `reports/W2_CURRENT_HANDOFF.md`
   - 当前 SHA、runtime、BLOCKER 和恢复点。
4. 聊天记录
   - 只作补充，不作为长期事实源。

执行包名称不等于 master roadmap 阶段编号。当前 Gate3 closure decision
reconciliation 是 active execution package，不能被解读为 Gate3 已关闭。

## 0.2 当前协作与发布协议

用户确认的长期工作流：

1. Web Sol 负责制定阶段计划、产品边界、验收标准和阶段 Review。
2. Codex 只按已批准阶段连续开发、修 bug、跑测试、做 staging 验收和生成证据报告。
3. Sol 不对每次小修逐项 Review，只在阶段完成、关键争议或最终确认时 Review。
4. Codex 按 Sol Review 结果做最小必要修改；不得扩大到未授权能力。
5. 最终由 Sol 确认后，再进行 Git commit、push 或 PR 同步。

当前固定边界：

- Dashboard UI、布局、CSS、路由和信息架构默认不改，除非用户单独批准。
- AH/OU 正式推荐、LMM 数值调整、锁单和 production 推荐默认关闭。
- GitHub 只在用户明确要求同步，或阶段达到统一提交点时使用。
- Web Sol 的验收意见应作为下一轮 Codex 执行输入；Codex 不自行替 Sol 裁决产品边界。
- 平台聊天记录只作补充；本文件和 GitHub 上的阶段报告才是跨会话事实源。

## 1. 当前任务清单

### 已完成

- Release Train 3A future-refresh hardening staging deployment attempt.
- Target revision `fcfba08824f42917d30bc8d0742ea99d2fc18349` was built and started on staging without running migration.
- Target API/Web/container health passed, but future-refresh dispatch contract failed.
- Rollback to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16` completed successfully.
- Post-rollback API/Web/container/port/Alembic checks passed.
- Release Train 3A-R1 static scheduler enablement repair implemented.
- Staging scheduler compose now explicitly enables future-refresh dispatch for `world_cup_2026`.
- Scheduler default code remains fail-closed when the env flag is absent.
- Release Train 3A-R1 staging retry attempted and rolled back after scheduler health contract failed.
- Post-rollback staging health passed on `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.
- Gate3 closure decision reconciliation。
- Stage7I 24h final observation read-only audit。
- 更新 handoff v33、roadmap status 与 R1B2 result。
- 新增 final audit report、decision 和合同测试。
- 单次阶段提交 `f6cb856eeaafdfafe0fd314c390d14faafe8e486`。
- `main` 与 `chore/stage7i-24h-observation` 同步到该提交。
- GitHub Actions run `28091440346`：`success`。
- 本勘误包清理 handoff/R1B2 中与最终决策冲突的“进行中”叙述。

### 未完成 / BLOCKER

- `FUTURE_REFRESH_SCHEDULER_DISPATCH_DISABLED`: target scheduler container did not have `W2_FUTURE_FIXTURE_REFRESH_ENABLED`; `future_fixture_refresh_tick()` returned `DISABLED`.
- Future-refresh append-only market ledger and read model were not verified in staging because scheduler dispatch did not occur.
- Release Train 3A-R1 retry deployment was attempted and rolled back; a follow-up config policy availability repair is pending.
- Release Train 3A-R1 retry failed because the staging scheduler could not load the future-refresh policy from the mounted config path: `FUTURE_REFRESH_POLICY_INVALID`.
- Next repair must make `config/policies/future_fixture_refresh.v1.json` available to the staging scheduler without migration, `.env` reads, or production changes.
- lifecycle collector 在完整比赛生命周期前已 inactive，且未恢复。
- actual kickoff 没有合法内部来源。
- closing observation 无法合法确定。
- result、settlement、evaluation 与 final Shadow DB audit 缺失。
- final checker 为 `FAIL`，该 run 不具备 Gate5 资格。
- Gate5 保持 `OPEN`。
- 后续 recovery 或 successor run 必须作为单独批准的阶段包；不得复用本 evidence gap 关闭 Gate5。

## 2. Stage7I 最终事实

Stage7I observer 自然完成并写出 `COMPLETED` 与 `summary.json`：

- 样本数：`289`
- coverage：`86487.295089s`
- 最大采样间隔：`300.338218s`
- revision stable：`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- observer 结束后不再存活
- `candidate=false`
- `formal_recommendation=false`

最终分类：

`BLOCKED_NON_QUALIFYING_LIFECYCLE_GAP`

该分类不否认 observer 的 24h 完成，只说明 lifecycle evidence chain 不完整，因此不得进入 Gate5 合格证据包。

权威证据：

- `reports/W2_STAGE7I_FINAL_OBSERVATION_AUDIT.md`
- `reports/W2_STAGE7I_FINAL_OBSERVATION_DECISION.json`
- `reports/W2_STAGE7I_R1B2_RESULT.md`
- `reports/W2_STAGE7I_FINAL_AUDIT_RECONCILIATION.md`

## 3. Gate 状态

- Gate0：`PARTIAL`
- Gate3：`PARTIAL`
- Gate4：`OPEN`
- Gate5：`OPEN`
- Gate6：`NOT_READY`
- `candidate=false`
- `formal_recommendation=false`

Gate3 remains `PARTIAL`。Baselight 历史 AH limited walk-forward 已达到
`PASS_LIMITED_WALK_FORWARD`，但 DATE-only、精确 phase coverage、export/retention、
closing-only OU 与 unknown pre-match aggregate 限制仍保留。

## 4. Runtime 与部署边界

最后确认的 staging revision 为
`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`，Alembic head 为
`0017_create_stage9a_shadow_strategy`。

Release Train 3A attempted to deploy `fcfba08824f42917d30bc8d0742ea99d2fc18349`
to staging. The deployment avoided production, migration, Stage10E, Stage7I
successor startup, permissions changes, sensitive-material changes, and W1 changes. Target
health passed, but the future-refresh scheduler contract failed because the
scheduler path was disabled in the container. The release was rolled back to
`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`.

Release Train 3A-R1 implemented the static repair only. It wires future-refresh
enablement explicitly into the staging scheduler compose definitions and adds a
no-side-effect scheduler health contract. It did not deploy, restart, migrate, or
touch staging runtime.

Release Train 3A-R1 retry deployment attempted `2d80e04b52af2b6ec957c554968c2c60a3a0cec0`
on staging. API, worker, and web became healthy, but scheduler health failed with
`FUTURE_REFRESH_POLICY_INVALID`, so dispatch was not attempted and no task audit
or provider request was created for the validation path. The release was rolled
back to `23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`, and post-rollback health
passed.

本 final audit、Release Train 3A 尝试与文档更新均未：

- 恢复 lifecycle collector；
- 调用 provider；
- 发送 signal；
- 保留目标部署；
- 写 staging runtime；
- 读取 `.env`；
- 修改 W1；
- 启用 candidate 或正式 recommendation。

`DEPLOYMENT_FREEZE=ACTIVE`。Future refresh hardening 的 scheduler enablement
修复已经完成，但 staging retry 暴露出 config mount policy availability gap。
Stage10E 仍未部署，不得与
Stage7I recovery 混合。

## 5. 新会话启动协议

1. 先读本文件。
2. 再读 `docs/W2_MASTER_ROADMAP.md` 和 `reports/W2_ROADMAP_STATUS.json`。
3. 将本文件视为最后确认基线，而不是未经现场复核的实时真相。
4. 变更前核对目标 ref、staging revision、Gate、runtime 与 dirty worktree。
5. 不重新抽取已完成的 Baselight 历史 AH 数据。
6. 不把 scheduled kickoff、poll time 或外部来源冒充 actual kickoff。
7. 不把 retrospective evidence 冒充 forward evidence。
8. 高风险操作和 Stage7I recovery/successor runtime 动作必须先取得明确批准。

## 6. 下一阶段停止点

当前自动推进停止在：

`RELEASE_TRAIN_3A_R2_CONFIG_POLICY_AVAILABILITY_REPAIR_REQUIRED`

下一步是修复 staging scheduler 的 future-refresh policy availability，再进入新的
approved retry deployment。
Stage7I recovery/successor 仍必须另开阶段包，并在
开始 runtime/provider 动作前取得明确批准。当前非运行态工作可以继续做静态审计、
测试与规划，但不得宣称 Gate5 closure。
