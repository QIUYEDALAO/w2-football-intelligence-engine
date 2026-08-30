# W2 × Penaltyblog：EV、概率与模型验证优化计划 V2.0

文档状态：`PROPOSED_NOT_AUTHORIZED`

用途：供 Owner 与多 Agent 独立评审、补证和形成统一意见

创建日期：2026-08-29（Asia/Shanghai）

当前修订：V2.0（重新定位：已完成工作归入 Phase 4.5 的测量能力建设，Phase 4.5 复用 U2 冻结管线并接入 Penaltyblog challenger；不改变 A–J、Gate 结构或阶段顺序）

实施状态：Gate 0A、Gate 0B 与 Phase 2.5a 的只读/静态审计已部分完成；U2 已执行并在评分前因功效不足停止；业务实施未授权

生产影响：无

> 本文不是实施授权、模型晋级决定、阈值变更批准或部署指令。任何代码修改、模型重训、生产写入、Provider 调用、候选准入或部署，都必须经过对应阶段的 Owner 授权。

## 当前状态速览

| 状态 | 当前事实 |
|---|---|
| 研究问题 | Penaltyblog 能否为 W2 的 EV 提供增量概率信息 |
| 当前答案 | 未测量。测量能力已建成，但功效不足以在 `MME=0.0025` 下评分 |
| 已建成 | cohort 冻结 / PIT / 五态管线 / futility（见 U2） |
| 已查清 | 生产 λ 在 11 个启用联赛上是纯 rolling-xG |
| 待解决 | MME 是否应为 `0.0025`（同时卡住 U2 / champion 晋级与 Phase 4.5 / Penaltyblog 增量检验） |
| 下一步 | Phase 4.5：把 Penaltyblog 接入 U2 管线，先算 futility |

## 1. Executive Summary

本计划解决三个必须分离的问题：

1. W2 的 EV 算术、盘口结算与报价绑定是否正确且全链一致；
2. W2 输入 EV 的概率是否可识别、可复现、校准有效；
3. Penaltyblog 能否作为独立 challenger 提供增量证据，而不是作为未经验证的替代模型。

当前最合理的结论是：

- **研究问题仍未测量：**Penaltyblog 能否为 W2 的 EV 提供增量概率信息，当前没有评分结论。生产 champion 的概率质量与 challenger 相对它的差距也未测量；此前第一优先级是只读的 EV/概率血缘审计和 W2 `BASELINE_PRIOR` 概率质量审计，而不是修改公式、删除安全门或接入六模型；
- **测量能力已经建成：**Gate 0A/0B、Phase 2.5a、U1 与 U2 共同建立正确 comparator、cohort、PIT、五态管线和 futility。U2 状态为 `EXECUTED`，结论为 `INSUFFICIENT_POWER_DO_NOT_SCORE`；冻结的 futility 规则在评分前触发，validation 五态分数未被读取。对照身份为 `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO`；对任意非零 `raw_delta`，`elo_delta/raw_delta = 0.14` 的绝对容差为 `1e-9`，零 `raw_delta` 时必须有零 `elo_delta`。真实 cohort 逐 fixture 断言首次通过：违反 `0` 例，且 `3` 例 `raw_delta == 0` 全部满足 `elo_delta == 0`。旧 `PRODUCTION_FORMULA_XG_ONLY` 只作为 `SUPERSEDED_BY_STATIC_CODE_VERIFICATION` 审计轨迹保留；
- **生产 comparator 已查清：**生产在当前 11 个启用联赛上的实际 λ 形态已静态查清，是纯 rolling-xG，非本文 §2.7 原描述的 xG+Elo+身价+首发四路融合；Elo 是 rolling-xG proxy，使 `raw_delta` 放大 14%；身价与首发两项当前为零贡献，`rho=0`；这不等于生产概率质量已经测量；
- **共同瓶颈是 MME：**`MME=0.0025` 从 1X2 LogLoss 搬用到五态 AH/OU NLL，尚无理论依据；它同时决定 U2 / champion 晋级与 Phase 4.5 / Penaltyblog 增量检验的功效；
- **下一步规格是 Phase 4.5：**在 U2 已冻结管线上替换为 Penaltyblog challenger，并先算 futility。Penaltyblog 六模型在已完成的竞彩结算 1X2 研究中没有击败市场，Phase 3 为零 survivor；该结果否决“直接替换即可提升”，但不能直接外推到 W2 的 AH/OU 同时点可执行报价。完整 Penaltyblog adapter 前的 `MINIMAL_FROZEN_FEASIBILITY_PROBE` 仍必须有 fixture/cutoff/outcome parity 和不可变 artifact，不能用无身份的一次性脚本；
- 只有 C0-MODEL 预检结论为 `PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH`，才建设隔离的 Poisson parity adapter；
- Gate 0B 已确认生产权威为 `ea557bb8 / schema 0070`；`origin/main@3b7f87db / schema 0051` 落后生产 19 个 migration，但四个核心审计文件跨基线逐字节相同，因此对应静态结论存活；
- W2 的正式 simulation 并不调用 `models/dixon_coles.fit_dixon_coles()`，不能把该离线模型直接称为生产概率源；
- W2 的亚洲盘五态 EV 公式已经存在，尚无证据证明核心算术错误；W2 同时存在多个 EV 实现入口，需要做语义、单位、盘口方向和数值等价审计；
- `models/calibration.py` 中的 PLATT、ISOTONIC、BETA 等名称与实现不符，但目前没有证据表明它进入正式 production simulation；
- `RecommendationDecisionV4` 的现役准入为 `EV > 0`、`cashflow_price_edge >= 0.05` 与 `EV - uncertainty > 0`；`probability_delta` 只作诊断，legacy/parallel dynamic evaluation 中的 5pp 门不得冒充现役 public gate；
- 当前代码同时存在 PROPORTIONAL 计算与“计算实为 PROPORTIONAL、来源却标 POWER”的 provenance 不一致；方法 authority 和历史行可归因性未闭合时，只阻断 market-relative 评价，不阻断 W2-vs-PB 的严格配对模型评价；
- 本计划不包含生产晋级。任何生产准入必须另立决策包和 Owner 授权。

## 2. `main@3b7f87db` 事实基线

### 2.1 权威与版本边界

V2.0 继承的 V1.4.1 原始代码断言、符号和行号统一以本地已有 Git 对象 `3b7f87db2f0cb49d75582313ca593d30262c0d3d` 为 PR 静态基线。当前 checkout 落后该基线 310 个提交，不得作为这些行号的代码事实来源。

后续 Gate 0B 已只读确认：生产 exact runtime 权威为 `ea557bb8ff64e06add91bbe32814fe073ec64642 / 0070_notification_delivery_routing`；`origin/main@3b7f87db / 0051_apply_seven_day_collection_policy` 是落后 19 个 migration 的选择性历史静态快照。`strategy/calibration.py`、`domain/five_state_pricing.py`、`models/independent.py` 与 `backtest/free_tier_2024.py` 在两基线逐字节相同，因此其已登记静态结论存活；其他生产事实不得从旧 snapshot 外推。

权威分层不得混同：

- `RecommendationDecisionV4` 是当前 public recommendation 的决策与方向权威；V3 仅历史/结算用；
- `NEW_INTELLIGENCE_WORKSPACE_ONLY` 是公共产品展示权威；workspace 将 V4 作为受验证的诊断输入，不意味着 V4 可以越过 workspace 成为整个公共产品投影权威。

### 2.2 Canonical 五态定价与符号

Canonical 定义位于 `src/w2/domain/five_state_pricing.py:6-82`。`src/w2/markets/value_engine.py:9-24` 只作 compatibility re-export，不再是 `SettlementDistribution`、`expected_value()`、`fair_decimal_odds()` 或 `cashflow_price_edge()` 的定义者。

| 符号 | 定义 | 含义 |
|---|---|---|
| `W` | `WIN + 0.5 × HALF_WIN` | 每单位名义本金的有效赢面暴露 |
| `L` | `LOSS + 0.5 × HALF_LOSS` | 每单位名义本金的有效输面暴露 |
| `S` | `W + L` | 期望结算暴露本金比例，即期望非退款结算本金比例 |
| `F*` | `S / W` | 未量化 fair decimal odds |
| `Fq` | `1 + quantize(L/W, 0.0001, ROUND_HALF_UP)` | 代码实际四位 fair decimal odds |
| `edge*` | `d/F* - 1 = EV/S` | 未量化 cashflow price edge，严格恒等式 |
| `edge_code` | `d/Fq - 1` | 当前代码实际 `cashflow_price_edge` |
| `T*` | `0.05 × S` | 未量化 5% 归一化政策对应的 raw-EV 门槛 |
| `Tq` | `1.05 × Fq × W - S` | 四位量化后的代码实际 raw-EV 门槛 |

本文“结算暴露本金”专指非 PUSH/退款部分的期望本金暴露，不等同于赛前资金占用、最大可能损失，或 Kelly 意义的 risk capital。令单位名义 stake 的实现收益为 `Y`，非退款结算暴露比例为 `R`，则：

```text
R: WIN 1 | HALF_WIN 0.5 | PUSH 0 | HALF_LOSS 0.5 | LOSS 1
E[R] = W + L = S
EV/S = E[Y] / E[R]
```

`EV/S` 是期望利润与期望结算暴露之比，不是 `E[Y/R]`；PUSH 时 `R=0`，`Y/R` 无定义。

其中 `d` 为 executable decimal odds。五态 EV 为：

```text
EV = (d - 1) × W - L = d × W - S
```

`p × odds - 1` 只是 `S=1` 且无 HALF/PUSH 的二态特例，不能作为 W2 全市场通用定义。

### 2.3 `cashflow_price_edge` 与 EV 的精确关系

未量化时：

```text
F*    = S / W
edge* = d / F* - 1 = EV / S
```

`cashflow_price_edge` 是 EV 经期望结算暴露比例 `S = W + L` 确定性归一化后的价格优势表示；当前实现另受 fair odds 4 位量化影响，因此代码层非逐值严格相等。

量化误差满足：

```text
|edge_code - EV/S| = d × |Fq - F*| / (F* × Fq)
|Fq - F*| <= 0.00005
```

测试不得使用统一硬编码 epsilon。应先对 `expected_value()` 和 `fair_decimal_odds()` 做 Decimal 精确断言，再用上述样本特定量化界验证 `edge_code` 与 `EV/S` 的差。

### 2.4 三条黄金向量

以 `d = 1.95` 复算：

| 盘型 | distribution | W | L | S | EV | F* | Fq | edge_code | EV/S | 量化残差 | Tq |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 半盘 | WIN .55 / LOSS .45 | .55 | .45 | 1.000 | .072500 | 1.8181818182 | 1.8182 | .0724892751 | .0725000000 | -1.072e-5 | .05001050 |
| 整数盘 | WIN .45 / PUSH .12 / LOSS .43 | .45 | .43 | .880 | -.002500 | 1.9555555556 | 1.9556 | -.0028635713 | -.0028409091 | -2.266e-5 | .04402100 |
| 四分盘 | WIN .42 / HALF_WIN .10 / PUSH .08 / HALF_LOSS .15 / LOSS .25 | .470 | .325 | .795 | .121500 | 1.6914893617 | 1.6915 | .1528229382 | .1528301887 | -7.250e-6 | .039755250 |

对这三条向量，`abs_tol = 3e-5` 可作为有界样例检查；`abs_tol = 1e-5` 会让半盘和整数盘产生假失败，禁止使用。`3e-5` 也不是全域 property test 的通用容差，全域必须使用逐样本量化感知界。

对应的未量化 `T*` 为 `.0500 / .0440 / .03975`。这些只是黄金向量示例，不是 line-type 常数。真正决定门槛的是逐场 `S`；同为整数盘的不同比赛也可有不同 PUSH 概率、不同 `S` 和不同门槛。

### 2.5 `S` 的经济含义

按本金去向展开：PUSH 全额退回，HALF_WIN/HALF_LOSS 退回一半，WIN/LOSS 全额进入输赢结算。

```text
E[结算暴露本金比例]
  = WIN × 1 + HALF_WIN × 0.5 + HALF_LOSS × 0.5 + LOSS × 1
  = W + L
  = S
```

四分盘黄金向量中，`S = 0.795`，而 `1-S = 0.205 = PUSH + 0.5 × (HALF_WIN + HALF_LOSS) = 0.08 + 0.125`。因此：

```text
EV                  = 每单位名义本金的期望利润
cashflow_price_edge ≈ 每单位期望结算暴露本金的期望利润
                    = E[Y] / E[R]（受 Fq 量化影响的代码表示）
```

```text
INTENDED_NORMALIZATION_IDENTIFIED
  已确认：当前代码有意以 S 做结算暴露归一化；该结构不是 algebra 副作用，
  recommendation authority 收敛记录也表明 5pp probability delta
  -> EV + EV-SE + cashflow edge 是有意迁移。

POLICY_JUSTIFICATION_PENDING_EVIDENCE
  未确认：没有代码或设计证据表明 Owner 的经济目标明确是
  “每单位期望结算暴露至少 5%”，也没有证据表明该尺度优于
  名义本金 / 资金占用 / 回撤 / log-growth / 流动性消耗 / 盘口限额。
```

`cashflow_price_edge` 不是独立于 EV 的第二个模型信号。Owner 的政策选择仍须按 binding constraint 预注册检验：

| binding constraint | 政策候选 |
|---|---|
| 结算暴露归一化 | 保持当前 `EV/S` 结算归一化 |
| 周转量 / 流动性 / 盘口限额 | 评估恒定名义 EV 政策 |

两种政策候选的经济正当性均未在本计划中确认，须由 Phase 4 的单一预注册 decision rule 裁决。

### 2.6 当前 recommendation admission 与 legacy 平行合同

`src/w2/domain/recommendation_decision_v4.py:54-70,418-442` 表明：

- `RecommendationDecisionV4` 的必需定价输入包含 `settlement_distribution / fair_odds / expected_value / uncertainty`；
- `model_probability / market_probability / probability_delta_diagnostic` 都属 `_OPTIONAL_DIAGNOSTIC_FIELDS`；
- 当前 recommendation admission 是 `EV > 0` + `cashflow_price_edge >= 0.05` + `EV - uncertainty > 0`，再叠加 readiness/capability/formal admission；
- `src/w2/markets/analysis_evidence.py:204-240` 同样明确写入 `probability_delta_admission_gate = False`。

`src/w2/prematch/lifecycle.py:12-20,250-353` 中的 `ACTIVE_DELTA_THRESHOLD = 0.05` 仍存在，但它属 `LEGACY / PARALLEL DYNAMIC EVALUATION CONTRACT`，不是现役 public recommendation gate。Phase 1/2 必须继续追踪其 writer/read consumer，但 Phase 4 不得把 legacy probability-delta 5pp 误当成 V4 政策 estimand。

### 2.7 W2 当前概率主链与卫生问题

生产 `ea557bb8` 的有效 simulation 路径经静态核验为：

```text
point-in-time rolling xG
  -> deterministic rolling_xg_proxy Elo (not an independent signal)
  -> squad value = None for the current enabled competitions
  -> lineup numeric adjustments = 0.0 / evidence gates = False
  -> strategy.calibration.calibrate_lambdas()
  -> lambda_home / lambda_away / uncertainty
  -> exact score matrix with optional DC tau correction
  -> AH / OU five-state settlement distribution
  -> executable quote
  -> canonical five-state EV / cashflow price edge / EV-SE / readiness
  -> RecommendationDecisionV4
```

`strategy.calibration` 仍明确标记 `CALIBRATION_VERSION = w2.formal.lambda_baseline_prior.v1` 和 `CALIBRATION_STATUS = BASELINE_PRIOR`。默认参数仍包括主场优势 `.12`、Elo `.28`、身价 log `.18`、首发 `.08`、单边 λ `.15–4.25`、总进球 `1.35–4.40` 和 `dixon_coles_rho = 0.0`。这些是 baseline prior 参数，不得写成已由历史拟合或前瞻验证。

五项生产效果现已静态查清：

```text
base_h = (xgF_h + xgA_a) / 2
base_a = (xgF_a + xgA_h) / 2
raw_delta = base_h - base_a

elo_h - elo_a = 2 * raw_delta * 100
elo_delta = ((elo_h - elo_a) / 400) * 0.28
          = ((2 * raw_delta * 100) / 400) * 0.28
          = 0.14 * raw_delta

adjusted_delta_non_neutral = 1.14 * raw_delta + 0.12
adjusted_delta_neutral     = 1.14 * raw_delta
```

因此 `elo_gap_weight` 有效果，但只是 xG delta 的 14% 放大器；不能称为死代码或独立 Elo 信号。身价项在当前启用联赛为死代码，是因为只有 `world_cup_2026` artifact、与当前 11 个启用联赛交集为空；换到有匹配 artifact 的 competition 可重新生效。首发数值项在当前唯一生产构造路径为死代码。`dixon_coles_rho=0.0` 使默认 tau correction 为 no-op。

两项卫生结论仍保留：

1. `models/dixon_coles.fit_dixon_coles()` 只有 backtest/测试直接调用，未进入正式 simulation；其实现为收缩场均进失球加 rho 网格，不是标准联合 MLE Dixon-Coles；
2. `models/calibration.py` 的 PLATT/ISOTONIC/BETA/DIRICHLET_MULTICLASS 是 power-strength heuristic，命名不符标准算法；当前直接调用仍是测试/离线边界，不得称为生产 EV 根因。

### 2.8 Devig 权威与可识别边界

`main@3b7f87db` 仍存在：

- `analysis_evidence.py:124-140` 与 `score_baseline.py:202-218` 显式使用 PROPORTIONAL；
- `analysis_calculator.py:5213-5254` 实际也做 reciprocal-odds normalization，数学上是 PROPORTIONAL，但 `analysis_calculator.py:6122-6135` 声明 source 为 POWER；
- `LockedPrediction.devig_method` 与 migration `recommendation_locks.devig_method` 仍 nullable。

因此 `COMPUTED = PROPORTIONAL / DECLARED = POWER` 的 provenance 错标已证实；Gate 0B 已关闭生产身份，但历史行实际方法覆盖与可归因性仍为 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`。该冲突只阻断 `MODEL_VS_MARKET` 与任何 market-edge 声明，不阻断使用完全相同 fixture/outcome 交集的 `MODEL_VS_MODEL` 概率质量评价。

### 2.9 Penaltyblog 已有证据

Penaltyblog 项目路径：

```text
/Users/liudehua/.hermes/workspace/penalty-football-research
```

已确认：

- 使用 Penaltyblog 1.12.0；
- Phase 1.1 已把 optimizer reliability 与 probability performance 分离；
- 六模型相对 `JINGCAI_SETTLEMENT_MARKET` 的 1X2 DeltaLogLoss 全部为负；
- Poisson、Negative Binomial、Zero-Inflated Poisson 高度冗余；
- Phase 3 在 W500/XI0.0018 与 W750/XI0.0009 两个配置上均为零 survivor；
- Phase 3 只覆盖预注册网格 2/9，剩余配置没有 refit；
- 最终状态为 `STOP_INCREMENTAL_RESEARCH`。

解释边界：

- `JINGCAI_SETTLEMENT_MARKET` 是竞彩结算 SP，不是 initial、closing、sharp、Pinnacle-equivalent、historical entry 或 CLV entry；
- Phase 3 结果针对其冻结的 1X2 研究问题；
- 不得直接把该结论写成 W2 AH/OU executable-quote 策略已被证伪；
- 也不得声称 Penaltyblog 已证明能改善 W2；
- Penaltyblog 的历史进球训练信息与 W2 当前生产的 PIT rolling-xG + deterministic proxy-Elo 信息并非已证明的严格集合包含关系：两者的训练样本、可见时点、覆盖、特征语义和参数身份均不同；当前启用联赛的身价与首发数值项不得继续写成有效独立输入。

## 3. 已排除的错误方向

本计划明确不执行：

- 不把 `p × odds - 1` 强行用于 AH 或可走盘 OU；
- 不因当前 EV 表现不佳而修改五态公式；
- 不删除 `expected_value > 0` 的 payload 合法性检查；
- 不把 legacy probability-delta 5pp 平行合同误当成现役 V4 admission；
- 不把 `cashflow_price_edge` 与 EV 当作两个独立 predictor 做交叉归因；
- 不把黄金向量的 `.0500/.0440/.03975` 写成半盘/整数盘/四分盘的固定门槛；
- 不使用旧报告中的小样本盈亏、命中率或 point EV 选择模型、校准参数、阈值或 EV-SE 系数；当前生产 settled N 必须在未来独立授权的 Phase 4 evaluability 只读范围重新计数，不能把旧 `65` 当成当前事实；
- 不把跨 bookmaker 更高赔率自动称为正 EV；除非严格构成套利，否则它只是价格改善；
- 不同时接入六个 Penaltyblog 模型；
- 不做 ensemble、majority vote、alpha blend、log opinion pool；
- 不用某模型结果 fallback 另一个失败模型；
- 不把 settlement SP 当作 entry/closing price；
- 不让 Penaltyblog负责 quote freshness、bookmaker depth、line identity、settlement ledger、candidate、BET/SKIP 或 staking；
- 不改历史 append-only 证据；
- 不访问 GitHub、GHCR 或 GitHub CI；
- 不部署、不改生产配置、不调用 Provider、不写生产数据库；
- 不更新 W2 或 Penaltyblog Obsidian Vault 为“已完成”，直到重要事实实际通过验收。

## 4. 优化目标与非目标

### 4.1 优化目标

1. 建立唯一、可验证的 EV 语义合同；
2. 证明所有 EV 入口对同一五态分布与报价数值一致；
3. 建立从原始点时输入到 λ、score grid、settlement distribution、EV、EV-SE、decision 的完整血缘；
4. 评估 V4 的 `EV/S` 结算归一化 admission 政策，并区分名义本金与期望结算暴露归一化空间；
5. 先验证 W2 当前 `BASELINE_PRIOR` 的参数来源、覆盖、clipping、概率质量和稳定性；
6. 将误导性的模型/校准名称与生产事实分开；
7. 用冻结的最小预检决定是否值得建设 Penaltyblog shadow adapter；
8. 仅在预检通过后，建立最小化、隔离、可删除的 Penaltyblog adapter；
9. 在相同 fixture、cutoff、selection、line、quote 上进行 W2/Penaltyblog/Market 配对评价；
10. 以预注册和 fail-closed 规则决定继续、修订或停止，而不是追求漂亮结果。

### 4.2 非目标

- 本计划不选 Champion；
- 不保证提升 ROI 或盈利；
- 不修订 W2 当前模型权重；
- 不批准任何新 Provider 或外部数据；
- 不批准生产推荐、真实下注或通知；
- 不解决全部 Factor Model V2 问题；
- 不重新开放已使用的 holdout；
- 不把 Penaltyblog 项目合并进 W2 Vault 或仓库历史。

## 5. 设计原则

### 5.1 问题分层

```text
数学层
  五态 settlement 与 EV 是否正确

绑定层
  fixture / team / market / selection / line / quote / as_of 是否一致

概率层
  lambda / score grid / calibration 是否可信

决策层
  threshold / EV-SE / capability / readiness 是否有验证依据
```

Penaltyblog主要作用于概率层和诊断层，不能替代绑定层、结算层和决策治理层。

### 5.2 最小集成原则

完整 adapter 第一版只做一个模型：独立 Poisson parity adapter。此前先做 Phase 4.5 的最小冻结预检，不建设生产 ledger、不增加 runtime 依赖。

理由：

- 最容易验证 score grid、尾部归一化和方向；
- W2 与 Penaltyblog 都有同族实现，可做数值血缘对照；
- 不引入 optimizer retry、warm start 和团队参数身份的额外复杂性；
- parity 未通过前，接 Dixon-Coles 或六模型没有价值。

Poisson parity PASS 后，是否增加 Dixon-Coles 必须先冻结新的模型身份、训练规则和评价 Gate。

### 5.3 隔离原则

第一版建议通过离线 artifact 交换，而不是把 Penaltyblog 作为 W2 production runtime 依赖：

```text
W2 PIT export
  -> isolated Penaltyblog job
  -> immutable probability artifact
  -> W2 analysis-only evaluator
```

这样可以保留：

- 两项目独立环境；
- 两个 Vault 的知识边界；
- Penaltyblog版本与 artifact hash；
- W2 production runtime 不受新依赖影响；
- adapter 可随时删除，不影响当前决策链。

## 6. 目标架构

```text
W2 canonical fixture + PIT feature export
        |                         |
        |                         +--> W2 current probability path
        |
        +--> Penaltyblog isolated shadow job
                  |
                  +--> lambda / score grid / 1X2 / fit ledger
                                   |
W2 exact quote identity -----------+
                                   v
                    W2 canonical settlement engine
                                   |
                    five-state distribution + EV
                                   |
                       analysis-only paired ledger
                                   |
                  preregistered offline/prospective review
```

Penaltyblog不得直接写：

```text
official opportunity
official evaluation
formal recommendation
outbox / Bark
outcome ledger
production dashboard decision state
```

## 7. 分阶段执行计划

### 7.0 依赖顺序与评审角色

执行依赖：

```text
Gate 0A local authority audit
  -> Phase 1 EV Contract Audit
  -> Phase 2 Probability Lineage Audit

Phase 1 + Phase 2 accepted
  -> Phase 2.5 W2 Baseline Probability Quality Audit

Phase 1 + Phase 2 audit computed/declared/persisted devig identity
  -> if consistent: DEVIG_AUTHORITY_RESOLVED
  -> if conflict: DEVIG_AUTHORITY_CONFLICT decision packet
     -> Owner-authorized Phase 3 minimal devig contract resolution
     -> independent acceptance
     -> DEVIG_AUTHORITY_RESOLVED

Gate 0B readonly VPS runtime verification
  -> production-exact authority and preliminary U2 cohort metadata COMPLETE
  -> Phase 4 cohort counts and devig attribution coverage remain PENDING_RECHECK

Phase 1 accepted and no devig conflict
  -> optional Phase 3 EV Contract Convergence

DEVIG_AUTHORITY_CONFLICT
  -> Phase 3 devig contract resolution is required only before market-relative tracks

Gate 0B + Phase 1 + Phase 2 accepted
  -> Phase 4 V4 EV Admission Policy Preregistration

Phase 2.5 = BASELINE_QUALITY_IDENTIFIED
and W2_COHORT_BURN_LEDGER has an eligible development cohort
  -> Phase 4.5 MODEL_QUALITY_TRACK preregistration may proceed

U1 input/cohort readiness COMPLETE
and U2 frozen pipeline EXECUTED
  -> Phase 4.5 preregistration: frozen U2 pipeline + Penaltyblog challenger
  -> futility before validation scoring

Phase 4.5 MODEL_VALUE_TRACK
  -> additionally requires DEVIG_AUTHORITY_RESOLVED

Phase 2.5 = BASELINE_QUALITY_NOT_IDENTIFIABLE
or cohort classification = UNKNOWN_BLOCKED
or comparator identity/PIT/outcome binding not reproducible
  -> BLOCK_PB_VS_W2_FEASIBILITY

Gate C0-MODEL = PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH
  -> Phase 5 PB Adapter Preregistration
  -> Phase 6 Engineering Parity
  -> Phase 7 Gate D1 Probability Quality

Phase 6 PASS
  -> Phase 7 EV realization on the PB paired cohort
     inheriting the frozen Phase 4 contract; no devig prerequisite

Phase 6 PASS
and Gate C0-MARKET = PASS
and DEVIG_AUTHORITY_RESOLVED
  -> Phase 7 Gate D2 Market-Relative Probability Benchmark

Gate D1 passes
  -> separate Owner request for PROBABILITY_SHADOW

Gate D2 market-relative benchmark passes
  -> may support the corresponding component of a separate Owner request
     for MARKET_VALUE_SHADOW; inherited EV realization remains separately identified
```

Gate 0A 与 Gate 0B 的已执行只读范围均已完成。生产 identity 与 U2 cohort 汇总元数据已有 Gate 0B 证据；但 Phase 4 evaluability counts、历史 devig attribution 和两个 5% 语义文件的生产基线复核仍为 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`，不得被 Gate 0B identity PASS 偷换为已完成。Phase 1 与 Phase 2 可以由不同 Agent 独立审查。Phase 3 与 Phase 4 不得并行修改同一 EV/threshold 路径。Phase 4.5–7 必须串行，以保证预检、合同、实现和结果的时间顺序。

以上两轨必须保持下列不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

建议评审角色：

| role | responsibility | must not decide alone |
|---|---|---|
| Runtime/Release Auditor | exact release、schema、capability、生产写读边界 | 模型优劣、阈值 |
| EV/Settlement Reviewer | 五态公式、盘口方向、quote binding、数值等价 | 模型晋级 |
| Model/Statistics Reviewer | probability lineage、校准、预注册、power | 生产部署 |
| Data Integrity Reviewer | PIT、fixture identity、row conservation、failure ledger | 盈利结论 |
| Independent Acceptance Reviewer | 复跑证据、验证 stop line、审查越权结论 | 修改冻结协议 |
| Owner | 授权、风险偏好、阶段继续/停止 | 不以多数票替代证据 Gate |

任何 Agent 同时承担实现与验收时，最终结论仍需独立复核。

### Gate 0A — Local Authority & Static Reconciliation

状态：`COMPLETE`

完成证据（`origin/main@3b7f87db` detached worktree，只读执行）：

```text
docs/review_packages/EXACT_AUTHORITY_SNAPSHOT.json
docs/review_packages/FIVE_PERCENT_SEMANTIC_REGISTRY.md
```

Gate 0A 曾将 `origin/main@3b7f87db` 视为审计权威，该判断经 Gate 0B 更正为方向错误。生产 `ea557bb8 / schema 0070` 是权威；`origin/main` 是选择性推送的快照，落后生产 19 个 migration。

但 `strategy/calibration.py`、`domain/five_state_pricing.py`、`models/independent.py`、`backtest/free_tier_2024.py` 四者在两个基线上逐字节相同，因此 Gate 0A 中依赖它们的静态结论对生产成立；`markets/analysis_evidence.py` 与 `prematch/lifecycle.py` 已变更，`FIVE_PERCENT_SEMANTIC_REGISTRY.md` 标 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`。

目标：确认本地可审计的代码、迁移、历史 commit 与治理文件边界，而不是把当前脏 checkout、旧 context branch 或 Vault 任一方冒充生产 exact source。

只读任务：

1. 核对本地 checkout、base commit、未跟踪/未提交文件和历史本地 commits；
2. 核对本地迁移链、capability 默认值和 release/Vault 记录的冲突；
3. 核对 EV、概率、evaluation、settlement 的静态 caller/writer/read path；
4. 记录可验证文件与 hash，不推断 VPS 当前运行状态。

输出：

```text
LOCAL_AUTHORITY_SNAPSHOT.json
LOCAL_AUTHORITY_RECONCILIATION.md
```

验收：

- 本地候选 base commit 明确；
- 本地 migration/capability/caller graph 明确；
- 与 Vault、旧 `origin/context/current` 的冲突显式记录；
- 无 Provider 调用；
- 无业务写入；
- 无部署。

### Gate 0B — Readonly VPS Runtime Verification

状态：`COMPLETE_READ_ONLY_ZERO_WRITE_FOR_AUTHORITY_AND_U2_COHORT_SCOPE`

已完成证据：

```text
docs/review_packages/EXACT_AUTHORITY_SNAPSHOT.json
docs/review_packages/GATE_0B_EXECUTION_RECEIPT.md
docs/review_packages/U2_PREREGISTRATION.md
```

Gate 0B 当时已确认生产 `ea557bb8 / schema 0070`、四服务 revision parity、历史 snapshot 落后 19 个 migration、生产 `team_xg_match` 汇总元数据，以及 Provider/业务写入/导出/部署/U2 执行均为 0。当时的候选 cohort 规模为 `9,502` 场 / `19,004` 行，xG 非空率 `100%`，时间范围 `2024-02-22 → 2026-08-29`；这是 U2 冻结前的只读元数据快照，不是最终执行 cohort。

后续 U2 已另行完成导出、冻结与披露更正：最终可复用 cohort 为 `9,551` 场，修正后的权威 SHA-256 为 `c74eaf0fc3b780f6b04c20353e55e5e83ffdebd213a4c1bbb83b0dcc903ce44e`，competition 数为 `13`、`UNLABELLED=0`，league 映射与 home/away 映射各为 `9,551 / 9,551 = 100%`。`docs/review_packages/U2_ARMING_FREEZE.json` 写于任何拟合与评分之前，并在 `cohort_label_correction` 块披露事后标签更正；执行结果与停止位置见 `docs/review_packages/U2_EXECUTION_RECEIPT.md`。该后续事实不扩大 Gate 0B 的 Phase 4/devig 只读范围。

原 Gate 0B 任务 4–7 所要求的 Phase 4 evaluability counts、official/shadow settled 分层、历史 `devig_method` 覆盖和 declared/computed attribution 尚未产生计划所列的完整 artifacts，继续保持 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`。不得因为 authority scope 已 PASS 而把这些统计前置写成已通过。

目标：在不访问 GitHub/GHCR、不调用 Provider、不写业务数据、不部署的前提下，核验当前生产 exact runtime 与可评价 cohort 计数。

只读任务：

1. 核对 API/worker/scheduler/Web release 和 OCI revision；
2. 核对 Alembic head 与 capability 实际开关；
3. 核对 POINT-EV 当前 production identity；
4. 只读计数 V4 可评价行的 `EV - Tq` 两侧、line type、连续 `S` 区间、权威结算覆盖与 fixture 去重数；legacy dynamic evaluation 的 `delta < 0.05` / `>= 0.05` 仅作平行合同盘点，不作为 Phase 4 primary；
5. 只读计数当前 official/shadow settled rows，并按 schema/model/calibration identity 分层；
6. 对可能用于 Phase 4 附加 market track 或 Phase 7 D2 的历史 evaluation/lock/settlement 行计数 `devig_method` 非空覆盖率、未知率和方法分布，至少按 evidence source、release/schema、market、checkpoint 和 model/calibration identity 分层；
7. 区分“持久化字符串”与“可由当时代码复算的实际算法”，计数 declared/computed mismatch；当历史 release source 不可证明时标 `METHOD_NOT_ATTRIBUTABLE`，不得根据当前代码反推；
8. 保存查询文本、时间、结果 hash 和零写入证据。

已产出：

```text
docs/review_packages/EXACT_AUTHORITY_SNAPSHOT.json
docs/review_packages/GATE_0B_EXECUTION_RECEIPT.md
```

仍待未来独立授权范围产出：

```text
PRODUCTION_EVALUABILITY_COUNTS.json
PRODUCTION_DEVIG_ATTRIBUTION_COUNTS.json
PRODUCTION_AUTHORITY_RECONCILIATION.md
```

原 full-scope 验收状态：

- Python/Web/worker/scheduler identity 明确：`PASS`；
- schema 与核心 capability 明确：`PASS`；
- `EV - Tq` 两侧、各 line type、`S` 区间与结算覆盖可复算：`PENDING_FUTURE_AUTHORIZATION`；
- `devig_method` 非空/未知/混合覆盖可复算，且 declared method 与 computed algorithm 的可归因性明确：`PENDING_RECHECK_ON_PRODUCTION_BASELINE`；
- GitHub/GHCR 访问 0：`PASS`；
- Provider 调用 0：`PASS`；
- 业务写入 0：`PASS`；
- 部署 0：`PASS`。

剩余 STOP 条件：任何依赖未完成的 settled N、`EV-Tq` 分层、历史 devig attribution 或 cohort coverage 的结论必须标 `PENDING_RECHECK_ON_PRODUCTION_BASELINE` 或对应的 `NOT_IDENTIFIABLE`；不得复用 authority-only PASS 代替这些证据。

### Phase 1 — EV Contract & Call-Graph Audit

状态：`READ_ONLY_FIRST`

目标：回答“W2 到底有几种 EV、每种使用什么分布和什么报价”。

审计范围：

- canonical `domain.five_state_pricing` 定义者与所有 compatibility re-export/重复 `expected_value`、`risk_adjusted_ev`、`probability_edge`、`fair_odds`、`implied_probability`；
- 所有五态/三态/二态 settlement 转换；
- opening/current/reference/executable/settlement quote 的来源和用途；
- 每条 market probability 路径的 computed devig algorithm、declared source label、persisted method/version/overround 是否一致；
- AH 主客方向、四分盘拆分、OU push；
- Decimal/float、rounding 和 score-grid tail mass；
- `effective_settlement_probability` 是否被错误当作五态 EV 替代；
- 展示层是否把 probability delta、line difference 或 EV 混名。

必须生成矩阵：

| caller | market | probability shape | quote source | quote usage | formula | rounding | decision impact |
|---|---|---|---|---|---|---|---|

必须验证的固定样例：

- AH `0`、`±0.25`、`±0.5`、`±0.75`、`±1.0`；
- OU `2.0`、`2.25`、`2.5`、`2.75`、`3.0`；
- HOME/AWAY、OVER/UNDER 对称性；
- WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS 五态和为 1；
- 同一分布下赔率上升时 EV 不下降；
- 主客符号互换后结算一致；
- reference quote 不能进入 EV；
- stale/incomplete quote 必须 fail closed。

新增的固定合同断言：

```text
W = WIN + 0.5 * HALF_WIN
L = LOSS + 0.5 * HALF_LOSS
S = W + L
S = 1 - PUSH - 0.5 * (HALF_WIN + HALF_LOSS)
EV = (d - 1) * W - L = d * W - S
F* = S / W
edge* = d / F* - 1 = EV / S
Fq = 1 + quantize(L / W, 0.0001, ROUND_HALF_UP)
edge_code = d / Fq - 1
Tq = 1.05 * Fq * W - S
```

黄金向量 artifact 每条必须完整保存：

```text
distribution / odds / W / L / S / EV / F* / Fq
edge_code / EV_over_S / quantization_residual / Tq
```

测试顺序必须是：

1. `expected_value()` 对三条向量做 Decimal 精确相等；
2. `fair_decimal_odds()` 对 `Fq` 做 Decimal 精确相等；
3. 按逐样本 `d × |Fq-F*|/(F*×Fq)` 上界验证 `edge_code` 与 `EV/S`；
4. 只对这三条有界向量可用 `abs_tol=3e-5` 作附加检查；禁止 `abs_tol=1e-5`，禁止把 `3e-5` 当全域容差。

输出：

```text
EV_CALL_GRAPH.md
EV_SEMANTIC_MATRIX.json
DEVIG_AUTHORITY_MATRIX.json
EV_CONTRACT_AUDIT.md
```

Phase 1 PASS：

- 所有入口已枚举且可定位；
- 同输入数值差异为 0，或每个差异都有明确合同依据；
- 无 silent fallback；
- 无 quote identity 丢失；
- computed/declared/persisted devig identity 一致，或冲突已显式标为 `DEVIG_AUTHORITY_CONFLICT`；
- 未修改公式或阈值。

### Phase 2 — Probability Lineage & Naming Audit

状态：`READ_ONLY_FIRST`

目标：区分生产概率、离线模型、实验校准和展示字段。

任务：

1. 从 production decision 反向追踪至 λ 输入和 point-in-time raw lineage；
2. 列出 `models/dixon_coles.py` 的真实调用者和使用边界；
3. 列出 `models/calibration.py` 的真实调用者和 artifact 使用边界；
4. 区分：
   - `strategy.calibration.BASELINE_PRIOR`；
   - Stage 7 independent model utilities；
   - Factor Model V2 calibration candidate；
   - EV-SE uncertainty calibration；
5. 检查同名 calibration 是否导致日志、报告或 Dashboard 误读；
6. 检查 model/calibration identity 是否完整进入持久化和导出。
7. 检查 devig provenance 命名是否与实际算法一致；当前 `POWER devig` 标签与 PROPORTIONAL 实现不一致必须进入决策包，但本阶段不直接改代码或历史行。

输出：

```text
PROBABILITY_LINEAGE.md
MODEL_CALIBRATION_IDENTITY_MATRIX.json
MISLEADING_API_DECISION_PACKET.md
```

允许提出但不得自动执行的处置：

- 重命名离线简化 DC；
- 将 heuristic calibration 标为 experimental；
- 从公共导出移除未使用 API；
- 实现真正校准算法作为新模型身份。

禁止：在没有新身份、预注册和验证时，把“重命名”扩大为生产模型替换。

### Phase 2.5 — W2 Baseline Probability Quality Audit

状态：`PARTIALLY_COMPLETE`

Phase 2.5a 参数来源审计与五系数生产效果静态核验已完成。生产 champion 的概率质量至今未测。

Phase 2.5a 静态审计仍只允许以下两个结论字段：

```text
BASELINE_PROVENANCE_IDENTIFIED_NO_FITTING_EVIDENCE
BASELINE_CALIBRATION_DEFICIENCY_EVIDENCED_SINGLE_FOLD
```

阶段产物：

```text
docs/review_packages/W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md
docs/review_packages/W2_BASELINE_PARAMETER_PROVENANCE.json
docs/review_packages/PRODUCTION_LAMBDA_EFFECTIVE_FORM.md
```

目标：先回答 W2 当前 `BASELINE_PRIOR` 自身的概率质量和证据边界，再评价外部 challenger。

已知起点：

- `strategy.calibration.CALIBRATION_STATUS = BASELINE_PRIOR`；
- 默认 λ 参数直接存在于 `LambdaCalibrationParams`；
- 当前启用联赛的生产有效式为非中立场 `adjusted_delta = 1.14 * raw_delta + 0.12`、中立场 `1.14 * raw_delta`；Elo 是 rolling-xG proxy 放大器，身价与首发当前为零，默认 `rho=0`；
- 上述有效式已静态识别，不等于它的 LogLoss/Brier/RPS/ECE 或五态概率质量已建立；
- Factor V2 B0/B1/B2 消融已产生历史证据，但 Gate 1 因 ECE 恶化保持 FAIL；
- TRAIN-only temperature `0.928709586` 只形成 prospective candidate identity，OOF NLL 轻微改善且各 bin ECE 均恶化，不能晋级或证明当前 baseline 有效；
- 已冻结的 Factor V2 `5,500` 场、`2028-02-01T00:05:00Z` one-look 只属于该 successor B2-vs-B0 问题，不得复用于 PB。

审计至少报告：

```text
parameter provenance / fitting identity
calibration version and status
lambda and total-goals clipping frequency
input availability and fail-closed coverage
1X2 LogLoss / Brier / RPS / ECE
AH/OU five-state NLL / Brier / RPS where outcome identity is valid
league and chronological-block stability
fixture-set digest and row-conservation ledger
identifiability limits
relationship to Understat and Factor V2 evidence
```

同时生成 cohort use/burn ledger。每个候选 cohort 至少记录：

```text
cohort_id / data source / competition scope
time interval / N / fixture-set digest
outcome visibility and first-view time if known
experiments and commits that accessed it
role in each experiment = FIT / TUNE / SELECT / EVALUATE / DESCRIPTIVE_ONLY
whether metrics influenced a later model/protocol decision
eligibility by new research question
classification and reason
```

允许的分类至少包括：

```text
VIRGIN_CONFIRMATORY
PREREGISTERED_SEALED
DEVELOPMENT_REUSABLE_WITH_DISCLOSURE
DESCRIPTIVE_ONLY
CONTAMINATED_FOR_CONFIRMATION
FORWARD_ONLY
UNKNOWN_BLOCKED
```

“曾加载赛果”不自动等于对所有未来问题永久烧毁；但被用于 fit/tune/select、或在看过指标后修改候选/协议的 cohort，不得再冒充该候选的 virgin confirmation。任何无法从 commit、artifact、脚本或运行证据确定用途的 cohort 必须标 `UNKNOWN_BLOCKED`，不得由执行方自行宣布干净。

硬约束：

- 只能使用已明确允许作 development/descriptive audit 的 cohort；
- 不重新打开已关闭或已查看后被重新用于调参的 holdout；
- 不用结果改生产权重、clamp、阈值或模型身份；
- 不把离线 candidate 的指标归给 production `BASELINE_PRIOR`；
- 如果没有可合法评分的 paired set，结论为 `BASELINE_QUALITY_NOT_IDENTIFIABLE`，不得补造数据。

输出：

```text
W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md
W2_BASELINE_PROBABILITY_METRICS.json
W2_BASELINE_PARAMETER_PROVENANCE.json
W2_COHORT_BURN_LEDGER.json
```

Phase 2.5 的工程验收与统计结论必须分开：artifact/row-conservation 可以 PASS，但统计结论仍可为 `BASELINE_QUALITY_NOT_IDENTIFIABLE`。本阶段只建立 baseline，不选择 champion，不批准模型替换。

### U1 — Challenger Promotion Readiness Audit

状态：`COMPLETE`

产物：

```text
docs/review_packages/U1_PROMOTION_READINESS_AUDIT.md
```

仓库已有 2026-07-07 的单折 + 稳健性（跨季双向 + 四折 rolling-origin）1X2 Understat 证据，但该证据比较的是 fitted challenger 与离线 `models/independent.py::predict_from_features` 对照，不是生产 `strategy/calibration.py::calibrate_lambdas` champion。

既有 Understat/历史回测证明过其他离线 fitted candidate 的局部表现。

晋级裁决：`OWNER_DECISION_REQUIRED`

在生产 `strategy/calibration.py::calibrate_lambdas` 的 `BASELINE_PRIOR` 概率质量完成合法测量之前，Phase 4 的 EV calibration、Phase 4.5 的 W2-vs-PB 配对与 Phase 7 全部内容都缺少已验证的生产基准。不得把离线 `predict_from_features` 对照的校准缺陷归给生产 champion。

已存在一个经稳健性验证、优于某离线 `predict_from_features` 对照约 `0.026` nats 的拟合模型；其相对生产 champion 的差距未测，晋级裁决从未作出。该事实应纳入 Owner 的优先级判断，但不升级当前两个 Phase 2.5 结论字段，也不授权生产替换。

是否重排优先级、是否冻结 Penaltyblog 轨道，属 Owner 裁决；本文档不自行改变阶段顺序。本记录不授权继续 Phase 1/2、执行 Phase 2.5b、修改生产 calibration，或补跑 Gate 0B 尚未完成的 Phase 4 evaluability/devig attribution 范围。

### U2 — Five-State Pipeline Validation（Understat challenger，非 Penaltyblog）

U2 使用 Understat 重拟合模型作 challenger，**不含 Penaltyblog**；它验证的是管线，不是本文的研究问题。

U2 已按新生产静态事实更正为 `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO` 并执行完成：

```text
U2_STATUS = EXECUTED
U2_CONCLUSION = INSUFFICIENT_POWER_DO_NOT_SCORE
VALIDATION_FIVE_STATE_SCORES_READ = 0
STOP_POSITION = FUTILITY_BEFORE_SCORING
```

冻结链与披露更正共同成立：最终可复用 cohort 为 `9,551` 场，修正后的权威 SHA-256 为 `c74eaf0fc3b780f6b04c20353e55e5e83ffdebd213a4c1bbb83b0dcc903ce44e`；competition 数为 `13`、`UNLABELLED=0`，league 映射和 home/away 映射均为 `100%`；`U2_ARMING_FREEZE.json` 写于任何拟合与评分之前。冻结后按 `min_history=5` 得到 eligible `8,659` 场，其中 train `5,869`、validation `2,790`。证据权威仅为：

```text
docs/review_packages/U2_ARMING_FREEZE.json
docs/review_packages/U2_EXECUTION_RECEIPT.md
```

**cohort league 标签更正 — `DISCLOSED_CORRECTION_CONCLUSION_UNAFFECTED`**

原 digest `40802614114c06ebc7bf4a3eb93578a313631fd50c6440803c1ff1622f86469c` → 修正 digest `c74eaf0fc3b780f6b04c20353e55e5e83ffdebd213a4c1bbb83b0dcc903ce44e`；`UNLABELLED 706 → 0`，competition `14 → 13`。缺陷是本地 join 以 last-wins 解析 fixture→league，部分 payload 的 `parameters.league` 为空，导致实际有 league id 的 `706` 场被错标为 `UNLABELLED`；修正规则为同一 fixture 同时出现空与非空 league 时取非空。

三项复核均已完成：数据本体 `fixture_id / kickoff / team ids / xg / goals` 经两条独立提取路径逐字节互证；league 标签修正经第三条独立路径确证，覆盖 `9,551 / 9,551`，不一致 `0` 例；修正 cohort 全链重跑后，`train_mean / train_sd / clustered_se / N_val / mde` 逐位相同，`8,659` 场中 `λ / raw_delta / elo_delta / 比分 / split` 零差异，结论仍为 `INSUFFICIENT_POWER_DO_NOT_SCORE`。

这不是设计变更：未触及 split、`min_history`、线网格、cluster、MME 或决策规则，且先验证“结论不变”才采纳修正。详情仅引用 `docs/review_packages/U2_ARMING_FREEZE.json` 的 `cohort_label_correction` 块与 `docs/review_packages/U2_EXECUTION_RECEIPT.md` 末节，不在本计划复制完整证据。

proxy Elo 的 `elo_delta = 0.14 × raw_delta` 不再只有代数推导：它第一次在真实 cohort 上完成逐 fixture 验证，违反为 `0` 例；`3` 例 `raw_delta == 0` 均满足 `elo_delta == 0`。旧 `PRODUCTION_FORMULA_XG_ONLY` 只保留为 `SUPERSEDED_BY_STATIC_CODE_VERIFICATION` 历史轨迹。

futility 在读取任何 validation 五态分数之前触发：train `n=5,869`，`d_i` 的 `sd=0.078733`；按 kickoff 日聚类得到 `SE=0.001005`、`G=455` 天；validation `N=2,790` 的预计 `SE=0.001457`。80% power、单侧 5% 下，MDE 约为 `0.003624` nats（执行回执以六位小数展示为 `0.003623`），高于冻结的 `MME=0.0025`，因此必须返回 `INSUFFICIENT_POWER_DO_NOT_SCORE`，不得读取 validation 五态分数或形成模型优劣结论。

保持当前方差与设计不变，所需 validation 样本量按 `2,790 × (0.003623 / 0.0025)^2` 估算约为 `5,859`，即当前的约 `2.10` 倍，缺口约 `3,069` 场。按本次 validation cohort 的积累速度，约需再等待 `0.9` 年；这是功效规划估算，不是新的执行结果。

U2 的硬约束：不得为换取功效而修改切分比例、`min_history`、线网格、cluster 定义或下调 MME。上述任一改动都属于在看到 futility 结果之后调整设计。若要在更小 MME 下重做，必须另立新的预注册；不得修订本版 U2 合同。

**U2 描述性观察 — `NON_CONCLUSION`**

对照 λ 均值为主 `1.414` / 客 `1.302`（差 `0.11`），实际进球均值为主 `1.560` / 客 `1.250`（差 `0.31`）。challenger 在训练前缀拟合的 `home_field=+0.2175`（对数尺度，约 `+24%`）；生产 `home_advantage_goals=0.12` 在 λ≈`1.35` 上约为 `+9%`。这提示生产主场项可能偏低，但仅属训练集内描述性观察，未经任何 out-of-sample 检验，不得作为 challenger 晋级、生产参数修改或任何模型优劣结论的依据。

生产 comparator 的工程身份已从 `XG_ONLY` 更正为 `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO`，且真实 cohort 的 `0.14` 断言已通过。U2 已执行，但因 futility 在评分前返回 `INSUFFICIENT_POWER_DO_NOT_SCORE`；因此“对照概率质量如何”的统计问题仍未被 validation 结果回答，也不产生任何晋级或生产修改授权。

### 已建立的测量能力（为 Phase 4.5 服务）

| 已完成工作 | 建立的能力 | 对 Phase 4.5 的作用 |
|---|---|---|
| Gate 0A / Gate 0B | 确定生产权威 `ea557bb8 / 0070`，查清生产 λ 的实际闭式 | comparator 才有正确身份 |
| Phase 2.5a | 确证 `BASELINE_PRIOR` 五系数硬编码、无拟合证据 | 说明 comparator 是什么、不是什么 |
| U1 | 输入可得性、联赛范围、cohort 可行性 | 构成 Phase 4.5 的数据前置 |
| U2 | cohort 冻结、PIT 特征、五态管线、futility 机制全部跑通 | Phase 4.5 直接复用，只需替换 challenger |

这些工作不是脱离 Penaltyblog × W2 研究问题的平行 champion 轨道，而是让 Phase 4.5 可以用正确 comparator、合法数据和评分前功效门回答原研究问题的测量能力建设。

### OPEN_QUESTION_MME — Five-State NLL Minimum Meaningful Effect

`MME=0.0025` nats 从 Penaltyblog 项目的 1X2 LogLoss 搬用到五态 AH/OU NLL，**没有理论依据**，是一个待外部独立论证的假设。

该数字同时决定两件事：

```text
U2 / champion 晋级是否有功效
Phase 4.5 / Penaltyblog 增量检验是否有功效
```

当前 U2 的 `MDE=0.003624`。若 MME 应更大，两条路当时都有功效；若 MME 应更小，两条路都要等待更久。Phase 4.5 因 challenger 改为 Penaltyblog，仍必须用自己的 `d_i` 离散度重新估计 MDE，不得直接复用 U2 的方差结果。

在 MME 得到独立论证之前，不得以任何理由在本版内调整 `MME=0.0025`。

### Phase 3 — EV Contract Convergence

状态：`REQUIRES_PHASE_1_PHASE_2_ACCEPTANCE_AND_OWNER_AUTHORIZATION`

目标：只在审计证明重复实现或 devig identity 存在漂移风险时，做最小收敛。本阶段未获 Owner 授权前不得开始修复。

候选改动顺序：

1. 优先复用 canonical `domain.five_state_pricing.expected_value`；保留 `markets.value_engine` compatibility re-export；
2. 删除或薄封装重复公式；
3. 保留现有公开 schema 和历史 artifact 兼容；
4. 增加最小参数化合同测试；
5. 不改阈值、模型概率、推荐方向或历史结果。

Devig 冲突处置必须在修改前分支：

```text
LABEL_OR_PERSISTENCE_ONLY
  actual computed algorithm remains unchanged
  source label and persisted method/version/overround become truthful
  numeric probabilities and recommendation set must remain byte/value identical

ALGORITHM_CHANGE
  canonical computed method would change, for example PROPORTIONAL -> POWER
  this is a new market-probability identity and can change legacy/parallel
  delta classifications and every market-relative score
  requires separate preregistration, compatibility plan, Owner authorization,
  and prospective-only activation; it cannot masquerade as a naming fix
```

禁止根据哪个 devig 方法让历史 delta 通过率、market-relative LogLoss、EV 归因或推荐更好而选择方法。禁止回写、猜测或清洗无法归因的历史 `devig_method`。

验收：

- 既有测试继续 PASS；
- 固定黄金向量 byte/value parity；
- property/parameter tests PASS；
- 历史 artifact 不改写；
- 推荐集合在相同输入下不变；
- diff 只覆盖共享 EV 合同及直接测试。

对 `LABEL_OR_PERSISTENCE_ONLY` 分支，验收还必须包括：

- computed algorithm golden vectors 完全不变；
- declared label 与 persisted method/version/overround 与实际算法一致；
- 存量历史行不回填，不可归因行仍保持 `METHOD_NOT_ATTRIBUTABLE`；
- 独立验收后才可将未来身份标为 `DEVIG_AUTHORITY_RESOLVED`。

如果当前实现已经数值一致、computed/declared/persisted devig identity 也一致，且没有维护风险，Phase 3 可以结论为 `NO_CHANGE_REQUIRED`。当前已确认 `analysis_calculator.py` 存在 label/algorithm mismatch，因此 devig 分支不满足 `NO_CHANGE_REQUIRED`。

### Phase 4 — V4 EV Admission Policy & Settlement-Normalization Evaluation

状态：`PREREGISTRATION_REQUIRED`

目标：评价 V4 的结算归一化 admission 政策，而不是重新评价 legacy `probability_delta >= 0.05`。Estimand 层级固定如下：

```text
PRIMARY
  NOMINAL_EV_CALIBRATION
  realized_unit_return Y_i ~ EV_i
  理由：canonical EV 的定义即为每单位名义 stake 的期望利润，
        该 estimand 最不可争议。

KEY SECONDARY
  EXPOSURE_NORMALIZED_CALIBRATION
  Y_i / S_asof,i ~ EV_i / S_asof,i
```

硬合同：

```text
S_asof = 该 fixture 在预测时点、由模型五态分布导出的 S。
S_asof 在预测时点即固定，因此 E[Y/S_asof] = EV/S_asof 成立。

禁止使用赛后实现的 R 作为分母。
理由：PUSH 时 R=0 除零；且以 outcome state 作分母会改变 estimand，
      构成 outcome conditioning。
```

两个空间必须同时报告，但只有 `NOMINAL_EV_CALIBRATION` 是 primary；`EXPOSURE_NORMALIZED_CALIBRATION` 是 key secondary，不得单独覆盖 primary 裁决。`cashflow_price_edge` 是受 `Fq` 量化影响的 `EV/S_asof` 代码表示，不是独立于 EV 的新信号。硬禁止把 `cashflow_price_edge` 与 EV 当作两个独立 predictor 做交叉归因。

政策裁决必须冻结为单一 decision rule，不得根据哪个空间的回归 p 值更好看而选择政策。若 Owner 坚持双 primary，必须事前同时冻结 multiplicity control、joint success rule、两个独立 MME，以及 `BOTH PASS` 或 hierarchical gatekeeping；未冻结这些内容时禁止称 co-primary。

在查看新结果前必须冻结：

- evaluation universe，且不得只看 selected/recommended rows；
- fixture、executable quote、cutoff 和 authority result binding；
- AH/OU 分开报告；
- half/integer/quarter line 覆盖与分层；
- `S_asof` 作为连续量的分层/交互报告方式；
- primary 与 key-secondary 的 estimand、MME、cluster、power design 和单一政策 decision rule；
- failure/coverage Gate、futility rule 与 one-look rule；
- 政策门槛不允许根据结果移动。

每行至少记录：

```text
predicted_EV
S_asof
Fq
Tq
EV_threshold_margin = predicted_EV - Tq
cashflow_price_edge
line_type
EV_SE
EV_minus_SE
realized_unit_return
fixture / quote / model / calibration identity
```

Evaluability check 必须确认 threshold margin 两侧、各 line type 和 `S_asof` 区间都有可绑定结果的样本，并按 fixture 去重/聚类，分开 current/superseded、official/shadow、market、checkpoint 和 model/calibration identity。不足时返回 `RECORD_FIRST_EVALUATE_LATER`，不得以推荐集代替完整 evaluation universe。

Half-line 的 `S_asof=1` 只是结算归一化的边界特例，不代表 integer/quarter line 的 admission 行为。因此 Phase 4 不得只在 half-line 上评价，必须覆盖全部 line type 并以 `S_asof` 为连续量分层。

Devig authority 不是 Phase 4 的入口前置：本阶段的 primary 使用模型五态分布、executable price 和实现结算回报，不需要 latent market probability。任何附加 `MODEL_VS_MARKET` 分析仍必须遵守 `DEVIG_AUTHORITY_RESOLVED`。

可能结论只允许：

```text
KEEP_NORMALIZED_EDGE_POLICY
REPLACE_WITH_CONSTANT_NOMINAL_EV_POLICY
REVISE_POLICY_WITH_NEW_PREREGISTRATION
NOT_IDENTIFIABLE
RECORD_FIRST_EVALUATE_LATER
```

`REPLACE_WITH_CONSTANT_NOMINAL_EV_POLICY` 必须另行预注册，不得由本阶段直接改代码。Owner 裁决必须显式引用 §2.5 的两段式证据状态与经济含义表；当前文档既未证明结算暴露归一化优于名义 EV，也未证明相反结论。

本阶段只出决策包，不直接改阈值。

### Phase 4.5 — Frozen U2 Pipeline with Penaltyblog Challenger

状态：`REQUIRES_BASELINE_QUALITY_IDENTIFIED_AND_ELIGIBLE_COHORT`；未执行，且需要新的 Phase 4.5 预注册与 Owner 授权。

定位：Phase 4.5 不再从零建设 minimal probe，而是复用 U2 已冻结并跑通的测量管线，把 challenger 替换为 Penaltyblog 独立 Poisson，从而直接回答“Penaltyblog 是否为 W2 增加概率信息”。

| 合同项 | Phase 4.5 冻结规格 | 来源 |
|---|---|---|
| comparator | `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO`；已冻结、已验证 | U2 comparator 与真实数据 `0.14` 断言 |
| cohort | 沿用 U2 修正后的权威 cohort，SHA-256 `c74eaf0fc3b780f6b04c20353e55e5e83ffdebd213a4c1bbb83b0dcc903ce44e`，`9,551` 场、`13` 个 competition、`UNLABELLED=0` | `U2_ARMING_FREEZE.json` 的 `cohort_label_correction` |
| PIT / 切分 | 沿用 U2：`min_history=5`，split `2025-11-11 00:15:00+00`；目标 fixture 不进入自身特征 | `U2_ARMING_FREEZE.json` |
| primary | 五态 NLL 逐 fixture 配对差；合成线网格、market/line-type 分层与 cluster 均沿用 U2 | U2 `primary_estimand` / `line_grid` |
| challenger | Penaltyblog 独立 Poisson，在同一训练前缀上拟合 | Phase 4.5 新增且必须预冻结的唯一模型变更 |

以下是 Phase 4.5 未来执行的新增流程前置，不是对 U2 已冻结项的追溯修改：在 cohort 冻结之前，必须至少由两条独立路径产出同一份数据并逐字段比对；全部字段一致后，才允许计算 digest 并冻结。U2 的 `706` 个 league 标签缺陷是在冻结后由偶然完成的后台交叉比对发现；本前置将该偶然检查固化为流程。

禁止搬用任何既有系数。Penaltyblog 的模型版本、拟合公式、正则化/优化器、收敛规则、失败处理和任何超参数必须在看结果前冻结；不得把 U2 的 Understat challenger 系数或 2026-07 的既有系数带入 Phase 4.5。

原 Phase 4.5 预估的大部分基础设施成本已经沉没进 U2：cohort 身份、PIT 特征、chronological split、五态结算/评分、合成线网格、分层、cluster、futility 顺序和零 silent-loss 约束均已有可复用实现与证据。剩余工作是接入 Penaltyblog、在相同训练前缀重新拟合，并为新的 `d_i` 重新估计功效。

两个问题继续拆轨：

```text
MODEL_QUALITY_TRACK
  does not require devig authority

MODEL_VALUE_TRACK
  requires DEVIG_AUTHORITY_RESOLVED
```

依赖闭合：

- `W2_BASELINE_PROBABILITY_QUALITY_AUDIT` 必须给出可评分的 W2 baseline identity、预测与结果绑定；
- W2 baseline 必须按 `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO` 复现；任意非零 `raw_delta` 的 `elo_delta/raw_delta` 必须在 `1e-9` 内等于 `0.14`，零 `raw_delta` 必须对应零 `elo_delta`，否则 fail closed；
- Phase 4.5 必须逐字节复用 U2 cohort digest、PIT、切分、`min_history`、线网格、cluster 与 `MME=0.0025`；
- `W2_COHORT_BURN_LEDGER.json` 必须如实记录该 cohort 已用于 U2 fit/futility，并给出 Phase 4.5 用途分类；不得把已查看状态伪装为 virgin confirmation；
- 如果 Phase 2.5 为 `BASELINE_QUALITY_NOT_IDENTIFIABLE`，或 comparator identity、PIT、预测/结果绑定、cohort 用途不可复现，`MODEL_QUALITY_TRACK` 返回 `NOT_IDENTIFIABLE`，不得改用 market-only 结果批准 adapter；
- devig authority 未解决时，只将 `MODEL_VALUE_TRACK` 标为 `MARKET_TRACK = NOT_IDENTIFIABLE`，不得阻断合法的 `MODEL_QUALITY_TRACK`。

这不是无合同的一次性脚本。U2 已冻结合同不得改写；查看任何 Phase 4.5 指标前，只允许另行冻结 Penaltyblog challenger 与本次执行特有部分：

```text
Penaltyblog version / independent-Poisson model / fit configuration
training-prefix fit rule and coefficient artifact identity
per-fixture paired d_i implementation and sign check
futility variance estimator and clustered-SE implementation
coverage and failure rule
track hierarchy and track-specific estimands
devig method and method identity for MODEL_VALUE_TRACK only
seed/bootstrap or uncertainty method
```

最小实现边界：

- 只做 `INDEPENDENT_POISSON_FEASIBILITY_ONLY`；
- 复用 U2 cohort、fixture identity、PIT rows、score-matrix/five-state helpers 和冻结 split，不生成可漂移的替代 cohort；
- Penaltyblog challenger 只能在相同训练前缀拟合，validation outcome 不得参与 fit/config 选择；
- 每个候选 fixture 必须证明 fixture、cutoff、training rows 和 actual outcome parity；
- 失败 fixture 保留 reason，silent loss 为 0；
- 产生一个 immutable analysis artifact 和 execution receipt；
- 不建 migration、production ledger、worker、UI 或 runtime dependency；
- 不把 Penaltyblog 的信息集称为 W2 的严格子集；
- Penaltyblog 使用历史进球；W2 在当前启用联赛的生产有效输入是 PIT rolling xG 加其确定性 proxy Elo，身价与首发当前不提供数值增量。“进球减 xG 的残差可能携带终结效率信息”只作为待检验机制，不得在结果前写成已证明增量；
- 1X2 只能作为 secondary diagnostic；1X2 单独为正不得返回 `PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH`。

#### Phase 4.5 `MODEL_QUALITY_TRACK`

primary 完整沿用 U2 的五态合同：

```text
d_i = NLL_comparator_i - NLL_penaltyblog_i
positive favours the Penaltyblog challenger
reporting = stratified by market and line type
cluster = matchday (kickoff date) and league
pooled primary uses all 13 corrected league labels; UNLABELLED = 0
```

合成线网格保持冻结：OU `[1.5, 2.0, 2.5, 3.0, 3.5]`；AH `[-1.5, -1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.5]`；分层保持 `EXACT_HALF_LINE / INTEGER_LINE / QUARTER_LINE`。

```text
Cohort membership MUST NOT depend on
analysis_direction_allowed, cashflow_price_edge threshold,
candidate status, recommendation status, or realized outcome.
```

exact half-line WIN/LOSS LogLoss/Brier 与 `PB_TO_W2_BOUNDARY_SCORE` 只保留为预注册 secondary diagnostic；它们不得替代五态 NLL primary。1X2 同样只是 secondary diagnostic。

先算 futility，再决定是否读取 validation 五态分数。U2 在同一 cohort/切分上得到 `MDE=0.003624 > MME=0.0025`；Phase 4.5 因 challenger 与 `d_i` 均已变化，必须只用训练前缀重新估计自己的 `d_i` 离散度和 clustered SE。若新的 MDE 仍高于 `MME=0.0025`，必须在评分前返回：

```text
INSUFFICIENT_POWER_DO_NOT_SCORE
```

此时不得读取 validation 五态分数。不得为换取功效而修改 cohort、切分比例、`min_history`、线网格、cluster 定义或下调 MME。

`MODEL_QUALITY_TRACK` 不使用 market probability，也不需要 devig authority。除评分前的功效停止外，原结论集保持：

```text
PROBABILITY_INCREMENT_IDENTIFIED
NO_PROBABILITY_INCREMENT
NOT_IDENTIFIABLE
```

#### Phase 4.5 `MODEL_VALUE_TRACK`

本轨在 exact half-line 上增加同 bookmaker、同 capture/checkpoint、同 fixture、互补 selection、精确 line 的 quote-pair 要求。两边赔率仍包含 overround，model-vs-market 只能报告：

```text
METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK
```

不得称为唯一 latent market probability。Primary devig method 必须在 outcome metric 前冻结；其他预声明方法只能做 sensitivity，不得事后挑选。任何 `MODEL_TO_MARKET_BOUNDARY_SCORE` 必须绑定冻结 devig method。如果 `DEVIG_AUTHORITY_RESOLVED` 不成立，本轨标 `MARKET_TRACK = NOT_IDENTIFIABLE`，不得影响 `MODEL_QUALITY_TRACK` 的合法结论。

两轨共同不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

输出：

```text
PB_MINIMAL_FEASIBILITY_PREREGISTRATION.md
PB_MINIMAL_FEASIBILITY_MANIFEST.json
PB_MINIMAL_FEASIBILITY_RESULT.json
PB_MINIMAL_FEASIBILITY_EXECUTION_RECEIPT.md
```

是否进入 adapter model research 只由 Gate C0-MODEL 裁决；market-only 结果、1X2 secondary 或 C0-MARKET 均不得替代 C0-MODEL。

`NO_PROBABILITY_INCREMENT` 只停止 Penaltyblog challenger 集成，不否定 Phase 1–4 的 W2 EV/baseline 治理改进。

### Phase 5 — PB Adapter Preregistration & Contract

状态：`OWNER_AUTHORIZATION_REQUIRED_AND_C0_MODEL_PASS_ONLY`

目标：冻结一个只产生 shadow probability artifact 的最小接口。

第一版模型：`INDEPENDENT_POISSON_PARITY_ONLY`。

输入合同至少包含：

```text
canonical_fixture_id
competition_id
season
kickoff_utc
training_cutoff
home_team_identity
away_team_identity
training_row_ids/hash
feature/source lineage
```

输出合同至少包含：

```text
probability_provider
library_version
adapter_version
model_family
model_version
fit_config_hash
training_cutoff
generated_at
lambda_home
lambda_away
score_grid
score_grid_max_goals
tail_mass
p_home / p_draw / p_away
fit_status
failure_reason
artifact_hash
```

硬约束：

- Penaltyblog固定版本；
- deterministic fit/predict；
- `training_date < training_cutoff`；
- 不读取目标 fixture 的赛果、赛后证据、quote 或 W2 candidate 结果来选择配置；历史训练窗口内、cutoff 之前的赛果仍是合法训练输入；
- 不使用 W2 模型结果 fallback；
- 失败行保留；
- 原始 W2 数据只读；
- 输出只进入 analysis-only artifact/ledger。

输出：

```text
PB_ADAPTER_PREREGISTRATION.md
PB_ADAPTER_CONTRACT.json
PB_ADAPTER_FAILURE_TAXONOMY.json
```

### Phase 6 — Poisson Parity & Engineering Validation

状态：`REQUIRES_PHASE_5_FREEZE`

目标：验证 adapter，而不是评价模型优劣。

这里的 parity 指：

- W2 export 与 Penaltyblog job 的 fixture/training-row 身份一致；
- Penaltyblog原生输出与 adapter artifact 一致；
- score grid 经 W2 聚合与结算后的转换一致。

它不要求 W2 当前 xG/factor λ 与 Penaltyblog 历史赛果 Poisson λ 数值相等；两者预测差异属于 Phase 7 的模型评价问题。

测试：

1. fixture ID parity；
2. training cutoff parity；
3. row conservation / no silent loss；
4. lambda 与 score-grid normalization；
5. tail-mass accounting；
6. 1X2 从 grid 聚合一致性；
7. W2 五态 AH/OU 派生一致性；
8. HOME/AWAY 与 line sign 测试；
9. deterministic rerun hash；
10. failure reason persistence；
11. 同 fixture/quote 的 W2/PB evaluation parity；
12. Penaltyblog项目已有冻结 optimizer evidence 不被改写。

Phase 6 PASS 必须满足：

- fixture 与 cutoff mismatch 为 0；
- silent row loss 为 0；
- 重跑 artifact hash 完全一致；
- 概率和为 1，tail policy 明确；
- 所有失败都有持久化 reason；
- 生产 writer 调用为 0。

Parity PASS 不代表模型有效，只代表接口可信。

### Phase 7 — W2-Specific Paired Model Evaluation

状态：`NEW_PREREGISTRATION_REQUIRED`

目标：在 W2 自己的 PIT 时间与盘口语境中，将 challenger 的概率质量与报价可利用性分开评价。Phase 7 不再以 `DEVIG_AUTHORITY_RESOLVED` 作为整体硬前置，而是拆为 D1/D2 两轨。

两轨分别冻结 W2 专属 power design，不得共享拍脑袋样本门槛。必须用允许的 development data 估计 paired/clustered variance，处理同 matchday、联赛、重复 checkpoint/fixture 的相关性，并预先批准 MME、alpha、power、look rule 与 attrition。`N≈2500/6900` 只是依赖未验证方差、EV dispersion 与独立观测的敏感性示例，不是 Gate；Factor V2 的 `N=5500` 也只服务其原始 successor 对照，不得搬用。若当前 N、覆盖或可达 MDE 不满足相应冻结设计，该轨返回 `INSUFFICIENT_POWER_DO_NOT_SCORE`，不得先看结果再移动 MME、primary metric 或阈值。

#### Phase 7 D1 — Probability Quality

D1 不使用 market probability，不需要 devig authority。Primary 是 exact half-line binary subset 上 W2 与 PB 的同 selection、同 line、同 fixture 配对概率质量；1X2 只作 secondary diagnostic。

```text
EVAL_D1 =
predefined fixture/market/selection/line eligible
∩ actual outcome valid
∩ W2 prediction valid
∩ PB prediction valid
```

每个模型/配对集合必须报告 `N / coverage / failure_rate / fixture-set digest / league/time-block coverage`。D1 至少报告：

```text
W2 LogLoss / Brier
PB LogLoss / Brier
W2-minus-PB paired DeltaLogLoss
PB-to-W2 boundary score at w=0
ECE where preregistered and powered
AH/OU separate intersection N
fixture-clustered uncertainty
```

模型间冗余只在两模型交集上评价，报告 `intersection N`、lambda/probability correlation、mean absolute probability difference 与 direction agreement；禁止使用所有模型共同成功集作为唯一集合。D1 PASS 的唯一含义是：

```text
CHALLENGER_PROBABILITY_VALUE_IDENTIFIED
```

它不授权 edge、recommendation、profitability、market value 或 production admission 结论。

Phase 7 的 EV realization 不在 D2 内重新定义，也不以 `DEVIG_AUTHORITY_RESOLVED` 为前置。其 estimand、MME、cluster 定义与 power design 一律继承 Phase 4 已冻结的 `NOMINAL_EV_CALIBRATION` 合同；这里只声明 cohort 差异：

```text
Phase 4 cohort = 全部 official evaluation opportunities
D1/D2 cohort   = PB 配对集
```

不得在 Phase 7 为同一 EV realization estimand 建立第二套合同。

#### Phase 7 D2 — Market-Relative Probability Benchmark

D2 必须在 D1 身份合同之外证明 `DEVIG_AUTHORITY_RESOLVED`、同 bookmaker/checkpoint 的 quote-pair identity、executable price 与 market attribution。Computed algorithm、declared label、persisted method/version/overround 或 primary cohort attribution 任一未闭合时，D2 返回 `BLOCKED_BY_DEVIG` 或 `NOT_IDENTIFIABLE`；不得用事后 sensitivity 分层替代冻结。该硬前置只约束 market-relative probability benchmark，不回溯阻断上文继承 Phase 4 合同的 EV realization。

```text
EVAL_D2 =
EVAL_D1
∩ exact executable quote identity valid
∩ frozen market attribution valid
```

D2 按预注册分别评价：

```text
METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK LogLoss / Brier
model-vs-market paired proper-score delta on identifiable subsets
market probability boundary metrics
coverage / failure / method-version / overround
```

整数盘或四分盘无法从双边赔率识别 market 三态/五态概率时，禁止伪造 market LogLoss；只报告可识别指标与限制。只有 D2 可以支持 `MARKET_EDGE_SUPPORTED` 类结论。

Phase 7 必须保持下列不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

### Phase 8 — Prospective Shadow

状态：`NOT_AUTHORIZED_BY_THIS_PLAN`

Phase 8 分为两个互不替代的 shadow；两者都必须另行申请，均为 `NOT_AUTHORIZED_BY_THIS_PLAN`：

```text
PROBABILITY_SHADOW
  entry: Gate D1 PASS
  purpose: prospective paired probability quality only

MARKET_VALUE_SHADOW
  market-relative component entry: Gate D2 PASS, including resolved devig,
                                   quote-pair identity, executable price
                                   and market attribution
  EV realization component entry: Phase 4 contract frozen + Phase 6 PASS;
                                  inherits NOMINAL_EV_CALIBRATION and has
                                  no devig prerequisite
  purpose: prospective market-relative benchmark and EV realization,
           with their entry conditions kept separate
```

共同要求：

- 独立 shadow registry/ledger；
- cohort start 在首条 row 前冻结；
- W2 与 PB 同 opportunity、同 quote、同 cutoff；
- 不写现有 official evaluation/opportunity/outbox；
- 不影响 Dashboard 正式状态；
- 不产生 BET/SKIP 或通知；
- append-only；
- outcome 只在结算后绑定；
- 不根据早期盈亏改阈值或模型。

`PROBABILITY_SHADOW` 不得生成 edge、profitability 或 production-admission 结论；`MARKET_VALUE_SHADOW` 也只形成 Owner decision packet，不自动晋级生产。

Phase 8 entry 必须保持下列不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

## 8. 数据与评价合同

### 8.1 Quote Binding

任何 EV 记录必须同时绑定：

```text
canonical_fixture_id
market
selection
canonical_line
side_line
quote_id / capture_id
provider
bookmaker_id
quote_usage = EXECUTABLE
captured_at
price
freshness_status
bookmaker_depth
```

任何字段缺失或冲突：`EV_NOT_ELIGIBLE`。

### 8.2 Probability Identity

```text
provider
model_family
model_version
calibration_version/status
training_cutoff
input_manifest_hash
fit_config_hash
prediction_artifact_hash
```

禁止只有一个没有身份的 `model_probability` 浮点数。

### 8.3 Settlement Identity

```text
settlement_contract_version
WIN
HALF_WIN
PUSH
HALF_LOSS
LOSS
distribution_sum
EV_formula_version
```

`effective_settlement_probability` 只能用于明确声明的 scalar comparison，不得替代五态分布或五态 EV。

### 8.4 Failure Ledger

每个模型每个 fixture 必须有一行终态：

```text
SUCCESS
INPUT_INELIGIBLE
FIT_FAILED
PREDICTION_INVALID
QUOTE_BINDING_FAILED
SETTLEMENT_DISTRIBUTION_INVALID
EVALUATION_NOT_IDENTIFIABLE
```

禁止 silent drop。

## 9. 测试计划

### 9.1 EV 合同测试

- `expected_value()` / `fair_decimal_odds()` 的 Decimal 精确黄金向量断言；
- 每条保存 `distribution / odds / W / L / S / EV / F* / Fq / edge_code / EV/S / quantization residual / Tq`；
- 未量化 `edge* = EV/S` 恒等式与量化后 `edge_code = d/Fq - 1` 定义；
- 逐样本量化界 `d × |Fq-F*| / (F* × Fq)`；
- 禁止以 `abs_tol=1e-5` 验证黄金向量；`3e-5` 只允许用于三条已界定样例，不得作全域容差；
- `Tq = 1.05 × Fq × W - S` 与逐场 `S` 门槛测试，禁止把黄金向量门槛固化为 line-type 常数；
- quarter-line split；
- integer push；
- side symmetry；
- odds monotonicity；
- distribution normalization；
- invalid/stale/reference quote fail closed；
- duplicate implementation parity。

### 9.2 Probability Adapter 测试

- schema validation；
- fixture/training set equality；
- deterministic reproduction；
- no future row；
- score-grid/tail normalization；
- aggregation parity；
- failure persistence；
- no cross-model fallback。

Phase 2.5/4.5 另需：

- baseline parameter identity and provenance guard；
- λ/total-goals clipping conservation；
- cohort burn ledger schema/completeness guard；
- cohort usage classification guard：`FIT/TUNE/SELECT/EVALUATE/DESCRIPTIVE_ONLY/UNKNOWN_BLOCKED`；
- development-cohort allowlist guard，且 `UNKNOWN_BLOCKED` 不得进入预检；
- forbidden holdout/outcome-access guard；
- probe preregistration hash check；
- W2/PB fixture、cutoff、training-row、outcome parity；
- exact half-line binary/no-push classification test；
- bookmaker/fixture/market/line/checkpoint/captured-at quote-pair parity test；
- devig method/version/overround persistence test；
- `BASELINE_QUALITY_NOT_IDENTIFIABLE` hard-block test；
- cohort membership independent of `analysis_direction_allowed`、cashflow edge threshold、candidate/recommendation status 与 realized outcome；
- half-line `S=1` boundary test，且不得外推 integer/quarter policy；
- 1X2 secondary cannot promote to `PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH` test；
- C0-MODEL/C0-MARKET separation test；
- `DEVIG_AUTHORITY_CONFLICT` blocks market track but not model-quality track test；
- computed devig algorithm versus declared provenance parity test；
- nullable/mixed `devig_method` coverage and row-conservation test；
- unattributable historical method persistence test；
- deterministic probe result/hash；
- probe no-migration/no-runtime/no-ledger-write guard。

### 9.3 Evaluation 测试

- W2/PB Model-vs-Model fixture parity；
- Model/Market fixture parity on D2 only；
- per-model EVAL set equality；
- pairwise intersection；
- no silent row loss；
- metric sign convention；
- settlement-result binding；
- selected-only bias guard；
- market-five-state identifiability guard；
- method-specific devig benchmark naming guard；
- mixed-method pooling forbidden test；
- Phase 4 primary does not require devig authority test；
- Phase 4 primary/key-secondary hierarchy and single decision-rule test；
- Phase 4 covers all line types and stratifies continuously by `S_asof` test；
- `S_asof` fixed from the prediction-time five-state distribution test；
- realized `R` denominator forbidden / PUSH division-by-zero guard；
- Phase 4 forbids treating EV and cashflow edge as independent predictors test；
- Phase 4.5/D1 remains evaluable when devig is unresolved test；
- Phase 4.5 market track/D2 blocks when devig is unresolved test；
- Phase 7 EV realization inherits the Phase 4 contract and does not require devig test；
- D2 scope contains only market-relative probability benchmark metrics test；
- Gate D1/D2 conclusion-authority separation test；
- D1 cannot produce edge, recommendation or profitability claims test；
- `PROBABILITY_SHADOW`/`MARKET_VALUE_SHADOW` entry separation test；
- preregistration hash check。

### 9.4 Production Isolation 测试

- Provider calls 0；
- production DB writes 0；
- official ledger writes 0；
- outbox/Bark 0；
- capability state unchanged；
- W2 and Penaltyblog frozen artifact hashes unchanged。

## 10. 决策门

### Gate A — EV Contract

PASS：公式、单位、方向、报价用途全部明确且一致。

FAIL：出现无法解释的数值漂移、quote fallback 或方向冲突。

动作：FAIL 时停止 Adapter 工作，先修合同。

Gate A 通过只证明审计完整，不自动产生 `DEVIG_AUTHORITY_RESOLVED`。若审计发现 computed/declared/persisted 身份冲突，必须保留 `DEVIG_AUTHORITY_CONFLICT`，直到最小修复、方法冻结和历史可归因性验收分别完成。

### Gate B — Probability Lineage

PASS：生产、离线、实验模型身份完全分开。

FAIL：无法证明实际概率源或 calibration artifact。

动作：FAIL 时不得评价 Penaltyblog增量。

### Gate B2 — W2 Baseline Quality

PASS：`BASELINE_PRIOR` 的参数来源、输入覆盖、clipping、fixture set、概率指标与可识别限制均可复算，统计结论标记为 `BASELINE_QUALITY_IDENTIFIED`；`W2_COHORT_BURN_LEDGER.json` 存在且至少一个 cohort 对本问题的用途分类和可用性可核验。

NOT IDENTIFIABLE：没有合法 cohort、结果绑定或可核验的 cohort 用途时，输出 `BASELINE_QUALITY_NOT_IDENTIFIABLE`；用途无法核实的 cohort 必须标记 `UNKNOWN_BLOCKED`，不伪造 baseline。

动作：`BASELINE_QUALITY_NOT_IDENTIFIABLE` 或只有 `UNKNOWN_BLOCKED` cohort 时，硬阻断 Phase 4.5 的 W2-vs-PB 预检；不得用 market-only 结果替代 baseline 并批准 adapter。Market-only 如需研究，必须另立问题、预注册和 Owner 授权。无论 baseline 结果好坏，本 Gate 都不自动修改生产参数。

### Gate C0 — Minimal PB Feasibility

#### Gate C0-MODEL

PASS：复用 U2 冻结管线的五态 `MODEL_QUALITY_TRACK` 返回 `PROBABILITY_INCREMENT_IDENTIFIED`，且 fixture/cutoff/training-row/outcome mismatch 与 silent loss 均为 0。Gate 结论为：

```text
PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH
```

STOP：`NO_PROBABILITY_INCREMENT` 时停止 Penaltyblog challenger 集成，不建设 Phase 5–8，但不否定 Phase 1–4 的 W2 治理工作。

NOT IDENTIFIABLE：`BASELINE_QUALITY_NOT_IDENTIFIABLE`、只有 `UNKNOWN_BLOCKED` cohort、comparator/PIT 身份或预测/结果合同不完整时，不得凭不完整结果继续 adapter。功效不足时返回 `INSUFFICIENT_POWER_DO_NOT_SCORE`，同样不得继续 adapter。Devig 冲突本身不阻断 C0-MODEL。

1X2 只是 secondary diagnostic；即使单独为正，也不得触发 C0-MODEL PASS。C0-MODEL PASS 不授予 edge claim、recommendation claim、profitability claim 或 production admission。

#### Gate C0-MARKET

只评价 `MODEL_VALUE_TRACK` 的可识别性与冻结完整性，允许结论：

```text
PASS
BLOCKED_BY_DEVIG
NOT_IDENTIFIABLE
```

C0-MARKET PASS 不能替代 C0-MODEL；C0-MARKET blocked 也不能推翻合法的 C0-MODEL 结果。

Gate C0 必须保持下列不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

### Gate C — Adapter Parity

PASS：零 silent loss、零 identity mismatch、确定性重现。

FAIL：任何结果都不用于模型判断。

### Gate D — Retrospective Paired Evaluation

两个 Gate 都必须在执行前冻结各自的 W2 专属 power design；不得硬编码 `2500/6900`，也不得复用 Factor V2 的 `5500`。

#### Gate D1 — Probability Quality

D1 可在 devig authority 未解决时运行。必须基于严格配对的 W2/PB model probabilities、actual outcome 与预冻结 exact half-line cohort；结论只允许：

```text
CHALLENGER_PROBABILITY_VALUE_IDENTIFIED
NO_CHALLENGER_PROBABILITY_VALUE
REVISE_ADAPTER_OR_PROTOCOL
INSUFFICIENT_POWER_DO_NOT_SCORE
NOT_IDENTIFIABLE
```

D1 PASS 只能表示 `CHALLENGER_PROBABILITY_VALUE_IDENTIFIED`，不得出现 market edge、recommendation、profitability 或 production-admission 结论。

继承 Phase 4 合同的 EV realization 可在 devig authority 未解决时运行；其 `NOMINAL_EV_CALIBRATION` estimand、MME、cluster 定义与 power design 不得在 Gate D 重定义。cohort 差异固定为：Phase 4 使用全部 official evaluation opportunities，Phase 7 使用 PB 配对集。

#### Gate D2 — Market-Relative Probability Benchmark

D2 的硬前置为 `DEVIG_AUTHORITY_RESOLVED`、quote-pair identity、executable price 与 market attribution。该状态必须覆盖 primary cohort 的方法归因；任何 null、mixed pooled、label/algorithm mismatch 或事后选取 sensitivity method，均使 D2 返回 `BLOCKED_BY_DEVIG` 或 `NOT_IDENTIFIABLE`。该硬前置仅适用于 `METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK`、model-vs-market LogLoss/Brier 与 market probability boundary metrics，不适用于继承 Phase 4 合同的 EV realization。D2 结论只允许：

```text
MARKET_EDGE_SUPPORTED
MARKET_EDGE_NOT_SUPPORTED
REVISE_MARKET_PROTOCOL
INSUFFICIENT_POWER_DO_NOT_SCORE
BLOCKED_BY_DEVIG
NOT_IDENTIFIABLE
```

只有 D2 允许出现 `MARKET_EDGE_SUPPORTED` 类结论。

Gate D 必须保持下列不变量：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

#### D1/D2 决策矩阵

| D1 | D2 | 允许解释 | Shadow eligibility |
|---|---|---|---|
| PASS | 未运行 / `BLOCKED_BY_DEVIG` / `NOT_IDENTIFIABLE` | 只识别 challenger 概率价值；EV realization 仍按 Phase 4 继承合同独立解释；不得声称 market-relative 报价可利用 | 可另行申请 `PROBABILITY_SHADOW`；若 Phase 6 PASS，可另行申请 `MARKET_VALUE_SHADOW` 的 EV realization component，不得进入 market-relative component |
| PASS | PASS | 概率价值与 market-relative benchmark 分别通过各自 Gate；EV realization 仍继承 Phase 4 合同；均非生产授权 | 可分别另行申请两类 shadow 及其已满足 entry 的组件 |
| FAIL / `NO_CHALLENGER_PROBABILITY_VALUE` | 任意 | 不继续 PB adapter model research；D2 不得替代 D1 | 两类 shadow 均不可进入 |
| `INSUFFICIENT_POWER_DO_NOT_SCORE` / `NOT_IDENTIFIABLE` | 任意 | 不评分、不外推 | 两类 shadow 均不可进入 |

决策矩阵同样受以下不变量约束：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

### Gate E — Prospective Shadow

`PROBABILITY_SHADOW` 仅可由 D1 PASS 支持。`MARKET_VALUE_SHADOW` 的 market-relative component 必须由 D2 PASS 支持；其 EV realization component 则继承 Phase 4 合同并要求 Phase 6 PASS，不以 devig 为前置。两者均为 `NOT_AUTHORIZED_BY_THIS_PLAN`，即使后续独立 PASS，也只能提交 Owner decision packet，不自动产生 production admission。

Gate E entry 继续受以下不变量约束：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

## 11. 风险登记

| 风险 | 后果 | 控制 |
|---|---|---|
| 把竞彩 settlement SP 当 entry/closing | 虚假 EV/CLV | 市场命名和 quote_usage 硬约束 |
| 从 1X2 外推 AH/OU | 错误策略结论 | 分市场预注册，禁止直接外推 |
| 只评价被推荐比赛 | selection bias | 评价全部 official opportunities |
| 用旧小样本或未核验的当前 N 调参数 | outcome-driven overfit | 未来独立授权的 Phase 4 evaluability 范围重计数；新冻结 cohort；不足则不评分 |
| 用 `2500/6900` 或别的粗略近似作硬门 | 错误功效与虚假确定性 | proper-score/EV calibration 分开做 W2 专属 clustered power design |
| 把 Factor V2 的 5,500 借给 PB | estimand/identity 混用 | 原预注册保持不变，PB 单独冻结 power |
| 用 scalar probability 代替五态 | AH/OU EV 错误 | 保存完整五态分布 |
| 两边赔率伪造 market 五态 | 不可识别问题被隐藏 | `MARKET_FIVE_STATE_NOT_IDENTIFIABLE` |
| 同时接六模型 | 复杂度和冗余 | Poisson parity first |
| 模型失败 fallback | 评价污染 | per-model ledger/no fallback |
| 本地/生产版本错位 | 基于错误代码优化 | Gate 0A/0B 分离；production claims 依赖 0B |
| baseline 未验证就只审 challenger | challenger 结论无法解释 | Phase 2.5 先审 W2 `BASELINE_PRIOR` |
| cohort 使用历史错分或把“曾看过赛果”当作对所有新问题永久烧毁 | 伪造污染或伪造可用 cohort | burn ledger 保存实验身份、estimand、outcome visibility 和用途分类；无法核实时 `UNKNOWN_BLOCKED` |
| 无身份 futility probe | fixture/cutoff/outcome 污染 | Phase 4.5 最小冻结合同与 immutable receipt |
| PROPORTIONAL/POWER 等 devig 权威冲突 | 事后选取有利的 market benchmark | Phase 1/2 核实 authority；方法未冻结或冲突时仅 market-relative 轨道 fail closed，model-quality 轨道不受阻断 |
| 只信 `POWER` source 字符串而不核对实际计算 | 把 PROPORTIONAL 历史行错分为 POWER | computed/declared/persisted 三身份分开审计；不可重建时 `METHOD_NOT_ATTRIBUTABLE` |
| 混合或 nullable `devig_method` 行直接 pooled 做 market-relative 评价 | 模型效果与方法变更混杂 | Gate 0B 覆盖率计数；D2 只评价 100% 可归因同质子集，否则 `BLOCKED_BY_DEVIG` / `NOT_IDENTIFIABLE` |
| 把 EV 与 `cashflow_price_edge` 当两个独立 predictor | 对同一结算信息重复归因 | Phase 4 固定名义 EV primary 与期望结算暴露 key secondary，禁止交叉归因 |
| 用赛后实现 `R` 归一化回报 | PUSH 除零并形成 outcome conditioning | `S_asof` 必须在预测时点由模型五态分布固定；禁止 realized `R` 作分母 |
| 把 `.0500/.0440/.03975` 固化为 line-type 门槛 | 忽略同一盘型逐场 `S_asof` 差异 | 门槛逐行由 `S_asof/W/Fq` 推导，按连续 `S_asof` 分层 |
| 只在 half-line 上评价 V4 policy | 把 `S=1` 边界误外推到 integer/quarter | Phase 4 覆盖全部 line type；half-line 只作 model-quality primary |
| 把 D1 PASS 解读为 market edge | 从概率改进跳到报价可利用性 | D1/D2 分轨；edge/profitability 结论只允许 D2 |
| 使用量化无感的统一 epsilon | 正确黄金向量假失败或全域误放行 | Decimal 精确断言 + 逐样本量化误差界 |
| 用 1X2 结果外推 AH/OU 产品市场 | 预检通过但产品 estimand 未被验证 | U2 冻结合成线网格上的五态 AH/OU NLL 为 primary；exact half-line binary 与 1X2 只作 secondary，无单独晋级权 |
| 把 method-specific devig benchmark 称为真实 market probability | 过度声明可识别性 | 强制名称 `METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK`，持久化 method/version/overround |
| calibration 名称误导 | 假安全感 | 调用审计、重命名/隔离决策包 |
| threshold 事后移动 | 研究失效 | preregistration hash |
| 新依赖进入生产 runtime | 运维和供应链风险 | 初期 artifact boundary |
| Vault 混用 | 状态污染 | W2/Penaltyblog 独立 Vault |

## 12. 交付物清单

### 本计划已交付

- `W2_PENALTYBLOG_EV_OPTIMIZATION_PLAN_V1.md`
- `U2_ARMING_FREEZE.json`：任何拟合与评分前写入的 U2 冻结链证据
- `U2_EXECUTION_RECEIPT.md`：U2 执行、futility 停止与零生产影响回执

### 后续阶段候选交付物

```text
LOCAL_AUTHORITY_SNAPSHOT.json
LOCAL_AUTHORITY_RECONCILIATION.md
PRODUCTION_AUTHORITY_SNAPSHOT.json
PRODUCTION_EVALUABILITY_COUNTS.json
PRODUCTION_DEVIG_ATTRIBUTION_COUNTS.json
PRODUCTION_AUTHORITY_RECONCILIATION.md
EV_CALL_GRAPH.md
EV_SEMANTIC_MATRIX.json
DEVIG_AUTHORITY_MATRIX.json
EV_CONTRACT_AUDIT.md
PROBABILITY_LINEAGE.md
MODEL_CALIBRATION_IDENTITY_MATRIX.json
MISLEADING_API_DECISION_PACKET.md
W2_BASELINE_PROBABILITY_QUALITY_AUDIT.md
W2_BASELINE_PROBABILITY_METRICS.json
W2_BASELINE_PARAMETER_PROVENANCE.json
W2_COHORT_BURN_LEDGER.json
V4_EV_ADMISSION_POLICY_PREREGISTRATION.md
V4_EV_ADMISSION_POLICY_RESULT.json
PB_MINIMAL_FEASIBILITY_PREREGISTRATION.md
PB_MINIMAL_FEASIBILITY_MANIFEST.json
PB_MINIMAL_FEASIBILITY_RESULT.json
PB_MINIMAL_FEASIBILITY_EXECUTION_RECEIPT.md
PB_ADAPTER_PREREGISTRATION.md
PB_ADAPTER_CONTRACT.json
PB_ADAPTER_FAILURE_TAXONOMY.json
PB_PARITY_EXECUTION_RECEIPT.md
W2_PB_PROBABILITY_QUALITY_RECEIPT.md
W2_PB_MARKET_VALUE_RECEIPT.md
W2_PB_PRODUCTION_ADMISSION_DECISION_PACKET.md
```

文件名只是建议；未授权阶段不得提前生成“PASS”或“IMPLEMENTED”状态文件。

## 13. 多 Agent 评审问题

请每个 Agent 独立回答，并引用具体文件、函数、测试或证据：

1. 当前 exact production probability path 是什么？是否遗漏任何实际 writer/read path？
2. W2 是否存在数学上不等价的 EV 实现？请提供固定向量复算。
3. `effective_settlement_probability` 的当前使用是否存在语义误用？
4. `MIN_MARKET_ANCHOR_DIVERGENCE` 在 legacy/parallel dynamic evaluation 与 V4 optional diagnostic 中的角色是否被正确区分？
5. V4 的 `EV > 0`、`cashflow_price_edge >= 0.05`、`EV - uncertainty > 0` 是否在全部 public recommendation path 一致？
6. `models/dixon_coles.py` 与 `models/calibration.py` 是否进入 production？请给完整 caller graph。
7. AH/OU 市场五态概率能否由当前双边赔率唯一识别？若不能，哪些指标仍可合法比较？
8. Penaltyblog adapter 最小输入是否足以复现训练？是否缺联赛/赛季/球队身份或权重语义？
9. Poisson parity 是否应为第一模型？若反对，请给更小、更可验证的替代方案。
10. 哪些阶段与 Factor Model V2 当前 Gate/holdout 冲突？
11. 哪些任务可以只读完成，哪些需要新模型身份、迁移或生产授权？
12. 哪个结论会因当前 checkout 与生产 release 不一致而失效？
13. 本计划是否存在隐性 outcome tuning、selection bias 或 holdout reuse？
14. 最小、可回滚、不会污染正式账本的实现边界是什么？
15. W2 当前 `BASELINE_PRIOR` 的默认 λ 参数是如何产生的？其 clipping、1X2/AH/OU 概率质量、分联赛/时间稳定性和 calibration status 有哪些可复算证据？
16. Claude 提出的 `2500/6900` 是否能由 W2 的真实 clustered variance、EV dispersion 和 attrition 重现？若不能，正确的 power estimand/design 是什么？
17. 各历史 cohort 曾被哪个实验用于 `FIT/TUNE/SELECT/EVALUATE/DESCRIPTIVE_ONLY`？对当前 PB-vs-W2 estimand 是否仍可用，证据是什么？
18. exact half-line 的 quote-pair authority 和 primary devig authority 分别是什么？`analysis_evidence.py` / `score_baseline.py` 的显式 PROPORTIONAL 与 `analysis_calculator.py` 的 computed-PROPORTIONAL/declared-POWER 是否冲突？
19. 哪些报告或 API 可能把 `METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK` 误表述为唯一真实 market probability？最小命名与 provenance 修复是什么？
20. `analysis_calculator.py` 的 computed PROPORTIONAL 与 declared POWER 冲突影响了哪些历史行？哪些 release 可以从 exact source 归因，哪些必须标 `METHOD_NOT_ATTRIBUTABLE`？
21. `cashflow_price_edge` 与 `EV/S` 的四位 fair-odds 量化残差，是否逐样本满足量化感知界？
22. Phase 4 是否覆盖全部 line type，并把逐场 `S` 作为连续量，而不是使用固定盘型门槛？
23. Gate D1 的任何结论是否越权暗示 market edge、profitability 或 production admission？
24. 你的最终建议是：

```text
ACCEPT_PLAN
ACCEPT_WITH_REVISIONS
REJECT_PLAN
```

## 14. 建议的 Agent 回复格式

```markdown
# Review: W2 × Penaltyblog EV Optimization Plan V2.0

Agent role:
Review date:
Code/evidence baseline:

## Verdict
ACCEPT_PLAN / ACCEPT_WITH_REVISIONS / REJECT_PLAN

## Confirmed facts
- claim
- evidence path:line

## Disputed claims
- claim
- reason
- counter-evidence

## Missing risks
- risk
- required control

## Phase changes
- phase
- exact proposed change

## Stop conditions
- condition

## Minimal next action
- one bounded action only
```

## 15. Owner 决策点

Gate 0A、Gate 0B authority/U2 cohort scope、Phase 2.5a 静态审计与 U2 执行均已有证据。U2 的独立执行授权已经消耗并以 `INSUFFICIENT_POWER_DO_NOT_SCORE` 终止；它不延伸为继续 Phase 1/2、补跑 Gate 0B 的 Phase 4/devig 统计、再次导出或重切 cohort、重新拟合、读取 validation 五态分数、模型晋级或生产修改的授权。

Owner 当前需要分别审阅两项，不得把任一项视为本计划内的实施授权：

```text
REVIEW_A_NEW_PHASE_4_5_PREREGISTRATION
  frozen U2 pipeline + Penaltyblog challenger + futility before scoring

REQUEST_INDEPENDENT_MME_JUSTIFICATION
  whether 0.0025 nats is meaningful for five-state AH/OU NLL
```

Phase 4.5 的新预注册只能复用本版冻结的 comparator、cohort、PIT、切分、`min_history`、线网格、cluster 与 `MME=0.0025`，并只新增 Penaltyblog challenger 的预冻结拟合合同；执行仍需另行授权。MME 论证是两条路共同的外部论证事项，不得在本版内据此改数值。若未来主张更小 MME，U2 / champion 与 Phase 4.5 / Penaltyblog 均须另立新的预注册；不得修订本版。

U2 / champion 分支原有选择仍保留：在 `MME=0.0025` 下等待 validation 约 `5,859` 场（约再 `0.9` 年），或在 MME 获得独立论证后另立新预注册。该分支不再取代本文 Penaltyblog 研究问题的 Phase 4.5 下一步。

Gate 0B 剩余的 Phase 4 evaluability 与 devig attribution 统计范围仍需未来独立授权；任何新生产访问授权不得继承既有授权。Phase 4.5、adapter、D1/D2 与两类 shadow 均需后续分别授权；本计划不授权其中任何一项。

## 16. 最终建议

```text
NEXT_ACTION = REVIEW_PHASE_4_5_PREREGISTRATION_AND_INDEPENDENT_MME_JUSTIFICATION
IMPLEMENTATION = NOT_AUTHORIZED
PRODUCTION_CHANGE = FORBIDDEN
```

建议收集意见后，先合并事实分歧，不按投票多数直接实施。所有能改变概率、阈值、候选集合或生产行为的意见，都必须回到代码证据、预注册和 Owner 授权。

## 17. Revision History

| revision | date | change | implementation authority |
|---|---|---|---|
| V1 | 2026-08-29 | 初始多 Agent 评审计划 | `NOT_AUTHORIZED` |
| V1.1 | 2026-08-29 | 按真实 caller graph、`BASELINE_PRIOR`、dynamic evaluation persistence、Factor V2 frozen power 与 Claude 首轮意见，新增 Gate 0A/0B、Phase 2.5、Phase 4.5 和独立 power 前置 | `NOT_AUTHORIZED` |
| V1.2 | 2026-08-29 | 吸收 Claude 第二轮意见：增加 cohort burn ledger 分类保护、baseline 不可识别 hard block、exact half-line 产品 primary、method-specific devig benchmark 与对应 Gate/测试/风险闭环 | `NOT_AUTHORIZED` |
| V1.3 | 2026-08-29 | 将 devig authority 与历史方法归因提升为 Phase 4/7 硬前置；增加 Gate 0B `devig_method` 覆盖率、computed/declared/persisted 三身份、方法敏感性边界和混合/null fail-closed 规则 | `NOT_AUTHORIZED` |
| V1.4 | 2026-08-29 | 按 `main@3b7f87db` 重建代码事实与 canonical pricing；明确 V4 EV/结算归一化 admission、逐场 `S` 与量化边界；拆分 model/market、C0-MODEL/C0-MARKET、D1/D2 及双 shadow | `NOT_AUTHORIZED` |
| V1.4.1 | 2026-08-29 | 措辞勘误：`S` 术语、Kelly、`S_asof` 与 D2 前置；不改变 A–J、Gate 结构或阶段顺序 | `NOT_AUTHORIZED` |
| V1.5 | 2026-08-30 | Gate 0B：生产权威更正 + 生产 λ 闭式 | `NOT_AUTHORIZED` |
| V1.6 | 2026-08-30 | U1 完成 + U2 预注册 V2 | `NOT_AUTHORIZED` |
| V1.7 | 2026-08-30 | U2 执行 + `INSUFFICIENT_POWER_DO_NOT_SCORE` | `NOT_AUTHORIZED` |
| V2.0 | 2026-08-30 | 重新定位：测量能力建设归位，Phase 4.5 复用 U2 冻结管线并接入 Penaltyblog challenger | `NOT_AUTHORIZED` |

## 附录 A — 四轮评审处置与事实同步

### A.1 首轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| 完整 adapter 前增加 futility-first 预检 | `ACCEPT_WITH_CORRECTION` | 增加 Phase 4.5；但预检必须先冻结最小身份、PIT、配对和结果绑定合同。Penaltyblog 历史进球信息也不能表述为 W2 信息集的严格数学子集。 |
| Gate D 硬设 `N_settled >= 2500` | `REJECT_AS_HARD_GATE` | `2500/6900` 依赖未由 W2 验证的方差、EV 离散度和独立性假设。Phase 7 必须先做 W2 专属 power design，并分开 proper-score 与 EV calibration estimand。 |
| Gate 0 拆成本地静态与 VPS 只读 | `ACCEPT` | 拆为 Gate 0A/0B；0B 需 Owner 单独授权，但不需要 GitHub/GHCR，也不允许 Provider 调用、业务写入或部署。 |
| 先核验 5% 阈值两侧是否都有已结算样本 | `ACCEPT_WITH_CODE_CLARIFICATION` | 代码合同已保存 `NO_EDGE_CURRENT/current_delta/required_delta/shortfall`，设计上未天然丢弃阈值下方；Gate 0B 已关闭生产身份，但实际两侧行数和结算覆盖仍属未来独立授权的 Phase 4 evaluability 只读计数。 |
| 先验证 W2 当前 λ champion/baseline | `ACCEPT` | 新增 Phase 2.5，优先于 PB feasibility probe；不得把既有 Factor V2 candidate 证据冒充生产 `BASELINE_PRIOR` 已验证。 |

### A.2 第二轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| Phase 2.5 增加 cohort burn ledger | `ACCEPT_WITH_CLASSIFICATION_GUARD` | 增加 `W2_COHORT_BURN_LEDGER.json`；逐项记录 fit/tune/select/evaluate/descriptive 用途和 outcome visibility，禁止把“曾查看”粗暴外推为对所有新问题永久不可用。 |
| `BASELINE_QUALITY_NOT_IDENTIFIABLE` 时闭合 Phase 4.5 分支 | `ACCEPT_AND_HARD_BLOCK` | W2-vs-PB model-quality 预检不得运行或晋级。market-only 可以另立预注册研究，但不能返回 `PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH`。 |
| Phase 4.5 加入 AH/OU 半盘子集 | `ACCEPT_WITH_V1_4_TRACK_SPLIT` | 半盘结算确为二态，提升为 `MODEL_QUALITY_TRACK` primary；该配对模型评价不需要 devig。只有附加 market-relative 轨道才需冻结去水方法并标记 method-specific benchmark。1X2 仅作 secondary diagnostic。 |

### A.3 第三轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| 将 devig authority 提升为 market-relative 轨道显式前置 | `ACCEPT_WITH_V1_4_1_SCOPE_CORRECTION` | `analysis_calculator.py` 实际做 PROPORTIONAL 归一，却标记来源为 POWER；必须分开计算算法、provenance 标签和持久化方法身份。该冲突只阻断 `MODEL_VS_MARKET`、Gate D2 的 market-relative probability benchmark 与 `MARKET_VALUE_SHADOW` 的对应组件；不阻断 Phase 4、`MODEL_VS_MODEL`、Gate D1 或继承 Phase 4 合同的 EV realization。 |
| Gate 0B 增加历史 `devig_method` 非空覆盖率 | `ACCEPT_AND_FAIL_CLOSED_FOR_MARKET_TRACK` | 按 evidence source/release/schema/market/checkpoint 统计 null、单一方法和混合方法，并检查方法标签能否由当时代码身份证明。混合或大量 null 时，market-relative 轨道只能用可归因子集，否则返回 `BLOCKED_BY_DEVIG` 或 `NOT_IDENTIFIABLE`；不得阻断 model-quality 轨道。 |

### A.4 V1.4 交接单处置

| 项目 | 处置 | V1.4 结论 |
|---|---|---|
| 在 `main@3b7f87db` 上重建代码事实 | `ACCEPT_AFTER_INDEPENDENT_CHECK` | 不再使用落后 checkout 的符号定义或行号；后续 Gate 0B 已确认生产 exact runtime 为 `ea557bb8 / 0070`。 |
| 将 5% 政策重写为结算归一化 EV admission | `ACCEPT` | 未量化时 `edge* = EV/S`；代码使用四位量化 `Fq`，因此 `edge_code` 只是量化感知近似。 |
| exact half-line 保留为 model-quality primary | `ACCEPT_WITH_BOUNDARY_NOTE` | `S=1` 是归一化边界特例，不能代表 integer/quarter line 的 admission 行为。 |
| Phase 4.5、Phase 7 与 Gate C0/D 拆成 model/market 两轨 | `ACCEPT` | devig authority 只阻断 `MODEL_VS_MARKET`，不阻断严格配对的 `MODEL_VS_MODEL`。 |
| Phase 8 拆成两类 shadow | `ACCEPT` | `PROBABILITY_SHADOW` 与 `MARKET_VALUE_SHADOW` 均不在本计划授权范围。 |

### A.5 Gate 0B 与 U2 comparator 事实同步

| 项目 | 当前事实 | 计划影响 |
|---|---|---|
| 生产权威 | `ea557bb8 / schema 0070`；`3b7f87db / schema 0051` 落后 19 个 migration | 生产事实服从 Gate 0B；既有静态结论仅在逐字节相同文件上存活 |
| 生产 Elo | 从 rolling xG 确定性构造，`is_independent_signal=False` | `elo_gap_weight` 不是死代码，而是 `raw_delta` 的 14% 放大器 |
| 生产身价 | 当前启用联赛与 `team_values` artifact 交集为空 | 当前为零贡献；不得外推到有匹配 artifact 的其他联赛 |
| 生产首发数值项 | 唯一 `SimulationInputs` 构造点不填充，capability 为 `NOT_IMPLEMENTED` | 当前生产构造路径恒为零贡献 |
| U2 comparator 与执行 | `PRODUCTION_FORMULA_XG_WITH_PROXY_ELO`；`EXECUTED` | 旧 `XG_ONLY` 已被静态核验取代；冻结链与训练前缀 refit 已完成，futility 在 validation 五态评分前触发，结论为 `INSUFFICIENT_POWER_DO_NOT_SCORE` |

本轮复核锚点（均为 `main@3b7f87db`）：

- `src/w2/domain/five_state_pricing.py:6-82`：canonical 五态分布、EV、四位量化 fair odds 与 `cashflow_price_edge`；
- `src/w2/markets/value_engine.py:9-24`：上述 canonical 定义的 compatibility re-export；
- `src/w2/domain/recommendation_decision_v4.py:54-70,418-442`：概率字段仅为 optional diagnostic；现役 admission 使用 EV、cashflow edge 与 EV-minus-uncertainty；
- `docs/operations/W2_RECOMMENDATION_AUTHORITY_IMPLEMENTATION_MATRIX.md:34-44`：V4 是当前 recommendation 决策/方向权威；
- `src/w2/dashboard/workspace.py:14-16`、`src/w2/dashboard/intelligence.py:15-16` 与 `src/w2/dashboard/day_view.py:150-160`：Intelligence Workspace 是 public product/display authority，V4 在其投影中是 diagnostic input；
- `src/w2/strategy/calibration.py:6-22,35-132`：production calibration identity、默认先验权重和 clamp；
- `src/w2/strategy/simulate.py:128-163`：正式 simulation 调用 `calibrate_lambdas()` 后生成 score matrix；
- `src/w2/markets/analysis_evidence.py:124-140,204-240`：显式 PROPORTIONAL devig；`probability_delta_admission_gate = False`，准入使用 EV、cashflow edge 与 EV-minus-SE；
- `src/w2/prematch/lifecycle.py:12-20,245-353`：legacy/parallel dynamic evaluation 的 5pp delta 合同；
- `src/w2/prematch/repository.py:94-138`：dynamic evaluation append-only payload 持久化；
- `src/w2/domain/odds.py:10-21,45-107`：半盘不拆分且整数比分无法在半球线上 push，因此 AH/OU exact half-line 仅有 WIN/LOSS；
- `src/w2/markets/devig.py:9-114`：同一报价支持四种去水方法，证明 market-implied probability 依赖冻结的方法身份；
- `src/w2/markets/analysis_evidence.py:86-140,184-240`：同盘口双边身份检查、当前 PROPORTIONAL 去水及现役 analysis admission；
- `src/w2/markets/score_baseline.py:202-218`：当前 score baseline 也显式使用 PROPORTIONAL；
- `src/w2/prematch/analysis_calculator.py:5213-5254,6122-6135`：实际按 implied probability 总和归一，与 PROPORTIONAL 等价，但 source 字符串写为 `POWER devig from matchday_market_observations`；
- `src/w2/settlement/settle.py:24-50` 与 `migrations/versions/0022_extend_recommendation_lock_snapshot.py:123-126`：`devig_method` 可持久化但为 nullable，因此必须核验实际覆盖率；
- local commit `22dc0dbe` 的 `V2_GATE1_CALIBRATION_RECOVERY_01/REPORT.md`：temperature `0.928709586`、NLL 小幅改善、各 ECE bin 变差、candidate-only；
- local commit `f0d201c5` 的 successor preregistration：Factor V2 one-look `5,500` 与 `2028-02-01T00:05:00Z` 的专属身份；
- `/Users/liudehua/.hermes/workspace/penalty-football-research/src/penalty_research/validation_design.py:22-29`：boundary score 是 1X2 log-pool 在 `w=0` 的导数，不能绕过概率/结果配对合同或扩展为 AH/OU 五态结论。
- `docs/review_packages/GATE_0B_EXECUTION_RECEIPT.md`：生产 `ea557bb8 / 0070` 身份、只读零写入证明与 U2 disposition；
- `docs/review_packages/PRODUCTION_LAMBDA_EFFECTIVE_FORM.md`：五系数生产效果、proxy Elo 代数推导与当前启用联赛有效闭式；
- `docs/review_packages/U2_PREREGISTRATION.md`：`PRODUCTION_FORMULA_XG_WITH_PROXY_ELO` 的预注册控制合同与 refit/非可比性约束；
- `docs/review_packages/U2_ARMING_FREEZE.json`：任何拟合与评分前写入的 cohort、切分、模型、断言、线网格、cluster 与 MME 冻结证据；
- `docs/review_packages/U2_EXECUTION_RECEIPT.md`：U2 执行链、真实数据 proxy Elo 断言、futility 数字、停止位置与零生产影响证据。
- `docs/review_packages/W2_BASELINE_PARAMETER_PROVENANCE.json`：五项 `production_effect` 与 production effective closed form。
