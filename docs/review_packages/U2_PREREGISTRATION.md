# U2 Five-State Incremental Validation Preregistration

文档状态：`PREREGISTRATION_DRAFT_NOT_ARMED`

审计基线：`main@3b7f87db`

```text
COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_ELO_ONLY
MISSING_PRODUCTION_INPUT_1 = HISTORICAL_CLUB_SQUAD_VALUE
MISSING_PRODUCTION_INPUT_2 = LINEUP
COMPARATOR_IS_PRODUCTION_RUNTIME = FALSE
COMPARATOR_IS_PRODUCTION_CHAMPION = FALSE
U2_EXECUTION_COUNT = 0
```

**身价与首发两路生产输入缺失。** 本对照是生产公式在离线可得 xG + Elo 输入子集上的实例，不是生产运行态，也不得称为“生产 champion”。

本文只预注册 U2。在第 8 节所有 arming 项目冻结并获得 Owner 独立授权前，禁止加载 outcome 评分、执行 backtest、获取 Understat 数据或生成 U2 结果。

## 1. Research Question

在五大联赛、严格 point-in-time 的配对 fixture 上，冻结的 Understat fitted lambda challenger 是否相对 `PRODUCTION_FORMULA_XG_ELO_ONLY` 降低 AH/OU 固定合成线网格的五态 NLL？

本问题评价模型概率质量，不评价赔率、devig、EV、收益、下注决策或生产 admission。

## 2. Frozen Model Identities

### 2.1 Primary comparator

```text
identity = PRODUCTION_FORMULA_XG_ELO_ONLY
function = src/w2/strategy/calibration.py::calibrate_lambdas
params = LambdaCalibrationParams() at main@3b7f87db

home_xg_for / home_xg_against / away_xg_for / away_xg_against
  = rolling Understat xG strictly before fixture kickoff
home_elo / away_elo
  = proxy Elo strictly before fixture kickoff
home_squad_value_eur = None
away_squad_value_eur = None
lineup_strength_adjustment = 0.0
lineup_ah_adjustment = 0.0
lineup_totals_adjustment = 0.0
lineup_ah_evidence_enabled = False
lineup_totals_evidence_enabled = False
```

中立场必须传 `apply_home_advantage = False`，其余 fixture 为 `True`。所有输入缺失、clamp 触发和模型失败必须逐行记录。

### 2.2 Secondary offline comparator

`src/w2/models/independent.py::predict_from_features(ModelFamily.INDEPENDENT_POISSON)` 保留为第二对照，只用于与 2026-07-07 Understat 报告衔接。该对照不得代替 primary，也不得称为生产模型。

### 2.3 Challenger

拟合算法、特征集、L2、iteration、learning rate、temperature 拟合规则和联赛范围均继承 `main@3b7f87db` 的既有 Understat fitted identity，禁止因 U2 结果调整。

五态 primary 的 challenger 身份为冻结的 fitted **raw lambdas** 生成的 normalized score matrix。`free_tier_2024.py:1606-1644` 的 temperature 只定义了 1X2 概率缩放，因此仅用于 1X2 key secondary。本预注册不创造 temperature-to-five-state 映射；若执行方无法保持该边界，五态分支必须返回 `NOT_IDENTIFIABLE`。

## 3. Frozen Scope and Synthetic Lines

联赛范围只允许：

```text
premier_league / la_liga / bundesliga / serie_a / ligue_1
```

任何晋级结论必须 per-competition scoped，不得扩展至其他联赛或全局 champion。

固定合成线网格：

```text
OU = 1.5 / 2.0 / 2.5 / 3.0 / 3.5
AH = 0 / +/-0.25 / +/-0.5 / +/-0.75 / +/-1.0 / +/-1.5
```

为避免把对称选项当成独立样本，每条线只评分一个 canonical selection：AH = `HOME`，OU = `OVER`。相反选项只用于对称性合同测试，不重复进入 primary N。

分层为：

- `EXACT_HALF_LINE`：二态，只有 `WIN/LOSS`；
- `INTEGER_LINE`：包含 `PUSH`；
- `QUARTER_LINE`：五态结算。

## 4. Outcome and Probability Construction

每个 model/fixture 先生成 normalized score matrix，再按合成线求和为：

```text
LOSS / HALF_LOSS / PUSH / HALF_WIN / WIN
```

实现 outcome 只由真实比分与固定线通过
`domain/odds.py::settle_asian_handicap` / `settle_total_goals` 确定。每个五态概率向量必须非负、有限且总和在冻结数值容差内为 1；非法向量 fail closed 并写入 failure ledger。

RPS 的有序类别顺序冻结为：

```text
LOSS < HALF_LOSS < PUSH < HALF_WIN < WIN
```

## 5. Estimands

### 5.1 Primary

对每个合法 fixture `f`、market `m` 和 line `l`：

```text
NLL_comparator(f,m,l) = -log(p_comparator(actual_settlement))
NLL_challenger(f,m,l) = -log(p_challenger(actual_settlement))

d(f,m,l) = NLL_comparator(f,m,l) - NLL_challenger(f,m,l)
```

正 `d` 表示 challenger 优于 `PRODUCTION_FORMULA_XG_ELO_ONLY`。主结果按 market 与 line type 分层报告，同时报告每层 fixture N、fixture-line N、coverage 与 failure rate。不得用一个总 pooled N 隐藏联赛或线型差异。

### 5.2 Key secondary

- 五态 Brier；
- 五态 RPS；
- 按 settlement outcome 的 calibration table/plot data；
- 1X2 LogLoss/Brier/RPS/ECE，用于与既有报告衔接，不是 primary。

### 5.3 Explicit exclusions

```text
predicted EV vs realized return = NOT_RUN
market-relative metric = NOT_RUN
devig = NOT_USED
odds / executable quote = NOT_USED
ROI / staking / recommendation = NOT_RUN
```

## 6. Pairing, PIT and Row Conservation

配对集合必须满足：

```text
fixture identity valid
actual score valid
all model inputs strictly timestamped before kickoff
PRODUCTION_FORMULA_XG_ELO_ONLY prediction valid
challenger prediction valid
fixed synthetic line valid
five-state probability vector valid
```

每个 fixture 必须有 `training_cutoff < kickoff`、训练行集 digest、input availability、clamp 状态、两模型预测状态和排除原因。禁止 fallback、禁止用另一模型填失败行、禁止静默丢行。

每层必须证明：

```text
candidate_rows = paired_rows + excluded_rows
comparator_fixture_ids = challenger_fixture_ids = outcome_fixture_ids on paired set
reported_fixture_line_N = exact count of scored rows
```

## 7. Uncertainty and Futility Contract

聚类维度冻结为 `matchday` 与 `league`。精确的多维 cluster 不确定性算法、bootstrap 次数和 seed 必须在查看任何 U2 outcome metric 前填入第 8 节并冻结；本文不伪造交接单未给出的数值。

MME 和目标 N 同样必须事前冻结。评分 outcome 之前，先基于冻结的 `DeltaNLL_achievable`、目标 N、cluster 设计和不确定性方法计算可检测下限：

```text
if MME < detectable_floor:
    return INSUFFICIENT_POWER_DO_NOT_SCORE
    do not compute or view outcome scores
```

禁止在查看 U2 结果后修订 MME、futility rule、primary、线网格、cohort 或 model identity。

## 8. Pre-Execution Arming Checklist

`PENDING_BEFORE_ARMING` 表示本轮未执行，不是授权执行方自行选值。

| freeze item | required frozen value / artifact | current status |
|---|---|---|
| comparator identity | `PRODUCTION_FORMULA_XG_ELO_ONLY`; exact params and code SHA | `FROZEN_IN_SPEC` |
| comparator missing inputs | squad value `None`; all lineup values zero/gates false | `FROZEN_IN_SPEC` |
| offline second comparator | `predict_from_features(INDEPENDENT_POISSON)` | `FROZEN_IN_SPEC` |
| challenger algorithm | existing fitted-lambda algorithm/L2/training rule; no U2 tuning | `FROZEN_IN_SPEC` |
| five-state temperature boundary | raw lambdas only for primary; temperature only for 1X2 secondary | `FROZEN_IN_SPEC` |
| challenger artifact | coefficients, temperature, training-row digest, artifact SHA-256 | `PENDING_BEFORE_ARMING` |
| fixture cohort | exact date interval, competitions, eligibility and fixture-set SHA-256 | `PENDING_BEFORE_ARMING` |
| PIT contract | per-fixture cutoff and training-row digest; strict `< kickoff` | `PENDING_BEFORE_ARMING` |
| synthetic line grid | section 3 exact AH/OU grid and canonical selections | `FROZEN_IN_SPEC` |
| primary estimand | section 5 sign and strata | `FROZEN_IN_SPEC` |
| MME | numeric NLL MME with rationale | `PENDING_BEFORE_ARMING` |
| target N / power inputs | target fixture and fixture-line N; achievable delta assumptions | `PENDING_BEFORE_ARMING` |
| cluster uncertainty | exact multiway method, bootstrap repetitions and seed | `PENDING_BEFORE_ARMING` |
| coverage/failure rule | minimum coverage; full reason taxonomy; no-silent-loss assertions | `PENDING_BEFORE_ARMING` |
| futility rule | executable detectable-floor formula and immutable decision artifact | `PENDING_BEFORE_ARMING` |
| outcome access guard | proof no U2 outcome score was viewed before all prior rows froze | `PENDING_BEFORE_ARMING` |
| Owner execution authority | separate explicit authorization | `NOT_AUTHORIZED` |

只有所有 `PENDING_BEFORE_ARMING` 项转为可核验的冻结值、artifact 及 hash，且 Owner 明确授权执行后，U2 才可 armed。

## 9. Allowed Conclusions

```text
CHALLENGER_FIVE_STATE_BETTER
NO_FIVE_STATE_IMPROVEMENT
NOT_IDENTIFIABLE
INSUFFICIENT_POWER_DO_NOT_SCORE
```

任何结论都不授权替换生产模型、把 temperature/拟合系数写入生产路径、产生 EV/投注建议或扩展至五大联赛以外。

## 10. Stop Record

```text
U2_EXECUTED = FALSE
UNDERSTAT_DATA_FETCHED = FALSE
BACKTEST_RUN = FALSE
GATE_0B_REQUESTED = FALSE
BUSINESS_CODE_CHANGED = FALSE
PRODUCTION_PATH_CHANGED = FALSE
```
