# W2 Decision Contract V1

Status: 提议（Proposed）。本文件是 W2 输出语义的**唯一真源**。一经接受，它**取代**以下文档中一切相互冲突的输出定义：`W2_STATE_MODEL_V1`（DecisionStatus 五态 + DisplayGrade A/B/C）、`W2_FORMAL_RECOMMENDATION_P0`（FORMAL/WATCH）、`ADR-0026`（ANALYSIS_PICK/RECOMMEND）。选定方向：**两档分层**。

## 为什么需要这份契约

今天"判断"在代码里有四套并存的词，dashboard 在读取时现场做考古来调和它们：

- `src/w2/dashboard/recommendations.py` 定义了一个五值枚举 `RecommendationTier = {FORMAL, CANDIDATE, ANALYSIS_PICK, WATCH, NO_RECOMMENDATION}`；
- `derive_recommendation_tier()` 读**四个不同字段**（`formal_recommendation`、`candidate`、`decision`、`analysis_decision`）去反推该显示哪一档；
- `src/w2/domain/enums.py` 里**根本没有**决策档位——`RecommendationStatus` 只有 `DRAFT/LOCKED`（那是生命周期，不是决策）。

结论：产品最核心的输出契约住在了**错误的层**（dashboard），而且说四种方言。任何"清楚判断"都无从谈起，因为系统自己没有一个"判断"的定义。

## 三条正交状态轴（保留，但收敛决策轴）

W2 的三轴设计本身是对的，问题只在决策轴分叉。收敛后：

**1. DecisionTier（决策轴 — 收敛为唯一枚举，落在 `domain/`）**

| 值 | 含义 | 是否面向用户 |
|---|---|---|
| `NOT_READY` | 系统/数据前置状态缺失，尚未评估 | 是（灰） |
| `SKIP` | 已评估：覆盖或数据不足，不产出任何盘口观点 | 是（灰，带 reason_code） |
| `WATCH` | 上下文足够，值得盯，但不足以给出观点 | 是（带 reason_code + 重评时间） |
| `ANALYSIS_PICK` | **W2 的默认"正式推荐"**：分析级、透明因子、带风险与失效条件、`分析参考·非稳赢` | 是（首屏主卡） |
| `RECOMMEND` | 保留上档：需**独立前向证明的正 EV**。**默认关闭**，非产品必需 | 默认不产出 |

**2. LifecycleStatus（生命周期轴 — 不变）**：`DRAFT / LOCKED / SUPERSEDED / VOID / SETTLED`。`LOCKED` 内容不可变，修改产生新版本 + `SUPERSEDED`；`SETTLED` 只追加结果。

**3. DataStatus（数据轴 — 不变，喂给就绪门）**：`READY / PARTIAL / STALE / BLOCKED`。`BLOCKED` 不可进入 `ANALYSIS_PICK/RECOMMEND`；`STALE` 不可 `LOCKED`；`RECOMMEND + LOCKED` 要求 `READY`。

> 一句话读法：**DataStatus 决定"能不能判"，DecisionTier 决定"判成什么"，LifecycleStatus 决定"这张判断处于生命周期哪一步"。** 三者正交，任何卡片同时各持一个值。

## 关键决定："正式推荐" = `ANALYSIS_PICK`

从此刻起，产品面向用户的**"正式推荐"就是 `ANALYSIS_PICK`**。停止把它叫"非正式推荐"。它诚实、每天都能稳定产出、符合 ADR-0026。它必须携带免责声明 `分析参考·非稳赢`，禁止一切确定性措辞（稳赢/必中/保证/包赢）。

`RECOMMEND` 是**未来**的上档，默认 `false`，只有独立的前向正 EV 证据（Gate4/Gate5）才能点亮。它**不是**产品跑起来的前提，也**不得**在缺证据时压制 `ANALYSIS_PICK` 的产出。

## 退役映射（这些词从输出枚举里消失）

| 旧词 | 归宿 |
|---|---|
| `FORMAL` | 折叠进 `ANALYSIS_PICK`。"实数据 + 模拟就绪 + 方向自洽"从此是 `ANALYSIS_PICK` 的**前置条件**，不再是独立档位 |
| `CANDIDATE` | 从**输出**枚举移除。它本是内部/系统预备态；对用户而言"在评估但还没有观点"就是 `WATCH` |
| `NO_RECOMMENDATION` | 等价于 `SKIP`，合并 |
| DisplayGrade `A/B/C/NA` | 废弃。展示层不再有 B/C 这种"半官方"灰色地带；档位即展示 |
| 卡片 flag `formal_recommendation` / `candidate` | 废弃。由单一字段 `decision_tier` 取代 |

## 统一卡片契约（每张卡、每一档，同一信封）

每个 fixture 每天产出**恰好一张** DecisionCard：

```
DecisionCard {
  fixture_id, competition_id, kickoff_utc, kickoff_beijing
  decision_tier            # DecisionTier 之一（唯一决策字段）
  data_status              # DataStatus 之一
  lifecycle_status         # LifecycleStatus 之一
  model_version, card_hash # 确定性哈希，同输入同版本必同哈希
  provenance[]             # 每个输入的来源 + 采集时间戳

  # 仅当 decision_tier == ANALYSIS_PICK / RECOMMEND：
  pick {
    market, selection, line, odds
    fair_line, market_line, value_edge
    key_factors[]          # 透明的独立因子
    risks[]
    invalidation[]         # 失效条件（什么发生就作废）
    disclaimer = "分析参考·非稳赢"
  }

  # 仅当 decision_tier == NOT_READY / SKIP / WATCH：
  non_pick {
    reason_code            # 见下（可执行原因）
    reason_human           # 一句人话
    action                 # 需要发生什么才可能改判
    next_eval_at           # 下一次自动重评时间
  }
}
```

## 非推荐 = 可执行原因（reason_code 分类法）

"不能出就给可执行原因"——每个非推荐**必须**带一个 reason_code，且每个 reason_code 绑定 `action` 与 `next_eval_at`。禁止只丢一个裸 `WATCH`。

| reason_code | 人话 | action | 典型 next_eval |
|---|---|---|---|
| `DATA_MISSING_XG` | 缺关键 xG | 等待 xG 回填任务 | 下一个 backfill tick |
| `DATA_STALE_ODDS` | 盘口线过期 | 触发盘口刷新 | T-90m 刷新点 |
| `LINEUPS_PENDING` | 首发未出 | 等官方首发 | 开球前 ~60m |
| `MARKET_UNAVAILABLE` | 该盘口无线 | 换盘口或等开盘 | 下一刷新点 |
| `EDGE_INSUFFICIENT` | 有观点但价值不够 | 盯价格变动 | T-30m |
| `CONTRADICTION_UNEXPLAINED` | 因子方向与价值方向冲突且无"盘口价值"解释 | 人工复核或补解释 | 人工 |
| `COVERAGE_NONE` | 联赛/赛事未覆盖 | 不承诺，降级 SKIP | 不重评 |
| `FIXTURE_LIVE_OR_FINISHED` | 已开赛/已结束 | 赛前窗口关闭 | 无 |

## 硬不变量（沿用 `W2_ACCEPTANCE_METRICS_V1`，不可违反）

无赛前泄漏；LOCKED 卡片证据链完整；同输入同版本卡片哈希确定；原始 payload 不可变；失败推荐保留不删；赛后不得改写赛前概率；不存在被迫推荐；`RECOMMEND` 必须带反方论据与失效条件。Edge / 命中率 / CLV 等一律为 `CALIBRATION_REQUIRED`，是赛后复盘指标，**不是**开档门槛。

## 落地检查（此契约"进了代码"的判定）

- `domain/enums.py` 出现唯一的 `DecisionTier`，五个值如上；
- 卡片只有一个 `decision_tier` 字段，`formal_recommendation` / `candidate` 两个 flag 删除或仅存于迁移 shim；
- `dashboard/recommendations.py` 的 `derive_recommendation_tier()` 退化为**直接读 `decision_tier`**，删掉四字段考古；
- `grep -rE "\b(FORMAL|CANDIDATE|NO_RECOMMENDATION)\b" src/w2 --include=*.py` 只剩归档/迁移代码；
- 每个非推荐卡片都带 `reason_code + action + next_eval_at`。
