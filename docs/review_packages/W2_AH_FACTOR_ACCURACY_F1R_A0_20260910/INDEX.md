# W2 AH-FACTOR-ACCURACY-V1 / F1R-A0 交付包（窄整改后）

```text
TASK_ID             W2_AH_FACTOR_ACCURACY_F1R_A0_NARROW_REMEDIATION_20260910
PARENT_COMMIT       0821f472115ca2d1aabf0d0c51248057de9c5693
F1R_A0_FINAL_STATE  BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE
```

## 结论：仍然阻塞，而且这是正确的终态

R1 指出的三个问题全部成立，全部已修。修完之后的结论**不是**"可以放行"，
而是把阻塞点从"没被发现"变成"被机器强制"：

**F5 与 F6 在生产中没有可绑定的逐因子来源观测时点。**
修复前它们用 `kickoff_at` 冒充；修复后没有真实来源时点就整批拒绝。

```text
OFFLINE_RECORDER_IMPLEMENTED        是（端口、批次契约、原子提交均已实装）
F5_F6_SOURCE_TIME                   不存在 → fail closed
PRODUCTION_WIRING_NOT_STARTED       未接线
LIVE_CAPTURE_NOT_STARTED            未采集
DEPLOYMENT_NOT_EXECUTED             未部署
WEIGHT_CALIBRATION_NOT_STARTED      未调权
```

## 三个问题的修复

### P0 —— kickoff 不能证明赛果何时被观察

`TeamMatchHistory.observed_at` 的实现就是 `return self.kickoff_at`。
F5 读已结算 AH 结果、F6 读历史进球，**这两类事实在开球时都还不存在**。

修复：按因子分成三种证据规则，逐条强制。

```text
F3_REST_FITNESS   FIXTURE_EVENT_TIME            允许用 observed_at
                  理由：F3 只读开球间隔，不读任何结果字段；
                        "某场比赛在 T 开球"在 T 就可观察
F9_TRUE_XG        SOURCE_SNAPSHOT_OBSERVED_AT   允许用 observed_at
                  理由：来自 TeamXgSnapshot.observed_at，是真实抓取时点
F5 / F6           RESULT_DERIVED                必须由调用方显式传入来源观测时点
                  缺失 → RESULT_DERIVED_FACTOR_WITHOUT_SOURCE_OBSERVED_TIME
                  传入值等于 kickoff → SOURCE_OBSERVED_TIME_IS_KICKOFF_DERIVED
```

第二条守卫是关键：光要求"显式传入"挡不住把 kickoff 换个名字传进来。

**生产中该时点是否存在？** 数据库里 `results.confirmed_at` 确实存在，
但它**从未被带到因子 builder 消费的对象上**——`TeamMatchHistory` 根本没有这个字段。
要接通必须改 `src/w2/features/`（本轮只读）与 `src/w2/prematch/`（本轮禁止）。
因此终态保持 `BLOCKED_BY_UNPROVABLE_FACTOR_SOURCE`。

### P1 —— READY 不等于参与计分

修复前把 `status == READY` 当作 participated。但 `w2.pricing.team_score`
的准入还要求 `is_independent_signal`、`source_group ∈ AUTHORITATIVE_SIGNAL_GROUPS`
（`{xg, team_fixture_history, h2h}`）、非 `NON_SCORING_GROUPS`、`weight > 0`。

修复：**直接复用 `independent_team_scores_from_contributions`**，不复制过滤逻辑
（有测试断言记录器源码里不出现 `AUTHORITATIVE_SIGNAL_GROUPS` /
`NON_SCORING_GROUPS` / `is_scoring_factor`）。

```text
participated              = 该因子出现在权威的 scoring_factors 里
applied_weight            = 权威给的 weight；与 contribution.weight 不一致即整批拒绝
READY 但被权威排除         → FACTOR_ADMISSION_FAILED，score=null，
                            weight_entered_weight_sum_used=false
```

参考账本里就有一例：完整夹具的 F3 因 `source_group=canonical_historical_ah_fact`
不在权威组内而被排除，**记录为 `FACTOR_ADMISSION_FAILED` 而不是参与**。
修复前它会被错记成 PARTICIPATED。

### P1 —— 批次写入原子性

修复前是逐行 append，第二行 I/O 失败会留下第一行。

修复：在同目录建临时文件 → 写入"旧内容逐字节 + 完整新批次" → `flush` → `os.fsync`
→ **`os.replace` 作为唯一提交点**。提交点之前的任何异常都不改动原账本，
临时文件被清理。同目录是必要条件：`os.replace` 只在同一文件系统内原子。

append-only 语义保留：旧行原样重新写出，不编辑、不重排（有测试断言新文件以旧内容为前缀）。

**注入式故障测试**覆盖：第一行写失败、中途写失败、fsync 失败、提交点失败，
每种都验证账本新增 0 行且不留临时文件；另测失败后重试仍能正常提交、
重放仍幂等、修订链/冲突/dangling/cycle 继续 fail closed。

## factor_version 与 source capture

保持 fail-closed：无真实 `factor_version` 即拒整批，不生成默认版本号。
runner 里的 `SYNTHETIC_FIXTURE_v1` 已明确标注为合成夹具值，
synthetic capture id / hash **不是生产证据**。
真实 `factor_version` 与逐因子 source capture identity 仍待 F1R-B 解决。

## 文件

```text
INDEX.md                        本文件
F1R_A0_DATA_FLOW.md             数据流、三种证据规则、提交点与失败恢复语义
FACTOR_SOURCE_MAPPING.json      四因子真实来源逐项映射（含 F5/F6 阻塞原因）
OFFLINE_RECORDER_RESULT.json    机器可读结果与边界计数
F1R_A0_REFERENCE_LEDGER.jsonl   参考账本（SYNTHETIC_CONTRACT_FIXTURE）
TEST_RESULTS.md                 测试矩阵与故障注入逐条对应
OBSIDIAN_UPDATE_PROPOSAL.md     给 Codex 的 Vault 更新建议（不是更新证明）
HASHES.sha256                   本包哈希
```

## 边界

```text
PROVIDER_CALLS = 0            PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = 0       PRODUCTION_DB_WRITES = 0
DEPLOYMENT_EXECUTED = false
OBSIDIAN_ACCESS_MODE = READ_ONLY     OBSIDIAN_WRITES = 0
```

未修改 `src/w2/prematch`、`src/w2/strategy`、RecommendationDecisionV4、
`src/w2/api`、Dashboard、Scheduler、Provider allowlist、`migrations`、生产配置，
以及 F0/F1/F1P 冻结产物。`src/w2` 整棵树变更 0 字节。

下一步：**R1-A0 独立复验**。解除阻塞需要 F1R-B 把
`results.confirmed_at` 一类的真实来源观测时点接到因子 builder 消费的对象上，
那需要单独授权。
