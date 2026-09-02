# W2-LAMBDA-MULTIAXIS-DESIGN

状态：`DESIGN_ONLY_NOT_AUTHORIZED_FOR_IMPLEMENTATION`

本文件比较架构选项，不实现新架构、不拟合系数、不修改生产代码、参数、calibration identity 或运行环境。

## 1. 场景答案

问题：曼城以 3-4-3 派四名高身价前锋，曼联以 5-4-1 派五名高身价前锋时，W2 会如何理解？

当前诚实答案是：**概率模型无法理解这个跨队、按位置线和阵型展开的对抗关系。**

- 整队身价按 `LATEST_COMPLETE_SNAPSHOT_AT_OR_BEFORE_AS_OF` 聚合全部注册球员；改变首发位置组合不会改变 `squad_value_eur`。
- lineup 路径能计算确认首发身价、进攻/防守替换差、前场连续性等按位置线特征，但生产投影的 AH/TOTALS 数值调整固定为 `0.0`。
- 阵型只表达 `formation_changed: bool`，没有 3-4-3 偏进攻、5-4-1 偏防守的固定语义或学习参数。
- `derive_lineup_change_features()` 比较单队自己的预期首发与确认首发，不比较主队进攻线与客队防守线。
- API-Football statistics 原始响应可含射门，但 W2 的当前 materializer 只解析 `expected_goals / Expected Goals`，没有射门特征。

## 2. 九因子实测清单

`build_feature_set()` 固定组装九个 contribution。下表区分“算出 contribution”与“进入 lambda/probability”两个概念：

| contribution | 当前值来源 | 进入概率模型 | 当前实际作用 |
|---|---|---|---|
| `market_movement_factor` | 盘口时间线 | 否 | analysis reason 与 READY 计数 |
| `bookmaker_divergence_factor` | 机构报价 | 否 | analysis reason 与 READY 计数 |
| `rest_fitness_factor`（F3） | 球队历史 | 否 | analysis reason 与 READY 计数 |
| `match_importance_factor`（F4） | competition profile | 否 | analysis reason 与 READY 计数 |
| `recent_ah_cover_factor`（F5） | 球队历史盘口 | 否 | analysis reason 与 READY 计数 |
| `h2h_factor`（F6） | 历史交锋 | 否 | analysis reason 与 READY 计数 |
| `strength_form_factor`（F7） | rating snapshots | 否 | analysis reason 与 READY 计数 |
| `squad_value_factor`（F8） | value snapshots | 否 | analysis reason 与 READY 计数 |
| `true_xg_factor`（F9） | xG snapshots | 是，作为四字段 xG 的同源核心输入 | 决定基础 lambda total/delta |

上述八个非 xG contribution 的数值没有被 `_signal_strength()` 读取。该函数只计算 READY 数量：

```python
ready_count = sum(item.status == READY)
coverage_bonus = min(ready_count / 10, 0.25)
```

因此相反方向的同一因子，只要 READY 数相同，就产生相同 coverage bonus。这里的 `coverage_bonus` 是数据完整度奖励，不是因子评分。

另有三条不属于上述 FeatureSet contribution 的直接 lambda 输入通路：rating、整队身价、lineup strength。它们由 `calibrate_lambdas()` 单独消费；这不改变“九因子 contribution 中只有 xG 值进入概率”的结论。现役可观测性实现 `0b1e4fdb` 已把这些 lambda 贡献单列，避免把 READY 计数误写成数值贡献。

## 3. 当前两旋钮约束

当前核心形式是：

```text
base_home = (home_xg_for + away_xg_against) / 2
base_away = (away_xg_for + home_xg_against) / 2
total = clamp(base_home + base_away)
adjusted_delta = base_home - base_away + home + elo + value + lineup
lambda_home = (total + adjusted_delta) / 2
lambda_away = (total - adjusted_delta) / 2
```

除 gated `lineup_totals_adjustment` 外，非 xG 因子只能改变 delta，不能改变 total。于是模型能表达“主队相对强多少”，却不能自然表达“双方进攻都强、双方防守都弱，所以总进球上升”或其相反情形。

TOTALS 的既有诊断中，W2 resolution `0.006878` 约为市场 `0.012944` 的 53%，而 reliability `0.000474` 优于市场 `0.001739`。固定十等频/等宽分箱对集中预测可能不利，所以只将方向解释为“校准较好但分辨率偏钝”，不把 53% 当精确结构参数或方案裁决依据。

## 4. 共同需求：跨队位置线表达

无论选 A 或 B，输入层都应先形成可审计、PIT-safe 的 matchup tensor，而不是把阵型名字直接转成进球调整：

```text
home_attack_line  vs away_defence_line
away_attack_line  vs home_defence_line
home_midfield     vs away_midfield
home_goalkeeper   vs away_attack_line
```

每条线只使用 kickoff 前可知的确认首发、位置映射、球员价值/能力快照、缺阵与连续性；同时保留 source hash、captured_at、coverage 和缺失原因。输出至少分为：

- `home_attack_advantage`
- `home_defence_advantage`
- `away_attack_advantage`
- `away_defence_advantage`
- `midfield_control_delta`
- `formation_interaction`

缺失不得用联赛均值、默认零或当前身价回填历史。跨队 matchup 是两个方案共享的研究输入，不预先决定它作用在 lambda 还是 xG。

## 5. 阵型语义：手工编码与数据学习

### 手工编码

把阵型映射为后卫/中场/前锋人数和少量交互规则，例如 3-4-3 对 5-4-1。

- 优点：实现快、可解释、冷启动可用。
- 代价：阵型字符串不能表达边翼卫职责、球员实际站位或比赛内变化；专家规则容易把标签当战术真相。
- 适用：只作为展示/分组或学习模型的输入，不直接给生产 lambda 加固定分数。

### 从数据学习

以阵型、位置线构成、首发价值/连续性和对手位置线为交互输入，在严格 PIT cohort 上学习对目标 xG 或进球分布的影响。

- 优点：能估计同一阵型在不同人员与对手下的条件效果。
- 代价：需要大样本、稳定位置映射、阵型 first-seen、跨赛季漂移控制和预注册；共线性与稀疏组合风险高。
- 适用：数据覆盖和前向 cohort 足够后，作为 A/B 的共同实验输入。

建议先保存原始阵型与位置线，不预置进攻/防守分值；研究阶段并列比较简单人数编码与学习交互。

## 6. 三方案并列比较

| 维度 | 方案 A：lambda 多轴 | 方案 B：上游 xG 调整 | 方案 C：维持现状 |
|---|---|---|---|
| 核心形式 | 预测 `home_attack/home_defence/away_attack/away_defence`，可加 correlation/dispersion，再映射 lambda 与分布 | 先修正四字段 xG，再复用现有 `calibrate_lambdas` | 保留 xG total + delta 架构 |
| 表达 total | 直接、完整 | 通过调整后四字段 xG 自然改变 | 除 lineup totals gate 外基本不能 |
| 跨队位置线 | 模型原生交互 | 转成对手条件下的 xG 修正 | 不能表达 |
| 可解释性 | 中等；需解释四轴到 lambda | 高；效果以 xG 单位表达 | 高，但信息被丢弃 |
| 独立验证 | 需同时验证 lambda/比分分布 | 可先验证“调整后 xG 是否更接近实际 xG”，再验证进球 | 无新验证成本 |
| 迁移风险 | 高：新输出契约、identity、校准与分布验证 | 中：保留大部分下游契约，但必须防 target leakage/重复计入 | 低 |
| 模型自由度 | 较高 | 可从低维 additive/shrinkage 开始 | 不变 |
| 主要风险 | 过拟合、四轴不可辨识、分布层复杂度 | 调整目标 xG 与真实 xG source 定义漂移；下游又叠加同一信号 | 模型持续无法理解阵型/位置线，TOTALS 可能保持钝化 |

本文不预设 A 胜出。B 不是 A 的简化版：它多一个可独立检验的中间目标（调整后 xG），也可能以更低迁移成本解决 total 无法响应的问题。C 是有效 null：公开因子大概率已被市场定价，W2 速度也不占优势；如果 A/B 不能在干净 cohort 上改善 proper score，维持现状优于增加噪声与维护面。

## 7. 与 `calibrate_lambdas` 的兼容与迁移

方案 A：

1. 保留现役 `calibrate_lambdas` 作为固定 comparator，不原地改签名。
2. 新建独立候选 identity，输入为四轴与可选相关/dispersion，输出仍归一为 `lambda_home/lambda_away/score_matrix`。
3. 适配器仅服务离线预注册实验；通过独立验证前不接 production read model。
4. 只有候选通过后，才讨论版本化替换与旧 payload 兼容。

方案 B：

1. 在上游生成版本化 `adjusted_four_field_xg`，同时保留原始四字段、逐因子贡献和 PIT hash。
2. 原样调用现有 `calibrate_lambdas`；禁止在下游再叠加同一 lineup/value/rest 信号，避免双计数。
3. 先以未来实际 xG 作为中间验证，再以进球/AH/TOTALS proper score 作最终验证。
4. 通过前只作为 shadow artifact，不覆盖 canonical xG snapshot。

两方案都必须产生新 calibration/model identity；不得借兼容层沿用 `21960a…db71` 的 `APPROVED_VALIDATED` verdict。

## 8. 现有权重与 coverage bonus 的处置

`elo_gap_weight=0.28`、`squad_value_log_weight=0.18`、`lineup_adjustment_weight=0.08` 从未在真实数据上拟合；历史上对应输入长期为 proxy、`None` 或 `0.0`。A/B 均不得继承它们作为已校准权重：

- 新模型中全部从预注册训练设计重新估计或明确剔除；
- 冻结正则化、交互范围、缺失策略和比较门后才拟合；
- 不得用生产当前权重当 informative prior，除非另有独立依据并预先冻结。

`coverage_bonus` 有两个可选处置：

1. 推荐默认：改名为 `data_coverage_bonus`，明确仅表示可解释材料完整度，不进入概率、经济准入或“信号强度”含义。
2. 若要读取 contribution 数值：必须另建预注册的 factor score，规定方向、量纲、正交化和缺失语义；不能在现函数中把值简单相加。

在没有因子效果证据前，采用第 1 项更诚实，也最小化行为变化。

## 9. 工作量与分期

估算以单名熟悉仓库的工程人员为单位，不含等待前向样本时间：

| 阶段 | 内容 | A | B | 共同 |
|---|---|---:|---:|---:|
| P0 数据合同 | matchup tensor、PIT/provenance、coverage | - | - | 5-8 人日 |
| P1 研究实现 | 四轴生成模型与适配器 / adjusted xG shadow materializer | 8-12 人日 | 5-8 人日 | - |
| P2 预注册与离线验证 | split、score、bootstrap、泄漏审计 | 4-6 人日 | 4-6 人日 | 可共用大部分 |
| P3 产品接入候选 | payload、可观测性、兼容测试 | 6-10 人日 | 3-6 人日 | 仅通过后 |
| P4 独立验收/发布 | identity、registry、全量、部署证据 | 4-7 人日 | 4-7 人日 | 仅 Owner 授权后 |

建议顺序：先 P0；随后用同一冻结输入对 A/B 做最小 shadow 原型；在训练结果前冻结独立比较；任何一方未胜过 C 就停止该方。不要先重写生产 `calibrate_lambdas`。

## 10. 诚实边界

本方向不承诺跑赢市场。射门、身价、战绩、交锋与首发都是公开信息，市场能够看到同类数据，且庄家通常比 W2 更快。价值仅在于让 W2 的分析真实表达“谁的哪条位置线对谁形成什么影响”，并用可复核数据证明这种表达是否改善概率质量。

当前结论是设计比较，不是实施授权，也不改变今天的模型准确度。
