# W2 AH-FACTOR-ACCURACY-V1 / F1R-A0 交付包

```text
TASK_ID           W2_AH_FACTOR_ACCURACY_F1R_A0_20260910
阶段              F1R-A0_OFFLINE_FACTOR_RECORDER
PARENT_COMMIT     d8c8bf8259b30cd9fd81dfbf7be8555aa42680aa
F1R_A0_FINAL_STATE  OFFLINE_FACTOR_RECORDER_READY_FOR_R1
```

## 这一轮做了什么，没做什么

```text
OFFLINE_RECORDER_IMPLEMENTED        是
PRODUCTION_WIRING_NOT_STARTED       未接线
LIVE_CAPTURE_NOT_STARTED            未采集
DEPLOYMENT_NOT_EXECUTED             未部署
WEIGHT_CALIBRATION_NOT_STARTED      未调权
```

`OFFLINE_FACTOR_RECORDER_READY_FOR_R1` **不等于**生产记录已接线、
数据已开始采集、可以部署或 F2 可以开始。它只表示离线端口与批次契约已实装并自证。

## 文件

```text
INDEX.md                        本文件
F1R_A0_DATA_FLOW.md             从活对象到 F1P 观测的数据流与设计取舍
FACTOR_SOURCE_MAPPING.json      四因子真实来源逐项映射（只读定位）
OFFLINE_RECORDER_RESULT.json    机器可读结果与边界计数
F1R_A0_REFERENCE_LEDGER.jsonl   参考账本（合成夹具，8 行 = 2 个批次）
TEST_RESULTS.md                 26 项强制矩阵的逐条对应
OBSIDIAN_UPDATE_PROPOSAL.md     给 Codex 的 Vault 更新建议（不是更新证明）
HASHES.sha256                   本包哈希
```

## 三个关键事实

1. **逐因子证据时点确实拿得到。** `FeatureContribution.observed_at` 在四个因子的
   ready 分支全部设置且经 UTC 校验；F1 拿不到是因为它已被序列化丢弃，
   不是因为它不存在。差别在**记录时机**。
2. **`applied_weight` 是真实生效值。** 取 `FeatureContribution.weight`，
   即 `team_score.py` 累加进 `weight_sum_used` 的那个值，不是注册表默认值
   （那份注册表根本没有数值权重）。
3. **`factor_version` 目前无来源。** 四个 builder 都不产出版本号，记录器要求
   调用方提供、缺失即拒整批，**不自造**。真正的版本来源属于 F1R-B。

## 夹具性质

参考账本用的是 **`SYNTHETIC_CONTRACT_FIXTURE`**，通过生产 builder 构造真实
`FeatureContribution` 对象，但比赛、球队、ID 全部合成。
它是**合同用法示例**，不是任何真实比赛的证据，也不证明生产链已接线。

## 边界

```text
PROVIDER_CALLS = 0            PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0       PRODUCTION_DB_WRITES = 0
DEPLOYMENT_EXECUTED = false
OBSIDIAN_ACCESS_MODE = READ_ONLY     OBSIDIAN_WRITES = 0
```

未修改 `src/w2/prematch`、`src/w2/strategy`、RecommendationDecisionV4、
future-refresh 业务路径、`src/w2/api`、Scheduler、Dashboard、Provider allowlist、
生产配置、现役迁移，以及 F0/F1/F1P 冻结产物。

下一步：**R1 独立验收**。不得进入 live wiring、VPS 部署、W1、F2、F3、F4。
