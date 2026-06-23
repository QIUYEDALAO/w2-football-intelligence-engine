# W2 Football Intelligence Engine — Current Handoff

> **跨会话权威交接文件。** 新会话必须先读本文件，再规划、修改、部署或验收。
> 本文件保存“最后已确认状态”，但任何变更前仍须核对受影响的仓库与 staging 实态。

## 0. 机器可读摘要

```yaml
handoff_version: 23
state_captured_on: 2026-06-24
project: W2 Football Intelligence Engine
workspace: /Users/liudehua/.openclaw/workspace/w2-football-intelligence-engine
legacy_project: W1
legacy_policy: frozen_read_only
active_stage_package: Stage7I-R1B2 successor forward observation in progress
master_roadmap_path: docs/W2_MASTER_ROADMAP.md
master_roadmap_version: 1
roadmap_status_path: reports/W2_ROADMAP_STATUS.json
roadmap_status_relation: current as of containing commit
active_execution_package: Stage7I-R1B2
execution_package_is_not_master_phase: true
gate0_audit_path: reports/W2_GATE0_LEGACY_CLOSURE_AUDIT.md
gate0_manifest_path: reports/W2_GATE0_W1_SHA256_MANIFEST.json
gate0_classification_path: reports/W2_GATE0_W1_ASSET_CLASSIFICATION.json
gate0_status: PARTIAL
gate3_audit_path: reports/W2_GATE3_MARKET_BASELINE_AUDIT.md
gate3_decision_path: reports/W2_GATE3_MARKET_BASELINE_DECISION.json
gate3_status: PARTIAL
gate3_historical_source_inventory_path: reports/W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json
gate3_phase_coverage_path: reports/W2_GATE3_PHASE_COVERAGE.json
gate3_ah_walk_forward_path: reports/W2_GATE3_AH_WALK_FORWARD.json
gate3_historical_build_result_path: reports/W2_GATE3_HISTORICAL_MARKET_BUILD_RESULT.md
gate3_historical_data_status: NO_USABLE_INTERNAL_HISTORICAL_AH_DATA
gate3_external_source_requirements_path: docs/data/W2_HISTORICAL_MARKET_SOURCE_REQUIREMENTS_V1.md
gate3_external_source_comparison_path: reports/W2_GATE3_EXTERNAL_SOURCE_COMPARISON.json
gate3_external_source_decision_path: reports/W2_GATE3_EXTERNAL_SOURCE_DECISION.md
gate3_external_source_status: USER_DECISION_REQUIRED
gate3_acquisition_authorized: false
gate3_checker_mode: audit
gate3_data_route: FORWARD_ONLY_ACCUMULATION
gate3_baselight_probe_status: NOT_EVALUATED_SOURCE_MISMATCH
gate3_baselight_observed_source: API_SPORTS_LOCAL_JSON
gate3_baselight_settlement_validation: PASS
gate3_baselight_time_series_status: NO_REPEATED_ECONOMIC_KEY_ACROSS_DATES
gate3_baselight_license_status: UNVERIFIED
gate3_baselight_actual_query_completed: false
gate3_blockers:
  - AH_WALK_FORWARD_EVIDENCE_MISSING
  - CLOSING_ONLY_OU_LIMITS_PHASE_CLAIMS
  - HISTORICAL_AH_BASELINE_BACKTEST_MISSING
  - UNKNOWN_PREMATCH_AGGREGATE_LIMITS_AS_OF_CLAIMS
gate0_blockers:
  - EXPECTED_W1_PATH_NOT_FOUND
  - W1_TAG_W1_LEGACY_FINAL_MISSING
  - W1_WORKTREE_NOT_CLEAN
  - W1_LEGACY_STATUS_UNTRACKED
  - W1_CURRENT_HEAD_DIFFERS_FROM_LEGACY_BASELINE_HEAD
  - FULL_W1_BACKUP_NOT_VERIFIED
stage7i_status: SUCCESSOR_OBSERVATION_IN_PROGRESS
parallel_mainline_status: FUTURE_DATA_REFRESH_IMPLEMENTATION_COMPLETED
future_refresh_hardening_status: OPERATIONAL_HARDENING_COMPLETED
future_refresh_hardening_commit: 8e467e657836641975294aeea12066cc125307f7
future_refresh_hardening_ci_run: 28022797264
future_refresh_hardening_ci_result: success
pending_staging_deployment: true
pending_deployment_reason: preserve active Stage7I revision continuity
ci_patch1_status: REMOTE_CI_FAILED_ALEMBIC_SMOKE
ci_patch2_status: REMOTE_CI_SUCCESS
server_revision: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
alembic_head: 0017_create_stage9a_shadow_strategy
deployment_freeze: ACTIVE
gate5: OPEN
candidate: false
formal_recommendation: false
stage10e_deployed: false
github_repository: QIUYEDALAO/w2-football-intelligence-engine
github_remote: github-w2
repository_main_branch: main
repository_main_before_ci_patch1: 6a67e984b3af7700567133f7a2b1e53c700d9616
repository_main_before_ci_patch2: 467d5b3241098fba7c553f4e3d117c68327c9e90
github_default_branch_observed: chore/stage7i-24h-observation
prior_ci_run_id: 27993426548
prior_ci_result: failure
prior_ci_failed_step: Pytest
ci_patch1_commit: 467d5b3241098fba7c553f4e3d117c68327c9e90
ci_patch1_run_id: 27994161482
ci_patch1_remote_result: failure
ci_patch1_failed_step: Alembic smoke
ci_patch2_commit: 787f93a25aa39d83c48a1ee022923b5cb73e28a8
ci_patch2_run_id: 27995062248
ci_patch2_remote_result: success
ci_patch2_validated_refs:
  - main
  - chore/stage7i-24h-observation
ci_baselight_correction_commit: 3f8cb84793100e994665e28ce720a85b6979a963
ci_baselight_correction_run_id: 28052676101
ci_baselight_correction_result: failure
ci_baselight_correction_failed_step: Pytest
ci_baselight_correction_failure_type: HARDCODED_VERSION_DRIFT
ci_baselight_correction_fix_commit: 3f8cb847 + 2-test contract fix in ci_reconciliation
ci_baselight_correction_fixed_local: true
ci_baselight_correction_unrelated_ruff_errors: 52_pre_existing
local_untracked_baselight_drafts_archived: true
local_untracked_baselight_archive_dir: /Users/liudehua/.openclaw/workspace/w2_untracked_archive/20260623T200711Z
local_untracked_baselight_archive_manifest: /Users/liudehua/.openclaw/workspace/w2_untracked_archive/20260623T200711Z/MANIFEST.txt
local_verify_after_archive: PASS
remote_ci_baselight_correction_run: 28053133417
remote_ci_baselight_correction_result: success
stage7i_run_01_fixture_id: 1489401
stage7i_run_01_status: BLOCKED_NON_QUALIFYING
stage7i_run_01_observer_pid: 343187
stage7i_run_01_forward_complete: false
stage7i_run_01_gate5_eligible: false
stage7i_same_fixture_restart_allowed: false
stage7i_successor_fixture_required: true
stage7i_successor_fixture_id: 1489404
stage7i_successor_kickoff_utc: 2026-06-23T17:00:00Z
stage7i_successor_observer_pid: 1435421
stage7i_successor_observer_pgid: 1435396
stage7i_successor_runtime_dir: /opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404
stage7i_successor_started_at_utc: 2026-06-23T09:59:44.331436Z
stage7i_successor_expected_end_utc: 2026-06-24T09:59:44.331436Z
stage7i_successor_run_status: IN_PROGRESS
stage7i_lifecycle_capture_status: ACTIVE_CONTINUITY_RESTORED
stage7i_lifecycle_collector_identity: host_pid_1678226_container_pid_23041
stage7i_lifecycle_collector_runtime_tooling: /opt/w2/shared/runtime/stage7i/tooling/lifecycle_74999d0_budget_v5
stage7i_lifecycle_collector_container_tooling: /tmp/w2_stage7i_lifecycle_tooling_budget_v5
stage7i_lifecycle_collector_tooling_sha: a025acc386da7580d10c03975b78cf53fe2a945020ea93d4817de9f907713d5c
stage7i_lifecycle_collector_lock: /opt/w2/releases/23c89be4d2a32019d8d21bb9b102ae0b7ca15c16/infra/compose/runtime/stage7i/lifecycle-1489404.lock
stage7i_lifecycle_collector_lock_holder: 1678226
stage7i_lifecycle_shared_runtime_sync: APPEND_ONLY_MERGED
stage7i_lifecycle_probe_request_count: 7
stage7i_lifecycle_probe_remaining_quota: 6790
stage7i_lifecycle_quota_daily_remaining: 6790
stage7i_lifecycle_quota_burst_remaining: 298
stage7i_lifecycle_quota_daily_source: x-ratelimit-requests-remaining
stage7i_lifecycle_quota_burst_source: x-ratelimit-remaining
stage7i_lifecycle_quota_observed_at: 2026-06-23T15:05:58.147308Z
stage7i_lifecycle_budget_preflight: PASS
stage7i_lifecycle_configured_request_budget: AUTO
stage7i_lifecycle_effective_request_budget: 103
stage7i_lifecycle_consumed_attempts_at_v5_start: 5
stage7i_lifecycle_projected_required_at_v5_start: 98
stage7i_lifecycle_remaining_budget_at_v5_start: 98
stage7i_lifecycle_daily_capacity_after_reserve: 5290
stage7i_lifecycle_runtime_dir: /opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404/lifecycle
stage7i_lifecycle_final_evidence: /opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404/lifecycle/final_evidence.in_progress.json
stage7i_lifecycle_fixture_evidence_count: 1
stage7i_lifecycle_market_evidence_count: 2
stage7i_lifecycle_market_bookmaker_count: 14
stage7i_lifecycle_result_evidence_count: 0
stage7i_lifecycle_request_audit_append_only_attempt_counting: true
stage7i_lifecycle_collector_exits_append_only: true
stage7i_lifecycle_residual_pid_classification: stale_python_collectors_terminated_with_container_term
stage7i_lifecycle_graceful_shutdown_support: true
stage7i_lifecycle_current_state: PREMATCH
actual_kickoff_status: PENDING
closing_status: PENDING
final_evidence_status: IN_PROGRESS
stage7i_server_revision_baseline: 23c89be4d2a32019d8d21bb9b102ae0b7ca15c16
stage7i_r1b1_commit: 54a498c701af0e754645cf51658e45683fa6352a
stage7i_r1b1_ci_run: 28009675284
stage7i_r1b1_ci_result: success
stage7i_r1b1_status: COMPLETED
stage7i_tooling_fixture_binding: DYNAMIC
stage7i_tooling_archive_fixture_id: 1489401
stage7i_tooling_expected_alembic_head: 0017_create_stage9a_shadow_strategy
stage7i_tooling_global_observer_lock: /opt/w2/shared/runtime/stage7i/observer-global.lock
stage7i_tooling_selector_mode: DRY_RUN_ONLY
stage7i_r1b1_ci_source: GitHub Actions status for the containing commit
stage7i_selector_direct_fixture_summary_supported: false
stage7i_candidate_manifest_required: true
stage7i_selection_min_pre_kickoff_hours: 6
stage7i_selection_min_post_kickoff_hours: 6
stage7i_r1b2a_ci_source: GitHub Actions status for the containing commit
stage7i_r1b2a_commit: 7126f7540e8171dab83c1e2f81ab9a2b6c04fbbc
stage7i_r1b2a_ci_run: 28010736953
stage7i_r1b2a_ci_result: success
stage7i_r1b2a_status: COMPLETED
stage7i_r1b2_legacy_observer_terminated: true
stage7i_r1b2_legacy_observer_old_pids:
  - 723787
  - 723789
stage7i_r1b2_legacy_observer_old_pgid: 723782
stage7i_r1b2_legacy_observer_sample_count: 177
stage7i_r1b2_legacy_observer_completed: false
stage7i_r1b2_provider_recovery_request_count: 3
stage7i_r1b2_provider_recovery_future_candidate_count: 4
stage7i_r1b2_candidate_manifest_count: 1
stage7i_r1b2_selection_blocker: null
stage7i_r1b2_observer_started: true
stage7i_r1b2_observer_first_sample_count: 1
stage7i_r1b2_bootstrap_check: PASS
stage7i_r1b2_tooling_fix: typed_alembic_revision_parser_and_legacy_runtime_dir_compat
future_refresh_formal_scheduler_entry: apps/scheduler/main.py
future_refresh_formal_worker_entry: apps/worker/celery_app.py
future_refresh_service: src/w2/ingestion/future_refresh.py
future_refresh_policy: config/policies/future_fixture_refresh.v1.json
future_refresh_scheduler_semantics: dispatch_celery_task_only
future_refresh_worker_lock: redis_preferred_file_fallback_owner_marker
future_refresh_task_key: future-refresh:<competition_id>:<season>:<time-bucket>
future_refresh_market_ledger: runtime/future_refresh/ledger/market_observations.jsonl
future_refresh_read_model_source: append_only_market_ledger
future_refresh_runtime_root: runtime/future_refresh
future_refresh_deployment_status: PENDING_STAGE7I_COMPLETION
repository_head_relation: handoff is current as of its containing Git commit
containing_commit_ci_source: GitHub Actions status for the containing commit
repository_branch_at_capture: chore/stage7i-24h-observation
repository_head_before_handoff: b98d3e3cdf19c47d5da25d5e681936970c75856c
handoff_file_added_on: 2026-06-23
handoff_file_tracked: true
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

执行包名称（例如 Stage7I、Stage10E、Patch、Release Train）不等于 master
roadmap 阶段编号。当前 Stage7I-R1B2 是 active execution package，不能被解读为
master roadmap Stage 7 已完成。

## 0.2 Gate0 Legacy Closure Evidence

Gate0 was re-audited from W2 on 2026-06-24 with W1 treated as read-only. The audit generated:

- `reports/W2_GATE0_LEGACY_CLOSURE_AUDIT.md`
- `reports/W2_GATE0_W1_SHA256_MANIFEST.json`
- `reports/W2_GATE0_W1_ASSET_CLASSIFICATION.json`

Result: `gate0_status=PARTIAL`. The audit improves tracked-file SHA256 and classification evidence, but does not close Gate0 because the audited W1 repository lacks the `w1-legacy-final` tag, has a dirty worktree, has an untracked `W1_LEGACY_STATUS.md`, differs from the recorded legacy baseline HEAD, and lacks a complete current backup verification. Stage7I, Gate4, Gate5, `candidate=false`, and `formal_recommendation=false` remain unchanged.

## 0.3 Gate3 Market Baseline Closure Audit

Gate3 was audited from W2 without provider calls, deployment, migration, model tuning, candidate output, or formal recommendation output. Evidence was written to:

- `reports/W2_GATE3_MARKET_BASELINE_AUDIT.md`
- `reports/W2_GATE3_MARKET_BASELINE_DECISION.json`

Result: `gate3_status=PARTIAL`. Stage6 implementation remains complete, but Gate3 production closure is blocked by missing historical AH baseline/backtest, limited `UNKNOWN_PREMATCH_AGGREGATE` 1X2 semantics, `CLOSING`-only OU subset evidence, and `CALIBRATION_REQUIRED` movement thresholds. Gate4, Gate5, `candidate=false`, and `formal_recommendation=false` remain unchanged.

## 0.4 Gate3 Historical Market Evidence Build

Gate3 historical market evidence was built from existing W1/W2 assets without provider calls, deployment, migration, runtime mutation, or W1 modification. Outputs:

- `reports/W2_GATE3_HISTORICAL_MARKET_SOURCE_INVENTORY.json`
- `reports/W2_GATE3_PHASE_COVERAGE.json`
- `reports/W2_GATE3_AH_WALK_FORWARD.json`
- `reports/W2_GATE3_HISTORICAL_MARKET_BUILD_RESULT.md`

Result: `gate3_status=PARTIAL`. Captured-at market coverage exists, but no usable settled internal historical AH data was found, so AH baseline/walk-forward remains missing. Gate4, Gate5, `candidate=false`, and `formal_recommendation=false` remain unchanged.


## 0.5 Gate3 External Historical Odds Source Decision

Gate3 external historical odds source decision materials were prepared from public provider websites and public documentation only. No provider was contacted, no account/trial was created, no purchase was made, no commercial terms were accepted, no external API was called, and no non-public data was downloaded. Outputs:

- `docs/data/W2_HISTORICAL_MARKET_SOURCE_REQUIREMENTS_V1.md`
- `reports/W2_GATE3_EXTERNAL_SOURCE_COMPARISON.json`
- `reports/W2_GATE3_EXTERNAL_SOURCE_DECISION.md`

Result: `gate3_external_source_status=USER_DECISION_REQUIRED`. Gate3 remains `PARTIAL` because internal historical AH data is exhausted and no external source acquisition is authorized. The user must choose provider trial/procurement evaluation, forward-only accumulation, or an explicit Gate3 scope change. Gate4, Gate5, Gate6, `candidate=false`, and `formal_recommendation=false` remain unchanged.


## 0.6 Local Baselight Draft Triage

Two untracked Baselight draft files were classified as unfinished local drafts because they were not part of the successful remote commit tree and caused local `make verify` to fail through Ruff scanning. They were moved outside the repository without deletion to:

`/Users/liudehua/.openclaw/workspace/w2_untracked_archive/20260623T200711Z/`

The archive manifest records original paths, SHA256, size, mode, and mtime. After archiving, local `make verify`, secret scan, and `git diff --check` passed. Gate3 state, Stage7I runtime, W1, deployment, and `.env` were not changed.

## 1. 新会话启动协议

新会话第一条指令：

> 请先读取 `reports/W2_CURRENT_HANDOFF.md`，然后继续按阶段包推进。

执行顺序：

1. 先读本文件。
2. 把本文件作为最后已确认基线，而不是未经核验的实时真相。
3. 变更前核对相关仓库 SHA、服务器 revision、服务、容器、migration 与 gate 状态。
4. 优先保持当前主线阶段包连续性，不把延期 redesign 混入紧急 runtime 包。
5. 阶段状态、SHA、服务器状态、报告路径或 BLOCKER 变化后，同步更新本文件。
6. 代码阶段包应在同一提交中更新本文件；纯运维阶段应在验收后尽快提交 docs-only handoff 更新。
7. 详细历史证据放阶段报告；本文件只保留最新有效状态。
8. 本文件不得保存 `.env` 内容、密钥、token、密码或私密 payload。

状态可信度优先级：

1. 已现场验证的仓库和 staging 实态
2. 本文件
3. 聊天历史

## 2. 不可突破的项目边界

- W1 已冻结为 **Legacy**，仅作历史参考。
- 不得给 W1 新增功能。
- 不得修改 W1。
- 不得把 retrospective 冒充 forward。
- 不得启用 DeepSeek。
- 不得启用 `CANDIDATE`。
- Gate4 / Gate5 未通过前不得输出正式 `RECOMMEND`。
- 不得削弱 shadow write、correlation、lock、settlement、evaluation 或 recommendation 安全边界。
- `DEPLOYMENT_FREEZE=ACTIVE`，除非经批准的阶段包明确变更。

## 3. 授权与必须确认事项

本项目的 staging 常规部署已授权自动同意，不再逐次询问。

以下操作必须停止并取得明确确认：

- production 变更
- 破坏性 migration
- 删除数据或不可逆数据重写
- 权限、密钥、凭据、secret 或 `.env` 变更
- 外部通知
- 资金、交易或投注

同时遵守第 11 节的阶段停止条件。

## 4. 最后已确认的 staging 基线

- 首尔 staging：`ubuntu@43.155.208.138`
- Server current revision：`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`
- `w2-staging.service`：`enabled / active`
- 长期容器：`6` 个，全部 `healthy`
- API `/health`：`200`
- API `/ready`：`200`
- Web：`200`
- 公网业务端口：无，仅 SSH
- 本机 Web 隧道：`http://127.0.0.1:18080`
- 本机 API 隧道：`http://127.0.0.1:18000`
- `.env`：mode `600`；不得读取或打印内容
- Alembic：`0017_create_stage9a_shadow_strategy (head)`
- 新 migration：无
- `DEPLOYMENT_FREEZE=ACTIVE`
- Patch2 override：`COMPLETED`

## 5. Release Train 2 / Patch2

状态：**COMPLETED**

已验证：

- `w2-shadow-cycle` PATH 问题已修复
- console scripts 可直接执行
- Shadow dry-run：`PASS`
- FORWARD cycle：连续两次 `PASS`
- `forward_lock_count=0`
- RETROSPECTIVE replay：`PASS`
- Shadow DB audit：无 candidate / lock / settlement / evaluation 脏写入
- Gate5 preflight：`PASS`，但 Gate5 仍未关闭
- Ops API 与 Web `/api/ops/...` 代理：JSON `200`
- Stage7I observer 已启动
- Observer 容器：`dc3961afb019`

权威报告：

`/opt/w2/shared/runtime/deployments/20260622T232712Z_release_train_2_patch2_COMPLETED.json`

不得把 Patch2 重跑包装为新进展；只有在确认回归后，才能另开范围明确的新 patch。

## 6. Runtime Patch 本地历史

- Patch1 commit：`dd96c79dd3a3798148a0fa6bb6cb21cb90a7951d`
- Patch2 最终服务器 revision：`23c89be4d2a32019d8d21bb9b102ae0b7ca15c16`

## 7. Stage10E Dashboard redesign — 延期支线

本地 redesign 已完成，但未部署：

- Worktree：`/tmp/w2-stage10e-dashboard-redesign`
- Branch：`feat/stage10e-dashboard-redesign`
- Commit：`5c9cf2e74cb6cb2b11e59a8cfe8bb10f6ce93115`
- staging Web `http://127.0.0.1:18080`：仍是旧版 dashboard
- 部署决策：放入下一次 Release Train

不得把 Stage10E 部署混入紧急 Stage7I / runtime evidence 包。

## 7A. CI-Patch1 — baseline Pytest repair

状态：**REMOTE_CI_FAILED_ALEMBIC_SMOKE**

CI-Patch1 是 Stage7I 继续推进前的 GitHub baseline 阻塞修复，不改变 Stage7I 作为当前主线阶段包的地位。

已知输入：

- GitHub repository：`QIUYEDALAO/w2-football-intelligence-engine`
- Remote：`github-w2`
- Main branch：`main`
- Main before patch：`6a67e984b3af7700567133f7a2b1e53c700d9616`
- GitHub default branch observed：`chore/stage7i-24h-observation`
- Prior CI run：`27993426548`
- Prior CI result：`failure`
- Prior failed step：`Pytest`
- CI-Patch1 commit：`467d5b3241098fba7c553f4e3d117c68327c9e90`
- CI-Patch1 run：`27994161482`
- CI-Patch1 result：`failure`
- CI-Patch1 failed step：Alembic smoke

本地修复范围：

- Secret scan 对 handoff 安全说明文字的误报。
- Clean checkout 中 Stage10A read API 无 runtime fixture fallback。
- Clean checkout 中 Stage14A league audit 无 runtime Stage5B raw data fallback。

CI-Patch1 新增的 committed-report fallback 后续被 Patch2 判定为不合格，因为它可能让 clean checkout 读到与当前 runtime 无关的合成或旧审计数据。

## 7B. CI-Patch2 — PostgreSQL Alembic bootstrap and Patch1 correction

状态：**REMOTE_CI_SUCCESS**

Patch2 修复目标：

- Alembic PostgreSQL fresh bootstrap 版本表宽度。
- 移除 Stage10A synthetic fixture fallback。
- 移除 Stage14A implicit old report fallback。
- 用测试夹具承担 clean checkout 单元测试数据。

已确认根因：

- W2 revision IDs 最长为 `43` 字符。
- Alembic PostgreSQL 默认 `alembic_version.version_num` 仍为 `VARCHAR(32)`。
- 旧的 Alembic version-table kwargs 配置在当前 PostgreSQL implementation 路径下不能达成 W2 所需宽度。

Patch2 范围：

- 注册 W2 PostgreSQL Alembic implementation hook，将 version table `version_num` 设为 `String(64)`。
- `migrations/env.py` 不再使用被忽略的 version-table kwargs 配置。
- `pyproject.toml` Alembic lower bound 调整为 `>=1.14,<2`；当前 lock 仍解析到 Alembic `1.18.4`。
- Stage10A test 改用测试专属 fixture payload。
- Stage14A test 改用测试专属 top-five fixture rows。
- Fresh Stage14A audit 在无 runtime data 时保持 `MISSING`。

远端验收：

- Commit：`787f93a25aa39d83c48a1ee022923b5cb73e28a8`
- GitHub Actions run：`27995062248`
- Workflow：`W2 Stage 2 CI`
- Event：`push`
- Result：`success`
- Validated refs：`main`、`chore/stage7i-24h-observation`
- Alembic smoke 已在 GitHub CI PostgreSQL 服务上通过。
- Docker Compose config 已在 GitHub CI 通过。
- Secret pattern scan 已在 GitHub CI 通过。

CI-Patch2 已关闭 Patch1 引入的 Alembic smoke failure；Stage7I 仍未完成，Gate5 仍为 OPEN。

## 8. 当前比赛研究卡

### Norway vs Senegal

- Competition：世界杯 Group I
- Fixture ID：`1489401`
- Scheduled kickoff：`2026-06-23T00:00:00Z`
- 北京时间：`2026-06-23 08:00`
- AH main line：Norway `-0.5` / Senegal `+0.5`
- OU main line：`2.5`
- Norway win：`44.30%`
- Draw：`24.96%`
- Senegal win：`30.74%`
- Expected goals：Norway `1.55`，Senegal `1.25`

Primary：

- Senegal 1X2 @ `3.50`
- Bookmaker：Dafabet
- Model fair odds：`3.253`
- Adjusted minimum odds：`3.367`
- Risk-adjusted EV：`+4.10%`
- Published grade：`C`
- Action：`WATCH`

Secondary：

- `null`
- 原因：correlation policy 缺失

正式状态：

- `formal_recommendation=false`
- `candidate=false`

直接判断：

- 主看 Senegal 胜，价格必须 `>= 3.37`
- 比分优先：
  1. Norway 1-2 Senegal
  2. Norway 1-1 Senegal
  3. Norway 2-1 Senegal
  4. Norway 2-2 Senegal
- 这是研究级 `WATCH`，不是正式 `RECOMMEND`

## 9. 当前主线阶段包

### Stage7I-R1B2 — Dynamic successor selection and observer bootstrap

目标：

fixture `1489401` 的观察已归档为 `BLOCKED_NON_QUALIFYING`。R1B1 tooling commit `54a498c701af0e754645cf51658e45683fa6352a` 已通过 GitHub Actions run `28009675284`。R1B2A contract commit `7126f7540e8171dab83c1e2f81ab9a2b6c04fbbc` 已通过 GitHub Actions run `28010736953`。R1B2 主线已按用户批准优雅终止 legacy observer PID `723787/723789`，并追加 runtime audit。随后确认当前 staging scheduler 仍为 heartbeat-only，read model 只剩过期 fixture 摘要，不能直接形成 successor manifest。R1B2 使用现有 `ApiFootballClient` provider path 做受控 live recovery，3 次只读请求恢复 4 个未来 World Cup fixture，其中 fixture `1489404` 有 14 家 bookmaker 市场证据。builder 产出 1 个合格 candidate，selector 动态选择 `1489404`，global-lock observer 已启动并写入首个 forward sample。

Run 01 archive:

- Fixture：`1489401`
- Scheduled kickoff：`2026-06-23T00:00:00Z`
- Observer PID：`343187`
- Status：`BLOCKED_NON_QUALIFYING`
- forward_complete=false
- gate5_eligible=false
- same_fixture_restart_allowed=false
- successor_fixture_required=true
- successor_fixture_id=1489404
- successor_kickoff_utc=2026-06-23T17:00:00Z
- successor_run_status=IN_PROGRESS
- successor_observer_pid=1435421
- successor_observer_pgid=1435396
- successor_runtime_dir=/opt/w2/shared/runtime/stage7i/runs/stage7i_20260623T095944Z_1489404
- successor_started_at_utc=2026-06-23T09:59:44.331436Z
- successor_expected_end_utc=2026-06-24T09:59:44.331436Z
- legacy_observer_terminated=true
- legacy_observer_sample_count=177
- provider_recovery_request_count=3
- provider_recovery_future_candidate_count=4
- candidate_manifest_count=1
- selection_blocker=null
- observer_started=true
- first_sample_count=1
- bootstrap_check=PASS
- ordinary_tooling_fixes=typed Alembic revision parser; legacy runtime_dir compatibility
- tooling_fixture_binding=DYNAMIC
- archive_fixture_id=1489401
- expected_alembic_head=0017_create_stage9a_shadow_strategy
- global_observer_lock=/opt/w2/shared/runtime/stage7i/observer-global.lock
- selector_mode=DRY_RUN_ONLY
- direct_fixture_summary_supported=false
- candidate_manifest_required=true
- selection_window=now+6h through run_end-6h

连续性检查：

1. 任何变更前核对 staging revision。
2. 核对 `w2-staging.service`、6 个长期容器、API health/readiness、Web 和 Stage7I observer。
3. 保护不可变 `as_of_time` 和 forward 时间边界。
4. successor fixture 必须从 W2 staging/provider 数据动态选择，不得硬编码；当前 successor `1489404` 仍需完成完整 24h forward lifecycle before Gate5 evidence.
5. 定义最后一笔赛前观测时，区分 scheduled kickoff 与 actual kickoff。
6. 禁止把赛后事实回填为赛前 forward evidence。
7. RETROSPECTIVE replay 与 FORWARD evidence 必须分别归档和表述。
8. 完整赛程生命周期后审计 candidate、lock、settlement、evaluation 写入。
9. 只有验证过的 forward evidence 才能进入 Gate5 evidence package。
10. Gate5 满足全部独立验收条件前保持 OPEN。

## 10. 当前 BLOCKER / 未完成

- Gate5 尚未关闭。
- Stage7I successor 24h observation 尚未完成。
- `ACTUAL_KICKOFF_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `CLOSING_NOT_CAPTURED_BY_CONTINUOUS_FORWARD_RUN`
- `SETTLEMENT_EVALUATION_NOT_CAPTURED`
- `FINAL_SHADOW_DB_AUDIT_PENDING`
- Stage10E 按计划尚未部署。

## 11. Stage7I 停止条件

出现任一情况，停止自动推进：

- staging revision 与预期基线不一致且来源不明
- actual kickoff 无法可靠确定，并会影响 evidence boundary
- observer 不健康、反复重启或有无法解释的数据断档
- 合法事件边界前出现 settlement / evaluation 写入
- 出现未知 candidate、lock、recommendation、settlement 或 evaluation 写入
- `candidate` 或 `formal_recommendation` 意外变为 `true`
- 需要新 migration 或破坏性 migration
- 需要权限、凭据、密钥、secret、`.env` 或公网端口变更
- 涉及 production、删除数据、外部通知、资金、交易或投注

## 12. Handoff 维护契约

以下任一项变化时，必须更新本文件：

- repository / mainline commit SHA
- staging deployed revision
- active branch / worktree
- active stage package
- service / container health baseline
- migration head
- deployment freeze
- Gate4 / Gate5 状态
- observer identity / status
- fixture lifecycle 状态
- 最新完成的 deployment / stage report 路径
- BLOCKER / stop condition
- Stage10E 等延期包状态

每个阶段包验收结束前：

1. 用最新值替换已失效状态，不在本文件堆积时间流水账。
2. 记录权威 commit SHA 或报告路径。
3. 记录验收结果和剩余 BLOCKER。
4. 确认 W1 未修改。
5. 确认 retrospective 未冒充 forward。
6. 除非后续 gate 经明确批准改变策略，否则确认 `candidate=false`、`formal_recommendation=false`。

## 13. 固定回复结构

阶段级回复继续使用：

1. 当前任务清单
2. 已完成
3. 未完成
4. 风险
5. 自动修复和验证
6. 阶段验收
7. 停止条件
8. 最终报告

执行中间只报告有效增量和必要指令；阶段完成后再输出完整验收。
