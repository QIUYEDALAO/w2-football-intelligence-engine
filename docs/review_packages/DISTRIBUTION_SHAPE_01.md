# DISTRIBUTION_SHAPE_01

状态：`BLOCKED_ON_XG_AVAILABILITY / PREREGISTRATION_DRAFT_NOT_ARMED`

本文件只冻结研究设计草案。未执行拟合、未读取时序留出集、未修改生产代码或模型参数。xG 可得性探针已证明原 22 联赛 cohort 当前不可执行；在阻塞解除、Owner 明确批准并完成 arming freeze 前不得执行。

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
- 派发合同给出的未烧候选池规模约 `6,222` 场；草案阶段不读取结果列或留出集。最终 admitted 集必须在 arming 时依次执行：archive member/结构校验 -> 必需列完整性 -> fixture identity 唯一映射 -> **已烧 fixture 排除** -> 严格 5+5 PIT xG 可得性。任一阶段的清单、排除原因、计数与 SHA-256 均须在评分前冻结，不能在评分后回改。

已烧 fixture 排除不是声明，而是 admitted 的强制操作规则：

1. 权威来源只使用结果打开前冻结的 `docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_CLOSING_PREDICTIONS_PRE_RESULT.json`；不得从评分结果或 settled ledger 反推。
2. 来源 artifact SHA-256 固定为 `33ae870095e1c27e8797ff0f86bc3e1b0c2b2bdcddebba69b911a8a84731defb`，且其中 `result_columns_read=0`、`fixture_count=858` 必须成立，否则 `INVALID_EXECUTION_DO_NOT_SCORE`。
3. `BURNED_FIXTURE_IDS = sorted(unique(str(prediction.fixture_id)))`，按 UTF-8 canonical JSON（`ensure_ascii=false, sort_keys=true, separators=(',', ':')`）序列化；固定计数 `858`、SHA-256 `812a70b468fa7f2848157136e82c62ac544a90081164b29601a3d521235bd537`。
4. 为防止 future mapper 更换 ID，另冻结 identity tuple `(competition, kickoff_at, normalize(home_team), normalize(away_team))`；`normalize` 为 NFKD -> ASCII -> lowercase -> 删除非 `[a-z0-9]`，sorted unique canonical JSON 计数 `858`、SHA-256 `99054217d49343a6cf731915eeb29745258db08000198c738c469a3511cb6e31`。
5. archive row 映射后的 API-Football fixture ID 命中 `BURNED_FIXTURE_IDS`，或其 identity tuple 命中冻结 tuple 清单，均必须以 `EXCLUDED_BURNED_V1_HISTORICAL_CLOSING` 排除。两种身份判定不一致、映射缺失或一对多时 fail closed，不得 admitted。
6. arming artifact 必须输出逐场排除清单、来源与派生 SHA、命中方式和排除计数；未证明 858 项全部被处理前不得切分 `FIT/TEMPORAL_HOLDOUT`。

该 cohort 不设最低场次门槛，也不等待新比赛。验证采用 cohort 内严格时序留出，必须按以下不可逆顺序执行：

1. 冻结 source archive hash、22 个 member 名单、解析版本、必需字段、上述 858 项已烧排除清单、排除原因、fixture identity 与逐场 PIT 输入规则。
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

22 个联赛中多数不是 W2 当前生产联赛。该 cohort 原意是检验相关计数结构是否跨联赛具备形状改善，但不能直接证明生产联赛、实时赔率或 W2 当前候选链上的收益。

xG 可得性前置由 `codex/w2-dc-rho-xg-probe-01@344935b5` 的 `W2_DC_RHO_XG_AVAILABILITY_PROBE.md` 固定：

- xG 来源只能是 API-Football `fixtures + statistics`，数值门要求双方 Expected Goals 均非空且可转 float；lambda 的双方历史均要求 5 场严格早于目标 kickoff。
- 22 个 `league_id` 全部可解析，但只有 `B1 D1 E0 E1 F1 I1 N1 P1 SP1 T1` 为 `20/20` 数值 xG；`D2 E2 E3 EC F2 G1 I2 SC0 SC1 SC2 SC3 SP2` 均为 `0/20`。
- 可用 10 联赛全季 Football-Data 五列完整 `3,588` 场；按非五大全季 + 五大 2024-02-22 后窗口是 `2,453` 场。
- 若另行批准该 10 联赛子集，覆盖目标场和严格 5+5 的 Provider 预算下界 `2,985`、保守上界 `3,626`，在 daily limit 7,500、reserve 1,500 下约 1 个配额日。探针实际调用 `486/500`，最后 remaining `6324`。

上述 10 联赛只是可用性事实，不是缩小 cohort 的授权。原研究固定 22 联赛，而 12 联赛没有数值 xG；因此当前状态是 `BLOCKED_ON_XG_AVAILABILITY`。不得为了可行性改成 10 联赛、替换赛季、换 Provider、用 proxy xG 或删除不可用联赛。解除阻塞需要 Owner 对 cohort 变更或新的 xG 来源作单独决定；在此之前 `FIT`、arming 和 holdout 读取都禁止。

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
- [ ] 按双身份规则冻结并排除 858 个已烧 fixture；逐场排除清单计数与两个派生 SHA-256 一致。
- [ ] 冻结均值模型身份、PIT 输入、score matrix、五态 AH 映射与 score identity。
- [ ] 冻结两个候选的唯一形状参数空间和约束。
- [ ] 冻结 fixture-cluster bootstrap、两个 primary 的 one-sided 97.5% 门、四个最少 100 场时间块、八个 99.375% 退化检查和单次评分入口。
- [ ] 证明未加载 `8,659 / 858 / 354 / 133` 已烧 cohort。
- [ ] 解除 `BLOCKED_ON_XG_AVAILABILITY`；不得以缩小或更换 cohort 自行解除。
- [ ] 在结果读取前提交全部 arming artifacts。

在清单完成前：`FIT = FORBIDDEN`，`TEMPORAL_HOLDOUT_READ = FORBIDDEN`，`PRODUCTION_CHANGE = FORBIDDEN`。
