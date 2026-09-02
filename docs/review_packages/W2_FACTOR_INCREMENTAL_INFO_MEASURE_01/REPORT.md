# W2-FACTOR-INCREMENTAL-INFO-MEASURE 最终报告

状态：`DONE_NO_FACTOR_PASSED`

## 执行边界

- 预注册 commit `00eb9556` 保持冻结，JSON/MD 哈希分别为 `4dad76f5695809529df9970490a36baefe876b79dface15ec949c404b77c830a` 和 `3467b13f77a91c4a9ca313b29423a94a87b60065e03d5dc603a9187b9a3659d2`。
- 族固定为 F3/F5/F1/F2；Bonferroni `alpha=0.0125`；bootstrap `10000`次，seed `20260903`。
- 只使用 TRAIN 2024 选轴/拟合，VALIDATION 2025 确认一次。本轮结果产生后未改口径、未重跑。
- 早前两次 2026 信息暴露保持记录在案；Owner 已将开球时刻不晚于 2026-08-22 的已完赛部分标记为 `BURNED`。本测量没有使用 2026 记录。

## A1.5 装载硬门

所有数据均经同一 loader，按 fixture 开球日期先过滤到 `{2024, 2025}`，再向计算层暴露记录。loader 不提供逐行打印入口，结构检查只返回字段名和年份计数。

| 来源 | 装载后 2024 | 装载后 2025 | 2026 | 2027 | penaltyblog 烧毁赛季 | 断言触发 |
|---|---:|---:|---:|---:|---:|---:|
| history team-side rows | 8,744 | 9,040 | 0 | 0 | 0 | 0 |
| PIT factor snapshots | 3,118 | 4,520 | 0 | 0 | 0 | 0 |
| xG team-side rows | 5,926 | 8,362 | 0 | 0 | 0 | 0 |

三个来源共 9 项禁用集合断言全部通过，触发计数为 `0`。

## A2–A4 结果

| 因子 | TRAIN / VAL fixtures=clusters | 选定轴 | Brier 改善 | 单侧 95% 下界 | p | 判定 |
|---|---:|---|---:|---:|---:|---|
| F3_REST_FITNESS | 2,684 / 4,375 | DELTA | -0.000108429 | -0.000706455 | 0.617338 | FAIL |
| F5_RECENT_AH_COVER | 0 / 0 | DELTA | 不可计算 | 不可计算 | 不可计算 | FAIL_NOT_MEASURABLE |
| F1_MARKET_MOVEMENT | 0 / 0 | DELTA | 不可计算 | 不可计算 | 不可计算 | FAIL_NOT_MEASURABLE |
| F2_BOOKMAKER_INTENT | 0 / 0 | DELTA | 不可计算 | 不可计算 | 不可计算 | FAIL_NOT_MEASURABLE |

fixture ID 在本语料中唯一，因此上表 fixture 数与 fixture-cluster 数相同。

### F3_REST_FITNESS

- TRAIN pooled OOF Brier：DELTA `0.611242099`，TOTAL `0.611266921`，因此按冻结规则选 DELTA。F3 信息并非主要位于 total；本次不触发“当前架构无法表达 total”的限制。
- 全 TRAIN 拟合 `beta=-0.061137758`，未命中 `[-2,2]` 边界。
- TRAIN 分布：min `-1`、p25 `-0.208333`、median `0`、p75 `0.213542`、max `1`、mean `-0.001220`、std `0.357744`、zero `399`。
- VAL 分布：min `-1`、p25 `-0.223958`、median `0`、p75 `0.223958`、max `1`、mean `0.003107`、std `0.363514`、zero `498`。它不是近似常数。
- VALIDATION 基线/候选：Brier `0.617964290 / 0.618072719`，log-loss `1.029918587 / 1.030104390`，ECE mean `0.010953313 / 0.013709855`，reliability sum `0.001072115 / 0.001304648`，resolution sum `0.030051445 / 0.030761271`。
- classwise ECE 基线→候选：HOME `0.016767967→0.020281193`，DRAW `0.005292712→0.006464133`，AWAY `0.010799260→0.014384239`。

### F5 / F1 / F2

冻结 PIT snapshot 对目标 split 只提供 F3/F6/F7，没有与这些 2024/2025 target identities 绑定的 F5 canonical AH cover、F1 market movement 或 F2 intent scalar。两个现成 capture CSV 的记录年份全为 2026，loader 按本任务边界全部过滤。按 complete-case/no-imputation 与 TRAIN<300/VAL<100 停止规则，三者均为 `FAIL_NOT_MEASURABLE`。

这三个判定表示“本次冻结 split 没有可用的 PIT 绑定数据”，不表示已证明因子信息量为零。为遵守跑完即止，本任务不再换源或重跑。

## 结论

四个因子全部未通过：F3 在样本外没有改善概率质量，另外三个在本 split 上不可测。本任务不支持接入任何一个因子；新的建模投入应优先转向首发和 rho。F5/F1/F2 若未来建成 target-bound PIT 语料，需作为新任务重新预注册，不能追加到本次 one-look。

## 已知推断局限

bootstrap 按单场 fixture 成簇，每场的三类分量一起重采样；没有对同队同赛季的多场比赛做更粗聚类，因此残余相关会使置信区间略偏窄。本次依预注册不修改设计。

## 验证

- loader 定向：`2 passed`。
- canonical serialization：`18 passed`。
- package matrix：`5 passed`。
- Ruff：PASS。
- 全量 pytest：`2951 passed / 9 skipped / 5 failed`。

5 个失败均在父提交 `1de3c1ef` 工作树以同 node ID 复跑并同样失败：

1. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]`
2. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]`
3. `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking`
4. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid`
5. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime`

对应宿主限制为 Docker Compose 插件缺失 2、无裸 `python` 1、macOS 无法按 Linux UID/GID 准备目录 2。任务相关失败为 `0`。

## Stop lines

- Football Provider：`0`。
- 生产写、ledger、migration、部署、GitHub/GHCR：`0`。
- `CALIBRATION_VERSION`、模型参数/权重、`factor_registry.v1.json`、λ、`historical_replay_cutoff`、split 边界：改动 `0`。
- identity/verdict：代码与参数未修改，按 Owner M4 不重新实测。
