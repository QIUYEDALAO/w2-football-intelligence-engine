# W2 Decision Contract V2（收敛版）

Status: 已决，执行中。本文件是 W2 输出语义的**唯一真源**，取代 `W2_STATE_MODEL_V1`、`W2_FORMAL_RECOMMENDATION_P0`、`ADR-0026` 中一切相互冲突的输出定义。方向：**收敛不重写；展示 ≠ 可锁。** 2026-07-08 老板拍板：`lock_eligible ⇔ RECOMMEND`。

## 相对 V1 的变更（评审后）

| # | V1 的问题 | V2 的修正 | 来源 |
|---|---|---|---|
| 1 | 把 `ANALYSIS_PICK` 直接叫"正式推荐" | **拆两层出口**：`ANALYSIS_PICK` = 分析推荐（可展示、不可锁）；`lock_eligible / RECOMMEND` = 正式可锁推荐。展示推荐与可锁推荐分开 | 副经理评审 |
| 2 | "删除 `formal_recommendation / candidate` 旧字段" | 改为**迁移 shim**：只在写入路退役，读路保留兼容，历史锁定快照永不回写。已确认这些字段被 18 个模块读，含 `settlement/settle.py`、`settlement/history.py`、`audit_export/tables.py`、`tracking/formal_results.py` | 副经理评审 + 代码核实 |
| 3 | 决策档收敛为单枚举 | 单枚举**保留**，但补三个正交治理字段（见下），把 V1 误砍的 lock-eligibility 轴接回来 | 本次补充：settle ≠ lock ≠ +EV |
| 4 | — | 明确 `ANALYSIS_PICK` **可结算/被追踪但不可锁定**，让复盘覆盖 95% 的日常卡片 | 本次补充 |

## 核心原则一句话

**DataStatus 决定"能不能判"，DecisionTier 决定"判成什么"，`lock_eligible` 决定"能不能锁/能不能动作"，`outcome_tracked` 决定"进不进复盘"。四者正交，任何卡片各持一个值。** 展示一张分析推荐，和把它锁成正式可动作推荐，是两件事。当前已决口径：只有 `DecisionTier.RECOMMEND` 才能 `lock_eligible=true`。

## 决策轴：唯一的 `DecisionTier`（落在 `domain/`）

| 值 | 含义 | 面向老板的说法 |
|---|---|---|
| `NOT_READY` | 前置状态/数据缺失，尚未评估 | 未就绪 |
| `SKIP` | 已评估：覆盖或数据不足，不产出观点 | 今日不覆盖 |
| `WATCH` | 上下文足够、值得盯，但不足以给观点 | 观察比赛 |
| `ANALYSIS_PICK` | **分析推荐 / 可展示推荐**：透明因子 + 风险 + 失效条件 + `分析参考·非稳赢`。**可展示、可结算追踪，但默认不可锁** | 今日分析推荐 |
| `RECOMMEND` | **正式可锁推荐上档**：需独立前向证据。默认关闭 | 今日正式可锁推荐 |

> 术语纪律：`ANALYSIS_PICK` **不叫"正式推荐"**。面向老板首屏两个数字分开——「今日正式可锁推荐数量」= `lock_eligible` 卡片数；「今日分析推荐数量」= `ANALYSIS_PICK` 卡片数。禁止一切确定性措辞（稳赢/必中/保证/包赢）。

## 三个正交治理字段（把 V1 误砍的轴接回来）

"可锁"过去被一个词捆了三件不同的事，V2 拆开：

1. **`outcome_tracked`（可结算/被追踪）**：有 id、进 outcome 链，复盘能回答"当时判了什么、后来结果如何"。
2. **`lock_eligible`（可锁定/可动作）**：当且仅当 `decision_tier == RECOMMEND`。这是老板拍板的 B 方案，不再由 staging 完整性门直接授予。
3. **`RECOMMEND` / +EV 已证明**：最高门槛，默认关。实数据 + 未来 kickoff + 盘口线完整 + 具 `recommendation_id` + 前向 EV 证据，是进入 `RECOMMEND` 的前置条件，不得被降格为 `ANALYSIS_PICK` 的可锁理由。

**为什么必须拆：** 若三件捆成一个 `lock`，则 `ANALYSIS_PICK` 只展示、不进 outcome 链 → 日常分析推荐永远没有战绩 → 复盘对 95% 的卡片无从结算 → 也永远攒不出点亮 `RECOMMEND` 所需的前向证据（先有蛋才有鸡）。

**V2 规定：`ANALYSIS_PICK` 的 `outcome_tracked=true`、`lock_eligible=false`（settle ≠ lock）。** 既守住公信力防火墙（分析观点绝不冒充可下单），又让每天的推荐有真实战绩、顺带喂养未来的 `RECOMMEND`。

## ✅ 已决的可锁语义：B（2026-07-08 老板拍板）

| 选项 | 后果 | 老板需接受 |
|---|---|---|
| A. 不绑（已否决） | 可锁 = 过数据/kickoff/盘口完整性门；`+EV` 另算给 `RECOMMEND` | 风险：分析参考被误读为可动作推荐 |
| **B. 绑（已决）** | 可锁 = `RECOMMEND` = 需前向 +EV 证据 | 每天有分析，但正式可锁推荐可能**连续多天为 0** |

> 落地规则：`lock_eligible ⇔ RECOMMEND`。`ANALYSIS_PICK` 继续 `outcome_tracked=true`，继续进入 CLV/战绩积累，但必须 `lock_eligible=false`。EV/RECOMMEND 腿仍默认关闭，R3.0 前向门槛一字不动。

## 保留的两条正交状态轴（不变）

- **LifecycleStatus**：`DRAFT / LOCKED / SUPERSEDED / VOID / SETTLED`。`LOCKED` 不可变，改动产生新版本 + `SUPERSEDED`；`SETTLED` 只追加结果。
- **DataStatus**：`READY / PARTIAL / STALE / BLOCKED`。`BLOCKED` 不可进 `ANALYSIS_PICK/RECOMMEND`；`STALE` 不可 `LOCKED`；`RECOMMEND + LOCKED` 要求 `READY`。由**单一数据就绪门**产出（见路线图 Step 2）。

## 统一卡片契约：DecisionCard

每个 fixture 每天产出**恰好一张**：

```
DecisionCard {
  fixture_id, competition_id, kickoff_utc, kickoff_beijing
  decision_tier            # DecisionTier 之一（唯一决策字段）
  data_status              # DataStatus 之一
  lifecycle_status         # LifecycleStatus 之一

  # —— 治理字段（正交）——
  outcome_tracked          # bool：true 于 ANALYSIS_PICK 及以上，进复盘/结算（只读）
  lock_eligible            # bool：true iff decision_tier == RECOMMEND
  recommendation_id        # 仅锁定提交时铸；非锁为 null
  model_version, card_hash # 确定性哈希，同输入同版本必同哈希
  provenance[]             # 每输入的来源 + 采集时间戳
  market_probabilities     # 展示用市场概率一律 POWER devig；method 必须写入 provenance/概率对象

  # —— 仅当 decision_tier ∈ {ANALYSIS_PICK, RECOMMEND} ——
  pick {
    market, selection, line, odds
    fair_line, market_line, value_edge
    key_factors[], risks[], invalidation[]
    disclaimer = "分析参考·非稳赢"   # ANALYSIS_PICK 强制
  }

  # —— 仅当 decision_tier ∈ {NOT_READY, SKIP, WATCH} ——
  non_pick {
    reason_code, reason_human, action, next_eval_at
  }
}
```

## 非推荐 = 可执行原因（reason_code 分类法）

每个非推荐**必须**带 `reason_code`，且绑定 `action` 与 `next_eval_at`，禁止裸 `WATCH`。

| reason_code | 人话 | action | 典型 next_eval |
|---|---|---|---|
| `DATA_MISSING_XG` | 缺关键 xG | 等 xG 回填 | 下一 backfill tick |
| `DATA_STALE_ODDS` | 盘口线过期 | 触发盘口刷新 | T-90 刷新点 |
| `LINEUPS_PENDING` | 首发未出 | 等官方首发 | 开球前 ~60m |
| `MARKET_UNAVAILABLE` | 该盘口无线 | 换盘口/等开盘 | 下一刷新点 |
| `EDGE_INSUFFICIENT` | 有观点但价值不够 | 盯价格变动 | T-30 |
| `PROVIDER_BUDGET_EXHAUSTED` | 当日 provider 预算耗尽，数据降级 | 等下一 tick 预算 | 下一 tick |
| `CONTRADICTION_UNEXPLAINED` | 因子与价值方向冲突且无"盘口价值"解释 | 人工复核 | 人工 |
| `COVERAGE_NONE` | 赛事未覆盖 | 降级 SKIP | 不重评 |
| `FIXTURE_LIVE_OR_FINISHED` | 已开赛/结束 | 赛前窗口关闭 | 无 |

## 退役映射（迁移 shim，不删除）

| 旧词/字段 | 归宿 | 迁移规则 |
|---|---|---|
| `RecommendationTier.FORMAL` | 折叠：其语义（实数据+模拟就绪+方向自洽）成为 `RECOMMEND` 的前置条件，不直接授予新写入路 `lock_eligible` | 读路 shim 保留 |
| `RecommendationTier.CANDIDATE` | 从**输出**枚举移除；"在评估未成观点" = `WATCH` | 读路 shim 保留 |
| `RecommendationTier.NO_RECOMMENDATION` | = `SKIP`，合并 | 读路 shim |
| 卡片 flag `formal_recommendation` | 新写入路由 `decision_tier==RECOMMEND` + `lock_eligible` 表达 | **只退写入路**；读路兼容；历史 LOCKED 快照**永不回写** |
| 卡片 flag `candidate` | 由 `decision_tier` 表达 | 同上 |
| DisplayGrade `A/B/C/NA` | 废弃；档位即展示 | — |

> 迁移铁律：`settlement`、`audit_export`、`tracking`、历史复盘读到的**旧锁定快照原样不动**。shim 只做"旧字段 → 新字段"的只读映射，绝不重写已冻结数据。这正是系统 append-only / 可复现不变量的要求。

## 硬不变量（沿用 `W2_ACCEPTANCE_METRICS_V1`）

无赛前泄漏；LOCKED 证据链完整；同输入同版本卡片哈希确定；原始 payload 不可变；失败推荐保留；赛后不得改写赛前概率；无被迫推荐；`RECOMMEND` 必带反方论据与失效条件。Edge/命中率/CLV 为 `CALIBRATION_REQUIRED`，是赛后复盘指标，非开档门槛。

## R3.0 `RECOMMEND` / EV 腿重开预注册门槛

`RECOMMEND` / EV 腿默认关闭。任何人不得仅凭离线 log-loss、离线 +EV、历史回测命中率或单次看起来优秀的 dashboard 数字打开这条腿。

重开 `RECOMMEND` / EV 腿必须同时满足以下**前向**证据，且按单联赛独立验收：

1. **样本量**：该联赛已积累不少于 200 张前向赛前 DecisionCard，且每张卡的输入、盘口、概率源、决策时间、赛后结果与卡片哈希可复现。
2. **CLV**：该联赛前向样本的 CLV 中位数 `> 0`，且计算口径固定为赛前记录盘口对收盘盘口，不得事后换 bookmaker、换盘口线或剔除不利样本。
3. **市场基准**：滚动 blend `w* < 1` 且稳定优于纯市场基准；如果最优 blend 仍为 `w*=1`，说明模型对市场无增量，`RECOMMEND` 必须继续关闭。

离线 LL、离线 +EV、离线拟合改善、单场主观强信号只能作为研究或排序参考，**不得作为 `RECOMMEND` / EV 腿开关依据**。若未来重开，必须新增一份 R3.0 前向验收报告，列出样本窗口、CLV 分布、滚动 blend、失败样本与回滚条件。

## 分歧雷达放行规则（预注册，2026-07-08）

市场锚定期允许记录 `shadow_pick`，用于积累模型相对市场的方向证据；`shadow_pick` 必须标记 `not_a_recommendation=true`、`not_displayed=true`，不得作为展示推荐、可锁推荐、命中率或 production 动作依据。真实展示层的 `direction_allowed` 默认保持 false。

单联赛满足以下全部条件，方可经**单独批准 PR** 将该联赛 `direction_allowed` 置 true。放行必须按联赛白名单实施，禁止全局开关：

1. shadow CLV 样本 `>=100`；
2. shadow CLV 中位数 `>0`；
3. 该联赛最近一次 `market_baseline_eval` gap `<=0.04`。

放行后真实 pick 才开始积累，R3.0 的 `>=200` 真实 pick CLV 门槛仍在真实轨上计算，门槛数字不变。修改本规则必须留下评审记录。

`model_market_divergence.magnitude` 的单位为 AH 线差；当前默认门槛为 `0.25` 线差。概率空间阈值待展示概率分档后另行预注册。

## 落地检查（此契约"进了代码"的判定）

- `domain/enums.py` 出现唯一 `DecisionTier`（五值）；
- 卡片有 `decision_tier` + `outcome_tracked` + `lock_eligible` + `recommendation_id` 四字段；`formal_recommendation/candidate` 仅存于 shim；
- `compute_lock_eligible()` 当且仅当 `decision_tier==RECOMMEND` 返回 true；实数据/未来 kickoff/盘口完整/`recommendation_id`/前向 EV 证据作为 `RECOMMEND` 上档前置条件，而不是 `ANALYSIS_PICK` 可锁理由；
- `dashboard/recommendations.py:derive_recommendation_tier()` 退化为直接读 `decision_tier` + 治理字段，删掉四字段考古；
- `settlement / audit_export / tracking` 对历史快照的读取行为零变化（回归测试证明）；
- 每张非推荐卡带 `reason_code + action + next_eval_at`；
- 首屏「正式可锁推荐」「分析推荐」两个计数分别来自 `lock_eligible` 与 `decision_tier==ANALYSIS_PICK`。
