# F1R-A0 数据流：从活对象到 F1P 观测

```text
TASK_ID   W2_AH_FACTOR_ACCURACY_F1R_A0_20260910
阶段      F1R-A0_OFFLINE_FACTOR_RECORDER（Freeze A0 离线实装）
```

## 1. 为什么 F1R-A0 拿得到 F1 拿不到的东西

F1 的结论是历史 336 个单元 exact PIT 为 0，根因是**逐因子证据时点从未被序列化**：
分析卡的 `feature_contributions` 只有 10 个字段，没有 `observed_at`。

但那是**序列化之后**的形态。评估当时的活对象 `FeatureContribution` 是有的：

```text
src/w2/features/framework.py
  observed_at: datetime | None     __post_init__ 里经 require_utc 强制 UTC
  weight:      float               team_score.py 求 weight_sum_used 时消费的就是它
  score / status / reason / inputs / source / collection_status
```

所以差别不是"要不要更严格"，而是**记录时机**：在评估当时记录，
逐因子证据时点与实际生效权重都在手上；事后从卡片重建，它们已经不存在了。

这也是 F1R-A0 只做**离线记录器**、不碰现役链的原因——先把契约与端口做实，
接线是 F1R-B 的事。

## 2. 四因子的真实来源（只读定位，逐项见 FACTOR_SOURCE_MAPPING.json）

```text
F3_REST_FITNESS     team_factors.rest_fitness_factor
                    observed_at = max(主/客最近一场 kickoff_at)
F5_RECENT_AH_COVER  team_factors.recent_ah_cover_factor
                    observed_at = max(所用 canonical 已结算 AH 行的 kickoff_at)
F6_H2H              team_factors.h2h_factor
                    observed_at = max(历史交锋 kickoff_at)
F9_TRUE_XG          live_factors.true_xg_factor
                    observed_at = max(主/客 TeamXgSnapshot.observed_at)
```

四者的 **ready 分支全部设置 `observed_at`**，**缺数据分支全部不设**。
这不是缺陷，是正确的：没有证据就没有证据时点。

`applied_weight` 一律取 `FeatureContribution.weight`——即 `team_score.py`
实际累加进 `weight_sum_used` 的那个值，**不是**从
`config/factors/factor_registry.v1.json` 读的（那份注册表根本没有数值权重）。

**`factor_version` 当前无来源**：四个 builder 都不产出版本号。记录器因此要求
调用方逐因子提供，缺失即拒绝整批，**不自造版本号**。真正的版本来源属于 F1R-B。

## 3. 缺数据时的证据时点

契约要求每条观测都有 `evidence_time_utc < evaluated_at_utc`。
但缺数据的因子没有 `observed_at`。处理方式：

```text
PARTICIPATED   evidence_time = observed_at
               语义 LATEST_UNDERLYING_OBSERVATION
               缺 observed_at → 拒绝（PARTICIPATED_WITHOUT_OBSERVED_AT）

缺数据状态      evidence_time = FeatureContext.as_of
               语义 SOURCE_QUERIED_AT_AS_OF
```

`as_of` 是"我们去看的那一刻"，是真实且经 UTC 校验的每次评估事实。
对一次**缺席**而言，可证明的证据时点就是观察到缺席的时刻——
这不是给不存在的数据编一个观测时间。

语义标签写进 `factor_inputs.evidence_time_semantics`，**逐条可审计**。
两种语义永不混用：参与的因子不允许用 as_of 顶替真实观测时点。

**F1P 合同一个字节未改。** 语义标签走 `factor_inputs` 这个既有自由映射，
不是新增合同字段，也不是降级。

## 4. 批次流程

```text
build_batch(feature_set, context, …)
  ├ market != ASIAN_HANDICAP        → MARKET_OUT_OF_CONTRACT
  ├ context.fixture_id != feature_set.fixture_id → FIXTURE_ID_MISMATCH
  ├ 抽取四因子；重复 → DUPLICATE_FACTOR_ID
  ├ 缺任一 → INCOMPLETE_BATCH_MISSING_FACTOR
  └ 逐条 observation_from_contribution（含赛果字段泄漏检查）

append_batch(ledger, batch)
  ├ 四条全部 contract.validate（PIT、身份、状态、权重）
  ├ _batch_coherence：evaluation/attempt/fixture/evaluated_at/market 必须唯一，
  │                   factor 集合必须恰好是四个且不重复
  ├ 逐条比对既有账本：同 id 同内容 → 幂等；同 id 异内容 → 冲突
  ├ supersedes：目标必须存在、必须给理由、不得成环
  └ 全部通过后**一次性**写入；任一步失败则文件未被打开，磁盘 0 新行
```

**原子性靠"先全验再写"实现**，不是靠事务：文件在校验全部通过之前根本不会被打开。

## 5. 边界

记录器与运行器都不 import 网络、数据库、`w2.prematch`、`w2.strategy`、
`w2.api`、`w2.dashboard`、`w2.providers`、`w2.ingestion`、`w2.scheduler`、
`w2.infrastructure`（AST 断言）。身份全部来自 F1P，模块内不出现 `hashlib`，
也不定义任何 `canonical` / `sha256` / `identity_hash` 函数（AST 断言）。

只 import 了 `w2.features` 与 `w2.competitions.registry`——这正是 §4 要求的
"用真实四因子来源"，不是绕过。因此 package matrix 里这两个包各 +2 个 scripts caller，
已用机械生成器同步（2 增 2 删）。
