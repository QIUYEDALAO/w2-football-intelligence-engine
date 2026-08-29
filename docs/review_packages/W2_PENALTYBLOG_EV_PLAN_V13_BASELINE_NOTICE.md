# 基线告示 — 阅读 V1.3 计划书之前必读

文档状态：`FACT_NOTICE_NOT_A_PLAN_REVISION`
创建日期：2026-08-29
作者：Claude Code（独立复核）
适用对象：`W2_PENALTYBLOG_EV_OPTIMIZATION_PLAN_V1.md`（V1.3）

本文件不修改计划书内容，只记录一项在 V1.3 定稿后发现、且影响其全部「当前代码」断言的事实。

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

本告示不构成对 V1.3 方向的否定。分层设计、预注册、devig authority 前置、
baseline-before-challenger 的顺序均不受此影响。
