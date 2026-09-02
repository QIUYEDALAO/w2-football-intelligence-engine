# DISTRIBUTION_SHAPE_01

状态：`PREREGISTRATION_DRAFT_NOT_ARMED`

本文件只冻结研究设计草案。未执行拟合、未读取时序留出集、未修改生产代码或模型参数；只有 Owner 明确批准并完成 arming freeze 后才可执行。

## 1. 研究动机与唯一问题

生产默认参数 `dixon_coles_rho = 0.0`。在 `rho = 0` 时，`tau_correction()` 对 `0-0 / 0-1 / 1-0 / 1-1` 均返回 `1.0`，其余比分格本来就返回 `1.0`；生产比分矩阵因此没有 Dixon-Coles 低分相关修正。生产默认 simulation 输入的 `lambda_sigma_home / lambda_sigma_away` 也为 `0.0` 时，比分矩阵退化为两个独立 Poisson 的外积。

已烧的 858 场盲测只作为提出新问题的诊断证据，不进入本研究拟合、选择或评分：

| 形状量 | 现役模型 | 实际 | 误差 |
|---|---:|---:|---:|
| 净胜球 = 0（平局） | 24.62% | 27.27% | 实际高 `2.65pp` |
| 总进球 <= 2.5 | 48.25% | 47.78% | 实际低 `0.47pp` |

该方向与同一盲测的 ECE 诊断（AH `0.1008`、TOTALS `0.0103`）一致：AH 更敏感的平局结算格存在更大的形状误差。此前四个 AH 候选族调整的是 lambda 均值劈分；它们把净胜球 slope 从约 `1.173` 调到约 `1.00`，但未形成样本外 proper-score 改善。

**唯一研究问题：在保持输入与均值模型可比的前提下，修正平局与低分相关结构后，AH proper score 是否获得稳定改善？**

本研究不回答盈利、跑赢市场、实时可执行价差或 TOTALS 模型升级问题。

## 2. 固定比较对象

只比较以下三个生成模型，不增加第四个或第五个模型族：

1. `ACTIVE_INDEPENDENT_POISSON`：现役独立 Poisson 外积，作为固定基线。
2. `DIXON_COLES_FITTED_RHO`：仅拟合低分相关参数 `rho` 的 Dixon-Coles 修正；不得同时借机改均值模型参数。
3. `BIVARIATE_POISSON_ONE_SHARED_COMPONENT`：以一个非负共享 Poisson 分量表达主客进球相关性的低维替代；自由形状参数仅为共享分量强度，边际均值须与基线对齐。

三者必须使用同一批赛前输入、同一 PIT 规则、同一 lambda 均值身份、同一比分截断与归一化规则。任何均值重拟合、额外联赛参数、额外 dispersion 参数或模型族替换都超出本预注册。

## 3. Cohort 与不可逆冻结顺序

候选池为本地 Football-Data 2023/24 season archive：

- 物理来源：`/Users/liudehua/.hermes/data/w2/football-data-co-uk/raw/season_zips/2324_data.zip`
- archive SHA-256：`f86ac89c3df57be812fc25d4d4aeca0ef98b910483e59560c0f7b406118e3c5a`
- archive 中已只读核实存在 `22` 个联赛 CSV。
- 派发合同给出的未烧候选池规模约 `6,222` 场；草案阶段不读取结果列或留出集，最终 admitted count 必须在 arming 时仅由结构/必需列规则冻结，不能在评分后回改。

该 cohort 不设最低场次门槛，也不等待新比赛。验证采用 cohort 内严格时序留出，必须按以下不可逆顺序执行：

1. 冻结 source archive hash、22 个 member 名单、解析版本、必需字段、排除原因、fixture identity 与逐场 PIT 输入规则。
2. 仅依据比赛时间排序冻结 `FIT` 与 `TEMPORAL_HOLDOUT` 的边界、fixture ID 清单和各自 SHA-256；不得依据比分、市场结算、模型输出或样本量调整边界。
3. 在任何拟合前提交 arming freeze；此时留出赛果与留出评分保持封存。
4. 只用 `FIT` 拟合两个候选形状参数，并冻结参数、实现 commit、预测生成器与预留评分命令。
5. 冻结三者对 `TEMPORAL_HOLDOUT` 的赛前概率后，才允许一次性打开留出赛果并评分。

已烧的 `8,659 / 858 / 354 / 133` cohort 均不得参与上述任何一步，也不得用来挑参数、挑切分或补充功效。

## 4. Primary estimand 与稳定性

Primary estimand 为相同 fixture、相同 AH 结算线下，候选相对 `ACTIVE_INDEPENDENT_POISSON` 的 paired AH proper-score 差：

- primary：五态 AH settlement Brier difference（candidate minus baseline；负数更好）；
- key secondary：同一五态分布的 log-loss difference；
- diagnostics：平局概率偏差、四个低分格概率质量、按时间块与联赛的 paired 差异。

“稳定改善”须同时满足：

- temporal holdout pooled primary 点估计小于 `0`；
- fixture-cluster bootstrap 的 one-sided 95% upper bound `<= 0`；
- 预冻结时间块中不得出现方向相反且足以推翻 pooled 解释的系统性退化；
- log-loss secondary 不得显示明确退化。

两个候选分别相对同一基线裁决；不得在看过 holdout 后更换 bootstrap、时间块、权重、比分截断或 primary score identity。若 arming 前无法冻结上述实现细节，状态保持 `NOT_ARMED`。

## 5. 可移植性与声明边界

22 个联赛中多数不是 W2 当前生产联赛。该 cohort 能检验相关计数结构是否跨联赛具备形状改善，但不能直接证明生产联赛、实时赔率或 W2 当前候选链上的收益。这是外部可移植性限制，不是本研究的阻塞条件。

无论结果如何，本研究都不得声明跑赢市场、盈利、生产有效、可部署，或据此修改 `CALIBRATION_VERSION`、`dixon_coles_rho`、lambda 参数、ledger/白名单。任何生产接入都需要新的身份、独立验收和 Owner 授权。

## 6. 预注册裁决与停止规则

- 两个候选都未满足 primary 稳定改善：`REJECT_AND_CLOSE_DISTRIBUTION_GENERATOR_ROUTE`。
- 只有一个候选满足：仅记录该候选为后续独立生产可行性评审对象，不自动接入或部署。
- 两个都满足：按预冻结 primary 差异和复杂度规则选择唯一较简候选进入后续评审；不得在本 cohort 上继续扩展模型族。
- 任一实现发生泄漏、切分漂移、结果后改口径或身份不可复现：`INVALID_EXECUTION_DO_NOT_SCORE`，不得用同一留出结果修补后重跑。

失败即关闭该生成模型路线。不得放宽门槛、修改口径重开、换第五个模型族，或回到已烧 cohort 寻找支持。

## 7. Arming 前置清单

- [ ] Owner 明确批准本草案并授权执行拟合。
- [ ] 冻结 22 个 archive members、admitted fixtures、时间切分和全部 SHA-256。
- [ ] 冻结均值模型身份、PIT 输入、score matrix、五态 AH 映射与 score identity。
- [ ] 冻结两个候选的唯一形状参数空间和约束。
- [ ] 冻结 fixture-cluster bootstrap、时间块稳定性规则和单次评分入口。
- [ ] 证明未加载 `8,659 / 858 / 354 / 133` 已烧 cohort。
- [ ] 在结果读取前提交全部 arming artifacts。

在清单完成前：`FIT = FORBIDDEN`，`TEMPORAL_HOLDOUT_READ = FORBIDDEN`，`PRODUCTION_CHANGE = FORBIDDEN`。
