# F0 范围与证据合同 —— AH-FACTOR-ACCURACY-V1

```text
主线身份        AH-FACTOR-ACCURACY-V1
当前阶段        F0（范围与证据冻结）
下一阶段        F1（AH 84 条因子矩阵）
TASK_ID         W2_AH_FACTOR_ACCURACY_F0_SCOPE_AND_EVIDENCE_FREEZE_20260910
BASE_COMMIT     15bc23cb937cbac7843017d442db813639869f16
执行方          Claude Code；验收方 Codex；Obsidian 由 Codex 维护，本任务不写
```

## 1. 唯一输入范围

**148 条已发出的正式候选是本主线的唯一输入范围。** 主证据：

```text
docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/
  OFFICIAL_148_SOURCE_BUNDLE.jsonl
  sha256 = da9edb11be8144991addeb1c6e83724d3cca083ca46b0bd8de2eaa6d45f6e7e4   [核对一致]
```

辅助来源**仅用于补球队显示名**，不得作为模型输入：

```text
/Users/liudehua/Desktop/W2文档/evidence/W2_OFFICIAL_148_RAW_20260909/
  _raw_official_recommendations.json
  sha256 = 7e6bcbdc2baf4d8b255d8dbd79a907aa107d4536a642c13465b7828fd0b37110   [核对一致]
```

代码层面只取 `display_name` 两个字符串，不取 id、provider 名或状态位。

**不得读取、研究或混入**：5,818 场历史语料、8,659、858、377、280、
任务 0–3bis cohort、C1、rho、F5 新抓取结果、未正式推荐比赛、任何新的 Provider 响应。

## 2. 冻结口径（已独立复算，逐项一致）

```text
正式候选        148 条 / 111 个 fixture
市场            AH 84 / TOTALS 64
总收益          -20.375u（AH -8.655 / TOTALS -11.72）

结算分层        LOSS 66  HALF_LOSS 8  WIN 55  HALF_WIN 6  PUSH 13
AH 分层         LOSS 34  HALF_LOSS 8  WIN 32  HALF_WIN 6  PUSH 4
TOTALS 分层     LOSS 32  HALF_LOSS 0  WIN 23  HALF_WIN 0  PUSH 9   （派生登记）
```

生成器在做任何事之前先复算这些数字，任一不符即抛错停止，不产出交付物。

## 3. 四因子调权范围

**只有 AH 84 条进入 F3/F5/F6/F9 方向校准。**

**TOTALS 64 条登记为「非四因子方向校准范围」**，理由是口径而非数据可得性：
F3/F5/F6/F9 产出的是 HOME/AWAY 方向信号，而 TOTALS 的方向是 OVER/UNDER。
把主客强度权重套到大小球上，等于用一个不适用的坐标系解释结果。
TOTALS 的 32 条 LOSS 必须由 xG / lambda / 市场链单独诊断，
**不得用 F3/F5/F6/F9 解释或修复**。

roster 里 TOTALS 行标记 `is_ah_factor_scope=false` 保留在册，便于核对，
但不进入 `AH_84_FACTOR_MATRIX_READINESS.jsonl`（该文件恒为 84 行，有测试锁定）。

## 4. 本主线的禁止事项

- **禁止逐场根据赛果改分。** 任何"让这一场输局翻成实际结果"的调整都是结果泄漏。
- **禁止为单场定制权重。** 权重必须是一套全局权重，同时作用于全部 84 条。
- **禁止用事后捷报页面冒充历史赛前 PIT。** 捷报是赛后页面；
  没有证据证明某个值在 `evaluated_at` 之前可见，就不能当作赛前证据。
- **禁止把缺失因子写成 0。** 0 是一个分数，缺失不是分数，两者不得混淆。
- **禁止用当前权重假设替代历史实际权重。** 当前注册表基线
  （F3 33.33% / F5 16.67% / F6 16.67% / F9 33.33%）只是**今天**的配置，
  不是这 148 条当时实际生效的权重，不得填进历史矩阵。
- **禁止用当前分析卡回填历史因子**，卡片是读时投影，回填等于用今天的数据改写历史。
- **F1 之前禁止调权、抓取、调用 Provider、写生产、部署。**

## 5. F1 进入条件

F1 只有在能对 AH 84 条逐场重建以下六项时才能开始，且必须逐场可审计：

```text
F3/F5/F6/F9 各自的：signed score、status、原始 weight、参与状态、
证据时点（必须早于 evaluated_at）、来源 hash
```

任一场任一因子不满足，该行记 `NOT_RECONSTRUCTIBLE`，**不补零、不反推**。

## 6. 本阶段的实际结论

```text
FACTOR_MATRIX_STATUS      = NOT_RECONSTRUCTIBLE_FROM_FROZEN_148
WEIGHT_CALIBRATION_STATUS = BLOCKED_BY_FACTOR_MATRIX
FINAL_STATE               = F0_ACCEPTED_F1_BLOCKED_BY_MATRIX
```

84/84 行为 `NOT_RECONSTRUCTIBLE`。详见 `F0_REPORT.md` §5。
本阶段**不是** `MODEL_CANDIDATE_READY`，F0 不产出任何候选。

## 7. 边界

```text
PROVIDER_CALLS = 0            PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0       PRODUCTION_DB_WRITES = 0
DEPLOYMENT_EXECUTED = false   OBSIDIAN_WRITES = 0
GITHUB_PUSH = 0               PR_CREATED = false
```

未修改：`src/w2/prematch/`、`src/w2/strategy/`、RecommendationDecisionV4、
Scheduler、Dashboard、factor registry、F3/F5/F6/F9 权重、正式推荐方向、迁移。
未新建工作区。未抓取捷报，未访问 API-Football。
