# DISTRIBUTION_SHAPE_01

状态：`PREREGISTRATION_DRAFT_NOT_ARMED`

本文件只冻结研究设计草案。未执行拟合、未读取时序留出集、未执行 xG 采集，也未修改生产代码或模型参数。在 Owner 明确批准并完成 arming freeze 前不得执行。

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

候选池为本地 Football-Data 2023/24 season archive 中以 xG 物理可得性预先机械筛定的 10 个联赛：

- 物理来源：`/Users/liudehua/.hermes/data/w2/football-data-co-uk/raw/season_zips/2324_data.zip`
- archive SHA-256：`f86ac89c3df57be812fc25d4d4aeca0ef98b910483e59560c0f7b406118e3c5a`
- archive 中已只读核实存在 `22` 个联赛 CSV。依据 `codex/w2-dc-rho-xg-probe-01@344935b5` 在任何拟合与赛果读取前完成的可得性探针，冻结 `B1=144 D1=78 E0=39 E1=40 F1=61 I1=135 N1=88 P1=94 SP1=140 T1=203`。
- 探针报告 `docs/review_packages/W2_DC_RHO_XG_AVAILABILITY_PROBE.md` 的 SHA-256 冻结为 `131ac0525c45fe9016b7cedb0fba846e3716046252e5d52c057386ba8fdc7600`。其中 `D2 E2 E3 EC F2 G1 I2 SC0 SC1 SC2 SC3 SP2` 的冻结探针结果均为 `0/20`，因此这 12 联赛按“Provider 是否返回双方可转 float 的 Expected Goals”这一与赛果无关的物理可得性标准整体排除，不得在看过结果后改回。
- admitted 规则为：非五大联赛取 2023/24 全季；五大联赛 `D1 E0 F1 I1 SP1` 仅取严格晚于 `2024-02-22` 的场次；且 `AHCh / PCAHH / PCAHA / PC>2.5 / PC<2.5` 全部非空。该日期口径已将五大联赛已烧窗口整体排除，不再读取赛果或结算列判断。

| 联赛 | admitted 目标场 |
|---|---:|
| B1 | 312 |
| D1 | 104 |
| E0 | 123 |
| E1 | 552 |
| F1 | 108 |
| I1 | 132 |
| N1 | 306 |
| P1 | 306 |
| SP1 | 130 |
| T1 | 380 |
| **合计** | **2,453** |

上表已从冻结 archive 独立重算，逐项与探针报告一致，加总为 `2,453`，不是 `3,588`。admitted fixture 清单只含 `competition / date / home_team / away_team`，按 `(competition, date, home_team, away_team)` 排序后以 UTF-8 canonical JSON（`ensure_ascii=false, sort_keys=true, separators=(',', ':')`）序列化；冻结计数 `2,453`、SHA-256 `acd9e66bf6ecb15b84cb61cc05ce83f4aaf346f1e6d0a4a63c72b2f80a503eef`。该清单的生成未读取比分、赛果或结算列。

最终 admitted 集必须在 arming 时依次执行：archive member/结构校验 -> 上述联赛与日期口径 -> 必需列完整性 -> fixture identity 唯一映射 -> 严格 5+5 PIT xG 可得性。任一阶段的清单、排除原因、计数与 SHA-256 均须在评分前冻结，不能在评分后回改。

该 cohort 不设最低场次门槛，也不等待新比赛。验证采用 cohort 内严格时序留出，必须按以下不可逆顺序执行：

1. 冻结 source archive hash、22 个 member 名单、10 联赛物理可得性口径、解析版本、必需字段、admitted fixture identity 与逐场 PIT 输入规则。
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

两个候选共享 one-sided family alpha `0.05`。Primary 对同一基线做两次候选检验，采用 Bonferroni：每个候选 `alpha=0.025`，所以各自使用 one-sided `97.5%` upper bound；不得继续使用各自 one-sided 95%。

时间稳定性在 arming 前固定如下：将 `TEMPORAL_HOLDOUT` 按 `(kickoff_at, fixture_id)` 排序，按 rank 切成四个连续、场数差最多 1 的 `T1..T4` 块，不按联赛、比分或候选输出重排；每块最少 `100` 场，否则保持 `NOT_ARMED`。每个候选在每块计算相同 fixture-cluster bootstrap paired primary difference。八个 candidate × block 退化检查采用 Bonferroni one-sided `alpha=0.05/8=0.00625`，即 `99.375%` lower bound。任一块同时满足点估计 `> 0` 且 lower bound `>= 0`，即量化为 `SYSTEMATIC_TEMPORAL_DEGRADATION`，该候选失败；不再保留“足以推翻 pooled 解释”的人工判断。

“稳定改善”须同时满足：

- temporal holdout pooled primary 点估计小于 `0`；
- fixture-cluster bootstrap 的 one-sided `97.5%` upper bound `<= 0`；
- 四个冻结时间块均未触发上述 `SYSTEMATIC_TEMPORAL_DEGRADATION`；
- log-loss secondary 点估计不得大于 `0`，且同样按两个候选 Bonferroni 后的 one-sided `97.5%` lower bound 不得 `>= 0`。

两个候选分别相对同一基线裁决；不得在看过 holdout 后更换 bootstrap、时间块、权重、比分截断或 primary score identity。若 arming 前无法冻结上述实现细节，状态保持 `NOT_ARMED`。

## 5. 可移植性与声明边界

10 联赛 cohort 中，生产联赛为 `D1 E0 F1 I1 SP1` 5 个，非生产联赛为 `B1 E1 N1 P1 T1` 5 个。该 cohort 只检验相关计数结构在这 10 联赛中是否具备形状改善；结论对另外 12 联赛不成立，也不能直接证明实时赔率或 W2 当前候选链上的收益。

xG 可得性前置由 `codex/w2-dc-rho-xg-probe-01@344935b5` 的 `W2_DC_RHO_XG_AVAILABILITY_PROBE.md` 固定：

- xG 来源只能是 API-Football `fixtures + statistics`，数值门要求双方 Expected Goals 均非空且可转 float；lambda 的双方历史均要求 5 场严格早于目标 kickoff。
- 22 个 `league_id` 全部可解析，但只有 `B1 D1 E0 E1 F1 I1 N1 P1 SP1 T1` 为 `20/20` 数值 xG；`D2 E2 E3 EC F2 G1 I2 SC0 SC1 SC2 SC3 SP2` 均为 `0/20`。
- 可用 10 联赛全季 Football-Data 五列完整 `3,588` 场；按非五大全季 + 五大 2024-02-22 后窗口是 `2,453` 场。
- 覆盖目标场和严格 5+5 的 Provider 预算下界 `2,985`、保守上界 `3,626`，在 daily limit 7,500、reserve 1,500 下约 1 个配额日。探针实际调用 `486/500`，最后 remaining `6324`。

全量 xG 采集预算的可复核下界为 `2,985` 次、保守上界为 `3,626` 次。日限 `7,500`、保留 `1,500` 时可用 `6,000/天`，因此上下界均需 `1` 个配额日。采集是 arming 后的独立步骤；本草案未执行任何 xG 采集。

无论结果如何，本研究都不得声明跑赢市场、盈利、生产有效、可部署，或据此修改 `CALIBRATION_VERSION`、`dixon_coles_rho`、lambda 参数、ledger/白名单。任何生产接入都需要新的身份、独立验收和 Owner 授权。

## 6. 预注册裁决与停止规则

- 两个候选都未满足 primary 稳定改善：`REJECT_AND_CLOSE_DISTRIBUTION_GENERATOR_ROUTE`。
- 只有一个候选满足：仅记录该候选为后续独立生产可行性评审对象，不自动接入或部署。
- 两个都满足：按预冻结 primary 差异和复杂度规则选择唯一较简候选进入后续评审；不得在本 cohort 上继续扩展模型族。
- 任一实现发生泄漏、切分漂移、结果后改口径或身份不可复现：`INVALID_EXECUTION_DO_NOT_SCORE`，不得用同一留出结果修补后重跑。

失败即关闭该生成模型路线。不得放宽门槛、修改口径重开、换第五个模型族，或回到已烧 cohort 寻找支持。

## 7. Arming 前置清单

- [ ] Owner 明确批准本草案并授权执行拟合。
- [ ] 复核 22 个 archive members、10 联赛可得性口径、`2,453` 个 admitted fixtures 及其 SHA-256，并冻结时间切分与全部派生 SHA-256。
- [ ] 冻结均值模型身份、PIT 输入、score matrix、五态 AH 映射与 score identity。
- [ ] 冻结两个候选的唯一形状参数空间和约束。
- [ ] 冻结 fixture-cluster bootstrap、两个 primary 的 one-sided 97.5% 门、四个最少 100 场时间块、八个 99.375% 退化检查和单次评分入口。
- [ ] 证明未加载 `8,659 / 858 / 354 / 133` 已烧 cohort。
- [ ] 采集并冻结 10 联赛的严格 5+5 PIT xG；不得因样本量回头放宽门槛或增删联赛。
- [ ] 在结果读取前提交全部 arming artifacts。

在清单完成前：`FIT = FORBIDDEN`，`TEMPORAL_HOLDOUT_READ = FORBIDDEN`，`PRODUCTION_CHANGE = FORBIDDEN`。
