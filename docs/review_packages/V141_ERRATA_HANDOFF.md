# V1.4.1 Errata 交接单

用途：Codex 落 V1.4.1 的唯一输入。本文件自包含，不依赖任何对话上下文。
基线：`main@3b7f87db`（PR #534 base），文档 head `9938b42b`
状态：`ERRATA_INSTRUCTION_DOCS_ONLY`
授权范围：**仅文档勘误**。不改业务代码、不接 Penaltyblog、不访问 VPS/Provider、不部署。
计划书状态保持 `PROPOSED_NOT_AUTHORIZED`。

## 0. 这是勘误，不是重写

V1.4 已通过第四轮外部评审，裁定 `ACCEPT_WITH_MINOR_REVISIONS`。
A–I 九项全部 PASS，J 项 PARTIAL PASS。方向、分层、Gate 结构、双轨设计**全部不变**。

本单只改四处：三处是 J 项的措辞过强（数学上不成立的推断），
一处是 V1.4 在修复 V1.3 矛盾时引入的新矛盾。

**排期**：本 errata 须在 **Phase 4 预注册之前**完成，
但**不阻断** `Gate 0A + Phase 1 + Phase 2 + Phase 2.5`。
Phase 1 只需数学合同（`S / EV / EV/S / Fq / Tq`），不需要先裁定经济约束；
Errata 4 影响 Phase 7，离前置审计很远。

---

## Errata 1 — `S` 的术语必须收窄（第 117 / 182 / 185 / 292 / 1513 行）

### 问题

V1.4 把 `S` 称为「在险本金 / 在险资本」。该命名在数学上不成立：

1. **`EV/S` 是期望之比，不是比之期望。**
   设单位名义 stake 的实现收益为 `Y`，非 PUSH 结算暴露比例为 `R`：

   ```text
   R:  WIN 1 | HALF_WIN 0.5 | PUSH 0 | HALF_LOSS 0.5 | LOSS 1
   E[R] = W + L = S
   EV/S = E[Y] / E[R]
   ```

   而 `E[Y]/E[R] != E[Y/R]`。且 PUSH 时 `R = 0`，`Y/R` 无定义。
   「每单位在险本金的期望利润」读作 `E[Y/R]`，是错的。

2. **`S` 不是一般金融意义的 capital-at-risk。**
   赛前整笔 1u 均被占用，最大可能损失仍为 1u。
   `S` 只是按结算态加权后、进入非退款输赢分支的**期望**本金比例。

### 改法

统一术语为：

```text
S = 期望结算暴露本金比例（期望非退款结算本金比例）
    expected settlement-exposed (non-refunded) principal fraction
```

第 182 行改为：

```text
cashflow_price_edge ≈ 每单位「期望结算暴露本金」的期望利润
                    = E[Y] / E[R]（受 Fq 量化影响的代码表示）
```

首次出现处必须加限定句：

> 本文「结算暴露本金」专指非 PUSH/退款部分的期望本金暴露，
> **不等同于**赛前资金占用、最大可能损失，或 Kelly 意义的 risk capital。
> `EV/S` 是期望利润与期望结算暴露之比 `E[Y]/E[R]`，
> **不是** `E[Y/R]`（PUSH 时 `R=0`，该量无定义）。

第 117 行表格说明、第 292 行「名义本金与在险本金空间」、
第 1513 行风险表述，一并按新术语统一。

---

## Errata 2 — 删除 Kelly 推断，政策状态改为两段式（第 185 / 189 / 192 行）

### 问题

第 192 行：

> 按资金规模分注时，分注原本就作用于在险资本，因此先验倾向保持当前归一化政策

该推断不成立。Kelly 最大化 `E[log(1 + Y)]`，取决于整个五态回报分布与效用函数，
**不由 `EV/S` 决定**；`S` 也不是 Kelly 的风险资本分母。

第 185 行直接断言「当前 5% 门槛是一个在险资本回报率政策」，同样过强。

### 改法

**删除**第 192 行整句的 Kelly 推断部分。保留「须 Phase 4 预注册证据裁决」的限定。

第 185 行改为两段式状态标记：

```text
INTENDED_NORMALIZATION_IDENTIFIED
  已确认：当前代码有意以 S 做结算暴露归一化，
  该结构不是 algebra 副作用，仓库 recommendation authority 收敛记录
  亦表明 5pp probability delta -> EV + EV-SE + cashflow edge 是有意迁移。

POLICY_JUSTIFICATION_PENDING_EVIDENCE
  未确认：没有代码或设计证据表明 Owner 的经济目标明确是
  「每单位期望结算暴露至少 5%」，也没有证据表明该尺度优于
  名义本金 / 资金占用 / 回撤 / log-growth / 流动性消耗 / 盘口限额。
```

第 189 行 binding-constraint 表保留，但「风险资本（本金 / 回撤 / Kelly 分注）」
一栏改为「结算暴露归一化」，移除 Kelly 字样。

---

## Errata 3 — Phase 4 双空间必须定层级与 `S_asof`（第 801-808 行）

### 问题

当前写法两个空间并列，未指定 primary / secondary，也未指定 `S` 的取值时点。

1. **多重性风险**：若两空间都能单独触发 `KEEP` / `REPLACE`，
   即构成无多重性控制的 co-primary，可挑结果。
2. **分母泄漏风险**：未指定 `S` 是赛前预测值还是赛后实现值。
   若用实现的 `R` 作分母：PUSH 除零，且把 outcome state 放进分母，
   estimand 改变，属于 outcome conditioning。

### 改法

第 801-808 行改为：

```text
PRIMARY
  NOMINAL_EV_CALIBRATION
  realized_unit_return  Y_i   ~   EV_i
  理由：canonical EV 的定义即为每单位名义 stake 的期望利润，
        该 estimand 最不可争议。

KEY SECONDARY
  EXPOSURE_NORMALIZED_CALIBRATION
  Y_i / S_asof,i   ~   EV_i / S_asof,i
```

新增硬合同（必须以显式条款形式写入，不能只作说明文字）：

```text
S_asof = 该 fixture 在预测时点、由模型五态分布导出的 S。
S_asof 在预测时点即固定，因此 E[Y/S_asof] = EV/S_asof 成立。

禁止使用赛后实现的 R 作为分母。
理由：PUSH 时 R=0 除零；且以 outcome state 作分母会改变 estimand，
      构成 outcome conditioning。
```

政策裁决规则另写为**单一**预注册 decision rule，
不得以「哪个空间的回归 p 值更好看」选择政策。

若 Owner 坚持双 primary，则必须同时预注册：
multiplicity control、joint success rule、两个独立 MME、
是否要求 BOTH PASS 或 hierarchical gatekeeping。
未预注册上述内容时，**禁止**称 co-primary。

---

## Errata 4 — Gate D2 的 devig 前置过宽（第 1119-1121 / 1437-1440 行）

### 问题（V1.4 新引入的内部矛盾）

第 841 行 Phase 4 正确写：

> Devig authority 不是 Phase 4 的入口前置：本阶段的 primary 使用模型五态分布、
> executable price 和实现结算回报，不需要 latent market probability。

但第 1119/1437 行 `Gate D2 — Market Value / EV Realization`
把 `DEVIG_AUTHORITY_RESOLVED` 设为硬前置，而 D2 内部包含
`predicted EV vs realized unit return calibration`。

**同一份文档：EV realization 不需要 devig（Phase 4），
却又卡在 devig 硬前置之后（D2）。**

`predicted EV vs realized executable-quote return` 只需要
模型五态分布、executable quote identity、price、actual settlement，
不需要任何 latent market probability。

### 改法

**不新增 Gate。** 按下列方式拆前置条件：

```text
Gate D2 — Market-Relative Probability Benchmark
  硬前置：DEVIG_AUTHORITY_RESOLVED
        + quote-pair identity + executable price + market attribution
  评价范围仅限：
    METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK
    model-vs-market LogLoss / Brier
    market probability boundary metrics
  结论仍只有 D2 可出 MARKET_EDGE_SUPPORTED 类
```

EV realization 部分**不在 D2 内重新定义**，改为显式继承：

```text
EV realization 的 estimand、MME、cluster 定义、power design
一律继承 Phase 4 已冻结的 NOMINAL_EV_CALIBRATION 合同。
D2 章节只声明 cohort 差异：
  Phase 4 cohort  = 全部 official evaluation opportunities
  D1/D2 cohort    = PB 配对集
不得在 D2 重复定义同一 estimand，避免同一量出现两套合同而漂移。
EV realization 不以 DEVIG_AUTHORITY_RESOLVED 为前置。
```

同步更新第 448 / 453 / 1165 行的流程图与 entry 条件，
以及第 61 行处置表中对 D2 范围的描述。

**保持不变**：D1/D2 不变量四句（`D1 PASS does not imply D2 PASS` 等）
在全部 8 处保留，一字不改。

---

## 1. 验收要求

完成后自查并报告：

```text
- 全文不再出现「在险本金」「在险资本」作为 S 的名称
- 首次出现处已加 E[Y]/E[R] != E[Y/R] 的限定句
- Kelly 推断已删除；binding-constraint 表已去 Kelly 字样
- INTENDED_NORMALIZATION_IDENTIFIED + POLICY_JUSTIFICATION_PENDING_EVIDENCE
  两段式状态已写入
- Phase 4 已定 PRIMARY / KEY SECONDARY 层级
- S_asof 硬合同已写入，且明确禁止 realized R 作分母
- Gate D2 已限定为 market-relative；EV realization 继承 Phase 4 合同
- D1/D2 四句不变量仍在全部 8 处
- 状态仍为唯一一处 PROPOSED_NOT_AUTHORIZED
- 文档版本标为 V1.4.1
```

## 2. 不变的边界

不改业务代码、不接 Penaltyblog、不访问 VPS / GitHub Actions / Provider、不部署、不更新 Obsidian。
A–I 九项与 Phase 2.5 高优先级、Poisson-first、production isolation 全部保留不动。
完成后可申请的授权范围仍只是 `Gate 0A + Phase 1 + Phase 2 + Phase 2.5`。
