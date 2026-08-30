# V1.4 修订交接单

用途：Codex 落 V1.4 的唯一输入。本文件自包含，不依赖任何对话上下文。
基线：`main@3b7f87db`（PR #534 的 base）
状态：`REVISION_INSTRUCTION_DOCS_ONLY`
授权范围：**仅文档修订**。不改业务代码、不接 Penaltyblog、不访问 VPS/Provider、不部署。
计划书状态保持 `PROPOSED_NOT_AUTHORIZED`。

---

## 0. 背景：你缺的两轮上下文

V1.3 发出后经过两轮外部评审（基线均为 `main@3b7f87db`），产生下列已被接受的结论。
**这些不是待议项，是 V1.4 必须落地的内容。**

### 0.1 第二轮已接受（架构事实）

1. V1.3 的 §2 采集自落后 `origin/main` **310 个提交**的工作树，必须整体在 `3b7f87db` 上重写。
2. canonical 五态 pricing 已迁至 `src/w2/domain/five_state_pricing.py`；
   `markets/value_engine.py` 现为 compatibility re-export，不再是定义者。
3. `RecommendationDecisionV4` 是**当前 public recommendation authority**。
   `model_probability` / `market_probability` / `probability_delta_diagnostic`
   均属 `_OPTIONAL_DIAGNOSTIC_FIELDS`。
4. `prematch/lifecycle.py` 的 `ACTIVE_DELTA_THRESHOLD = 0.05` 应归类为
   `LEGACY / PARALLEL DYNAMIC EVALUATION CONTRACT`，**不是**现役 public gate。
5. `analysis_evidence.py` 已设 `probability_delta_admission_gate = False`；
   实际准入为 `EV > 0` + `cashflow_price_edge >= 0.05` + `EV - SE > 0`。
6. devig authority 冲突**只阻断 MODEL_VS_MARKET，不阻断 MODEL_VS_MODEL**。
7. `COMPUTED = PROPORTIONAL / DECLARED = POWER` 的 provenance 错标在 `3b7f87db` 仍成立。
8. `devig_method` 在 `LockedPrediction` 与 migration 中仍 nullable，历史归因须 Gate 0B。

### 0.2 第三轮新增（本次核心）

`cashflow_price_edge` **不是独立于 EV 的准入信号**。详见第 1 节。

---

## 1. 恒等式与量化（已独立复算两次，结论一致）

令：

```text
W = WIN  + 0.5 x HALF_WIN
L = LOSS + 0.5 x HALF_LOSS
S = W + L
d = executable decimal odds
```

由 `five_state_pricing.py` 的定义可推出：

```text
EV     = (d - 1) x W - L
F*     = S / W                      # 未量化 fair decimal odds
edge*  = d / F* - 1 = EV / S        # 严格恒等，仅在量化前成立
Fq     = 1 + quantize(L/W, 0.0001, ROUND_HALF_UP)
edge_code = d / Fq - 1              # 代码实际值
```

**措辞要求**：不得写「`cashflow_price_edge` 与 EV 是同一个量」。
必须写：

> `cashflow_price_edge` 是 EV 经结算现金流质量 `S = W + L` 确定性归一化后的价格优势表示；
> 当前实现另受 fair odds 4 位量化影响，因此代码层非逐值严格相等。

### 1.1 实测（三条黄金向量，`odds = 1.95`）

| 盘口 | 分布 | EV | S | EV/S | edge_code | 残差 |
|---|---|---|---|---|---|---|
| 半盘 | WIN .55 / LOSS .45 | 0.072500 | 1.0000 | 0.0725000000 | 0.0724892751 | −1.072e−5 |
| 整数盘 | WIN .45 / PUSH .12 / LOSS .43 | −0.002500 | 0.8800 | −0.0028409091 | −0.0028635713 | −2.266e−5 |
| 四分盘 | WIN .42 / HW .10 / PUSH .08 / HL .15 / LOSS .25 | 0.121500 | 0.7950 | 0.1528301887 | 0.1528229382 | −7.250e−6 |

### 1.2 量化误差界（公式与实测逐条一致）

```text
|edge_code - EV/S| = d x |Fq - F*| / (F* x Fq)
|Fq - F*| <= 0.00005
```

**容差要求**：`abs_tol = 1e-5` 会让半盘与整数盘黄金向量假失败，**禁止使用**。
针对上述三条向量可用 `abs_tol = 3e-5`，但**不得**作为全域 property-test 的通用容差。

### 1.3 代码实际隐含的 raw-EV 门槛

```text
未量化：T* = 0.05 x S
量化后：Tq = 1.05 x Fq x W - S
```

三条向量的 `T*`：半盘 0.0500 / 整数盘 0.0440 / 四分盘 0.0398。

**措辞要求**：这三个数是**黄金向量示例，不是 line-type 常数**。
真正决定门槛的是逐场的 `S`（受该场 PUSH / HALF_WIN / HALF_LOSS 概率影响），
同为整数盘不同比赛的 `S` 不同，门槛也不同。不得写成「整数盘低 12%、四分盘低 20%」的固定规律。

### 1.4 `S` 的经济含义（本轮新增，必须写入）

按本金去向展开：PUSH 全额退回，HALF_WIN / HALF_LOSS 退回一半，WIN / LOSS 全额结算。

```text
E[进入输赢结算的本金比例]
  = WIN x 1 + HALF_WIN x 0.5 + HALF_LOSS x 0.5 + LOSS x 1
  = W + L = S
```

四分盘验证：`S = 0.795`，且 `1 - S = 0.205 = PUSH + 0.5 x (HALF_WIN + HALF_LOSS) = 0.08 + 0.125`。

因此：

```text
EV                  = 每单位「名义本金」的期望利润
cashflow_price_edge = 每单位「在险本金」的期望利润
```

**当前门槛是标准的「在险资本回报率」政策，不是机械副作用。**
Owner 的裁决因此不是「缺陷还是设计」，而是：

| binding constraint | 应选 |
|---|---|
| 风险资本（本金 / 回撤 / Kelly 分注） | 保持当前归一化（`EV/S`） |
| 周转量 / 流动性 / 盘口限额 | 恒定名义 EV |

按资金规模分注的操作，分注本来就作用在在险资本上，预期结论倾向保持当前政策。
但该判断仍须 Phase 4 证据支持，V1.4 只负责把选项的经济含义写清楚。

---

## 2. V1.4 修订清单（A–J，逐项落地）

### A. §2 整体重写

按 `3b7f87db` 重写全部「当前代码」断言。至少覆盖 0.1 节的 8 条。
新增符号定义表：`W / L / S / F* / Fq / edge* / edge_code / T* / Tq`。

### B. Phase 1 — 新增固定合同断言

必须断言：EV 代数式、未量化 edge 恒等式、量化 edge 定义、代码隐含 EV 门槛 `Tq`、`S` 与盘口结构关系。

三条黄金向量每条须完整保存：
`distribution / odds / W / L / S / EV / F* / Fq / edge_code / EV/S / 量化残差 / Tq`。

测试策略：**先 Decimal 精确相等**（`expected_value()`、`fair_decimal_odds()` 对黄金向量直接断言，无需容差），
**再用量化感知界**验证 `edge_code ≈ EV/S`。禁止统一硬编码 epsilon。

### C. Phase 4 — 改名并改 estimand

删除旧名 `Market-Anchor 5% Policy Evaluation`，也**不要**用 `Cashflow Price Edge Policy Evaluation`。
改为：

```text
Phase 4 — V4 EV Admission Policy & Settlement-Normalization Evaluation
```

Primary estimand 改为 `EV_CALIBRATION`：`predicted_EV` 对 `realized_unit_return`。
**须同时在两个空间报告**：名义空间（`realized_return_per_nominal_stake ~ EV`）
与在险空间（`realized_return_per_at_risk_stake ~ EV/S`）。只报名义空间会把 `S` 的异质性混进残差。

预注册记录字段：
`predicted_EV / S / Fq / Tq / EV_threshold_margin = EV - Tq / cashflow_price_edge / line_type / EV_SE / EV_minus_SE / realized_unit_return`

硬禁止：把 `cashflow_price_edge` 与 `EV` 当两个独立 predictor 做交叉归因。

### D. Phase 4 结论集

```text
KEEP_NORMALIZED_EDGE_POLICY
REPLACE_WITH_CONSTANT_NOMINAL_EV_POLICY   # 须另行预注册
REVISE_POLICY_WITH_NEW_PREREGISTRATION
NOT_IDENTIFIABLE
RECORD_FIRST_EVALUATE_LATER
```

裁决说明须引用 1.4 节的经济含义表。

### E. exact half-line

保留为 Phase 4.5 `MODEL_VS_MODEL` primary。新增硬句：

```text
Cohort membership MUST NOT depend on
analysis_direction_allowed, cashflow_price_edge threshold,
candidate status, recommendation status, or realized outcome.
```

并写明：half-line（`S = 1`）是归一化的边界特例，
**不代表** integer / quarter line（`S < 1`）的准入行为。
因此 Phase 4 的政策评价不得只在 half-line 上做，须覆盖全部 line type 并以 `S` 为连续量分层。

### F. Phase 4.5 — 拆两条轨道

```text
MODEL_QUALITY_TRACK   不需要 devig authority
  primary: W2 vs PB paired LogLoss / Brier / PB_TO_W2_BOUNDARY_SCORE / coverage / failure
  结论集: PROBABILITY_INCREMENT_IDENTIFIED / NO_PROBABILITY_INCREMENT / NOT_IDENTIFIABLE

MODEL_VALUE_TRACK     需要 DEVIG_AUTHORITY_RESOLVED
  未解决时: MARKET_TRACK = NOT_IDENTIFIABLE，且不得因此阻断 MODEL_QUALITY_TRACK
```

把 V1.3 中 devig 对整个 probe 的强依赖，改为 market-relative conditional dependency。

### G. Gate C0 — 拆

```text
C0-MODEL  PASS = PROCEED_TO_ADAPTER_FOR_MODEL_RESEARCH
C0-MARKET PASS / BLOCKED_BY_DEVIG / NOT_IDENTIFIABLE
```

`C0-MODEL PASS` 不授予 edge claim / recommendation claim / profitability claim / production admission。

### H. Phase 7 / Gate D — 拆 D1 / D2

**V1.3 存在内部矛盾必须修**：Phase 7 现写着 `DEVIG_AUTHORITY_RESOLVED` 作为整体硬前置，
与已接受的「devig 只阻断 market track」直接冲突。

```text
Gate D1 — Probability Quality
  可在 devig authority 未解决时运行
  PASS 含义只能是 CHALLENGER_PROBABILITY_VALUE_IDENTIFIED

Gate D2 — Market Value / EV Realization
  须 DEVIG_AUTHORITY_RESOLVED + quote identity + executable price + market attribution
  只有 D2 允许出现 MARKET_EDGE_SUPPORTED 类结论
```

下列文字须同时进入 Phase 4.5、Phase 7、Gate C0、Gate D、决策矩阵、Phase 8 entry：

```text
D1 PASS does not imply D2 PASS.
Probability improvement may improve EV estimation accuracy.
Probability improvement is not evidence that quoted prices are exploitable.
No real-edge or profitability claim is permitted without the market-relative track.
```

### I. Phase 8

区分 `PROBABILITY_SHADOW`（D1 可支持）与 `MARKET_VALUE_SHADOW`（须 D2）。
两者仍均为 `NOT_AUTHORIZED_BY_THIS_PLAN`。

### J. 记录 `S` 的经济含义

把 1.4 节完整写入 §2 或 Phase 4 前言，作为 D 项 Owner 裁决的依据。

---

## 3. 不变的边界

- 计划书状态保持 `PROPOSED_NOT_AUTHORIZED`
- 不请求实施授权，不接 Penaltyblog，不访问 VPS / GitHub Actions / Provider
- Gate 0A / 0B、Phase 2.5（W2 baseline quality，仍为高优先级）、Poisson-first、
  production isolation 全部保留不变
- `fit_dixon_coles()` 未进入正式 simulation、`models/calibration.py` 命名不符实——
  两条结论在 `3b7f87db` 仍成立，保留
- 完成 V1.4 后可申请授权的范围仍只是：
  `Gate 0A + Phase 1 + Phase 2 + Phase 2.5`
