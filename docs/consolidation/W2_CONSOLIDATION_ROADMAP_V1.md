# W2 Consolidation Roadmap V1

Status: 提议。配套 `W2_DECISION_CONTRACT_V1`。方向：**两档分层**。

## 论点

W2 不缺代码（~38k 行、30 模块、26 ADR、15 stage，概念大多正确），缺的是**一条 always-on 的每日主干**。系统一直在优化"stage N 的 check 有没有绿"，而不是"今天的比赛有没有拿到清楚、可靠的判断"。所以这不是重写，是**收敛**。

**证据（皆在本仓库）：** ① console_scripts 是 `shadow-cycle / gate5-preflight / stage7i-observer`，没有一个是"产出今天的推荐"；`scripts/` 24 个 `run_*` 多按 stage 命名 + 一堆 `*_dry_run`——永远彩排，从不演出。② 决策档四套词并存（`FORMAL 111 / RECOMMEND 29 / ANALYSIS_PICK 19 / CANDIDATE 12` 处），dashboard 读取时现场调和。③ 最近 25 个 commit 几乎全在救亚盘显示/物化的火，且是 "at read time" 打补丁（在出库口补，不在源头修）。④ scheduler 的 `W2_FUTURE_FIXTURE_REFRESH_ENABLED` / `W2_XG_BACKFILL_ENABLED` 默认 `false`、固定 900s、与开球时间无关。⑤ README 停在 "Stage 3, 没有真实推荐"——正门在说谎。

## Step 0 — 冻结（半天）

**停止新增 stage。** 在收敛完成前不接 Stage 16、不加新 `check_w2_stageN.py`。把现有 `scripts/check_w2_stage*.py` 归拢为**一个回归测试套件**（`make regression`），它们是"保护网"，不是产品的操作面。README 顶部改成系统真实现状（决策契约 + 两档 + 当前 stage）。

## Step 1 — 把决策契约落进代码（解锁一切，先做）

**做什么**
- `domain/enums.py` 新增唯一 `DecisionTier`（NOT_READY/SKIP/WATCH/ANALYSIS_PICK/RECOMMEND）。
- 卡片改为单字段 `decision_tier`；废弃 `formal_recommendation` / `candidate` flag（保留一层迁移 shim 读旧数据）。
- 重写 `dashboard/recommendations.py:derive_recommendation_tier()` → 直接读 `decision_tier`，删掉四字段考古。
- 跨这 10 个文件退役 `FORMAL/CANDIDATE`：`audit_export/tables.py`、`reporting/report_generator.py`、`reporting/match_decision.py`、`matchday/cards.py`、`operations/production_readiness.py`、`backtest/s2_gate.py`、`dashboard/{recommendations,scorelines,performance,validation}.py`。
- 每个非推荐路径补 `reason_code + action + next_eval_at`。

**验收（结果，不是"绿"）**
- `grep -rE "\b(FORMAL|CANDIDATE|NO_RECOMMENDATION)\b" src/w2 --include=*.py` 只剩迁移/归档；
- 任一 fixture 的卡片有且仅有一个 `decision_tier`；
- dashboard 不再读 `formal_recommendation/candidate/analysis_decision` 三个以上字段来决定档位；
- 每张非推荐卡片可打印出一句可执行原因。

## Step 2 — 建每日主干（把"跑今天"变成一等公民）

**做什么**
- 新增**一个** console_script：`w2-matchday`（`pyproject [project.scripts]`）。语义：`w2-matchday --date today` = 端到端跑北京运营日：拉/刷数据 → **单一数据就绪门** → 判断 → 对**每个** fixture 产出恰好一张 DecisionCard（pick 或 non_pick+reason）。
- **单一就绪门模块**：所有 fixture 必经，消费 `DataStatus`，明确必需字段（滚动 xG、评分、身价、盘口线、可得时首发）+ 各字段最大陈旧时限，输出 `READY/PARTIAL/STALE/BLOCKED`。下游**只信**这个裁决，别处不许各自判断"够不够新"。
- scheduler 改为**感知开球**的节奏（T-24h / T-3h / T-90m / T-30m），每次写带时间戳快照；`W2_*_REFRESH_ENABLED` 系列**默认 on-path**（能删的死 flag 删掉）。
- 把 `scripts/run_stage*_*.py`、`run_prematch_refresh.py`、`run_stage10c_daily_cycle.py` 等**并入** `w2-matchday` 的实现，`run_*` 仅作薄封装或删除。

**验收**
- 一条命令 / 一个定时任务即产出当日全部判断，无需手工拼脚本；
- scheduler 按开球节奏刷新并留快照；dashboard 能显示"上次刷新/下次刷新/陈旧度"；
- 断网或数据缺失时，产出的是**带 reason_code 的降级卡**，而不是崩溃或空白。

## Step 3 — 决策优先的 dashboard（依赖 Step 1）

**做什么**
- 首屏只回答一个问题：**今天买什么·为什么 / 不买·为什么·何时再看**。顶部一条 freshness 带（last / next refresh / staleness）。
- 现有 34 个组件里的机器细节（data diagnostics、odds movement、readiness chips、confidence dots、settlement badge…）**折叠进二级视图**，默认收起。
- 主卡 = `ANALYSIS_PICK`（标"正式推荐 · 分析参考·非稳赢"）；`WATCH/SKIP` 成一条"未出原因"清单，每条带原因 + 重评时间。

**验收**
- 一个非技术用户打开首屏，5 秒内知道今天买什么/为什么/哪些没出及原因；
- 首屏不出现任何内部枚举名或调试字段；
- 停止"at read time"修数据——脏亚盘线在 Step 2 的源头/就绪门被拦，不在展示层补。

## Step 4 — 复盘/审计前门（依赖 Step 2）

**做什么**
- "当日复盘"视图：选任意历史日期 → 确定性重放当天系统**知道什么 / 判了什么 / 为什么 / 结果如何**。复用已有的可复现基建（卡片哈希、append-only 审计、provenance）。

**验收**
- 任取一个过去日期，能重现当天全部卡片（哈希一致）并叠加结算结果；
- 可回答"某场当时为什么没出/出了什么"，无需翻日志。

## 横切收尾

- README 与 stage 叙事同步现实（Step 0 起持续）。
- 校准闭环：`calibration_status` 从 `BASELINE_PRIOR` → 历史校准，作为**被追踪的后续项**，不阻塞产品上线（ANALYSIS_PICK 用先验也能诚实产出，只需在卡上标注校准状态）。
- `RECOMMEND` 上档保持默认关，前向证据（Gate4/Gate5）就绪前不点亮。

## 不要做

- 不加 Stage 16；不加新 `check_stageN`。
- 不重写引擎——收敛现有资产。
- 不再在展示层"at read time"修数据——在源头/就绪门修。
- 不把 dashboard 当引擎内部状态的镜子。

## 全产品完成定义（对齐你的五条标准）

| 你的标准 | 完成判据 |
|---|---|
| 每天赛前稳定拿到关键数据 | 单一就绪门，每 fixture 每天一个 `DataStatus`，必需字段与陈旧时限明确 |
| 自动刷新 | 一个 always-on、感知开球的 scheduler，留时间戳快照，前端显示刷新态 |
| 清楚判断 | 唯一 `DecisionTier`，每场每天恰好一个档 + 机器/人可读理由 |
| 该出就出、不能出给可执行原因 | `ANALYSIS_PICK` 即正式推荐；每个非推荐带 `reason_code + action + next_eval_at` |
| 可控·可审计·可复盘 | `w2-matchday` 单入口可控；append-only 审计 + 哈希可审计；当日复盘前门可复盘 |

## 顺序与解锁

Step 0 → **Step 1（先做，解锁全部）** → Step 2 与 Step 3 可部分并行（3 依赖 1）→ Step 4 依赖 2。建议从 Step 1 的 `domain/enums.py` + `dashboard/recommendations.py` 两处动刀，一天内就能让"判断"在代码里变成一件事。
