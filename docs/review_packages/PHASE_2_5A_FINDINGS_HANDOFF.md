# Phase 2.5a 发现交接单

用途：Codex 落 Phase 2.5 产物的唯一输入。本文件自包含，不依赖任何对话上下文。
执行者：Claude Code，只读静态审计
审计基线：`origin/main@3b7f87db`（detached worktree，用户工作树未修改）
状态：`FINDINGS_HANDOFF_DOCS_ONLY`
授权范围：**仅文档产出**。不改业务代码、不接 Penaltyblog、不访问 VPS/Provider、不部署。

---

## 0. 你缺的上下文

Gate 0A 与 Phase 2.5a 已由 Claude Code 在 `main@3b7f87db` 上执行完毕。
你没有见过这些结果。本节是全部输入。

Gate 0A 产物已生成（本地未跟踪）：

```text
docs/review_packages/EXACT_AUTHORITY_SNAPSHOT.json
docs/review_packages/FIVE_PERCENT_SEMANTIC_REGISTRY.md
```

---

## 1. Gate 0A 结论摘要

### 1.1 两项阻断发现

```text
PHASE_2_5_METRICS_BLOCKED_NO_LOCAL_DATA
  本地无历史预测+赛果数据集；postgres 为空库；fixtures 仅 44KB / 9 文件。
  Phase 2.5 的定量指标计算在本地不可执行。

PRODUCTION_RUNTIME_IDENTITY_UNKNOWN_REQUIRES_GATE_0B
  生产 release / OCI revision / 已应用 migration head / capability 运行态
  均无法本地确认。
```

### 1.2 capability manifest 静态事实

`config/capabilities/recommendation_capabilities.v1.json`（sha256 前缀 `bfc737aa640c0257`）：

```text
production_enabled          0 / 13
isolated_runtime_verified   0 / 13
staging_canary_passed       0 / 13

evidence_status = POLICY_THRESHOLD_UNVALIDATED:
  analysis_ah, analysis_ou, formal_ah,
  recommendation_lock, production_recommendation
```

manifest 自身即声明相关门槛未验证。

### 1.3 migration head

`0051_apply_seven_day_collection_policy`，down_revision `0050_gate_a_runtime_selection`，
静态检查为线性单 head。生产已应用 head 未知。

### 1.4 `0.05` 语义登记

决策相关的 `0.05` 在 `main` 上有 **5 种语义、7 处**，详见
`FIVE_PERCENT_SEMANTIC_REGISTRY.md`。其中两点需要处置：

- `src/w2/domain/decision_adapter.py` 在 `main@3b7f87db` **仍然存在**，
  带 `MIN_MARKET_ANCHOR_DIVERGENCE` 的第三份拷贝。按架构收敛计划该文件应在
  P1-04C 删除，说明该任务尚未完成或未合并。
- `src/w2/analysis/market_movement.py:628` 的 `abs(diff) < 0.05` 是
  `team_score` 差值的中性带，与 EV/概率**完全无关**，不得纳入政策讨论。

---

## 2. Phase 2.5a 结论：参数来源

### 2.1 三个系数确证为硬编码，从无拟合

```text
home_advantage_goals     0.12
elo_gap_weight           0.28
squad_value_log_weight   0.18
lineup_adjustment_weight 0.08
dixon_coles_rho          0.0     （tau correction 默认为空操作）
```

引入 commit：`d4ca41b7`，2026-06-29，`Add simulation-based formal recommendation engine (#96)`。
该 commit 无拟合脚本、无标定证据，diff 仅 `src/w2/strategy/calibration.py` + 一个测试。
此后**从未改动**。

全仓搜索这四个符号，`calibration.py` 之外的引用只有：

```text
tests/unit/test_simulation_engine.py:163   assert ... == 0.12   （测试把值钉死）
scripts/debug_w2_modeling_sanity.py        （回显）
```

**不存在任何估计这些系数的代码**：无回归、无网格搜索、无优化器。
`CALIBRATION_STATUS = "BASELINE_PRIOR"` 的命名与实现一致。

### 2.2 模型结构

```text
base_home = (home_xg_for + away_xg_against) / 2
base_away = (away_xg_for + home_xg_against) / 2
total     = clamp(base_home + base_away, 1.35, 4.40)

adjusted_delta = (base_home - base_away)
               + 0.12                                  # 主场
               + (elo_home - elo_away)/400 * 0.28       # Elo
               + log(value_home/value_away) * 0.18      # 身价
               + lineup_strength * 0.08                 # 首发

lambda_home = clamp((total + adjusted_delta)/2, 0.15, 4.25)
lambda_away = clamp((total - adjusted_delta)/2, 0.15, 4.25)
```

两点结构性观察（**属于假设，不是已证结论**，供 Phase 2.5 报告记录）：

1. `total` 仅由 xG 决定；Elo、身价、首发只影响 delta，不影响总进球
   （`lineup_totals_adjustment` 在其门开启时例外）。
2. xG、Elo、身价三者都在度量球队强弱，却被**相加**且无正交化。
   强队三项同向叠加，可能在实力悬殊场次系统性过冲。该假设可证伪，
   应在报告中登记为待验证项，不得写成已确认缺陷。

---

## 3. Phase 2.5b 的答案已经存在于仓库

`docs/archive/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_20260707.md`
（2026-07-07，PR #193，分支 `feat/w2-understat-model-iteration-1`）

方法：五大联赛 Understat 免费 xG；fixtures 1755 / xG matched 1750 /
eligible walk-forward 1510；按 kickoff 排序的时间序列切分，train/val = 1057/453；
lambda 与 temperature 只在 train 拟合；目标 fixture 自身 xG 被排除。

### Validation 指标（N = 453）

| model | log_loss | Brier | RPS | ECE |
|---|---:|---:|---:|---:|
| uniform | 1.098612 | 0.666667 | 0.240250 | 0.086093 |
| Elo-only | 1.028208 | 0.617209 | 0.220493 | 0.080288 |
| **baseline prior（生产）** | **1.005268** | 0.600625 | 0.213034 | **0.114102** |
| fitted raw | 0.970488 | 0.577814 | 0.202277 | 0.048973 |
| fitted + temperature | 0.969900 | 0.577688 | 0.202153 | 0.041136 |

fitted+temperature 相对 baseline prior：log_loss `-0.035368`、ECE `-0.072966`。
拟合 temperature = `0.88`。文档结论 `MODEL_ITERATION_PROMISING`。

### 必须精确表述的一点

**不要写成「生产模型比均匀分布差」。** 准确表述是：

> 生产 `BASELINE_PRIOR` 具备判别力——其 log_loss `1.005268` 优于 uniform 的
> `1.098612`；但其校准度 ECE `0.114102` **劣于** uniform 的 `0.086093`
> 与 Elo-only 的 `0.080288`，是该对照表中最差。
> 这是典型的「有判别力但过度自信」特征。

之所以关键：`EV` 对概率是**线性**的，取决于概率的**水平**而非排序。
判别力好但校准差，会让 EV 系统性偏离，而排序类指标看不出来。

### 范围限制（必须写入报告）

```text
- 单折结果，N=453，1X2，仅五大联赛 Understat xG
- 不是 AH/OU 五态指标
- 后续 robustness workorder
  docs/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_WORKORDER.md
  正是因为「单折 + 逼近市场级」而要求先证稳健性，该验证结论未见于仓库
  [CORRECTION 2026-08-29] 上句为错误历史记录，保留用于审计追踪。
  稳健性验证已完成并归档于：
  docs/archive/league_whitelist/W2_UNDERSTAT_MODEL_ITERATION_1_ROBUSTNESS_20260707.md
  状态为 ROBUST_IMPROVEMENT。错误原因是原审计只搜索 docs/league_whitelist/，
  未搜索 docs/archive/。
- 因此本节只能支持 BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD，
  不得写成已确证的生产缺陷
```

### 该模型两次未落地

- `temperature = 0.88` 从未进入 `src/w2/strategy/calibration.py`
- Factor V2 Gate 1 因 ECE 恶化保持 FAIL（见 V1.4 计划书 §2.5 引用）

---

## 4. 你要产出什么

### 4.1 生成两份产物

```text
docs/review_packages/W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md
docs/review_packages/W2_BASELINE_PARAMETER_PROVENANCE.json
```

`W2_BASELINE_PARAMETER_PROVENANCE.json` 至少包含：
参数名、当前值、引入 commit、引入日期、是否存在拟合代码（一律 `false`）、
被哪些测试钉死、`calibration_version`、`calibration_status`。

`W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md` 按 V1.4 计划书 Phase 2.5 的
「审计至少报告」清单组织，对本地不可得的项目明确标注：

```text
NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT
```

具体：clipping frequency、input availability/fail-closed coverage、
AH/OU 五态指标、联赛与时间块稳定性，均属此类。

结论字段只允许：

```text
BASELINE_PROVENANCE_IDENTIFIED_NO_FITTING_EVIDENCE
+
BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD
```

**不得**写 `BASELINE_QUALITY_ESTABLISHED` 或 `PRODUCTION_DEFECT_CONFIRMED`。

### 4.2 在 V1.4.1 计划书中记录三项状态变更

不改 A–J，不改 Gate 结构。只更新状态与排序说明：

1. **Phase 2.5 标为 `PARTIALLY_COMPLETE`**：2.5a 已完成；
   2.5b 定量部分本地不可执行，且 2026-07-07 已有单折证据，
   建议**不重复执行**，除非 robustness 验证需要新窗口。
2. **Gate 0A 标为 `COMPLETE`**，引用两份产物。
3. **新增一节记录优先级问题**（只描述，不自行决定）：

   > 在 `BASELINE_PRIOR` 的校准缺陷得到处置之前，Phase 4 的 EV calibration、
   > Phase 4.5 的 W2-vs-PB 配对与 Phase 7 全部内容，都是以一个校准度
   > 未达标的基准作对照。挑战者相对该基准的胜负不具可解释性。
   > 是否重排优先级、是否冻结 Penaltyblog 轨道，属 Owner 裁决，
   > 本文档不自行改变阶段顺序。

### 4.3 不要做的事

```text
- 不跑 Phase 2.5b（重复劳动，且本地无数据）
- 不继续 Phase 1 / Phase 2，等 Owner 就优先级裁决后再定
- 不修改 calibration.py 或任何业务代码
- 不把 temperature 0.88 或任何拟合结果写入生产路径
- 不申请 Gate 0B
- 不更新 Obsidian
- 不自行改变计划书的阶段顺序或 Gate 结构
```

---

## 5. 验收要求

```text
- 两份产物已生成，结论字段用的是第 4.1 节允许的两个值
- 「比均匀分布差」的错误表述未出现；用的是第 3 节的精确表述
- 单折/N=453/1X2/仅 Understat 的范围限制已写入
- 本地不可得项已逐项标 NOT_EXECUTABLE_LOCALLY_REQUIRES_GATE_0B_OR_EXPORT
- 结构性观察（total 仅由 xG 决定、三项强弱指标相加无正交化）
  已登记为待验证假设，未写成已确认缺陷
- 计划书三项状态变更已落，A–J 与 Gate 结构未动
- 计划书状态仍为唯一一处 PROPOSED_NOT_AUTHORIZED
- 业务代码 diff 为 0
```
