# U1 Promotion Readiness Audit

文档状态：`U1_COMPLETE_GATE_0B_AMENDED_U2_NOT_EXECUTED`

生产权威基线：`ea557bb8ff64e06add91bbe32814fe073ec64642 / 0070_notification_delivery_routing`

历史静态快照：`origin/main@3b7f87db / 0051_apply_seven_day_collection_policy`（落后生产 19 个 migration，不是运行权威）

证据来源：`docs/review_packages/U1_U2_HANDOFF.md`、`docs/review_packages/GATE_0B_AND_U2_COHORT_HANDOFF.md` 与交接单记录的跨基线逐文件复核。

执行边界：U1 静态结论已用 Gate 0B 生产只读结果修订。Gate 0B 只使用 `docker ps` / `docker inspect` / `psql -tAc SELECT`；Provider 调用、业务写入、生产导出与部署均为 0。本轮没有执行 U2、没有重跑 backtest，也没有修改业务代码或生产路径。

## 1. Executive Result

```text
OFFLINE_COMPARATOR_IDENTITY_CORRECTED
PRODUCTION_FORMULA_PROBABILITY_QUALITY_NOT_MEASURED
UNDERSTAT_FITTED_VS_OFFLINE_COMPARATOR_ROBUST_DELTA_NLL = -0.026376
UNDERSTAT_FITTED_VS_PRODUCTION_FORMULA = NOT_MEASURED
PRODUCTION_RUNTIME_AUTHORITY = ea557bb8 / schema 0070
ORIGIN_MAIN_3b7f87db = HISTORICAL_STATIC_SNAPSHOT_19_MIGRATIONS_BEHIND
U2_COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_ONLY
U2_COHORT = team_xg_match_METADATA_ONLY_NOT_EXPORTED_NOT_FROZEN
U2_EXECUTION_COUNT = 0
```

原 Understat 报告中名为 `baseline_prior` 的对照实际是
`models/independent.py::predict_from_features(INDEPENDENT_POISSON)`，不是
`strategy/calibration.py::calibrate_lambdas`。因此，`1.005268`、
ECE `0.114102`、单折 `-0.035368` 与稳健四折均值
`-0.026376` 都只能归给离线对照链。生产 champion 的概率质量、
以及 Understat fitted challenger 相对它的差距，至今均未测。

## 2. Authority Correction and Conclusion Survival

Gate 0B 实测确认生产 `ea557bb8 / schema 0070` 才是权威。`origin/main@3b7f87db / schema 0051` 只是给审计 agent 的选择性静态快照，落后生产 19 个 migration。

这一基线方向更正**不会自动使 U1 结论作废**。Gate 0B 已对两个 commit 做逐文件比较：

| core file | `3b7f87db` vs `ea557bb8` | dependent conclusion | survival |
|---|---|---|---|
| `src/w2/strategy/calibration.py` | byte-identical | `BASELINE_PRIOR` 硬编码系数与无拟合证据 | `SURVIVES` |
| `src/w2/domain/five_state_pricing.py` | byte-identical | 量化前 `EV/S` 身份存活；经 fair-odds 量化后代码层 `cashflow_price_edge` 仅近似 | `SURVIVES` |
| `src/w2/models/independent.py` | byte-identical | 离线 comparator 与生产公式身份错配 | `SURVIVES` |
| `src/w2/backtest/free_tier_2024.py` | byte-identical | 历史 U1 输入可得性与五联赛 Understat 范围 | `SURVIVES_AS_HISTORICAL_STATIC_CONCLUSION` |

另有两个文件变更：`analysis_evidence.py` `+34` 行、`lifecycle.py` `+339` 行。因此 `FIVE_PERCENT_SEMANTIC_REGISTRY.md` 只能标记 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`，不得宣布作废或继续当作生产实证。

## 3. Comparator Identity Audit

### 3.1 离线报告对照

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

### 3.2 生产公式路径

`src/w2/strategy/calibration.py:35-104` 定义 `calibrate_lambdas`，用四项 xG、
Elo、身价、首发及不同的常数/clamp 组合出 lambda。正式 simulation 的调用点为
`src/w2/strategy/simulate.py:128-143`。

| identity | function | inputs | constants / clamps | caller domain |
|---|---|---|---|---|
| offline comparator | `models/independent.py::predict_from_features` | Elo diff, home field, attack/defence strengths | `1.18/1.08`, `0.0013/0.0011`, `0.15`, `0.55/0.45`; no lambda clamp | offline/evaluation |
| production formula | `strategy/calibration.py::calibrate_lambdas` | xG x4, Elo, squad value, lineup | `0.12/0.28/0.18/0.08`; total `[1.35,4.40]`, lambda `[0.15,4.25]` | formal simulation |

两条 caller graph 不相交，不得因回测字段名 `baseline_prior` 相同就合并模型身份。

## 4. U2 Input Readiness After Gate 0B

| production-formula input | Gate 0B availability | evidence | U2 V2 treatment |
|---|---|---|---|
| home/away xG for/against | available | production `team_xg_match`: 19,004 team rows / 9,502 fixtures / 100% non-null | required; derive rolling xG with strict PIT |
| Elo | effectively unavailable for historical cohort | `team_rating_snapshots`: 16 rows / 16 teams / only 2026-07-17 to 2026-07-20 | pass `None` |
| historical club squad value | unavailable at team as-of level | `team_value_asof_artifacts`: 0 rows; player-level rows do not substitute for team as-of artifact | pass `None` |
| lineup | unavailable in cohort contract | audited persisted payloads do not contain calibration input fields | zero adjustments; evidence gates `False` |

`src/w2/strategy/calibration.py:62-84` 确认 Elo/身价缺失时相应 delta 为 0，`:45-49,85-92` 确认 lineup 默认值和证据门。U2 V2 对照因此必须命名为 `PRODUCTION_FORMULA_XG_ONLY`，不得称为“生产 champion”或“生产运行态”。

“生产历史上绝大多数 fixture 未实际使用 Elo/身价”只是根据源表空/极稀疏得出的推论，必须始终带标记：

```text
INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED
```

`dynamic_prematch_evaluations` / `model_forecast_capture` / `recommendation_locks` 的持久化 payload 不包含 calibration 输入字段，因此不能把该推论升级成运行时实证。

身价缺失不是可忽略的形式差异。生产公式的身价项为
`log(home_value / away_value) * 0.18`（`src/w2/strategy/calibration.py:65-74`）；
2 倍与 5 倍身价比约对应 `0.125` 球与 `0.29` 球的 delta。

## 5. Historical Competition Scope

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

## 6. Data and Artifact Readiness

| item | evidence | result |
|---|---|---|
| Understat cache path | local and production filesystem check | `runtime/w2_understat_xg/understat_*.json` absent; historical cohort cannot be reproduced |
| source identity | `src/w2/backtest/free_tier_2024.py:35` | `understat_xg_local` |
| fitted model code | `src/w2/backtest/free_tier_2024.py:1280-1323` | available offline |
| production reference | repository search under `src/w2/strategy`, `prematch`, `domain` | zero references to `free_tier_2024` / `_fit_offline_lambda_model` |
| promotion artifact contract | U1 static audit | absent |
| replacement cohort metadata | production `team_xg_match` read-only counts | 9,502 fixtures, 2024-02-22 through 2026-08-29, `api_football_statistics` |

原 Understat cohort 不可复现。替代生产 cohort 本轮只有汇总元数据，没有导出 fixture IDs 或数据行，因此尚未冻结。换 cohort 后 challenger 必须在新 cohort 的训练前缀上重新拟合，不得直接搬用 Understat 系数或 temperature。

## 7. AH/OU Five-State Readiness

不用赔率的 proper-score 路径在代码上可组合：

```text
lambda
  -> normalized_score_matrix()                         models/independent.py:134-145
  -> sum grid by fixed synthetic line                  U2 evaluator to be specified
actual home_goals / away_goals                         free_tier_2024.py:50-60
  -> settle_asian_handicap() / settle_total_goals()    domain/odds.py:83-106
```

五态 NLL/Brier/RPS 不需要赔率；本轮不研究 predicted EV、realized return 或任何 market-relative metric。

### 7.1 Temperature identity guard

`src/w2/backtest/free_tier_2024.py:1606-1644` 的 temperature 是对三类 1X2 概率逐项幂变换后重归一；它没有定义对 score matrix 或五态分布的映射。因此 U2 不得把 `0.88` 直接套到五态概率上创造新模型：

- 五态 primary 只能用冻结的 fitted raw lambdas 产生 score matrix；
- temperature 仅在 1X2 key secondary 中按现有冻结方法使用；
- 若要把 temperature 扩展到五态，必须先另行预注册映射与新模型身份，否则该分支为 `NOT_IDENTIFIABLE`。

## 8. Promotion Readiness Decision

```text
U1_STATIC_READINESS = COMPLETE
GATE_0B_PRODUCTION_IDENTITY = COMPLETE_READ_ONLY
U2_PREREGISTRATION_V2 = DRAFT_NOT_ARMED
U2_NEW_COHORT = METADATA_ONLY_NOT_EXPORTED_NOT_FROZEN
U2_CHALLENGER_REFIT = REQUIRED_AFTER_RULE_FREEZE
U2_EXECUTION = NOT_AUTHORIZED
PRODUCTION_PROMOTION = NOT_AUTHORIZED
```

当前证据只支持修订 U2 V2 预注册，不支持执行、导出生产数据、重新拟合、晋级、生产替换或把 temperature/拟合系数写入生产路径。新 cohort 的任何结果不得与 2026-07 的 `-0.026376` / `-0.035368` 直接比较。
