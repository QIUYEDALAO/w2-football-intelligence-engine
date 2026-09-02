# W2-FACTOR-DISPLAY-FOUR-01

状态：`DONE_DISPLAY_ONLY / MODEL_UNCHANGED`

## 展示内容

本任务复用 analysis card 已有的 `feature_contributions`，在本场因子体检中展示以下四项的原始输入、`score`、`status` 与 `weight`：

- `F1_MARKET_MOVEMENT`：盘口移动
- `F2_BOOKMAKER_DIVERGENCE`：庄家分歧（展示投影 ID 仍为既有 `F2_BOOKMAKER_INTENT`）
- `F3_REST_FITNESS`：休息与体能
- `F5_RECENT_AH_COVER`：近期赢盘率

页面逐项明确标注：这些数值不参与 λ 或概率；当前 `analysis_recommendation.py` 只把 `READY` 状态计入 `ready_count`，然后执行 `coverage_bonus = min(ready_count / 10, 0.25)`。它不读取这些 `score` 的方向或大小。

## 改动前后数值对照

对生产基线 `1de3c1ef554d00a408577f59f4864e04f1d341da` 与本分支工作树使用同一固定输入运行 `run_simulation`，并以主队 `-0.25 @ 1.95` 计算 EV：

| 输出 | 基线 | 本分支 |
|---|---:|---:|
| lambda_home | 1.328674 | 1.328674 |
| lambda_away | 0.971326 | 0.971326 |
| P(home win) | 0.448809 | 0.448809 |
| P(draw) | 0.277893 | 0.277893 |
| P(away win) | 0.273298 | 0.273298 |
| EV(home -0.25 @ 1.95) | 0.014124 | 0.014124 |
| calibration identity | `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` | 同左 |
| calibration status | `APPROVED_VALIDATED` | `APPROVED_VALIDATED` |

实现 diff 仅涉及 Dashboard 展示投影、Web 展示、测试与本报告；没有修改 `src/w2/features`、`src/w2/strategy`、`src/w2/models`、calibration registry 或因子权重配置。

## 边界

- `calibrate_lambdas`：未接入。
- 权重与 `coverage_bonus`：未修改。
- Football Provider：`0` 次。
- 生产写、ledger、migration、部署、GitHub/GHCR：均为 `0`。
- `CALIBRATION_VERSION`、模型参数、概率、EV、identity/verdict：均未改变。

## 验证

- Dashboard/契约定向：`142 passed`
- canonical serialization：`18 passed`
- package matrix：`5 passed`
- Web TypeScript：`tsc --noEmit` 通过；复用同一 `package-lock.json`（SHA-256 `855987381286cafeb5168ab971a8ea639ebe3dcb96cf9b3797cb979f6f61e704`）的既有本地 `node_modules`，未安装或修改依赖
- Ruff：全仓通过
- 全量 pytest：`2950 passed / 9 skipped / 5 failed`

5 个失败均在父提交 `1de3c1ef` 以相同 node ID 复跑并同样失败：

1. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`
2. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`
3. `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`
4. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`
5. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`

对应宿主限制分别为 Docker Compose 插件缺失 2、无裸 `python` 1、macOS 无法按 Linux UID/GID 创建目录 2；任务相关失败为 0。
