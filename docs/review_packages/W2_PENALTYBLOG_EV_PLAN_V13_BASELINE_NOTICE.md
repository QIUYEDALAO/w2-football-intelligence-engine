# 基线告示 — 阅读 V1.3 计划书之前必读

文档状态：`FACT_NOTICE_NOT_A_PLAN_REVISION`
创建日期：2026-08-29
作者：Claude Code（独立复核）
适用对象：`W2_PENALTYBLOG_EV_OPTIMIZATION_PLAN_V1.md`（V1.3）

本文件不修改计划书内容，只记录两项在 V1.3 定稿后、于 `main@3b7f87db` 上核实的事实：

1. 第 1-5 节：计划书 §2 的采集基线落后 `origin/main` 310 个提交，其「当前代码」断言须重写；
2. 第 6 节：`cashflow_price_edge` 与 `EV` 是同一个量，当前准入门槛的实际 EV 阈值随盘口类型浮动。

两项独立，第 6 节不依赖第 1-5 节的基线结论。

## 1. 结论

V1.3 第 2 节的代码事实基线，采集自一棵**落后 `origin/main` 310 个提交**的本地工作树。
该基线上的多项断言在当前 `main` 上已不成立。

**在把审计基线对齐到 `main` 之前，不要执行 Gate 0A、Phase 1、Phase 2 或 Phase 2.5。**
在旧树上产出的调用图与血缘结论，描述的是已不存在的代码。

## 2. 证据

```bash
git fetch --all
git rev-list --left-right --count origin/main...codex/eval-02b-write-side-implementation-04
# 310    1
```

- 计划书采集基线：`11c26e1e`（分支 `codex/eval-02b-write-side-implementation-04`）
- 当前 `origin/main`：`3b7f87db` — `Fix checkpoint collection truth (#533)`

符号存在性对照（两者均已实测）：

| 符号 / 路径 | 采集基线 `11c26e1e` | 当前 `main` `3b7f87db` |
|---|---|---|
| `src/w2/domain/five_state_pricing.py` | 不存在 | **存在** |
| `cashflow_price_edge` | 全仓零命中 | **存在**（`five_state_pricing.py:76` 等） |
| `src/w2/domain/recommendation_decision_v4.py` | 不存在 | **存在** |
| canonical 五态 EV 位置 | `markets/value_engine.py:214` | `domain/five_state_pricing.py` |
| `analysis_evidence.py` 准入条件 | `delta >= MIN_MARKET_ANCHOR_DIVERGENCE` | 已引入 `cashflow_price_edge` |

复现命令：

```bash
git cat-file -e origin/main:src/w2/domain/five_state_pricing.py && echo EXISTS
git grep -n "cashflow_price_edge" origin/main -- 'src/**/*.py'
```

## 3. 受影响的断言

V1.3 中凡以「当前代码」「当前 GitHub main」「当前生产路径」为前提的事实陈述，均须在对齐后重新核验，至少包括：

- 第 2.2 节 EV 实现入口清单与 canonical 位置
- 第 2.3 节概率主链
- 第 2.4 节两项代码卫生问题的调用边界
- 第 2.5 节 5% 门与正式推荐边界
- 全部 devig authority 相关结论（`PROPORTIONAL` / 标签冲突 / 归因）

**注意**：五态 EV 的数学式本身与代码版本无关，该结论不受影响。

## 4. 对评审分歧的解释

本轮出现过两位评审对「同一份代码」得出互相矛盾结论的情况：

- 一方读本地工作树，结论为 `analysis_evidence.py` 仍以 probability delta 准入；
- 一方读 GitHub `main`，结论为准入已迁移至 `cashflow_price_edge`。

**双方都正确，只是读了相差 310 个提交的两棵树。**

由此推论：`main` 上 `analysis_evidence`（已迁移）与 `prematch/lifecycle`（未迁移）之间的
policy 差异，性质更可能是**迁移进行中**，而非长期共存的设计矛盾——因为在旧基线上两者是一致的。
该判断须在对齐后由 Phase 1 证实或推翻。

## 5. 建议的下一步

```text
1. 裁定审计 authority 基线（建议 origin/main@3b7f87db，或 Gate 0B 核验后的生产 release）
2. 在该基线上重跑 V1.3 全部事实核验
3. 据此重写计划书第 2 节，并将本次 310-commit 偏差作为 Gate 0A 必要性的实证记入
4. 然后再申请 Gate 0A / Phase 1 / Phase 2 / Phase 2.5 授权
```

## 6. 追加事实 — `cashflow_price_edge` 与 `EV` 是同一个量

本节在 `main@3b7f87db` 上验证，与第 1-5 节的基线偏差问题独立。

### 6.1 恒等式

令：

```text
W = WIN  + 0.5 x HALF_WIN
L = LOSS + 0.5 x HALF_LOSS
```

由 `src/w2/domain/five_state_pricing.py` 的三个定义可直接推出：

```text
EV                  = (d - 1) x W - L
fair_decimal_odds   = (L + W) / W
cashflow_price_edge = d / fair_decimal_odds - 1
                    = ((d - 1) x W - L) / (W + L)
                    = EV / (W + L)
```

即 **`cashflow_price_edge` 是 `EV` 除以一个只依赖结算态分布的分母**，不是独立信号。

### 6.2 实测验证

使用 `main@3b7f87db` 的 `five_state_pricing.py` 直接计算（偏差约 1e-5，来自
`fair_decimal_odds` 的 `quantize(Decimal("0.0001"))`）：

| 盘口类型 | EV | cashflow_edge | W+L | EV/(W+L) |
|---|---|---|---|---|
| 半盘 AH±0.5 / OU2.5 | 0.072500 | 0.072489 | **1.0000** | 0.072500 |
| 整数盘（含 push） | -0.002500 | -0.002864 | 0.8800 | -0.002841 |
| 四分盘 | 0.121500 | 0.152823 | 0.7950 | 0.152830 |

四分盘一行使用的是评审提出的黄金向量
`WIN=0.42 / HALF_WIN=0.10 / PUSH=0.08 / HALF_LOSS=0.15 / LOSS=0.25 / odds=1.95`。

### 6.3 三项后果

**一、半盘上两个门槛完全相同。** 当 `PUSH = HALF_WIN = HALF_LOSS = 0` 时 `W + L = 1`，
于是 `cashflow_price_edge` 与 `EV` 逐值相等。当前准入：

```text
EV > 0  AND  cashflow_price_edge >= 0.05  AND  EV - SE > 0
```

在半盘上实际是两条件：`EV >= 0.05 AND EV - SE > 0`。

**二、有走盘/半赢半输质量的盘口，门槛系统性更松。**
`cashflow_edge >= 0.05` 等价于 `EV >= 0.05 x (W + L)`：

```text
半盘    ->  EV >= 0.0500
整数盘  ->  EV >= 0.0440   ( -12% )
四分盘  ->  EV >= 0.0398   ( -20% )
```

该差异是代数产物，不是设计选择。

**三、与「半盘作 primary」存在选择效应。**
exact half-line 被定为可识别的 primary 评价集，但半盘恰是准入门槛最严的一档，
因此 primary 评价集是准入上最难进入的子集。

### 6.4 对计划的影响

- **Phase 4** 不能把 `cashflow_price_edge` 当作独立于 `EV` 的政策信号评价。
  评价「5% cashflow edge 门」实为评价「随盘口类型浮动 12%-20% 的 EV 门槛」。
  建议 estimand 改为：primary 用 `EV`（按 `W+L` 分层或作连续量），
  `cashflow_edge` / `W+L` / `line_type` 作同一量的三种表示同时记录，
  禁止把 `cashflow_edge` 与 `EV` 作两个独立条件交叉分析。
- **Phase 1** 建议把该恒等式列为 EV 合同的固定断言之一，
  并注意 `fair_decimal_odds` 的 4 位量化会在门槛变量上注入约 `1e-5` 噪声，
  黄金向量 parity 测试必须容忍该量级，否则会假失败。

### 6.5 与 devig authority 的关系（独立结论）

`EV`、`fair_decimal_odds`、`cashflow_price_edge` 的计算链**完全不经过市场概率**，
因此不受 devig authority 冲突影响。据此：

```text
MODEL_VS_MODEL   ->  可继续（W2 vs PB 配对 proper score、boundary score）
MODEL_VS_MARKET  ->  fail closed，直到 devig authority 裁定
```

需要注意的边界：模型概率更准只能让 **EV 数值更准**，
要论证**真实 edge / 可盈利**仍须市场相对轨道。
不得以 `MODEL_VS_MODEL` 的正结果替代 `MODEL_VS_MARKET` 的结论。

本告示不构成对 V1.3 方向的否定。分层设计、预注册、devig authority 前置、
baseline-before-challenger 的顺序均不受此影响。
