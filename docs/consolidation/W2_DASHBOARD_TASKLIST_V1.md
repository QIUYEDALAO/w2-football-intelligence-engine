# W2 Dashboard 全链路任务清单 V1

Status: 提议，待评审。配套 `W2_DECISION_CONTRACT_V2` / `W2_CONSOLIDATION_ROADMAP_V2`。

**核心原则：dashboard 只渲染，不调和。** 一切"判成什么、为什么、可不可锁、进不进复盘"必须在上游算好、写进 DecisionCard；前端只做展示、排序、折叠。今天的问题正是这条被违反了——`derive_recommendation_tier()` 在读取时用四个字段反推档位、`scorelines.py` 在 dashboard 层跑泊松定价、`DashboardPage.tsx` 用 `formal_recommendation` 排序。本清单沿整条链把逻辑推回上游。

## 完整链路（现状 → 目标）

```
w2-matchday（上游写入）
  └─ dashboard:* checkpoints（读模型存储：fixture_latest / provider_status / data_health / forward_status / matchday_cards）
       └─ src/w2/dashboard/*  读模型函数（recommendations / readiness / scorelines / performance / results / status_labels / validation）
            └─ src/w2/api/repository.py  组装 + src/w2/api/dashboard_read_models.py
                 └─ API 端点（dashboard view）
                      └─ apps/web/src/types/dashboard.ts  类型
                           └─ apps/web/src/lib/dashboardApi.ts  取数
                                └─ apps/web/src/components/DashboardPage.tsx  组装
                                     ├─ L1 决策页（老板视角）
                                     └─ L2 技术诊断（折叠）
```

目标：这条链上"决策语义"只在**一处**产生（上游写 DecisionCard），其余每一环只做透传与渲染。

---

## A. 后端读模型收敛（src/w2/dashboard）

- [ ] **A-01** 删除 `recommendations.py:derive_recommendation_tier()` 的四字段考古（读 `formal_recommendation/candidate/decision/analysis_decision`），改为直接读单字段 `decision_tier`。
- [ ] **A-02** `recommendations.py:RecommendationTier`(FORMAL/CANDIDATE/ANALYSIS_PICK/WATCH/NO_RECOMMENDATION) 退役，改用 `domain` 的唯一 `DecisionTier`；`build_recommendation()` 输出对齐 DecisionCard 契约。
- [ ] **A-03** 合并两套并行的"就绪"词汇：`readiness.py:AnalysisReadinessStatus`(READY/PARTIAL/BLOCKED/UNKNOWN) 与契约的 `DataStatus`(READY/PARTIAL/STALE/BLOCKED) 统一为后者；`build_analysis_readiness()` 仅做展示映射，不再自造状态。
- [ ] **A-04** `readiness.py:AnalysisBlocker/AnalysisNextAction` → 映射到契约的 `reason_code` 分类法；`build_watch_recommendation()` 产出 `reason_code + action + next_eval_at` 三元组，不再产裸文案。
- [ ] **A-05** 把 `scorelines.py` 里的定价/概率逻辑（`_ah_key_scorelines`、`_poisson_probability`、`_quarter_line_parts`、`_over_probability`）**移出 dashboard 层**，迁到上游 `analysis`/`pricing`；dashboard 只接收算好的 scoreline/fair line 字段渲染。
- [ ] **A-06** `readiness_summary()` 改为按 `reason_code` 聚合（喂"未出原因统计"面板），键与契约一致。
- [ ] **A-07** `performance.py:_tier()` 改读 `decision_tier`；`dashboard_performance()` 输出 `lock_eligible` 计数与 `ANALYSIS_PICK` 计数两个口径（供首屏两个数字）。

**验收：** `grep -rE "formal_recommendation|analysis_decision|RecommendationTier" src/w2/dashboard` 只剩 shim；dashboard 层不再出现泊松/定价函数；读模型每个输出字段都能追到 DecisionCard 上的同名字段。

---

## B. 人话生成器（每场一句话，上游、确定性、可审计）

- [ ] **B-01** 决策"一句话解释"必须**在上游生成并写入 DecisionCard**（进 `card_hash`、可审计、可复盘），不在 React 里现拼。新增 `analysis/explanation.py`。
- [ ] **B-02** 为每个 `decision_tier` 定一套句式模板（填槽，不自由生成）：
  - `ANALYSIS_PICK`：`{主因子} + {模拟公允盘 vs 市场} + {价值%}`（例：主队 xG 与身价双优，公允盘 -1.3 深于市场，价值 +4%）。
  - `ANALYSIS_PICK 暂不可锁`：上句 + `{lock 缺什么} + {next_eval}`。
  - `WATCH`：`{数据齐但为何不出} + {next_eval}`。
  - `NOT_READY/SKIP`：`{reason_code 人话} + {action} + {next_eval}`。
- [ ] **B-03** 句子长度与用词护栏：单句 ≤ 40 字，禁确定性词（稳赢/必中/保证）；`ANALYSIS_PICK` 句尾或卡上强制 `分析参考·非稳赢`。
- [ ] **B-04** 句子随卡片进 audit 与 replay，历史复盘看到的解释与当时一致。

**验收：** 同输入同版本 → 同一句话（确定性）；每种 tier 有模板测试；无自由文本、无确定性措辞。

---

## C. API 契约（日信封 + 卡片）

- [ ] **C-01** `api/repository.py` 组装输出一个**日信封 DashboardDayView**：`date / environment / counts{lock_eligible, analysis_pick, watch, not_ready} / freshness{last_refresh, next_refresh_tick, staleness} / cards[]`。
- [ ] **C-02** `cards[]` 每项 = DecisionCard 契约字段（`decision_tier / data_status / lock_eligible / outcome_tracked / recommendation_id / pick? / non_pick? / one_liner / card_hash`）。
- [ ] **C-03** `freshness` 来自 scheduler（受控刷新的 T-24h/3h/90/30/15 节奏）：暴露"上次刷新 / 下次 tick / 陈旧度"，对齐 `dashboard:provider_status` 与 `dashboard:data_health` checkpoint。
- [ ] **C-04** `environment` 字段贯穿（staging/production），驱动 `lock_eligible` 的策略叠加（见 I 部分）。
- [ ] **C-05** `dashboard_read_models.py` 的 `dashboard:*` key 结构补一个 `dashboard:day_view:{date}`，让 L1 一次取全（减少前端多次拼装）。

**验收：** 一次 API 调用即拿到首屏所需全部（两个数字 + 卡片 + 刷新态 + 环境），前端无需二次聚合。

---

## D. 前端类型与取数（收口，别再宽松）

- [ ] **D-01** `types/dashboard.ts:Decision = "PICK"|"SKIP"|"WATCH"|"ANALYSIS_PICK"|string` 收口为契约枚举，**删掉 `| string` 兜底**；新增 `DecisionTier` 联合类型与 `DecisionCard`、`DashboardDayView` 接口。
- [ ] **D-02** `MarketAnalysis` 里同时存在的 `decision` 与 `analysis_decision` 合并为单一 `decision_tier`；清掉 `| null | string | number` 的松散并集。
- [ ] **D-03** `AnalysisReadiness`(READY/PARTIAL/BLOCKED/UNKNOWN) 前端类型对齐后端 `DataStatus`。
- [ ] **D-04** `lib/dashboardApi.ts:fetchDashboardView` 改为取 `dashboard:day_view`；bump `DASHBOARD_CACHE_VERSION`（现 `dashboard-v4-football-day-fallback`）。
- [ ] **D-05** `lib/normalize.ts` 里为兜容旧字段而生的转换逻辑，随后端收敛逐步删除（只保留 shim 读历史）。

**验收：** `tsc` 下 `Decision` 无 `string` 逃逸；前端不再引用 `formal_recommendation`/`candidate`/`analysis_decision`。

---

## E. L1 决策页（老板视角，新组件）

- [ ] **E-01** `MatchdayHeader`：日期 + `environment` 徽章 + freshness（上次/下次刷新/陈旧度）。
- [ ] **E-02** `DecisionCounts`：四张 metric 卡——正式可锁候选 / 分析推荐 / 观察 / 未就绪·不判；标注"可锁候选 ⊂ 分析推荐"。
- [ ] **E-03** `DecisionRow`：一场一行——队名+联赛+开球时间、pick 线（可锁/暂不可锁着色）、**一句人话**、右侧 tier 徽章。替代 L1 里臃肿的 `MatchCard`。
- [ ] **E-04** `ReasonCodePanel`：未出原因统计，按 `reason_code` 聚合成 chip（首发未出 ×N…）。
- [ ] **E-05** 排序：`sortFormalFirst`/`isFormalMatch`（现读 `formal_recommendation && tier==="FORMAL"`）改为按 `lock_eligible` → `ANALYSIS_PICK` → `WATCH` → `NOT_READY`，次级按开球紧迫度（复用 `sortByKickoffUrgency`）。
- [ ] **E-06** `DisclaimerFooter`：`分析参考·非稳赢·不构成投注建议`，常驻。

**验收：** 首屏只出现这六类元素；无内部枚举名、无 EV/盘口差/raw payload；非技术用户 5 秒内看懂"推什么/为什么/为什么不推/何时再看"。

---

## F. L2 技术诊断折叠（收纳现有 34 组件）

- [ ] **F-01** 新增 `DiagnosticsDrawer`：把 `DataDiagnosticsPanel`、`ReadinessChips`、`DataReadinessRow`、`OddsMovementMini`、`BookmakerIntentLine`、`ConfidenceDots`、`MarketStrip`、`ScorelinePicks` 等收进默认折叠的二级抽屉（每场卡片可展开）。
- [ ] **F-02** 现有 `shouldShowDiagnostics()`（靠 `?debug=1` query）升级为正式的 L1/L2 交互：L1 是决策页，L2 是抽屉，不再靠隐藏 URL 参数。
- [ ] **F-03** L2 保留全部技术字段（blocker/EV/盘口差/readiness/raw payload/settlement）——不是删，是降级到一键之外。

**验收：** L1 默认零技术字段；任一场可一键展开看到完整诊断；`?debug=1` 仍可强开全展开供工程用。

---

## G. 状态与降级（空/坏/断/预算）

- [ ] **G-01** 复用并统一现有 `emptyCopy()` 的空态文案到"数据不足保持空白、不强出推荐"口径。
- [ ] **G-02** 断网/超时（`dashboardApi` 20s timeout）→ 展示上次快照 + "数据陈旧"角标，不空屏。
- [ ] **G-03** `PROVIDER_BUDGET_EXHAUSTED`（受控刷新预算耗尽）→ 该场显示 `STALE + reason_code`，而不是空或崩。
- [ ] **G-04** `SkeletonCard` 仅在首次加载用；刷新期间保留旧内容 + 刷新指示。

**验收：** 四种异常路径都有可读降级卡，无白屏、无崩溃、无"假装有数据"。

---

## H. 复盘 / 日期导航（接 Roadmap Step 4）

- [ ] **H-01** `date_window.py` 的足球日窗口接入日期切换器：选任意历史日期加载当日 `dashboard:day_view:{date}`。
- [ ] **H-02** 复盘视图对每场展示：当时 `decision_tier` / 一句话 / `data_status` / 结算结果（复用 `results.py`、`validation.py`）。
- [ ] **H-03** 因 `ANALYSIS_PICK` 的 `outcome_tracked=true`，复盘覆盖**日常分析推荐**，不止锁定推荐。
- [ ] **H-04** 复盘页显示 `card_hash`，可证"重放与当时一致"。

**验收：** 任取过去日期能重现全部卡片（哈希一致）+ 叠加结算；能回答"某场当时为什么没出/出了什么"。

---

## I. 环境与公信力（staging A / production B）

- [ ] **I-01** `lock_eligible` 作为**环境策略叠加**计算，不烤进 `card_hash`：DecisionCard 核心（`decision_tier/pick/one_liner/outcome_tracked`）两环境一致、哈希一致，仅 `lock_eligible` 随 `environment` 变。
- [ ] **I-02** staging：`lock_eligible` = 过数据/未来 kickoff/盘口完整门；徽章"可锁候选"+ 强标 `staging-only · 非稳赢 · 非 +EV`。
- [ ] **I-03** production：`lock_eligible` 仅 `RECOMMEND`（默认 0）；首屏"正式可锁推荐"数字据此。
- [ ] **I-04** 标注绑定卡片、随**每个出口**带走（dashboard/markdown/audit/replay），每卡盖 `environment` 戳——防止 staging 截图外流被当"可下单"。

**验收：** 同场同版本卡在 staging/production 的 `card_hash` 一致、仅 `lock_eligible` 不同；任何导出物都带环境戳与标注。

---

## J. 验收与回归

- [ ] **J-01** "5 秒老板测试"：非技术用户看首屏，正确复述推什么/为什么/为什么不推/何时再看。
- [ ] **J-02** 契约测试：每个 `decision_tier` × 每种 `reason_code` 有一句话模板快照测试。
- [ ] **J-03** 视觉回归：L1 首屏（今日/复盘/空态/降级）截图基线。
- [ ] **J-04** 可访问性：语义标签、对比度、键盘可达 L2 抽屉。
- [ ] **J-05** 确定性：同输入同版本 → 同 `card_hash` + 同一句话（跨 staging/production 核对）。
- [ ] **J-06** 全部现有 stage checker 降级进 `make regression`，作为保护网跑，不阻塞 dashboard 迭代。

---

## 依赖与顺序

```
A（读模型收敛）──┐
B（人话生成器）──┼─→ C（API 日信封）─→ D（前端类型/取数）─→ E（L1 决策页）
                │                                          ├─→ F（L2 折叠）
I（环境叠加）────┘                                          ├─→ G（状态降级）
                                                           └─→ H（复盘）
J（验收）贯穿全程
```

先做 A + B（决策语义与人话回到上游），它们决定 C 的信封形状；C 定后 D/E 可并行；F/G/H 依赖 E 的骨架；I 贯穿 A/C/E；J 全程。

## 落地起手式（第一天）

`recommendations.py:derive_recommendation_tier()` 删四字段考古改读 `decision_tier`（A-01）＋ `DashboardPage.tsx:isFormalMatch()` 改按 `lock_eligible`（E-05）。这两处一改，"档位"在整条链上就从"读取时反推"变成"上游写死、前端只读"，其余任务都在这个地基上展开。
