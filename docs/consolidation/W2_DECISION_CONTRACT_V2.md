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

  fair_market_estimate_ids[]  # DecisionCard/pick/settlement/replay/audit 的唯一引用键
  fair_market_estimate_snapshots[] {
    schema_version = "w2.fme_snapshot.v2"
    estimate_id, model_basis_id, fixture_id
    market                 # ASIAN_HANDICAP | TOTALS
    status                 # READY | INSUFFICIENT | INVALID
    fair_line, probabilities
    home_mu, away_mu
    score_matrix           # 冻结的完整比分矩阵；replay 不得按当前代码重新推导
    model_one_x_two_probabilities
    model_fair_ah, model_fair_ou
    model_score_distribution
    model_settlement_distributions  # 同一矩阵在公平线及 quote line 的五态分布
    effective_cover_index  # 不是 win_probability；语义见 effective_cover_index_semantics
    distribution_context { # DC rho、12 球截断、Decimal12、残差和公平线规则
      distribution_family, dixon_coles_rho, max_goals, tail_policy
      matrix_mass_before_normalization, probability_quantization
      negative_tau_policy, normalization_residual_policy
      fair_line_candidate_grid_ah, fair_line_candidate_grid_totals
      fair_line_tie_break_policy, settlement_rules_version
      fair_line_rules_version, score_matrix_hash
    }
    semantic_status        # VERIFIED iff 可由冻结输入重算全部模型语义
    evidence_eligible      # true iff v2 integrity + semantics 均通过
    input_context {
      odds_snapshot_hash, feature_snapshot_hash
      odds_snapshot, feature_snapshot
    }
    model_context {
      model_family, artifact_hash, artifact_version
      train_cutoff, feature_as_of, dixon_coles_rho
    }
    integrity { estimate_hash, created_at }
  }
  fair_market_estimates[]  # 仅旧客户端兼容视图；新消费者不得按字段重新拼 provenance

  analysis_gate {
    estimate_id            # 指向 fair_market_estimate_snapshots
    market                 # 当前主方向；另一市场保留在 analysis_gates/L2
    status                 # ELIGIBLE | ACCUMULATING | NO_EDGE | BLOCKED
    market_ready, model_ready, evidence_ready, direction_allowed
    divergence_line_units, threshold_line_units
    blockers[], next_eval_at
  }

  # —— 仅当 decision_tier ∈ {ANALYSIS_PICK, RECOMMEND} ——
  pick {
    market, selection, line, odds, estimate_id
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
| `LINEUPS_PENDING` | 首发增强待公布（不阻塞分析推荐） | 使用球队模型继续评估 | 仅支持已验证首发增强的联赛临场重算 |
| `MARKET_UNAVAILABLE` | 该盘口无线 | 换盘口/等开盘 | 下一刷新点 |
| `EDGE_INSUFFICIENT` | 有观点但价值不够 | 盯价格变动 | T-30 |
| `PROVIDER_BUDGET_EXHAUSTED` | 当日 provider 预算耗尽，数据降级 | 等下一 tick 预算 | 下一 tick |
| `CONTRADICTION_UNEXPLAINED` | 因子与价值方向冲突且无"盘口价值"解释 | 人工复核 | 人工 |
| `COVERAGE_NONE` | 赛事未覆盖 | 降级 SKIP | 不重评 |
| `FIXTURE_LIVE_OR_FINISHED` | 已开赛/结束 | 赛前窗口关闭 | 无 |
| `MODEL_FAIR_LINE_UNAVAILABLE` | 盘口已齐但独立模型尚无可信 fair line | 等模型/特征就绪 | 下一模型评估点 |
| `NO_EDGE` | 模型与市场线差不足 0.25 球 | 保持观察，不降低阈值凑数 | 下一盘口刷新点 |
| `FORWARD_EVIDENCE_ACCUMULATING` | 模型有方向但该联赛该市场前向证据未过门 | 继续积累 shadow CLV/outcome | 下一 R1.1 检查点 |

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

## 分歧雷达放行规则（预注册，2026-07-10 修订）

市场锚定期允许记录 `shadow_pick`，用于积累模型相对市场的方向证据。自 2026-07-11 起，老板取消「满 100 个前向样本才能展示 `ANALYSIS_PICK`」的前置门：staging 中只要市场盘口完整、验证模型 fair line 可用且线差至少 `0.25`，即可展示 `ANALYSIS_PICK`，并强制标记「分析参考·非稳赢·前向验证中」。`direction_allowed/evidence_ready` 继续记录证据成熟度，但不再阻塞 staging 分析推荐；production 仍 fail closed。

以下条件改为「前向验证成熟度 / 正式升级」门，不再是 staging `ANALYSIS_PICK` 的展示前置。每个“联赛 + 市场（AH / TOTALS）”满足以下全部条件，方可经**单独批准 PR** 进入更高信任层或后续正式放行评审。AH 与 TOTALS 必须分别评估：

1. 不同 fixture 的有效同线 shadow CLV 样本 `>=100`；
2. 同线 decimal shadow CLV 中位数 `>0`；
3. 对应市场最近一次 `market_baseline_eval` gap `<=0.04`；
4. entry window 达标率 `>=80%`；
5. 有效赛前 closing pair 覆盖率 `>=80%`；
6. 可结算比赛 outcome 覆盖率 `>=90%`；
7. provider 日用量始终 `<=120`。

满足以上条件只产生 `ELIGIBLE_FOR_REVIEW`，不得自动放行。证据缺失、过期或任一指标退化时必须 fail closed 回 `WATCH`。

放行后真实 pick 才开始积累，R3.0 的 `>=200` 真实 pick CLV 门槛仍在真实轨上计算，门槛数字不变。修改本规则必须留下评审记录。

AH 与 TOTALS 的方向门槛均为 `0.25` 球线差。展示概率仍来自主线盘口的 POWER devig；模型输出只提供 fair line、分歧与解释。首发缺失是 advisory，不是 `ANALYSIS_PICK` 硬门。`ANALYSIS_PICK` 不设每日全局数量上限：每场比赛独立通过 `analysis_gate` 即保留分析推荐资格，排序只影响展示顺序，不得把第 N 场以后降级为 `WATCH`。允许无信号时为 0，禁止降低阈值凑数。

### Analysis Gate V2 Shadow Challenger（预注册，2026-07-12）

`analysis_gate_v2_shadow` 只使用当前 `analysis_gate` 已选择的市场方向、同一个
`estimate_id` 冻结的五态结算概率及捕获时实际赔率，计算亚洲盘净 EV。研究标签固定为：
`net_ev >= 2%`、`LOSS <= 35%`、`HALF_LOSS + LOSS <= 55%`。该标签始终
`shadow_only=true`、`affects_decision=false`，不得改变 pick、DecisionTier、lock、
`ANALYSIS_PICK` 或 `RECOMMEND`。

证据按“联赛 + 市场”分开累计，AH 与 TOTALS 不得合并。每组记录覆盖率、CLV、ROI、
EV 校准、最大回撤及样本日期范围。已结算 challenger 样本达到 35 个仅标记
`REVIEW_ELIGIBLE`，达到 100 个标记 `MATURE`；两者都只允许发起人工升级评审，禁止
自动放行或修改现行 divergence gate。正式/验证结算不得混入 challenger 样本，只有
`settled_side=shadow_pick` 的 outcome 可进入该证据流。

AH Strict Shadow v1 的策略阈值由随 wheel 发布的版本化 policy 固定，并以
`strict_gate_hash` 绑定；环境变量不得静默覆盖。AH 候选即使单次通过阈值也只能标记
`CONFIRMATION_PENDING`。只有同一 fixture、AH market、`model_basis_id` 与方向下的两条
不同 `quote_id`，间隔至少 15 分钟，且均位于 T-24h 至 T-30m、均为有效 Snapshot v2
证据、最新一次仍通过阈值时，才可成为 Strict Shadow PASS。每次 PASS 必须冻结两组
`estimate_id + quote_id` evidence binding。方向反转为 FAIL；model basis 改变会重置确认
窗口。Strict PASS 始终 `shadow_only=true`、`visible_eligible=false` 且不得影响 decision、
pick 或 tier；AH 可见层继续 WATCH。该双确认不改变 TOTALS challenger 的既有语义。

AH 方向集中度治理只读取具有完整 canonical performance identity 的 corrected、已结算
AH shadow evidence，并按 distinct fixture 去重。分别统计 HOME_AH/AWAY_AH、主让/客让、
主受让/客受让/0 盘、0.25/0.75/0.5/整数盘口、联赛、artifact 与 strategy version。
不足 8 场为 `INSUFFICIENT_SAMPLE`；最近 8 场全部同方向为 `EARLY_WARNING`；最近 10 场
9 场或以上同方向为 `BLOCKED`；恰好 8 场为不阻断的 `WARNING`。该状态只作安全治理，
不得自动改模型、改变 decision/pick/tier 或断言模型已被证明存在方向偏差。

### 可选首发与球员价值增强（2026-07-11）

`lineups` 与 `team_value` 不属于 `missing_fields` 硬缺失，不得降低
`analysis_gate=ELIGIBLE`，也不得成为主要 `reason_code`。DecisionCard 通过
`optional_enrichment.lineups`、`optional_enrichment.player_value` 公开其真实状态；
没有经过独立 walk-forward 验证的球员影响模型时，`affects_estimate=false`、
`PlayerImpactEstimate.status=NOT_SUPPORTED`、`net_adjustment=0`。只有证明能改善
联赛级市场 gap 的已验证模型才允许 `APPLIED`，并必须携带完整 provenance。

等待首发本身不得安排 T-90 重评。只有 `lineups.affects_estimate=true` 的联赛才可
保留临场首发重算点。未经授权不得抓取 Transfermarkt；授权数据源、capability probe
和 provider 调用均须单独审批。

### 推荐、结算概率与比分分布同源契约

- 推荐盘口、该盘口的 `WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS` 概率与参考比分必须由同一 `FairMarketEstimate` 的 `home_mu/away_mu` 比分分布生成。
- `scoreline_reference.source` 必须为 `fair_market_estimate`，并通过 pick 的 `estimate_id` 解析唯一不可变 snapshot；比分、结算、回放和审计不得各自拼接 provenance 字段。
- `estimate_id = fme_<estimate_hash>`；hash 覆盖 fixture、market、模型输出、输入快照及模型 artifact，上下游必须验证 integrity。`created_at` 属于捕获时间，不改变内容 ID。
- `model_basis_id = fmb_<model_basis_hash>`；只覆盖 fixture、market、feature/artifact、distribution context、模型比分分布与模型公平线，不包含 odds、quote/capture 时间或 runtime；同一模型基础面对新 quote 时 ID 不变。
- 模型概率与市场概率必须分域：FME 只保存由冻结模型比分矩阵产生的 `model_*` 字段；市场去水概率属于 MarketQuote。比较必须在同一 quote line 上进行，`effective_cover_index` 不得命名为 `win_probability`。
- `MarketQuote` 是内容寻址的不可变报价，`quote_id=mq_<quote_hash>`。AH 的模型线差只使用主队视角 `home_centric_market_line`；结算与 EV 使用所选方向的 `selection_line`（`HOME_AH=home_line`、`AWAY_AH=away_line`）。主客让球线必须互为相反数、盘口为 0.25 增量、赔率大于 1，且报价必须带 `captured_at` 与 `source_hash`。
- 盘口 freshness 必须按 AH/TOTALS 分别读取当前所选 quote 自身的 `captured_at/as_of` 并绑定其 `source_hash`；禁止回退到 DecisionCard/Dashboard `generated_at`、ledger capture time 或 evaluation time。所选 quote 缺少原始时间必须 `STALE/BLOCKED`，原因为 `QUOTE_CAPTURE_TIME_MISSING`。
- 双快照和 CLV 证据只能读取 fixture 的完整 market observation history，不得用按盘口分组压缩后的 latest projection 伪造时间序列。每条 capture 冻结 `estimate_id/model_basis_id/quote_id/selection_line/selection_price/quote_captured_at/capture_hash`。
- 表现统计的规范键为 `fixture_id + market + recommendation_scope + strategy_version`；每个键只取最后一个通过 Snapshot v2 语义、MarketQuote 完整性、赛前时间与 evidence eligibility 检查的候选，同时间以 `capture_hash` 确定性排序。其余 capture 仅供审计，禁止重复计入战绩。回放与 outcome 必须使用 `fixture/market/selection/scope/strategy/estimate/quote/source_capture_hash` 完整身份，不得只按 fixture 匹配。`OFFICIAL`、`VALIDATION`、Wide Shadow、Strict Shadow 各版本必须分账。
- forward capture/outcome 的 read、dedupe 与 append 必须在同一个跨进程文件锁内完成，并在返回成功前 flush + fsync；market timeline 必须按 fixture 加锁，通过同目录临时文件、fsync 与 atomic replace 写入。reader 遇到截断尾行或损坏文件时必须保留已解析证据并显式返回 `DEGRADED/CORRUPT/ERROR`，禁止伪装成“没有记录”。
- `/health` 只证明 API 进程存活，不探测外部依赖；`/ready` 必须同时验证 DB、Redis、必需模型 artifact、核心 read model 表和 migration/schema 兼容性，任一关键检查失败返回 HTTP 503。容器健康检查和 Web 的 API 依赖必须使用 `/ready`，不得以 liveness 代替 readiness。
- 全局 `ReadModelService` 的 fixture、observation、xG、formal snapshot 与 raw payload 缓存必须隔离到当前请求工作线程；并发的 today/next36/future/results/all 请求不得重置或覆盖彼此的请求期状态。跨请求 Dashboard 响应缓存必须在显式锁内读写，并以副本交付，禁止调用方修改共享缓存对象。
- future DB fixture reader 失败时不得清空已经加载的 checkpoint fallback，也不得将来源故障伪装成“今日无比赛”。Dashboard 必须透传 `degraded_source/failed_source/error_class/fallback_source/data_completeness`，有 fallback 时保留只读展示，无 fallback 时显式阻断并等待来源恢复。
- `/ops` 在 staging 必须使用 Bearer service credential fail closed：未配置凭据返回 503，缺失或错误凭据返回 401，可选 CIDR 不匹配返回 403；production 保持关闭。认证依赖必须绑定整个 ops router，public `/v1`、`/health` 与 `/ready` 不得受影响。凭据不得进入响应、日志、仓库上下文或 release audit。
- v1 snapshot 只读兼容，语义状态为 `LEGACY_DISTRIBUTION_CONTEXT_UNVERIFIED` 且不得进入 corrected evidence；不得回写历史 snapshot。
- release SHA、Docker image、dependency lock 和 runtime fingerprint 属于 DecisionCapture/Release Audit，不得进入 FairMarketEstimateSnapshot。
- 已有旧 `simulation.scoreline_picks` 不得覆盖 artifact-backed fair distribution。若 fair estimate 无完整 mu/provenance，应隐藏同源比分与结算概率，不得拼接另一模型的比分解释。
- 四分之一盘必须分开展示全赢、半赢、走水、半输和全输概率；例如大 3.25 的 4+ 球为全赢、3 球为半输、0–2 球为全输。

## 落地检查（此契约"进了代码"的判定）

- `domain/enums.py` 出现唯一 `DecisionTier`（五值）；
- 卡片有 `decision_tier` + `outcome_tracked` + `lock_eligible` + `recommendation_id` 四字段；`formal_recommendation/candidate` 仅存于 shim；
- `compute_lock_eligible()` 当且仅当 `decision_tier==RECOMMEND` 返回 true；实数据/未来 kickoff/盘口完整/`recommendation_id`/前向 EV 证据作为 `RECOMMEND` 上档前置条件，而不是 `ANALYSIS_PICK` 可锁理由；
- `dashboard/recommendations.py:derive_recommendation_tier()` 退化为直接读 `decision_tier` + 治理字段，删掉四字段考古；
- `settlement / audit_export / tracking` 对历史快照的读取行为零变化（回归测试证明）；
- 每张非推荐卡带 `reason_code + action + next_eval_at`；
- 首屏「正式可锁推荐」「分析推荐」两个计数分别来自 `lock_eligible` 与 `decision_tier==ANALYSIS_PICK`。
