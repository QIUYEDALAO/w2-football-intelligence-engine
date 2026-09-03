# W2-F3-REST-LEVEL-REMEASURE 最终报告

状态：`DONE_NO_CONSTRUCTION_PASSED / SCREENING_ONLY`

## 冻结与边界

- 生产基线：`1de3c1ef554d00a408577f59f4864e04f1d341da`。
- 预注册提交：`d5024e5d`；JSON SHA-256 `81f998b32da994258792bb03d728c7e7a2c9abafe616044dce0089e34a1092d8`；Markdown SHA-256 `53f4618022eaaa105bba659f07fd9e27f04e0178018fdd4a11f3516536c579c6`。
- loader 提交：`3fee1404`；安全嵌套结构检查提交：`78ae3121`；结果前 runner 冻结提交：`1b430ee9`。
- 只使用 TRAIN 2024，在固定 hash 五折内产生折外（OOF）预测。VALIDATION 2025 与 HOLDOUT 2026 均未进入计算，断言触发计数均为 `0`。
- 两个新构造均只作用于 TOTAL 轴；每折标准化和 beta 只在其余四折拟合。黄金分割 96 次，beta 范围 `[-2,2]`；fixture-cluster paired bootstrap 10,000 次，seed `20260905`；Bonferroni alpha `0.025`。
- 本任务是对 F3 的第二次检验，换了标量构造与作用轴，动机是“共同疲劳压低总进球”的具体物理机制，不是在同一假设上反复搜索显著性。

## 数据与 loader 审计

| 来源 | 原始记录 | loader 后 2024 | 排除的非 2024 | 禁用年份/赛季断言触发 |
|---|---:|---:|---:|---:|
| history team-side rows | 38,706 | 8,744 | 29,962 | 0 |
| PIT factor snapshots | 10,266 | 3,118 | 7,148 | 0 |
| xG team-side rows | 18,696 | 5,926 | 12,770 | 0 |

结构检查只返回字段名与计数：3,118 个 TRAIN snapshot 均有 F3 节点；`home_rest_days`、`away_rest_days` 位于该节点顶层。完成 join 后，两构造均有 `2,684` 个 fixture/cluster。逐项排除：`MISSING_SNAPSHOT=1,254`、`MISSING_PIT_XG=434`；其余缺失项为 `0`。

固定源 SHA-256：history `80e49d1a32b5dd9653d41826e87415acff0d32a6804dea408f3b99737a6ab5e2`；snapshot `aa77f112bae6d3f5a86b7ffc4a169baa77d5a2060e1a4a6a7e99a84ece96f3d3`；xG `09d921ffb7b39a88dd67ad5043d0102941b7357effb54487a700c83dc2399d9b`。

## OOF 结果

| 构造 | fixtures=clusters | OOF Brier 改善 | 单侧 95% 下界 | p | alpha | 筛选结论 |
|---|---:|---:|---:|---:|---:|---|
| `F3L_MIN_REST` | 2,684 | -0.000043605 | -0.000285414 | 0.605539 | 0.025 | FAIL |
| `F3L_MEAN_REST` | 2,684 | +0.000034292 | -0.000327300 | 0.425957 | 0.025 | FAIL |

五折 beta 均未命中搜索边界。两个构造都没有同时满足点估计大于 0、单侧下界大于 0、p 小于 0.025，因而都不值得仅凭本次结果进入确认。

### 次指标

| 构造 | Brier 基线→候选 | log-loss 基线→候选 | ECE mean 基线→候选 | reliability sum 基线→候选 | resolution sum 基线→候选 |
|---|---|---|---|---|---|
| `F3L_MIN_REST` | 0.611389193→0.611432798 | 1.020744493→1.020813999 | 0.021392605→0.021667932 | 0.002525701→0.002576078 | 0.032156652→0.032233789 |
| `F3L_MEAN_REST` | 0.611389193→0.611354901 | 1.020744493→1.020669091 | 0.021392605→0.021878631 | 0.002525701→0.002773650 | 0.032156652→0.033112729 |

## 实际取值分布与下尾

| 构造 | min | p05 | p10 | p25 | median | p75 | max | std | zero | <=2 | <=3 | <=4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `F3L_MIN_REST` | 2.0208 | 2.9792 | 3.0938 | 4.1042 | 6.1875 | 7.1250 | 39.0 | 5.0059 | 0 | 0 | 213 | 585 |
| `F3L_MEAN_REST` | 2.0625 | 3.1146 | 3.8628 | 5.1302 | 6.9427 | 7.9896 | 39.0 | 5.0887 | 0 | 0 | 89 | 366 |

`MIN_REST <=3` 仅 `213/2684`（7.94%），且 `<=2` 为 `0`。因此本检验对极端短休息/共同疲劳的下尾功率有限；当前 FAIL 不能外推为“极端短休息绝无效应”。但按冻结筛选规则，不因这一结果调整构造或重跑。

另一个需要保留的口径差异：冻结 snapshot 中的 `home_rest_days/away_rest_days` 实际为小数天（例如分位数带 1/24 天粒度），而当前 `team_factors.py` 的运行时代码使用 `timedelta.days` 整数。E 按预注册直接使用冻结字段构造水平量，没有事后取整；因此本结果是对该冻结 PIT artifact 的水平量筛选，不应夸大为对当前整数实现的逐字节复测。

## 与任务 A 并列

| 测量 | 数据/评估 | 轴 | Brier 改善 | 单侧 95% 下界 | p | 结论 |
|---|---|---|---:|---:|---:|---|
| 任务 A：封顶休息差 `clip((home-away)/4,-1,1)` | 2024 TRAIN 选轴/拟合，2025 VALIDATION one-look | DELTA | -0.000108429 | -0.000706455 | 0.617338 | FAIL |
| E：`F3L_MIN_REST` | 2024 TRAIN 内 5 折 OOF | TOTAL | -0.000043605 | -0.000285414 | 0.605539 | FAIL_SCREENING |
| E：`F3L_MEAN_REST` | 2024 TRAIN 内 5 折 OOF | TOTAL | +0.000034292 | -0.000327300 | 0.425957 | FAIL_SCREENING |

任务 A 的 FAIL 只适用于“休息天数差 / DELTA”；本任务补测水平量 / TOTAL，但两种预注册构造也都未通过筛选。VALIDATION 2025 未被再次查看，干净确认须等待开球 `> 2026-09-03` 的前向集另行预注册。

## Stop lines 与 identity

- 生产写、ledger、migration、部署、GitHub/GHCR、Provider：`0`。
- `CALIBRATION_VERSION`、模型参数/权重、registry、lambda、`historical_replay_cutoff`、split 边界：改动 `0`。
- 未把新构造写入 `team_factors.py`，未接入 `calibrate_lambdas`，代码行为未改变。
- identity：按 M4 回报“未修改、未重新实测”。
- RESULTS.json SHA-256：`fe4005c9de031f9003c1f9fe67780ead6efddeeef1ca9ffea4eb4e808b6d5aa7`。

## 本地验收

- loader/OOF 定向：`3 passed`；canonical serialization：`57 passed`；package matrix：`5 passed`；Ruff 与 `git diff --check`：PASS。
- 全量：`2952 passed / 9 skipped / 5 failed`。新增的 3 个 loader/OOF tests 解释了相对父提交的 passed 数增加。
- 以下 5 个失败在干净父提交 `1de3c1ef` 逐 node ID 精确复跑，结果 `5 failed`，均同样复现：
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`
  - `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`
  - `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`
  - `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`
- 失败原因分别是本机 Docker CLI 无 Compose 子命令、子进程 PATH 无 `python`、Docker 无法创建用于 uid/gid 权限检查的目录；均非本分支回归。
