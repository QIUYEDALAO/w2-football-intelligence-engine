# U2 对照身份更正交接单

用途：Codex 的唯一输入。自包含，不依赖对话上下文。
执行者：Claude Code，生产镜像静态只读（`docker exec grep/sed/ls`）+ 代数验证
状态：`CORRECTION_HANDOFF_DOCS_ONLY`
授权范围：**仅文档更正**。不改业务代码、不执行 U2、不写生产、不部署。

---

## 1. 被推翻的推论

`U2_PREREGISTRATION.md` V2 与 `GATE_0B_EXECUTION_RECEIPT.md` 目前记录：

```text
INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED
  依据 team_rating_snapshots 极稀疏、team_value_asof_artifacts 为空，
  推断 elo_gap_weight 与 squad_value_log_weight 在生产中不起作用。
```

**该推论的源表判断错误。** 生产不从这两张表读取 Elo 与身价。

因为它被正确标记为推论而非结论，**已发布的任何结论都不需要收回**；
本单只更正推论内容与由它推出的 U2 对照定义。

---

## 2. 生产实际形态（生产镜像静态实测）

### 2.1 Elo 是 rolling xG 的确定性代理

`/app/src/w2/prematch/analysis_calculator.py:3107`：

```python
home_ratings = self._team_ratings_from_existing_xg_snapshots(home_xg)
```

同文件 `:4674-4692` 的实现：

```python
elo = 1500.0 + (row.xg_for - row.xg_against) * 100.0
source = "rolling_xg_proxy"
is_independent_signal = False
proxy_of = "ratings"
collection_status = "PROXY_ONLY"
```

代码自身即声明该值为 proxy、非独立信号。

### 2.2 代数后果：`elo_delta = 0.14 × raw_delta`

```text
raw_delta = (xgF_h + xgA_a)/2 - (xgF_a + xgA_h)/2

elo_h - elo_a = (xgF_h - xgA_h - xgF_a + xgA_a) * 100
              = 2 * raw_delta * 100

elo_delta = ((elo_h - elo_a) / 400) * 0.28
          = 2 * raw_delta * 0.07
          = 0.14 * raw_delta
```

数值验证 5 组随机 xG，比值恒为 `0.1400`。

因此生产的实际 delta 为：

```text
adjusted_delta = raw_delta + 0.12 + elo_delta + value_delta + lineup
               = 1.14 * raw_delta + 0.12 + value_delta + lineup
```

**`elo_gap_weight = 0.28` 不是独立信号权重，而是 xG delta 的 14% 放大器。**
仅阅读 `strategy/calibration.py` 无法看出这一点；必须追踪 Elo 的构造处。

### 2.3 身价对所有启用联赛为空

`analysis_calculator.py:4383` → `_team_value_mapping`（`:4388-4398`）：
按 competition 作用域读取静态 `team_values` artifact，默认 `world_cup_2026`；
路径不存在时 `return {}`。

生产镜像 `/app/config/team_values/` 实际内容：

```text
README.md
world_cup_2026.team_ids.csv
world_cup_2026.v1.json
```

生产启用联赛（`league_season.payload.enabled = true`，11 个）：

```text
argentina_primera  brasileirao_serie_a  eliteserien  ligue_1  eredivisie
mls  primeira_liga  bundesliga  la_liga  premier_league  serie_a
```

**交集为空。** 每个启用联赛均走到 `return {}`，
`latest_*_value` 为 `None`，`value_delta = 0`。

`squad_value_log_weight = 0.18` 对当前全部生产流量为死代码。

### 2.4 五个系数的真实身份

### 2.4 lineup 项确证为死代码（两条独立证据）

**证据一 —— 唯一构造点从不填充。**
`SimulationInputs(` 在 `/app/src/w2/` 中只有一个构造点：
`analysis_calculator.py:3192`。该处设置 xG×4、elo×3、squad_value×2、
lambda_uncertainty×4，**五个 `lineup_*` 字段一个都没有设置**，
因此全部取 `simulate.py:41-45` 的 dataclass 默认值：

```text
lineup_strength_adjustment    = 0.0
lineup_ah_adjustment          = 0.0
lineup_totals_adjustment      = 0.0
lineup_ah_evidence_enabled    = False
lineup_totals_evidence_enabled = False
```

已排除绕过路径：全仓无 `SimulationInputs(**`、无 `replace(inputs`、
无对该类的 `asdict` 展开式构造。

**证据二 —— capability manifest。**

```text
lineup_numeric_adjustment_ah   NOT_IMPLEMENTED   feature_enabled = False
lineup_numeric_adjustment_ou   NOT_IMPLEMENTED   feature_enabled = False
evidence_status = NUMERIC_VALUE_MODEL_NOT_IMPLEMENTED
```

因此 `lineup_adjustment_weight = 0.08` 恒乘以 `0.0`。

### 2.5 五个系数的真实身份（全部已查证）

| 系数 | 表面含义 | 生产实际 |
|---|---|---|
| `elo_gap_weight = 0.28` | 独立 Elo 信号权重 | xG delta 的 **14% 放大器**（非独立信号） |
| `squad_value_log_weight = 0.18` | 身价信号权重 | **死代码**：启用联赛无 `team_values` artifact |
| `lineup_adjustment_weight = 0.08` | 首发权重 | **死代码**：唯一构造点不填充 + capability NOT_IMPLEMENTED |
| `home_advantage_goals = 0.12` | 主场优势 | **唯一真实加性常数** |
| `dixon_coles_rho = 0.0` | DC 相关性修正 | 默认关闭，`tau_correction` 为空操作 |

### 2.6 生产 λ 的实际闭式

```text
base_h = (xgF_h + xgA_a) / 2
base_a = (xgF_a + xgA_h) / 2

total     = clamp(base_h + base_a, 1.35, 4.40)
raw_delta = base_h - base_a

adjusted_delta = 1.14 * raw_delta + 0.12        # 身价与首发两项恒为 0

lambda_home = clamp((total + adjusted_delta) / 2, 0.15, 4.25)
lambda_away = clamp((total - adjusted_delta) / 2, 0.15, 4.25)
```

**生产模型在当前 11 个启用联赛上是一个纯 rolling-xG 模型，
只含两个常数（`1.14` 与 `0.12`）与两组 clamp。**
五个硬编码系数中，两个是死代码，一个是伪装成独立信号的放大器。
该结论现已完整查证，不再有 `NOT_VERIFIED` 项。

---

## 3. U2 对照身份更正（核心变更）

### 3.1 问题

V2 当前定义 `PRODUCTION_FORMULA_XG_ONLY` 为
`home_elo = away_elo = None`。按 2.2 节，这会产生
`1.00 × raw_delta`，而生产是 `1.14 × raw_delta`。

**传 `None` 会让对照系统性偏离生产 14% 的 delta 幅度，
在实力悬殊场次偏离最大。**

### 3.2 更正

```text
COMPARATOR_IDENTITY = PRODUCTION_FORMULA_XG_WITH_PROXY_ELO

calibrate_lambdas，默认 LambdaCalibrationParams，输入为：

  xG              来自 cohort 的 rolling xg_for / xg_against
  home_elo        = 1500.0 + (rolling_xg_for_home - rolling_xg_against_home) * 100.0
  away_elo        = 1500.0 + (rolling_xg_for_away - rolling_xg_against_away) * 100.0
                    （必须复现 analysis_calculator.py:4684 的 proxy 构造）
  squad_value     = None（生产启用联赛均无 artifact，与生产一致）
  lineup_*        = 0.0，两个 lineup 证据门 False
```

首屏声明改为：

> 本对照复现生产在当前启用联赛上的实际形态，包括 Elo 的 rolling-xG proxy 构造。
> 与生产的已知差异仅为 lineup 项，该项可得性未查证。
> 身价传 `None` 不是简化，而是与生产一致——所有启用联赛均无 `team_values` artifact。

### 3.3 必须新增的合同断言

在 U2 执行前的冻结清单中加入：

```text
proxy Elo 构造断言：
  对 cohort 中任意 fixture，
  elo_delta / raw_delta 必须等于 0.14（容差 1e-9）
  不满足则 fail closed，不得继续评分
```

该断言防止 proxy 构造被误实现或被静默改成真实 Elo。

---

## 4. 本轮要产出什么

1. **更正 `U2_PREREGISTRATION.md` V2**（不新开 V3，本次为同版内更正）：
   - 对照身份改为第 3.2 节；
   - 冻结清单加入第 3.3 节的 proxy Elo 断言；
   - 原 `PRODUCTION_FORMULA_XG_ONLY` 表述保留为「已更正」记录，不删除。
2. **更正 `GATE_0B_EXECUTION_RECEIPT.md`**：
   把 `INFERRED_FROM_SOURCE_TABLE_EMPTINESS_NOT_RUNTIME_VERIFIED` 相关段落
   改为第 2 节的实测事实，并注明该推论的源表判断错误、已被静态实测取代。
   **保留原推论文本作为轨迹**，标注 `SUPERSEDED_BY_STATIC_CODE_VERIFICATION`。
3. **在 `W2_BASELINE_PARAMETER_PROVENANCE.json` 增加 `production_effect` 字段**，
   按 2.5 节逐系数记录真实身份。五项全部已查证，无 `NOT_VERIFIED` 项。
   同时增加 `effective_closed_form` 字段，内容为 2.6 节的闭式。
4. 生成 `docs/review_packages/PRODUCTION_LAMBDA_EFFECTIVE_FORM.md`，
   记录第 2 节全部证据与代数推导，作为独立可引用的事实文档。

## 5. 措辞红线

```text
- **可以**写「生产在当前启用联赛上是纯 rolling-xG 模型」——五项已全部查证
- 不得写「elo_gap_weight 是死代码」（它有效果，是 14% 放大器；死的是身价与首发两项）
- 不得写「身价传 None 是简化」（它与生产一致）
- 不得删除被推翻的推论文本，只标注 SUPERSEDED
- 代数结论 elo_delta = 0.14 × raw_delta 必须带推导，不能只给结果
```

## 6. 不要做

```text
不执行 U2、不导出生产数据、不重新拟合 challenger
不改任何业务代码
不申请写权限、不部署、不更新 Obsidian
```

计划书状态保持唯一一处 `PROPOSED_NOT_AUTHORIZED`。
