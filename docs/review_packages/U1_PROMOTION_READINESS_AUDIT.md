# U1 Promotion Readiness Audit

文档状态：`U1_COMPLETE_U2_NOT_EXECUTED`

审计基线：`main@3b7f87db`

证据来源：`docs/review_packages/U1_U2_HANDOFF.md` 与该基线的本地静态符号/行号复核。

执行边界：本文只记录 U1 已交付的静态审计结果。本轮没有执行 U2、没有重跑 backtest、没有获取 Understat 数据、没有访问 VPS/Provider，也没有修改业务代码或生产路径。

## 1. Executive Result

```text
OFFLINE_COMPARATOR_IDENTITY_CORRECTED
PRODUCTION_FORMULA_PROBABILITY_QUALITY_NOT_MEASURED
UNDERSTAT_FITTED_VS_OFFLINE_COMPARATOR_ROBUST_DELTA_NLL = -0.026376
UNDERSTAT_FITTED_VS_PRODUCTION_FORMULA = NOT_MEASURED
U2_EXECUTION_COUNT = 0
```

原 Understat 报告中名为 `baseline_prior` 的对照实际是
`models/independent.py::predict_from_features(INDEPENDENT_POISSON)`，不是
`strategy/calibration.py::calibrate_lambdas`。因此，`1.005268`、
ECE `0.114102`、单折 `-0.035368` 与稳健四折均值
`-0.026376` 都只能归给离线对照链。生产 champion 的概率质量、
以及 Understat fitted challenger 相对它的差距，至今均未测。

## 2. Comparator Identity Audit

### 2.1 离线报告对照

`src/w2/backtest/free_tier_2024.py:1375-1382` 用
`ModelFamily.INDEPENDENT_POISSON` 调用 `predict_from_features`，并把结果写入
`output["baseline_prior"]`。函数定义在
`src/w2/models/independent.py:356-376`：

```text
base_home = 1.18 + 0.0013 * elo_diff + 0.15 * home_field
base_away = 1.08 - 0.0011 * elo_diff

home_mu = 0.55 * base_home + 0.45 * (home_attack + away_defence) / 2
away_mu = 0.55 * base_away + 0.45 * (away_attack + home_defence) / 2
```

该路径的 caller 仅见于离线/评价代码：

- `src/w2/backtest/free_tier_2024.py:308,404,410,1366,1375`；
- `src/w2/models/correction_evaluation.py:80,86`；
- `src/w2/models/__init__.py:22,47` 只是再导出。

### 2.2 生产公式路径

`src/w2/strategy/calibration.py:35-104` 定义 `calibrate_lambdas`，用四项 xG、
Elo、身价、首发及不同的常数/clamp 组合出 lambda。正式 simulation 的调用点为
`src/w2/strategy/simulate.py:128-143`。

| identity | function | inputs | constants / clamps | caller domain |
|---|---|---|---|---|
| offline comparator | `models/independent.py::predict_from_features` | Elo diff, home field, attack/defence strengths | `1.18/1.08`, `0.0013/0.0011`, `0.15`, `0.55/0.45`; no lambda clamp | offline/evaluation |
| production formula | `strategy/calibration.py::calibrate_lambdas` | xG x4, Elo, squad value, lineup | `0.12/0.28/0.18/0.08`; total `[1.35,4.40]`, lambda `[0.15,4.25]` | formal simulation |

两条 caller graph 不相交，不得因回测字段名 `baseline_prior` 相同就合并模型身份。

## 3. U2 Input Readiness

| production-formula input | offline availability | evidence | U2 treatment |
|---|---|---|---|
| home/away xG for/against | available | `src/w2/backtest/free_tier_2024.py:383-399` builds rolling `xg_for/xg_against` state | required |
| Elo | available | `src/w2/models/independent.py:261-270`; `free_tier_2024.py:383` obtains `proxy_features` | required |
| historical club squad value | unavailable | `config/team_values/` contains only `world_cup_2026.*` | pass `None`; disclose material omission |
| lineup | unavailable | `src/w2/backtest/free_tier_2024.py:50-62` `HistoricalFixture` has no lineup fields | zero adjustments; evidence gates `False` |

`src/w2/strategy/calibration.py:62-84` confirms that missing Elo/value contributions fall back to zero;
`:45-49,85-92` confirms lineup defaults/gates. U2 因此可建立一个只包含 xG + Elo 的生产公式实例，但必须命名为
`PRODUCTION_FORMULA_XG_ELO_ONLY`，不得称为“生产 champion”或“生产运行态”。

身价缺失不是可忽略的形式差异。生产公式的身价项为
`log(home_value / away_value) * 0.18`（`src/w2/strategy/calibration.py:65-74`）；
2 倍与 5 倍身价比约对应 `0.125` 球与 `0.29` 球的 delta。

## 4. Competition Scope

`src/w2/backtest/free_tier_2024.py:36-42` 的 `UNDERSTAT_LEAGUE_CODES` 只包含：

```text
premier_league
la_liga
bundesliga
serie_a
ligue_1
```

`docs/archive/league_whitelist/W2_PRO_DAY1_DATA_AUDIT_MODEL_RECHECK_20260707.md:129-132`
明确说明其他联赛不得继承五大联赛结论。任何未来晋级都必须按 competition 限定，不得全局替换。

## 5. Data and Artifact Readiness

| item | evidence | result |
|---|---|---|
| Understat cache path | `src/w2/backtest/free_tier_2024.py:34-35` | `runtime/w2_understat_xg`; current handoff records it as empty |
| source identity | `src/w2/backtest/free_tier_2024.py:35` | `understat_xg_local` |
| fitted model code | `src/w2/backtest/free_tier_2024.py:1280-1323` | available offline |
| production reference | repository search under `src/w2/strategy`, `prematch`, `domain` | zero references to `free_tier_2024` / `_fit_offline_lambda_model` |
| promotion artifact contract | U1 static audit | absent |

因为 cache 为空，本轮不获取数据或重跑；该限制已在 U2 预注册的 arming checklist 中 fail closed。

## 6. AH/OU Five-State Readiness

不用赔率的 proper-score 路径在代码上可组合：

```text
lambda
  -> normalized_score_matrix()                         models/independent.py:134-145
  -> sum grid by fixed synthetic line                  U2 evaluator to be specified
actual home_goals / away_goals                         free_tier_2024.py:50-60
  -> settle_asian_handicap() / settle_total_goals()    domain/odds.py:83-106
```

五态 NLL/Brier/RPS 不需要赔率；本轮不研究 predicted EV、realized return 或任何 market-relative metric。

### 6.1 Temperature identity guard

`src/w2/backtest/free_tier_2024.py:1606-1644` 的 temperature 是对三类 1X2 概率逐项幂变换后重归一；它没有定义对 score matrix 或五态分布的映射。因此 U2 不得把 `0.88` 直接套到五态概率上创造新模型：

- 五态 primary 只能用冻结的 fitted raw lambdas 产生 score matrix；
- temperature 仅在 1X2 key secondary 中按现有冻结方法使用；
- 若要把 temperature 扩展到五态，必须先另行预注册映射与新模型身份，否则该分支为 `NOT_IDENTIFIABLE`。

## 7. Promotion Readiness Decision

```text
U1_STATIC_READINESS = COMPLETE
U2_PREREGISTRATION = REQUIRED
U2_EXECUTION = NOT_AUTHORIZED
PRODUCTION_PROMOTION = NOT_AUTHORIZED
```

当前证据只支持建立 U2 的预注册文档，不支持执行、晋级、生产替换或把 temperature/拟合系数写入生产路径。
