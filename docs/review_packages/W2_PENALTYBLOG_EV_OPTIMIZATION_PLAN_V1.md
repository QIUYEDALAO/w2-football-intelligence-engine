# W2 × Penaltyblog：EV、概率与模型验证优化计划 V1

文档状态：`PROPOSED_NOT_AUTHORIZED`

用途：供 Owner 与多 Agent 独立评审、补证和形成统一意见

创建日期：2026-08-29（Asia/Shanghai）

当前修订：V1.3（已吸收三轮 Claude Code 评审，并按当前代码与冻结证据修正）

实施状态：未开始

生产影响：无

> 本文不是实施授权、模型晋级决定、阈值变更批准或部署指令。任何代码修改、模型重训、生产写入、Provider 调用、候选准入或部署，都必须经过对应阶段的 Owner 授权。

## 1. Executive Summary

本计划解决三个必须分离的问题：

1. W2 的 EV 算术、盘口结算与报价绑定是否正确且全链一致；
2. W2 输入 EV 的概率是否可识别、可复现、校准有效；
3. Penaltyblog 能否作为独立 challenger 提供增量证据，而不是作为未经验证的替代模型。

当前最合理的结论是：

- W2 的亚洲盘五态 EV 公式已经存在，尚无证据证明核心算术错误；
- W2 存在多个 EV 实现入口，需要做语义、单位、盘口方向和数值等价审计；
- W2 的正式 simulation 并不调用 `models/dixon_coles.fit_dixon_coles()`，不能把该离线模型直接称为生产概率源；
- `models/calibration.py` 中的 PLATT、ISOTONIC、BETA 等名称与实现不符，但目前没有证据表明它进入正式 production simulation；
- `MIN_MARKET_ANCHOR_DIVERGENCE = 0.05` 确实参与 analysis candidate 判定，但其 W2 专属预测效力未被验证；
- 当前代码同时存在 PROPORTIONAL 计算、POWER 历史身份与“计算实为 PROPORTIONAL、来源却标 POWER”的 provenance 不一致；在方法 authority 和历史行可归因性闭合前，5% 政策回顾与 market-relative proper score 都不得评分；
- Penaltyblog 六模型在已完成的竞彩结算 1X2 研究中没有击败市场，Phase 3 为零 survivor；该结果否决“直接替换即可提升”，但不能直接外推到 W2 的 AH/OU 同时点可执行报价；
- 第一优先级应是只读的 EV/概率血缘审计和 W2 `BASELINE_PRIOR` 概率质量审计，而不是修改公式、删除安全门或接入六模型；
- 完整 Penaltyblog adapter 前先做一个冻结的 `MINIMAL_FROZEN_FEASIBILITY_PROBE`。预检仍必须有 fixture/cutoff/outcome parity 和不可变 artifact，不能用无身份的一次性脚本；
- 只有预检结论为 `PROCEED_TO_ADAPTER`，才建设隔离的 Poisson parity adapter；
- 本计划不包含生产晋级。任何生产准入必须另立决策包和 Owner 授权。

### 1.1 首轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| 完整 adapter 前增加 futility-first 预检 | `ACCEPT_WITH_CORRECTION` | 增加 Phase 4.5；但预检必须先冻结最小身份、PIT、配对和结果绑定合同。Penaltyblog 历史进球信息也不能表述为 W2 信息集的严格数学子集。 |
| Gate D 硬设 `N_settled >= 2500` | `REJECT_AS_HARD_GATE` | `2500/6900` 依赖未由 W2 验证的方差、EV 离散度和独立性假设。Phase 7 必须先做 W2 专属 power design，并分开 proper-score 与 EV calibration estimand。 |
| Gate 0 拆成本地静态与 VPS 只读 | `ACCEPT` | 拆为 Gate 0A/0B；0B 需 Owner 单独授权，但不需要 GitHub/GHCR，也不允许 Provider 调用、业务写入或部署。 |
| 先核验 5% 阈值两侧是否都有已结算样本 | `ACCEPT_WITH_CODE_CLARIFICATION` | 代码合同已保存 `NO_EDGE_CURRENT/current_delta/required_delta/shortfall`，设计上未天然丢弃阈值下方；生产实际两侧行数和结算覆盖仍须 Gate 0B 只读计数。 |
| 先验证 W2 当前 λ champion/baseline | `ACCEPT` | 新增 Phase 2.5，优先于 PB feasibility probe；不得把既有 Factor V2 candidate 证据冒充生产 `BASELINE_PRIOR` 已验证。 |

### 1.2 第二轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| Phase 2.5 增加 cohort burn ledger | `ACCEPT_WITH_CLASSIFICATION_GUARD` | 增加 `W2_COHORT_BURN_LEDGER.json`；逐项记录 fit/tune/select/evaluate/descriptive 用途和 outcome visibility，禁止把“曾查看”粗暴外推为对所有新问题永久不可用。 |
| `BASELINE_QUALITY_NOT_IDENTIFIABLE` 时闭合 Phase 4.5 分支 | `ACCEPT_AND_HARD_BLOCK` | W2-vs-PB 集成预检不得运行或晋级。market-only 可以另立预注册研究，但不能返回 `PROCEED_TO_ADAPTER`。 |
| Phase 4.5 加入 AH/OU 半盘子集 | `ACCEPT_WITH_DEVIG_CORRECTION` | 半盘结算确为二态，提升为产品市场 primary；但两边赔率并不唯一决定无水概率，必须冻结去水方法并标记 method-specific benchmark。1X2 仅作 secondary diagnostic。 |

### 1.3 第三轮 Claude Code 评审处置

| 建议 | 处置 | 修订结论 |
|---|---|---|
| 将 devig authority 提升为 Phase 4/7 显式前置 | `ACCEPT_WITH_CODE_CORRECTION` | 提升为跨阶段必要事实 `DEVIG_AUTHORITY_RESOLVED`。代码不只是 PROPORTIONAL/POWER 并存：`analysis_calculator.py` 实际做 PROPORTIONAL 归一，却标记来源为 POWER。因此必须分开计算算法、provenance 标签和持久化方法身份；不得仅凭字符串断言历史行真正使用 POWER。 |
| Gate 0B 增加历史 `devig_method` 非空覆盖率 | `ACCEPT_AND_FAIL_CLOSED` | 按 evidence source/release/schema/market/checkpoint 统计 null、单一方法和混合方法，并检查方法标签能否由当时代码身份证明。混合或大量 null 时，Phase 4 只能用可归因子集，否则 `RECORD_FIRST_EVALUATE_LATER`。 |

本轮复核锚点：

- `src/w2/strategy/calibration.py:6-22,35-132`：生产 calibration identity、默认权重和 clamp；
- `src/w2/strategy/simulate.py:128-163`：正式 simulation 调用 `calibrate_lambdas()` 后生成 score matrix；
- `src/w2/markets/value_engine.py:214-221`：五态 EV 公式；
- `src/w2/prematch/lifecycle.py:12-19,270-343`：5% 门、`NO_EDGE_CURRENT` 和两侧 delta/shortfall payload；
- `src/w2/prematch/repository.py:94-138`：dynamic evaluation append-only payload 持久化；
- `src/w2/domain/odds.py:10-21,45-107`：半盘不拆分且整数比分无法在半球线上 push，因此 AH/OU exact half-line 仅有 WIN/LOSS；
- `src/w2/markets/devig.py:9-114`：同一报价支持四种去水方法，证明 market-implied probability 依赖冻结的方法身份；
- `src/w2/markets/analysis_evidence.py:86-137,233-305`：同盘口双边身份检查、当前 PROPORTIONAL 去水及从 score matrix 派生 AH/OU settlement distribution；
- `src/w2/markets/score_baseline.py:202-218`：当前 score baseline 也显式使用 PROPORTIONAL；
- `src/w2/prematch/analysis_calculator.py:4812-4853,5695-5709`：实际按 implied probability 总和归一，与 PROPORTIONAL 等价，但 source 字符串写为 `POWER devig from matchday_market_observations`；
- `src/w2/settlement/settle.py:23-58` 与 `migrations/versions/0022_extend_recommendation_lock_snapshot.py:123-126`：`devig_method` 可持久化但为 nullable，因此必须核验实际覆盖率；
- local commit `22dc0dbe` 的 `V2_GATE1_CALIBRATION_RECOVERY_01/REPORT.md`：temperature `0.928709586`、NLL 小幅改善、各 ECE bin 变差、candidate-only；
- local commit `f0d201c5` 的 successor preregistration：Factor V2 one-look `5,500` 与 `2028-02-01T00:05:00Z` 的专属身份；
- `/Users/liudehua/.hermes/workspace/penalty-football-research/src/penalty_research/validation_design.py:22-29`：boundary score 是 1X2 log-pool 在 `w=0` 的导数，不能绕过概率/结果配对合同或扩展为 AH/OU 五态结论。

## 2. 当前事实基线

### 2.1 权威与版本边界

本计划编写时观察到三套不同时间点事实：

- 当前本地 checkout：`11c26e1ed00750b6d9ee7cb839e77900f3e44bc1`，且存在用户所有的未跟踪文件；
- `origin/context/current`：内容更新时间为 2026-08-14，明确要求先核对 exact runtime identity；
- W2 Vault `当前状态.md`：最后核验为 2026-08-28，记录生产 POINT-EV release 为 `ea557bb8ff64e06add91bbe32814fe073ec64642`。

本轮没有连接 VPS，因此不能把任何一套本地文件直接称为当前生产 exact source。纯静态工作先完成 Gate 0A；所有 production-exact 声明和生产 cohort 计数必须完成 Gate 0B。

### 2.2 W2 已确认的 EV 事实

W2 对 AH/可走盘 OU 使用五态结算：

```text
EV =
P(WIN)      × (decimal_odds - 1)
+ P(HALF_WIN) × 0.5 × (decimal_odds - 1)
- P(HALF_LOSS) × 0.5
- P(LOSS)
```

当前可见实现包括：

- `src/w2/markets/value_engine.py::expected_value`
- `src/w2/strategy/simulate.py::ah_expected_value`
- `src/w2/matchday/cards.py::_expected_value`
- `src/w2/analysis/market_movement.py::_distribution_expected_value`（转调 canonical candidate）
- `src/w2/markets/analysis_evidence.py`（转调 `value_engine.expected_value`）

`p × odds - 1` 只适用于无走盘/半赢/半输的二态投注，不能作为 W2 全市场通用 EV 定义。

### 2.3 W2 当前概率主链

当前可见正式 simulation 路径为：

```text
point-in-time W2 inputs
  -> strategy.calibration.calibrate_lambdas()
  -> lambda_home / lambda_away / uncertainty
  -> exact score matrix with optional DC tau correction
  -> AH / OU five-state settlement distribution
  -> executable quote
  -> EV / EV-SE / readiness gates
```

`src/w2/models/dixon_coles.py::fit_dixon_coles()` 当前只在 backtest/测试路径被直接调用。正式 simulation 仅复用其中的 `tau_correction()`。

当前生产主链的 λ 校准身份明确写为：

```text
CALIBRATION_VERSION = w2.formal.lambda_baseline_prior.v1
CALIBRATION_STATUS = BASELINE_PRIOR
```

源码默认参数包括主场优势 `0.12`、Elo 权重 `0.28`、身价 log 权重 `0.18`、首发权重 `0.08`、单边 λ 边界 `0.15–4.25`、总进球边界 `1.35–4.40`。当前搜索到的是行为/边界测试和若干离线 challenger 证据，不能据此声称这组生产默认参数已经由历史拟合或前瞻验证。

### 2.4 两项代码卫生问题

1. `models/dixon_coles.fit_dixon_coles()` 实际是收缩场均进失球加 rho 网格搜索，不是标准的联合 MLE Dixon-Coles；
2. `models/calibration.py` 的 PLATT、ISOTONIC、BETA、DIRICHLET_MULTICLASS 实际为不同常数的 power-strength heuristic，不是对应标准算法。

这两项需要修复命名与边界，但在完成调用血缘审计前，不得称为生产 EV 根因。

### 2.5 Market divergence 与正式推荐边界

`src/w2/markets/analysis_evidence.py` 当前要求：

```text
current_ev > 0
probability_delta >= 0.05
current_ev - ev_se > 0
```

才允许 `analysis_direction_allowed=true`。

正式 AH 生成路径另有：

```text
EV >= 0.035
EV >= 0.035 + EV_SE
EV <= 0.15
exact executable quote
model uncertainty ready
direction/readiness gates
capability gate
```

当前仓库 capability manifest 中 `formal_ah`、`production_recommendation` 均未启用。Vault 记录 POINT-EV 权威上线后未验证概率均被 fail closed，但必须由 Gate 0B 重新核验线上 exact state。

### 2.6 Penaltyblog 已有证据

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
- Penaltyblog 的历史进球训练信息与 W2 的 PIT xG/Elo/身价/首发信息并非已证明的严格集合包含关系：两者的训练样本、可见时点、覆盖、特征语义和参数身份均不同。

## 3. 已排除的错误方向

本计划明确不执行：

- 不把 `p × odds - 1` 强行用于 AH 或可走盘 OU；
- 不因当前 EV 表现不佳而修改五态公式；
- 不删除 `expected_value > 0` 的 payload 合法性检查；
- 不把 5% divergence 直接定性为已证明的“反向筛选器”；
- 不使用旧报告中的小样本盈亏、命中率或 point EV 选择模型、校准参数、阈值或 EV-SE 系数；当前生产 settled N 必须经 Gate 0B 重新计数，不能把旧 `65` 当成当前事实；
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
4. 评估 5% market-anchor divergence 的真实角色与证据边界；
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
  -> production-exact claims, Phase 4 cohort counts, and devig attribution coverage

Phase 1 accepted and no devig conflict
  -> optional Phase 3 EV Contract Convergence

DEVIG_AUTHORITY_CONFLICT
  -> Phase 3 devig contract resolution is required before Phase 4/4.5/7

Gate 0B + Phase 1 + Phase 2 accepted
and DEVIG_AUTHORITY_RESOLVED
  -> Phase 4 Market-Anchor Preregistration

Phase 2.5 = BASELINE_QUALITY_IDENTIFIED
and W2_COHORT_BURN_LEDGER has an eligible development cohort
and DEVIG_AUTHORITY_RESOLVED
  -> Phase 4.5 Minimal Frozen PB Feasibility Probe

Phase 2.5 = BASELINE_QUALITY_NOT_IDENTIFIABLE
or cohort classification = UNKNOWN_BLOCKED
  -> BLOCK_PB_VS_W2_FEASIBILITY

Phase 4.5 = PROCEED_TO_ADAPTER
  -> Phase 5 PB Adapter Preregistration
  -> Phase 6 Engineering Parity
  -> Phase 7 Paired Evaluation only while DEVIG_AUTHORITY_RESOLVED remains true

Phase 7 passes a frozen gate
  -> separate Owner request for Phase 8
```

Gate 0A 完成后可以继续纯静态审计；任何“当前生产 exact state/row count”声明必须等待 Gate 0B。Phase 1 与 Phase 2 可以由不同 Agent 独立审查，但不得在 Gate 0B 前假定生产 identity。Phase 3 与 Phase 4 不得并行修改同一 EV/threshold 路径。Phase 4.5–7 必须串行，以保证预检、合同、实现和结果的时间顺序。

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

状态：`READ_ONLY_CAN_START_AFTER_OWNER_AUTHORIZATION`

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

状态：`SEPARATE_OWNER_AUTHORIZATION_REQUIRED`

目标：在不访问 GitHub/GHCR、不调用 Provider、不写业务数据、不部署的前提下，核验当前生产 exact runtime 与可评价 cohort 计数。

只读任务：

1. 核对 API/worker/scheduler/Web release 和 OCI revision；
2. 核对 Alembic head 与 capability 实际开关；
3. 核对 POINT-EV 当前 production identity；
4. 只读计数 dynamic evaluation 中 `delta < 0.05`、`delta >= 0.05`、各自有权威结算结果的行数及 fixture 去重数；
5. 只读计数当前 official/shadow settled rows，并按 schema/model/calibration identity 分层；
6. 对可能用于 Phase 4/7 的历史 evaluation/lock/settlement 行计数 `devig_method` 非空覆盖率、未知率和方法分布，至少按 evidence source、release/schema、market、checkpoint 和 model/calibration identity 分层；
7. 区分“持久化字符串”与“可由当时代码复算的实际算法”，计数 declared/computed mismatch；当历史 release source 不可证明时标 `METHOD_NOT_ATTRIBUTABLE`，不得根据当前代码反推；
8. 保存查询文本、时间、结果 hash 和零写入证据。

输出：

```text
PRODUCTION_AUTHORITY_SNAPSHOT.json
PRODUCTION_EVALUABILITY_COUNTS.json
PRODUCTION_DEVIG_ATTRIBUTION_COUNTS.json
PRODUCTION_AUTHORITY_RECONCILIATION.md
```

验收：

- Python/Web/worker/scheduler identity 明确；
- schema 与 capability 明确；
- 两侧阈值样本与结算覆盖可复算；
- `devig_method` 非空/未知/混合覆盖可复算，且 declared method 与 computed algorithm 的可归因性明确；
- GitHub/GHCR 访问 0；
- Provider 调用 0；
- 业务写入 0；
- 部署 0。

STOP 条件：任何组件 identity 无法确定时，只允许继续静态审计；任何依赖生产 exact state、settled N 或 cohort coverage 的结论必须标 `NOT_VERIFIED_CURRENT_PRODUCTION`。

### Phase 1 — EV Contract & Call-Graph Audit

状态：`READ_ONLY_FIRST`

目标：回答“W2 到底有几种 EV、每种使用什么分布和什么报价”。

审计范围：

- 所有 `expected_value`、`risk_adjusted_ev`、`probability_edge`、`fair_odds`、`implied_probability`；
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

状态：`HIGHEST_PRIORITY_STATISTICAL_AUDIT_AFTER_PHASE_1_AND_PHASE_2`

目标：先回答 W2 当前 `BASELINE_PRIOR` 自身的概率质量和证据边界，再评价外部 challenger。

已知起点：

- `strategy.calibration.CALIBRATION_STATUS = BASELINE_PRIOR`；
- 默认 λ 参数直接存在于 `LambdaCalibrationParams`；
- 既有 Understat/历史回测证明过其他离线 fitted candidate 的局部表现；
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

### Phase 3 — EV Contract Convergence

状态：`REQUIRES_PHASE_1_PHASE_2_ACCEPTANCE_AND_OWNER_AUTHORIZATION`

目标：只在审计证明重复实现或 devig identity 存在漂移风险时，做最小收敛。本阶段未获 Owner 授权前不得开始修复。

候选改动顺序：

1. 优先复用 `markets.value_engine.expected_value`；
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
  this is a new market-probability identity and can change the 5pp candidate set
  requires separate preregistration, compatibility plan, Owner authorization,
  and prospective-only activation; it cannot masquerade as a naming fix
```

禁止根据哪个 devig 方法让历史 5pp 通过率、LogLoss、EV 或推荐更好而选择方法。禁止回写、猜测或清洗无法归因的历史 `devig_method`。

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

### Phase 4 — Market-Anchor 5% Policy Evaluation

状态：`PREREGISTRATION_REQUIRED`

目标：判断 5% divergence 是有证据的稳定性门、无效门，还是单位/语义混用。

先做 evaluability check：

- 当前代码会把低于 5% 的完整 evaluation 保存为 `NO_EDGE_CURRENT`；payload 同时保留 `current_delta`、`required_delta` 与 `shortfall`，因此 schema/代码设计并未天然形成“只保存通过门槛者”的幸存者集合；
- 但代码能力不等于生产样本充足。必须使用 Gate 0B 的只读计数，确认 `delta < 0.05` 与 `delta >= 0.05` 两侧都有足够、同身份、可绑定权威结果的行；
- 必须按 fixture 去重，并分开 current/superseded、official/shadow、market、checkpoint、model/calibration identity；
- 必须使用 Gate 0B 的 `PRODUCTION_DEVIG_ATTRIBUTION_COUNTS.json` 确认每条候选历史行的 computed algorithm、declared label 和 persisted `devig_method` 能够归因；
- Phase 4 primary cohort 必须对方法身份 100% 可归因且在预先声明的同质方法子集上评价。混合方法只能分层报告，禁止 pooled 5pp 结论；null、标签/计算冲突或无法重建历史算法的行必须进 failure ledger，不得静默丢失；
- 如果任一侧不足或结果绑定不足，结论为 `RECORD_FIRST_EVALUATE_LATER`，不得只评价 selected/recommended rows。

#### Devig authority 硬前置

当前代码事实不能简化为“两条路径真正分别在跑 PROPORTIONAL 与 POWER”：

- `analysis_evidence.py` 和 `score_baseline.py` 显式调用 PROPORTIONAL；
- `analysis_calculator.py::_market_probabilities_from_observations()` 实际也是 reciprocal-odds normalization，数学上等价于 PROPORTIONAL；
- 同一 `analysis_calculator.py` 对这个结果的 source 标签却写为 POWER；
- 历史测试、artifact 与 nullable `devig_method` 字段中仍存在 POWER 身份。

因此当前状态是 `DEVIG_AUTHORITY_CONFLICT`，并包含已证明的 provenance 假标与待 Gate 0B 核验的历史方法混用两个问题。只有当下列条件全部成立时，才可改为 `DEVIG_AUTHORITY_RESOLVED`：

```text
canonical computed algorithm identified
declared label matches computed algorithm
persisted method/version/overround contract defined
historical primary cohort method attribution = 100%
mixed-method rows are not pooled
unknown/mismatch rows persist with explicit reason
```

使用 W2 当前 `devig.py` 对合成报价的确定性敏感性复算显示：

| 市场形状 | 报价 | max \|PROPORTIONAL - POWER\| | 占 5pp 门 |
|---|---:|---:|---:|
| 1X2 均势 | 2.60 / 3.30 / 2.75 | 0.207pp | 4.1% |
| 1X2 强客 | 6.00 / 4.30 / 1.55 | 1.351pp | 27.0% |
| 1X2 强主 | 1.50 / 4.20 / 6.50 | 1.879pp | 37.6% |
| 1X2 大热 | 1.25 / 6.00 / 11.0 | 2.788pp | 55.8% |
| 双边常见均衡 | 1.91 / 1.97 | 0.036pp | 0.7% |
| 双边中度偏离 | 1.70 / 2.20 | 0.413pp | 8.3% |
| 双边强偏离 | 1.50 / 2.70 | 0.797pp | 15.9% |
| 双边极端偏离 | 1.25 / 4.00 | 2.045pp | 40.9% |

这些是算法敏感性样例，不是 W2 生产报价分布或历史门槛效果的估计。1X2 的 55.8% 不得外推成 AH/OU 生产影响；双边例子也只证明极端报价下方法差可与 5pp 门同尺度。Penaltyblog 项目的 `0.0025 nats` MME 只能作跨项目尺度参照，不是 W2 的 MME 或 Gate。

在查看新结果前必须冻结：

- evaluation universe；
- fixture、quote 和 cutoff 规则；
- AH/OU 分开评价；
- primary metric；
- MME/non-inferiority margin；
- league/time-block stability；
- failure/coverage Gate；
- futility rule；
- threshold 本身不允许根据结果移动。

评价必须覆盖全部 official evaluation opportunities，而不是只看被选中的推荐，避免 selection bias。

至少并列记录：

```text
model_market_probability_delta
five_state_EV
EV_SE
EV_minus_SE
realized_settlement_return
quote_age
bookmaker_depth
model/calibration identity
```

重要识别边界：

- exact half-line（`line × 2` 为奇整数）上的 AH/OU 最终结算只有 WIN/LOSS；在同 bookmaker、同 captured_at/checkpoint、同盘口双边完整且去水方法已冻结时，可以建立 method-specific 二元 market benchmark；
- 即使是半盘，两边赔率也不能脱离去水假设唯一识别 latent market probability；W2 的四种去水方法会产生不同概率，必须保存 method/version/overround；
- 整数盘含 PUSH，四分盘可含 HALF_WIN/HALF_LOSS；两边赔率通常不能唯一识别其三态/五态概率分布；
- 如果 integer/quarter line 的 market settlement distribution 无法由证据唯一确定，必须报告 `MARKET_THREE_OR_FIVE_STATE_NOT_IDENTIFIABLE`；兼容旧报告时可同时保留 `MARKET_FIVE_STATE_NOT_IDENTIFIABLE` note；
- 禁止凭一个 scalar effective probability 伪造 market 五态 LogLoss；
- 可以报告模型 settlement-state Brier/RPS/NLL、EV calibration 与 realized unit return；
- 半盘可以对 actual WIN/LOSS 做模型 proper score，并与冻结 devig 方法的 market benchmark 比较；不得把方法特定 benchmark 写成唯一真实市场概率；
- 其他盘口只有在完整 market state distribution 有独立证据时，才做严格 model-vs-market proper-score 比较。

可能结论只允许：

```text
KEEP_5PP_POLICY
REVISE_POLICY_WITH_NEW_PREREGISTRATION
REMOVE_POLICY_WITH_EVIDENCE
NOT_IDENTIFIABLE
RECORD_FIRST_EVALUATE_LATER
```

当 `DEVIG_AUTHORITY_RESOLVED` 不成立，或没有方法身份 100% 可归因且两侧门槛均可评价的同质子集时，Phase 4 只能返回 `NOT_IDENTIFIABLE` 或 `RECORD_FIRST_EVALUATE_LATER`。

本阶段只出决策包，不直接改阈值。

### Phase 4.5 — Minimal Frozen PB Feasibility Probe

状态：`REQUIRES_BASELINE_QUALITY_IDENTIFIED_AND_ELIGIBLE_COHORT`

目标：在建设完整 adapter、迁移或长期 ledger 前，以最小成本判断 Penaltyblog 独立 Poisson 在 W2 实际产品市场上是否提供可评分的增量证据。

依赖闭合：

- `W2_BASELINE_PROBABILITY_QUALITY_AUDIT` 必须给出可评分的 W2 baseline identity、预测与结果绑定；
- `W2_COHORT_BURN_LEDGER.json` 必须存在明确允许作本问题 development probe 的 cohort；
- 如果 Phase 2.5 为 `BASELINE_QUALITY_NOT_IDENTIFIABLE`，本阶段返回 `BLOCK_PB_VS_W2_FEASIBILITY`，不得改用 market-only 结果批准 adapter；
- market-only 研究如有价值，必须另立问题、协议和授权，其结论不能是 `PROCEED_TO_ADAPTER`。

这不是无合同的一次性脚本。查看任何 probe 指标前，必须冻结：

```text
development cohort and permitted outcome visibility
canonical fixture IDs and digest
prediction cutoff and source-row eligibility
W2 baseline probability identity
Penaltyblog version/model/config identity
actual outcome binding rule
primary estimand and sign convention
boundary/futility rule
coverage and failure rule
product-market primary hierarchy
devig method and method identity
seed/bootstrap or uncertainty method
```

最小实现边界：

- 优先复用已冻结的 Factor V2 PIT dataset、fixture identity 和 score-matrix helper，但必须生成本预检自己的 manifest/hash；历史 artifact 只读且不得改写；
- 只做 `INDEPENDENT_POISSON_FEASIBILITY_ONLY`；
- 只使用明确允许的 development cohort；旧 Factor V2 VALIDATION/HOLDOUT、已关闭的 confirmatory cohort 和任何目标比赛赛后信息不得参与 fit/config 选择；
- `training_date < prediction_cutoff`，目标 fixture 不进入自身训练；
- 每个候选 fixture 必须证明 fixture、cutoff、training rows 和 actual outcome parity；
- 失败 fixture 保留 reason，silent loss 为 0；
- 产生一个 immutable analysis artifact 和 execution receipt；
- 不建 migration、production ledger、worker、UI 或 runtime dependency；
- 不把 Penaltyblog 的信息集称为 W2 的严格子集；
- Penaltyblog 使用历史进球，W2 使用 PIT xG/Elo/身价/首发；“进球减 xG 的残差可能携带终结效率信息”只作为待检验机制，不得在结果前写成已证明增量；
- 1X2 只能作为 secondary diagnostic；1X2 单独为正不得返回 `PROCEED_TO_ADAPTER`。

#### Phase 4.5 产品市场 primary

产品市场 primary 必须来自 exact half-line binary subset：

```text
AH: home/away exact lines at n + 0.5, opposite-side line identity exact
OU: over/under exact line at n + 0.5, same-line identity exact
settlement outcomes: WIN / LOSS only
```

在不查看 outcome metric 的 coverage-only preflight 后，预注册文件必须冻结：

- `AH_HALF_LINE`、`OU_HALF_LINE` 或二者的预先定义 hierarchical/co-primary 角色；
- 同 bookmaker、同 capture/checkpoint、同 fixture、互补 selection、精确 line 的 quote pair；
- W2/PB 从各自 score matrix 派生的同 selection 二元 WIN/LOSS 概率；
- fixture 内多 market/checkpoint 的相关性和去重/cluster 规则；
- primary proper-score paired difference：`W2 LogLoss - PB LogLoss`；
- primary incremental diagnostic：在 `w=0` 向 W2 log pool 加入 PB 的二元 boundary score；
- model-vs-market 指标的冻结去水方法与 provenance。

半盘的结果空间是二态，因此 W2-vs-PB 可以做严格 paired LogLoss/Brier。两边赔率仍包含 overround，且 W2 支持 `PROPORTIONAL/SHIN/POWER/LOGARITHMIC` 多种去水；因此 model-vs-market 只能报告：

```text
METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK
```

不得称为唯一 latent market probability。Primary devig method 必须在 outcome metric 前冻结；其他预声明方法只能做 sensitivity，不得事后挑选。`PB_TO_W2_BOUNDARY_SCORE` 不需要 market benchmark，但必须使用相同 fixture IDs、W2/PB 二元概率和合法 outcome binding；任何 `MODEL_TO_MARKET_BOUNDARY_SCORE` 则必须绑定冻结 devig method。如果 Gate 0A/Phase 2 发现 PROPORTIONAL/POWER 等 authority 冲突，market benchmark 标 `DEVIG_AUTHORITY_CONFLICT` 并失去晋级权，不能事后挑方法。

输出：

```text
PB_MINIMAL_FEASIBILITY_PREREGISTRATION.md
PB_MINIMAL_FEASIBILITY_MANIFEST.json
PB_MINIMAL_FEASIBILITY_RESULT.json
PB_MINIMAL_FEASIBILITY_EXECUTION_RECEIPT.md
```

结果只允许：

```text
PROCEED_TO_ADAPTER
STOP_PB_INTEGRATION_RESEARCH
NOT_IDENTIFIABLE
BLOCK_PB_VS_W2_FEASIBILITY
```

`PROCEED_TO_ADAPTER` 必须由预注册的 half-line product-market primary 触发；1X2 secondary、未冻结 devig 方法或 market-only 结果均无晋级权。

`STOP_PB_INTEGRATION_RESEARCH` 只停止 Penaltyblog challenger 集成，不否定 Phase 1–4 的 W2 EV/baseline 治理改进。

### Phase 5 — PB Adapter Preregistration & Contract

状态：`OWNER_AUTHORIZATION_REQUIRED_AND_PHASE_4_5_PROCEED_ONLY`

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

目标：在 W2 自己的时间点、市场和报价语境中评价 challenger。

硬前置：`DEVIG_AUTHORITY_RESOLVED`。Phase 7 不得与 devig authority 调查并行；computed algorithm、declared label、persisted method/version/overround 或历史 cohort attribution 任一未闭合，market-relative proper score 必须停止。不得用“在结果中分层解释”替代事前冻结。

执行前必须先冻结 W2 专属 power design，并至少分成两个不同 estimand：

1. 同 fixture 的 proper-score paired difference（例如 1X2 LogLoss delta）；
2. `realized_return ~ predicted_EV` 的 calibration intercept/slope 或其他事先批准的 EV calibration estimand。

两者不得共享一个拍脑袋样本门槛。功效设计必须用 W2 可用 development data 估计 paired/clustered variance，处理同 matchday、联赛、重复 checkpoint/fixture 的相关性，并先批准 MME、alpha、power、look rule 与 attrition。Claude 评审提出的 `N≈2500/6900` 仅是基于 `sigma_return≈1`、`sigma_EV≈0.04` 和独立观测的未验证敏感性示例，不是 Gate。Factor V2 已冻结的 `N=5500` 也只服务其原始 successor 对照，不得搬用。

如果 Gate 0B 核验后的当前 settled N、覆盖或可达 MDE 不满足冻结设计，结论必须为 `INSUFFICIENT_POWER_DO_NOT_SCORE`。不得以当前小样本先看结果、再移动 MME、primary metric 或阈值。

每个模型使用自己的 paired set：

```text
EVAL_M =
W2 opportunity eligible
∩ actual outcome valid
∩ exact quote identity valid
∩ model M prediction valid
```

必须分别报告：

```text
N
coverage
failure_rate
fixture-set digest
league/time-block coverage
```

1X2 与 exact half-line binary 集合：

```text
W2 LogLoss / Brier
PB LogLoss / Brier
W2-minus-PB paired DeltaLogLoss
PB-to-W2 boundary score at w=0
Method-specific devig Market LogLoss / Brier
RPS
ECE
devig method/version/overround
```

exact half-line 必须单独报告 AH/OU、intersection N、quote-pair identity 和 fixture-clustered uncertainty。市场对照必须使用预冻结 devig method；不同 devig sensitivity 不得改变 primary decision。

AH/OU：

```text
five-state NLL/Brier/RPS
settlement calibration by outcome
predicted EV vs realized unit return calibration
EV calibration intercept/slope with uncertainty
coverage and failure rate
```

对于无法识别 market 三态/五态概率的整数盘或四分盘，禁止伪造 market LogLoss；只报告可识别指标和限制。

模型间冗余只在两模型交集上评价：

```text
intersection N
corr(lambda_home/lambda_away)
corr relevant probabilities
mean absolute probability difference
decision-direction agreement
```

禁止使用所有模型共同成功集作为唯一评价集合。

### Phase 8 — Prospective Shadow

状态：`NOT_AUTHORIZED_BY_THIS_PLAN`

只有 Phase 7 通过预注册 Gate 后才可单独申请。

要求：

- 独立 shadow registry/ledger；
- cohort start 在首条 row 前冻结；
- W2 与 PB 同 opportunity、同 quote、同 cutoff；
- 不写现有 official evaluation/opportunity/outbox；
- 不影响 Dashboard 正式状态；
- 不产生 BET/SKIP 或通知；
- append-only；
- outcome 只在结算后绑定；
- 不根据早期盈亏改阈值或模型。

Phase 8 结束后只形成 Owner decision packet，不自动生产晋级。

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

- five-state formula golden vectors；
- quarter-line split；
- integer push；
- side symmetry；
- odds monotonicity；
- distribution normalization；
- invalid/stale/reference quote fail closed；
- Decimal/float tolerance；
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
- 1X2 secondary cannot promote to `PROCEED_TO_ADAPTER` test；
- `DEVIG_AUTHORITY_CONFLICT` fail-closed test；
- computed devig algorithm versus declared provenance parity test；
- nullable/mixed `devig_method` coverage and row-conservation test；
- unattributable historical method persistence test；
- deterministic probe result/hash；
- probe no-migration/no-runtime/no-ledger-write guard。

### 9.3 Evaluation 测试

- Model/Market fixture parity；
- per-model EVAL set equality；
- pairwise intersection；
- no silent row loss；
- metric sign convention；
- settlement-result binding；
- selected-only bias guard；
- market-five-state identifiability guard；
- method-specific devig benchmark naming guard；
- mixed-method pooling forbidden test；
- Phase 4/7 `DEVIG_AUTHORITY_RESOLVED` prerequisite test；
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

PASS：冻结的 exact half-line product-market primary 返回 `PROCEED_TO_ADAPTER`，且 fixture/cutoff/training-row/outcome/quote-pair mismatch 与 silent loss 均为 0；devig 方法身份已在赛果指标之前冻结，且不存在 `DEVIG_AUTHORITY_CONFLICT`。

STOP：`STOP_PB_INTEGRATION_RESEARCH` 时不建设 Phase 5–8。

NOT IDENTIFIABLE：先补合同/合法 cohort，禁止凭不完整结果继续 adapter。`BASELINE_QUALITY_NOT_IDENTIFIABLE`、`UNKNOWN_BLOCKED` cohort、未冻结 devig 或 `DEVIG_AUTHORITY_CONFLICT` 均属阻断态。

1X2 只是 secondary diagnostic；即使单独为正，也不得触发 `PROCEED_TO_ADAPTER`。Market-only 研究不得触发本 Gate PASS。

### Gate C — Adapter Parity

PASS：零 silent loss、零 identity mismatch、确定性重现。

FAIL：任何结果都不用于模型判断。

### Gate D — Retrospective Paired Evaluation

入口前必须再次证明 `DEVIG_AUTHORITY_RESOLVED`；该状态不得仅由当前配置文件声明，必须覆盖 primary cohort 的方法归因。任何 null、mixed pooled、label/algorithm mismatch 或事后选取 sensitivity method 均使 market-relative 结果无晋级权。

数值 Gate 必须在执行前通过 W2 专属 power design 冻结。proper-score paired difference 与 EV calibration 的 power、MME 和相关结构分别设计；不得硬编码 Claude 的 `2500/6900`，也不得复用 Factor V2 的 `5500`。结果只允许：

```text
CONTINUE_TO_PROSPECTIVE_SHADOW
REVISE_ADAPTER_OR_PROTOCOL
STOP_PB_INTEGRATION_RESEARCH
INSUFFICIENT_POWER_DO_NOT_SCORE
```

### Gate E — Prospective Shadow

不在本计划授权范围内。即使 PASS，也只能提交 Owner production-admission decision packet。

## 11. 风险登记

| 风险 | 后果 | 控制 |
|---|---|---|
| 把竞彩 settlement SP 当 entry/closing | 虚假 EV/CLV | 市场命名和 quote_usage 硬约束 |
| 从 1X2 外推 AH/OU | 错误策略结论 | 分市场预注册，禁止直接外推 |
| 只评价被推荐比赛 | selection bias | 评价全部 official opportunities |
| 用旧小样本或未核验的当前 N 调参数 | outcome-driven overfit | Gate 0B 重计数；新冻结 cohort；不足则不评分 |
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
| PROPORTIONAL/POWER 等 devig 权威冲突 | 事后选取有利的 market benchmark | Phase 1/2 核实 authority；方法未冻结或冲突时 `DEVIG_AUTHORITY_CONFLICT` fail closed |
| 只信 `POWER` source 字符串而不核对实际计算 | 把 PROPORTIONAL 历史行错分为 POWER | computed/declared/persisted 三身份分开审计；不可重建时 `METHOD_NOT_ATTRIBUTABLE` |
| 混合或 nullable `devig_method` 行直接 pooled 评价 5pp | 阈值效果与方法变更混杂 | Gate 0B 覆盖率计数；只评价 100% 可归因同质子集，否则先记录后评价 |
| 用 1X2 结果外推 AH/OU 产品市场 | 预检通过但产品 estimand 未被验证 | exact half-line AH/OU 为 primary；1X2 只作 secondary，无单独晋级权 |
| 把 method-specific devig benchmark 称为真实 market probability | 过度声明可识别性 | 强制名称 `METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK`，持久化 method/version/overround |
| calibration 名称误导 | 假安全感 | 调用审计、重命名/隔离决策包 |
| threshold 事后移动 | 研究失效 | preregistration hash |
| 新依赖进入生产 runtime | 运维和供应链风险 | 初期 artifact boundary |
| Vault 混用 | 状态污染 | W2/Penaltyblog 独立 Vault |

## 12. 交付物清单

### 本计划已交付

- `W2_PENALTYBLOG_EV_OPTIMIZATION_PLAN_V1.md`

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
PB_MINIMAL_FEASIBILITY_PREREGISTRATION.md
PB_MINIMAL_FEASIBILITY_MANIFEST.json
PB_MINIMAL_FEASIBILITY_RESULT.json
PB_MINIMAL_FEASIBILITY_EXECUTION_RECEIPT.md
PB_ADAPTER_PREREGISTRATION.md
PB_ADAPTER_CONTRACT.json
PB_ADAPTER_FAILURE_TAXONOMY.json
PB_PARITY_EXECUTION_RECEIPT.md
W2_PB_PAIRED_EVALUATION_RECEIPT.md
W2_PB_PRODUCTION_ADMISSION_DECISION_PACKET.md
```

文件名只是建议；未授权阶段不得提前生成“PASS”或“IMPLEMENTED”状态文件。

## 13. 多 Agent 评审问题

请每个 Agent 独立回答，并引用具体文件、函数、测试或证据：

1. 当前 exact production probability path 是什么？是否遗漏任何实际 writer/read path？
2. W2 是否存在数学上不等价的 EV 实现？请提供固定向量复算。
3. `effective_settlement_probability` 的当前使用是否存在语义误用？
4. `MIN_MARKET_ANCHOR_DIVERGENCE` 在不同模块中的单位和角色是否一致？
5. 5% threshold 的既有证据是什么？若无，最小可识别实验是什么？
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
18. exact half-line 的 quote-pair authority 和 primary devig authority 分别是什么？`analysis_evidence.py`/`formal_recommendation.py` 的 PROPORTIONAL 与历史 POWER 要求是否冲突？
19. 哪些报告或 API 可能把 `METHOD_SPECIFIC_DEVIG_MARKET_BENCHMARK` 误表述为唯一真实 market probability？最小命名与 provenance 修复是什么？
20. `analysis_calculator.py` 的 computed PROPORTIONAL 与 declared POWER 冲突影响了哪些历史行？哪些 release 可以从 exact source 归因，哪些必须标 `METHOD_NOT_ATTRIBUTABLE`？
21. 你的最终建议是：

```text
ACCEPT_PLAN
ACCEPT_WITH_REVISIONS
REJECT_PLAN
```

## 14. 建议的 Agent 回复格式

```markdown
# Review: W2 × Penaltyblog EV Optimization Plan V1

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

在收集多 Agent 意见后，Owner 先分别裁定两个权限边界：

```text
1. 是否授权 Gate 0A + Phase 1 + Phase 2 + Phase 2.5 的本地只读静态审计？
2. 是否单独授权 Gate 0B 的 VPS 只读核验？
```

Gate 0B 不需要 GitHub/GHCR 权限，且必须保持 Provider 调用 0、业务写入 0、部署 0。上述审计不改变模型、阈值、生产数据或运行状态。Phase 4.5 需要另行授权；只有其返回 `PROCEED_TO_ADAPTER`，才讨论 Phase 5–7。

## 16. 最终建议

```text
NEXT_ACTION = MULTI_AGENT_REVIEW
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
