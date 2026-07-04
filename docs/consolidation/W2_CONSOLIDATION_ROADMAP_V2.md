# W2 Consolidation Roadmap V2（收敛版）

Status: 提议，待评审。配套 `W2_DECISION_CONTRACT_V2`。方向：**收敛不重写；展示 ≠ 可锁；刷新受控开启。**

## 相对 V1 的变更（评审后）

| # | V1 | V2 |
|---|---|---|
| 1 | scheduler「默认 on-path，删死 flag」 | **受控开启**：T-24h/3h/90/30/15 节奏；endpoint allowlist、hard cap、ledger、task 去重**必须先在**才启用；禁止 60 秒循环与全量 endpoint（曾被 Football-API 打爆） |
| 2 | 「删旧字段」 | 迁移 shim，只退写入路；`settlement/audit/tracking`/历史复盘链路零破坏 |
| 3 | 「stage checker 归拢」 | 明确**降级为 regression safety net**（`make regression` / `check_w2_all`），是保护网不是操作面，不删 |
| 4 | 单一就绪门 | 就绪门**并入 provider 预算**：预算耗尽→该场降级 `STALE + PROVIDER_BUDGET_EXHAUSTED`，而不是继续捶 API |
| 5 | ANALYSIS_PICK=正式推荐 | 两层出口；`w2-matchday` 同时产出「分析推荐」与「正式可锁候选」，复盘覆盖前者 |

## 论点

W2 不缺代码（~38k 行、30 模块、26 ADR、15 stage，概念大多正确），缺**一条 always-on 的每日比赛日主干**。系统一直在优化"stage N 的 check 有没有绿"，而不是"今天有没有推荐、为什么有、为什么没有、下次何时刷新"。

**证据（皆在本仓库）：** console_scripts 是 `shadow-cycle / gate5-preflight / stage7i-observer`，没有一个是"产出今天的推荐"；`scripts/` 24 个 `run_*` 多按 stage 命名 + 一堆 `*_dry_run`——永远彩排；最近 25 个 commit 几乎全在救亚盘显示/物化的火，且是 "at read time" 打补丁；scheduler 的刷新 flag 默认 `false`、固定 900s、与开球无关；README 停在 "Stage 3, 没有真实推荐"。

## Step 0 — 冻结（半天）

停止新增 stage，不接 Stage 16、不加新 `check_w2_stageN.py`。把现有 `scripts/check_w2_stage*.py` **降级为回归保护网**（并入 `make regression` / `check_w2_all`）——它们继续跑、继续保护，但**不再是产品操作面**。README 顶部改成系统真实现状（决策契约 + 两层出口 + 当前 stage）。

## Step 1 — 决策契约落地（解锁一切，先做）

**做什么**
- `domain/enums.py` 新增唯一 `DecisionTier`（NOT_READY/SKIP/WATCH/ANALYSIS_PICK/RECOMMEND）。
- 卡片补四个治理字段：`decision_tier` + `outcome_tracked` + `lock_eligible` + `recommendation_id`。
- **迁移 shim**：`formal_recommendation / candidate` 只退写入路，读路做"旧→新"只读映射；历史 LOCKED 快照永不回写。
- 重写 `dashboard/recommendations.py:derive_recommendation_tier()` → 直接读 `decision_tier` + 治理字段，删四字段考古。
- 每个非推荐路径补 `reason_code + action + next_eval_at`。

**验收（结果，不是"绿"）**
- `grep -rE "\bFORMAL\b|\bCANDIDATE\b" src/w2 --include=*.py` 只剩 shim/归档；
- 任一 fixture 卡片有且仅有一个 `decision_tier` + 四治理字段；
- `settlement / audit_export / tracking` 读历史锁定快照的行为**零变化**（回归测试证明）；
- `ANALYSIS_PICK` 的 `outcome_tracked=true / lock_eligible=false`（除非老板选 B）。

## Step 2 — 唯一入口 `w2-matchday`（把"跑今天"变成一等公民）

**做什么**
- 新增**一个** console_script `w2-matchday`（`pyproject [project.scripts]`）。`w2-matchday --date today` 端到端跑完整比赛日：
  **数据刷新 → 单一数据就绪门 → 每场生成 DecisionCard → dashboard → markdown 日报 → audit → 正式可锁候选(lock_eligible) → settlement dry-run。**
- 把 `run_prematch_refresh.py`、`run_stage10c_daily_cycle.py`、各 `run_stage*_*.py` **并入** `w2-matchday` 实现；`run_*` 仅作薄封装或删除。

**验收**
- 一条命令即产出当日全部判断（pick / non_pick+reason），无需手工拼脚本；
- 每场恰好一张 DecisionCard，`lock_eligible` 候选单独成列；
- 断网/缺数据时产出**带 reason_code 的降级卡**，不崩溃、不空白。

## Step 2a — 单一数据就绪门（含 provider 预算）

**做什么**
- 所有 fixture 先过**统一就绪门**，消费 `DataStatus`，明确必需字段（滚动 xG、评分、身价、盘口线、可得时首发）+ 各字段最大陈旧时限，输出 `READY/PARTIAL/STALE/BLOCKED`。下游（dashboard/report/lock/settlement）**只信这个裁决**，不各自判一遍。
- **provider 预算并入就绪门**：每 tick 有预算，预算耗尽→该场 `STALE + PROVIDER_BUDGET_EXHAUSTED`，绝不因追数据而捶爆 API。

**验收**：任一 fixture 的"缺什么、陈旧到什么程度、下次何时刷新"来自**同一处**；预算耗尽时系统降级而非超额请求。

## Step 2b — 受控刷新（恢复正式比赛日，但受控）

**做什么**
- scheduler 改为**感知开球**的固定节奏：**T-24h / T-3h / T-90 / T-30 / T-15**，每次拉 `status / fixtures / odds / lineups`。
- 每 tick **必须**先有：endpoint **allowlist**、每 tick **预算 + hard cap**、**ledger**、**task 去重**。四者不齐不启用。
- **禁止**恢复 60 秒循环、**禁止**全量 endpoint。已有护栏可复用：`providers/control.py`、`providers/ledger.py`、`providers/quota.py`（现有 27 处 hard_cap/allowlist/ledger/budget 逻辑）。

**验收**：一天按五个 tick 受控刷新并留时间戳快照；单日 provider 用量在 hard cap 内；ledger 可核对每次请求；重复 task 被去重拦下。

## Step 3 — 老板视角 dashboard（依赖 Step 1）

**首页只保留六样：**
1. 今日**正式可锁推荐**数量（`lock_eligible` 计数）
2. 今日**分析推荐**数量（`ANALYSIS_PICK` 计数）
3. 观察比赛（`WATCH`）
4. 未出原因统计（按 `reason_code` 聚合）
5. 下一次刷新时间（来自 scheduler 节奏）
6. 每场**一句人话**解释

技术字段（blocker、EV、盘口差、raw payload、readiness）**全部折叠**进二级视图，默认收起。停止"at read time"修数据——脏亚盘线在 Step 2a 就绪门源头被拦。

**验收**：非技术用户 5 秒内看懂"今天推什么/为什么/为什么不推/何时再看"；首屏不出现内部枚举名或调试字段。

## Step 4 — 复盘/审计前门（依赖 Step 2）

**做什么**：选任意历史日期 → 确定性重放当天"知道什么 / 判了什么 / 为什么 / 结果如何"。复用卡片哈希 + append-only 审计 + provenance。因 `ANALYSIS_PICK` 的 `outcome_tracked=true`，**复盘覆盖日常分析推荐**，不止锁定推荐。

**验收**：任取过去日期能重现全部卡片（哈希一致）并叠加结算；能回答"某场当时为什么没出/出了什么"。

## 横切收尾

- README 与 stage 叙事同步现实（Step 0 起持续）。
- 校准闭环：`calibration_status` 从 `BASELINE_PRIOR` → 历史校准，**被追踪的后续项**，不阻塞产品（`ANALYSIS_PICK` 用先验也能诚实产出，卡上标校准状态）。
- 前向证据：把现有 forward-holdout / shadow（`docs/models/W2_FORWARD_HOLDOUT_POLICY_V1`）作为**并行影子轨**接入 `w2-matchday`，为未来点亮 `RECOMMEND` 攒 +EV 证据，但**不阻塞**每日分析产出。

## 不要做

- 不加 Stage 16、不加新 `check_stageN`。
- 不重写引擎——收敛现有资产。
- 不删旧字段——用 shim；历史锁定快照永不回写。
- 不恢复 60s 循环 / 全量 endpoint——受控刷新。
- 不再在展示层"at read time"修数据——在源头/就绪门修。
- 不把普通分析包装成"正式推荐/可下单"。

## 全产品完成定义（对齐五条标准）

| 标准 | 完成判据 |
|---|---|
| 每天赛前稳定拿到关键数据 | 单一就绪门（含 provider 预算），每场每天一个 `DataStatus` + 必需字段/陈旧时限 |
| 自动刷新 | always-on、感知开球、受控（T-24/3/90/30/15 + allowlist/hardcap/ledger/dedup），留快照 |
| 清楚判断 | 唯一 `DecisionTier`，每场每天恰好一档 + 机器/人可读理由 |
| 该出就出、不能出给可执行原因 | `ANALYSIS_PICK` 稳定产出分析推荐；`lock_eligible/RECOMMEND` 才是正式可锁；每个非推荐带 `reason_code+action+next_eval_at` |
| 可控·可审计·可复盘 | `w2-matchday` 单入口可控；append-only + 哈希可审计；复盘前门覆盖 `ANALYSIS_PICK` 及以上 |

## 顺序与解锁

Step 0 → **Step 1（先做，解锁全部）** → Step 2 / 2a / 2b（主干与刷新，2b 依赖 2a 的就绪门与预算）→ Step 3（依赖 1）与 Step 4（依赖 2）可部分并行。建议从 Step 1 的 `domain/enums.py` + `dashboard/recommendations.py` 两处动刀，一天内让"判断"在代码里变成一件事。

## 待批决策点（同契约 V2）

`lock_eligible` **绑不绑 "+EV 已证明"**：本路线图按**不绑 + 强标注**推进（每天有正式可锁候选、可建战绩，卡上强标"非稳赢/非 +EV 证明"）；若老板选**绑**，则 `lock_eligible ⇔ RECOMMEND`，正式可锁推荐可能连续多天为 0，其余不变。请副总监/老板拍板。
