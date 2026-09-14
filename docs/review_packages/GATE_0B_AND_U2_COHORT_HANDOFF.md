# Gate 0B 结果 + U2 cohort 修订 交接单

用途：Codex 的唯一输入。自包含，不依赖对话上下文。
执行者：Claude Code，生产只读核对（`docker ps` / `docker inspect` / `psql -tAc select`）
状态：`GATE_0B_COMPLETE_U2_AMENDMENT_DOCS_ONLY`
授权范围：**仅文档**。不改业务代码、不执行 U2、不写生产、不部署。

---

## 1. Gate 0B 结果：基线权威更正

### 1.1 生产身份（已实测确证）

```text
主机     root@45.207.194.97   HK112037094063   up 8 天
release  ea557bb8ff64e06add91bbe32814fe073ec64642
         web / api / worker / scheduler 四服务 image revision 完全一致，均 healthy
schema   0070_notification_delivery_routing
```

Obsidian `当前状态.md` 的记录**完全准确**。

### 1.2 必须更正的基线判断

Gate 0A 产物记录「审计基线 `origin/main@3b7f87db`」并将其视为权威。**方向错误。**

```text
生产 ea557bb8 / schema 0070      ← 真正权威（2026-08-27 部署）
本地工作树（21 个 worktree）       ← 实际开发处
origin/main 3b7f87db / schema 0051 ← 给 agent 看的选择性快照，落后生产 19 个 migration
```

`origin/main` 不是权威，是快照。所有 Gate 0A / Phase 2.5a / U1 结论的适用范围须据此重述。

### 1.3 结论存活性（逐文件 diff `3b7f87db` vs `ea557bb8`）

| 文件 | 差异 | 依赖它的结论 |
|---|---|---|
| `src/w2/strategy/calibration.py` | **相同** | BASELINE_PRIOR 五个硬编码系数、无拟合代码 —— **成立** |
| `src/w2/domain/five_state_pricing.py` | **相同** | `cashflow_price_edge = EV/S` 恒等式 —— **成立** |
| `src/w2/models/independent.py` | **相同** | comparator 错配 —— **成立** |
| `src/w2/backtest/free_tier_2024.py` | **相同** | U2 输入可得性、五联赛范围 —— **成立** |
| `src/w2/markets/analysis_evidence.py` | 变更 +34 | `0.05` 语义登记册 —— **须按生产基线重核** |
| `src/w2/prematch/lifecycle.py` | 变更 +339 | 同上 |

三个关键常量在两基线上出现次数一致
（`MIN_MARKET_ANCHOR_DIVERGENCE` 3+0、`ACTIVE_DELTA_THRESHOLD` 0+6、
`probability_delta_admission_gate` 1+0），登记册大概率无实质变化，但仍须重核。

---

## 2. U2 数据：原缓存已不存在，生产库有更好的

### 2.1 原缓存

```text
runtime/w2_understat_xg/understat_*.json   本地无、生产无
raw_dirs/fixtures_*.json                   本地无、生产无
```

2026-07 研究的回测缓存已不可得。按原 cohort 复现**不可能**。

### 2.2 生产库可用数据

```text
team_xg_match
  fixture_id, team_id, opponent_team_id, kickoff_at,
  xg_for, xg_against, goals_for, goals_against,
  source_system, raw_payload_sha256

  19,004 行 = 9,502 场
  xG 非空率 19004/19004 = 100%
  时间跨度 2024-02-22 → 2026-08-29
  分年 2024:2,963  2025:4,181  2026:2,358
  source_system = api_football_statistics（100%）
```

与原研究对比：样本 **9,502 vs 1,510（6.3 倍）**，xG 零缺失，但**来源不同**
（API-Football statistics vs Understat）。

### 2.3 Elo 与身价：实测不可得

```text
team_rating_snapshots        16 行 / 16 队 / 仅 2026-07-17→07-20
team_value_asof_artifacts    0 行
player_valuation_observations 31,507 行（球员级）
transfermarkt_player_references 50,149 行（球员级）
```

生产读取路径为 `analysis_calculator.py:3186-3188` 的
`max(home_ratings/home_values, key=observed_at, default=None)`，
再传入 `simulate.py:133-136` → `calibrate_lambdas`。
源表为空时该值为 `None`，`calibrate_lambdas` 相应令 `elo_delta = 0`、`value_delta = 0`。

**推论（非运行时实证，须标注）**：
`elo_gap_weight = 0.28` 与 `squad_value_log_weight = 0.18` 在生产历史上
对绝大多数 fixture 不产生任何效果；球员级身价数据存在，但队级 as-of 聚合
（`team_value_asof_artifacts`）从未物化。

**未能证实的部分**：`dynamic_prematch_evaluations`(5,733 行)、
`model_forecast_capture`(265 行)、`recommendation_locks`(0 行)
的 payload 均不含 calibration 输入字段，因此无法从持久化证据直接确认
生产预测实际使用了哪些输入。该推论须在 U2 报告中标为
`INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED`。

---

## 3. U2 预注册修订（`U2_PREREGISTRATION.md`）

### 3.1 对照身份降级

```text
原：PRODUCTION_FORMULA_XG_ELO_ONLY
改：PRODUCTION_FORMULA_XG_ONLY

即 strategy/calibration.py::calibrate_lambdas，默认 LambdaCalibrationParams，
输入仅为 team_xg_match 导出的 rolling xG；
home_elo = away_elo = None，squad_value = None，lineup_* = 0，两个 lineup 证据门 False。
```

首屏声明须改为：生产四路输入中 **Elo、身价、首发三路缺失**；
但按第 2.3 节的推论，该形态**可能正是生产实际形态**——
该说法必须与其 `INFERRED_...` 标记同时出现，不得单独引用。

### 3.2 cohort 更换（实质变更，须重新冻结）

```text
原：2026-07 Understat 研究 cohort，1,510 场，五大联赛
改：team_xg_match 导出，2024-02-22 → 2026-08-29，9,502 场

必须重新冻结：
  fixture cohort digest
  competition 集合与每联赛 N
  train/validation 时间切分点
  min_history 门槛
  challenger 重新拟合规则（原系数在 Understat 上拟合，不可直接搬用）
```

**关键约束**：challenger 的系数与 temperature 原在 Understat 数据上拟合。
换 cohort 后**必须在新 cohort 的训练前缀上重新拟合**，否则是跨数据集搬用，无效。
重新拟合的规则须在看任何结果前冻结。

### 3.3 与原研究不可比

新 cohort 的结果**不得**与 2026-07 报告的
`-0.026376` / `-0.035368` 直接比较。来源、样本、时间、联赛集合全不同。
原结论作为独立历史记录保留。

### 3.4 保持不变

线网格、primary estimand（五态 NLL 逐 fixture 配对差）、
分层（half / integer / quarter line）、cluster（matchday + league）、
futility 先算后跑、允许的四个结论字段、
「不授权生产替换、不授权写入生产路径」——全部不变。

---

## 4. 本轮要产出什么

1. 更正 `EXACT_AUTHORITY_SNAPSHOT.json` 与 `U1_PROMOTION_READINESS_AUDIT.md` 的
   基线权威表述（按第 1.2、1.3 节），并逐条标注结论存活性；
2. 按第 3 节修订 `U2_PREREGISTRATION.md`，版本记为 V2，
   原 V1 内容保留为历史；
3. `FIVE_PERCENT_SEMANTIC_REGISTRY.md` 标注
   `PENDING_RECHECK_ON_PRODUCTION_BASELINE`，不删除现有内容；
4. 生成 `docs/review_packages/GATE_0B_EXECUTION_RECEIPT.md`，
   记录第 1、2 节全部实测值与「只读、零写入」证明。

## 5. 不要做

```text
不执行 U2、不导出生产数据、不重新拟合 challenger
不改任何业务代码
不把推论写成运行时实证（必须带 INFERRED_ 标记）
不把新 cohort 结果与 2026-07 数字相提并论
不申请写权限、不部署、不更新 Obsidian
```

计划书状态保持唯一一处 `PROPOSED_NOT_AUTHORIZED`。
