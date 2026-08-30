# W2 Production Lambda Effective Form

状态：`STATIC_CODE_VERIFIED_FACT_DOC`

生产权威：`ea557bb8ff64e06add91bbe32814fe073ec64642 / 0070_notification_delivery_routing`

证据来源：`docs/review_packages/U2_COMPARATOR_CORRECTION_HANDOFF.md`

验证方式：生产镜像静态代码与随镜像 artifact 核验。本文不声称执行了运行时逐 fixture trace，也不执行 U2、导出生产数据、重新拟合 challenger、修改业务代码或部署。

## 1. Binding Conclusion

生产在**当前 11 个启用联赛**上是纯 rolling-xG 模型，只含两个有效常数（`1.14` 与非中立场的 `0.12`）和两组 clamp：

```text
adjusted_delta = 1.14 * raw_delta + 0.12
```

其中 `1.14` 不是独立 Elo 信息带来的增益。生产 Elo 是 rolling xG 的确定性 proxy，`elo_gap_weight = 0.28` 将 `raw_delta` 放大 14%。该系数有效，不能描述为死代码。

当前启用联赛的身价项与当前生产构造路径的首发项为零贡献。身价结论由 competition-scoped artifact 可得性决定，只限当前启用联赛；若未来联赛存在匹配的 `team_values` artifact，该项可以重新生效。

## 2. Production Construction Evidence

### 2.1 Elo is a deterministic rolling-xG proxy

生产镜像 `/app/src/w2/prematch/analysis_calculator.py:3107`：

```python
home_ratings = self._team_ratings_from_existing_xg_snapshots(home_xg)
```

同文件 `:4674-4692` 的 proxy 构造为：

```text
elo = 1500.0 + (row.xg_for - row.xg_against) * 100.0
source = rolling_xg_proxy
is_independent_signal = False
proxy_of = ratings
collection_status = PROXY_ONLY
```

因此 Elo 项有数值效果，但不提供 xG 之外的独立信息。

### 2.2 Squad value is zero for the current enabled leagues

`analysis_calculator.py:4383,4388-4398` 的 `_team_value_mapping` 按 competition 读取静态 `team_values` artifact；路径不存在时返回空 mapping。

生产镜像 `/app/config/team_values/` 只有：

```text
README.md
world_cup_2026.team_ids.csv
world_cup_2026.v1.json
```

当前 11 个启用联赛为：

```text
argentina_primera
brasileirao_serie_a
eliteserien
ligue_1
eredivisie
mls
primeira_liga
bundesliga
la_liga
premier_league
serie_a
```

两者交集为空，因此这些联赛的 `latest_*_value` 为 `None`，`value_delta = 0`。`squad_value_log_weight = 0.18` 对当前全部生产流量为死代码。此结论不得外推到存在匹配 `team_values` artifact 的其他 competition。

### 2.3 Lineup numeric adjustment is zero in the production path

生产 `/app/src/w2/` 中 `SimulationInputs(` 只有 `analysis_calculator.py:3192` 一个构造点。该构造点没有设置五个 lineup 字段，所以使用 `simulate.py:41-45` 的默认值：

```text
lineup_strength_adjustment = 0.0
lineup_ah_adjustment = 0.0
lineup_totals_adjustment = 0.0
lineup_ah_evidence_enabled = False
lineup_totals_evidence_enabled = False
```

静态核验同时排除了 `SimulationInputs(**...)`、`replace(inputs, ...)` 和 `asdict` 展开式绕过路径。独立的 capability manifest 还记录：

```text
lineup_numeric_adjustment_ah = NOT_IMPLEMENTED
lineup_numeric_adjustment_ou = NOT_IMPLEMENTED
feature_enabled = False
evidence_status = NUMERIC_VALUE_MODEL_NOT_IMPLEMENTED
```

所以 `lineup_adjustment_weight = 0.08` 在当前生产构造路径恒乘以零，是死代码。

### 2.4 Home advantage and Dixon-Coles rho

- `home_advantage_goals = 0.12` 是五项中唯一真实加性常数；中立场关闭 home advantage 时不得加上该项。
- `dixon_coles_rho = 0.0` 默认关闭，`tau_correction` 为 no-op。

## 3. Elo Multiplier Derivation

定义：

```text
base_h = (xgF_h + xgA_a) / 2
base_a = (xgF_a + xgA_h) / 2
raw_delta = base_h - base_a
```

生产 proxy Elo 的主客差为：

```text
elo_h - elo_a
  = [1500 + (xgF_h - xgA_h) * 100]
    - [1500 + (xgF_a - xgA_a) * 100]
  = (xgF_h - xgA_h - xgF_a + xgA_a) * 100
  = 2 * raw_delta * 100
```

代入 `elo_gap_weight = 0.28`：

```text
elo_delta
  = ((elo_h - elo_a) / 400) * 0.28
  = ((2 * raw_delta * 100) / 400) * 0.28
  = 2 * raw_delta * 0.25 * 0.28
  = 0.14 * raw_delta
```

所以：

```text
adjusted_delta
  = raw_delta + home_advantage + elo_delta + value_delta + lineup_delta
  = raw_delta + 0.12 + 0.14 * raw_delta + 0 + 0
  = 1.14 * raw_delta + 0.12
```

这也是 U2 comparator 的 fail-closed 身份断言来源：对每个 `raw_delta != 0` 的 fixture，`elo_delta / raw_delta` 必须在 `1e-9` 容差内等于 `0.14`；`raw_delta = 0` 时必须满足 `elo_delta = 0`。任何违反都必须在评分前停止。

## 4. Effective Closed Form

对启用 home advantage 的非中立 fixture：

```text
base_h = (xgF_h + xgA_a) / 2
base_a = (xgF_a + xgA_h) / 2

total     = clamp(base_h + base_a, 1.35, 4.40)
raw_delta = base_h - base_a

adjusted_delta = 1.14 * raw_delta + 0.12

lambda_home = clamp((total + adjusted_delta) / 2, 0.15, 4.25)
lambda_away = clamp((total - adjusted_delta) / 2, 0.15, 4.25)
```

中立 fixture 的同一闭式只移除 `+ 0.12`。身价和首发项仍为零，默认 `rho = 0.0`。

## 5. Five-Parameter Production Identity

| parameter | effective identity | verification |
|---|---|---|
| `home_advantage_goals = 0.12` | 非中立场加性常数 | `VERIFIED` |
| `elo_gap_weight = 0.28` | `raw_delta` 的 14% 放大器，非独立信号 | `VERIFIED` |
| `squad_value_log_weight = 0.18` | 当前启用联赛为零；有匹配 artifact 时可复活 | `VERIFIED` |
| `lineup_adjustment_weight = 0.08` | 当前生产构造路径恒乘零 | `VERIFIED` |
| `dixon_coles_rho = 0.0` | 默认 tau no-op | `VERIFIED` |

五项均已完成静态查证，没有 `NOT_VERIFIED` 项。

## 6. Superseded Inference

此前依据 `team_rating_snapshots` 稀疏和 `team_value_asof_artifacts` 为空，推断 Elo 与身价可能未进入生产。该推论的源表判断错误：Elo 来自 rolling xG proxy，身价来自 competition-scoped `team_values` artifact。

```text
SUPERSEDED_BY_STATIC_CODE_VERIFICATION
```

被推翻的推论仍保留在 `GATE_0B_EXECUTION_RECEIPT.md` 与 `U2_PREREGISTRATION.md` 中作为审计轨迹，不得删除或继续当作当前事实。

## 7. U2 Boundary

U2 当前对照身份必须是：

```text
PRODUCTION_FORMULA_XG_WITH_PROXY_ELO
```

它必须复现 rolling-xG proxy Elo，身价传 `None`，lineup 数值项为 `0.0` 且两个 evidence gate 为 `False`。本事实文档不武装或执行 U2；cohort 仍未导出、未冻结，challenger 仍未重新拟合，结果读取和评分次数均为零。
