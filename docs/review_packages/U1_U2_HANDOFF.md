# U1 结果 + U2 规格 交接单

用途：Codex 的唯一输入。自包含，不依赖对话上下文。
执行者：Claude Code，只读静态审计，`origin/main@3b7f87db` detached worktree
状态：`U1_COMPLETE_U2_SPEC_DOCS_ONLY`
授权范围：**文档更正 + U2 预注册撰写**。不改业务代码、不跑 backtest、不取数据、不访问 VPS/Provider、不部署。

---

## 0. 头号发现：对照身份错配（必须先更正）

### 0.1 事实

`src/w2/backtest/free_tier_2024.py:1375` 的 `baseline_prior` 对照是：

```python
predict_from_features(fixture_id, ModelFamily.INDEPENDENT_POISSON, sample.true_features, kickoff)
```

来自 `src/w2/models/independent.py:356`。**该回测文件从未 import 生产的 `calibrate_lambdas`。**

两者是不同模型，不是「缺几个输入」：

| | 离线对照 `predict_from_features` | 生产 `calibrate_lambdas` |
|---|---|---|
| 函数形式 | `0.55·base + 0.45·(attack+defence)/2` | xG 推总进球，再按加性 delta 拆分 |
| 常数 | `1.18 / 0.0013 / 0.15 / 0.55 / 0.45` | `0.12 / 0.28 / 0.18 / 0.08` |
| 输入 | `elo_diff`、`home_field`、attack/defence 强度 | xG for/against ×4、Elo、身价、首发 |
| 身价 / 首发 | 无 | 有 |
| clamp | 无 | total `[1.35,4.40]`、λ `[0.15,4.25]` |

调用点完全不相交（均已实测）：

```text
predict_from_features → models/__init__(再导出)、models/correction_evaluation.py、
                        backtest/free_tier_2024.py     全部离线/评价路径
calibrate_lambdas     → strategy/simulate.py:128       唯一调用者，正式 simulation
```

### 0.2 后果

```text
生产 BASELINE_PRIOR 的概率质量        仍然完全未测
Understat fitted vs 生产 champion     未知，方向亦未知
Understat fitted vs 离线对照           稳健领先 0.026 nats（该结论本身仍成立）
```

生产 champion 使用了**更多**输入（xG 总量、身价、首发），因此差距可能缩小、消失或反向。

### 0.3 需要更正的位置

`docs/review_packages/W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md`：

| 行 | 现文 | 应改为 |
|---|---|---|
| 103 | 表格行 `**baseline prior（生产）**` | `baseline prior（离线对照 models/independent.py::predict_from_features, INDEPENDENT_POISSON）` |
| 107 | 「生产 `BASELINE_PRIOR` 具备判别力……」 | 主语改为该离线对照，并追加一句：生产 `BASELINE_PRIOR` 的概率质量尚未测量 |
| 109 / 111 / 147 | `-0.035368` / `-0.026376` 相对 "baseline prior" | 明确该 delta 是相对**离线对照**，不是相对生产 champion |
| 18 | 结论字段说明 | 追加：本报告不含生产 champion 的概率质量结论 |

结论字段仍只允许原两个值。`BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD`
的主语必须同步改为离线对照，不得留给生产模型。

同时在 `PHASE_2_5A_CORRECTION_HANDOFF.md` 末尾追加本节，**不删除既有内容**，保留轨迹。

---

## 1. U1 其余结果

### 1.1 输入可得性（决定 U2 能不能跑）

| 生产输入 | 离线是否可得 | 证据 |
|---|---|---|
| xG for / against ×4 | **可得** | `free_tier_2024.py:396-399` rolling Understat `xg_for` / `xg_against` |
| Elo | **可得** | `proxy_features["elo_diff"]`，`free_tier_2024.py:383` |
| 身价 | **不可得** | `config/team_values/` 只有 `world_cup_2026`，无历史俱乐部身价 |
| 首发 | **不可得** | `HistoricalFixture`（`:50-62`）无首发字段 |

`calibrate_lambdas` 对缺失输入优雅降级：Elo 缺 → `elo_delta = 0`；
身价缺 → `value_delta = 0`；首发默认 `0.0` 且证据门默认 `False`。
因此可用 xG + Elo 驱动生产公式。

**量级提示**：身价项为 `log(v_h/v_a) × 0.18`。2 倍身价比 ≈ `0.125` 球，
5 倍 ≈ `0.29` 球。缺该项会在实力悬殊场次系统性改变 delta，**不可忽略**。

### 1.2 联赛范围

`free_tier_2024.py:36` `UNDERSTAT_LEAGUE_CODES` 恰好五个：
`premier_league / la_liga / bundesliga / serie_a / ligue_1`。

`docs/archive/league_whitelist/W2_PRO_DAY1_DATA_AUDIT_MODEL_RECHECK_20260707.md:131-132`
明确警告其余联赛不得继承五大联赛结论。因此任何晋级必须是
**per-competition scoped**，不是全局 champion 替换。

### 1.3 数据与产物

```text
DEFAULT_UNDERSTAT_CACHE_DIR = runtime/w2_understat_xg   （当前为空，需重新获取公开数据）
UNDERSTAT_XG_SOURCE = "understat_xg_local"
模型 artifact 合同                                       不存在
生产路径对 free_tier_2024 的引用                          0 处
```

### 1.4 AH/OU 五态可评价性：**可行，且不需要任何赔率**

链路在 `main` 上齐全：

```text
λ  →  normalized_score_matrix()        models/independent.py:134
score grid + line  →  五态预测分布      网格求和
真实比分 + line     →  五态实现结果      domain/odds.py:83 settle_asian_handicap()
                                        domain/odds.py:99 settle_total_goals()
真实比分可得                            free_tier_2024.py:59-60 home_goals/away_goals
```

**五态 proper score（NLL/Brier/RPS）不需要赔率。** 只有
`predicted EV vs realized return` 需要。盘口线使用**固定合成线网格**，
不使用报价线，因此完全绕开 devig authority 问题。

---

## 2. U2 规格（先写预注册，本轮不执行）

### 2.1 对照身份（必须显式声明）

```text
COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_ELO_ONLY

即 strategy/calibration.py::calibrate_lambdas，参数为默认 LambdaCalibrationParams，
输入为离线 rolling Understat xG + proxy Elo，
home_squad_value_eur = None，away_squad_value_eur = None，
lineup_* = 0.0，lineup_ah_evidence_enabled = False，lineup_totals_evidence_enabled = False。
```

**禁止**称其为「生产 champion」。必须在报告首屏写明：
生产四路输入中的**身价与首发两路缺失**，因此本对照是
「生产公式在可得输入子集上的实例」，不是生产运行态。

同时保留 `predict_from_features` 作为**第二对照**，用于与既有 Understat 报告可比。

### 2.2 挑战者

Understat fitted lambda + temperature，**完全冻结**：
系数拟合算法、L2、temperature 拟合规则、特征集、联赛集合一律不动。
**不得**因 U2 结果调整任何一项。

### 2.3 线网格（执行前冻结）

```text
OU:  1.5 / 2.0 / 2.5 / 3.0 / 3.5
AH:  0 / ±0.25 / ±0.5 / ±0.75 / ±1.0 / ±1.5
```

分层报告：`exact half-line`（二态，`S=1`）/ `integer line`（含 push）/ `quarter line`（五态）。

### 2.4 Primary estimand

```text
PRIMARY
  五态 NLL 的逐 fixture 配对差
  d_i = NLL_comparator,i - NLL_challenger,i
  按 line type 分层；cluster = matchday 与 league

KEY SECONDARY
  五态 Brier / RPS
  settlement calibration by outcome
  1X2（用于与既有报告衔接，非 primary）

不做
  predicted EV vs realized return   （需赔率，本轮不做）
  任何 market-relative 指标          （需 devig authority）
```

### 2.5 执行前必须冻结

```text
comparator identity 与其输入缺失清单
challenger 模型身份与 artifact hash
fixture cohort 与 digest
线网格
primary estimand 与符号约定
MME
cluster 定义与不确定度方法（seed、bootstrap）
coverage / failure 规则
futility 规则
```

**futility 规则必须先算再跑**：按 `ΔNLL_achievable` 与目标 N 估计可检测下限，
若 MME 低于该下限，返回 `INSUFFICIENT_POWER_DO_NOT_SCORE`，不看结果。

### 2.6 允许的结论

```text
CHALLENGER_FIVE_STATE_BETTER
NO_FIVE_STATE_IMPROVEMENT
NOT_IDENTIFIABLE
INSUFFICIENT_POWER_DO_NOT_SCORE
```

任何结论都**不**授权替换生产 champion，也不授权把 temperature 或系数写入生产路径。

---

## 3. 本轮要产出什么

1. 按第 0.3 节更正 `W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md`，并在
   `PHASE_2_5A_CORRECTION_HANDOFF.md` 末尾追加轨迹；
2. 生成 `docs/review_packages/U1_PROMOTION_READINESS_AUDIT.md`，
   内容为本单第 0 与第 1 节，逐项给出文件与行号证据；
3. 生成 `docs/review_packages/U2_PREREGISTRATION.md`，内容为第 2 节，
   把 2.5 的冻结项写成可核对清单；
4. 在计划书的 `OWNER_DECISION_REQUIRED` 一节更正：
   删除或改写「已存在优于当前 champion 约 0.026 nats 的模型」这一表述，
   改为「已存在优于某离线对照约 0.026 nats 的模型；相对生产 champion 的差距未测」。

## 4. 不要做

```text
不执行 U2（本轮只写预注册）
不重跑 backtest、不获取 Understat 数据
不改 calibration.py / independent.py / free_tier_2024.py 或任何业务代码
不把 temperature 0.88 或任何拟合结果写入生产路径
不申请 Gate 0B
不动 Penaltyblog 计划的 A–J 与 Gate 结构
不更新 Obsidian
```

计划书状态保持唯一一处 `PROPOSED_NOT_AUTHORIZED`。
