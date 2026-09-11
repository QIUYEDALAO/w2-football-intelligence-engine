# W2 现役正式候选赛后优化执行令 v1

执行方：Claude Code  
验收方：Codex  
日期：2026-09-09

## 一、任务身份与授权覆盖

```text
TASK_ID = W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_01
TASK_TYPE = OPERATIONAL_RECOMMENDATION_REMEDIATION
PRIMARY_GOAL = 提高 W2 实际正式候选推荐的赛后表现
OWNER_AUTHORIZED_LOCAL_IMPLEMENTATION = true
OWNER_AUTHORIZED_PRODUCTION_READ_ONLY = true
DEPLOYMENT_AUTHORIZED = false
```

这是 Owner 对仓库“当前仅量化离线基础任务”限制的一次窄范围显式覆盖：只允许修复现役正式候选链的已确认实现缺口，并离线评估概率校准候选。它不授权其他 V4 改造、Provider、Scheduler、Dashboard 重构、正式开关、生产写入或部署。

本轮不研究 W2 从未正式推荐的比赛。唯一赛果语料是生产正式推荐列表中的 148 条已结算候选，近 10 条是重点事故集。

立即停止并保持停止：

- C1；
- rho；
- task3bis；
- 5,818 场历史语料；
- 8,659、858、280 等历史 cohort；
- F5 新数据抓取；
- 新联赛、新 Provider 或公开网站抓取；
- 任何不属于这 148 条正式候选的比赛研究。

## 二、已知输入与证据等级

当前生产对照版本：

```text
PRODUCTION_REFERENCE_SHA = 3ac86c14fb951b93167d7a24f84a319663a6b9d9
PRODUCTION_REFERENCE_PARENT = bc1189e8f7f6a195075debb3d4bd7dcde3781ed2
PRODUCTION_WORKTREE = /Users/liudehua/Documents/Projects/W2-workspaces/w2-settlement-fix-20260909
```

Codex 于发令前已核实：`3ac86c14` 的父提交是 `bc1189e8`；本地 `origin/main=3b7f87db` 明显滞后，且 `3ac86c14` 不是 `origin/main` 的祖先。因此本任务**不得以 origin/main 为 base**，不得退回 `3b7f87db`。

Owner 提供、执行方必须独立复现的输入：

```text
OFFICIAL_SETTLED_BETS = 148
OFFICIAL_SETTLED_FIXTURES = 111
TOTAL_PROFIT_UNITS = -20.375
ROI = -13.77%

LAST10:
LOSS = 6
WIN = 2
HALF_WIN = 1
PUSH = 1
PROFIT_UNITS = -3.98

LAST10_AH_FACTOR_EV_CONFLICT = 5
CONFLICT_RESULTS = 4 LOSS / 1 WIN
```

若按 Owner 标注的 5 条冲突记录作机械事故重放：

```text
RETAINED = 5
RESULTS = 2 LOSS / 1 WIN / 1 HALF_WIN / 1 PUSH
PROFIT_UNITS = -0.88
```

该组数字只可作为 `OWNER_ANNOTATED_INCIDENT_REPLAY`。只有因子裁决能与对应 evaluation 的冻结时点及身份绑定时，才能升级为正式历史反事实；不能绑定时不得伪造成已独立复现。

现有只读故障报告：

```text
/Users/liudehua/Desktop/W2文档/W2_正式候选链因子否决绕过_故障报告_20260909.md
SHA256 = 0b305d3392e159f7547405539e36bf9e93a9ebb389581bcbceeb9c86a5fd4de9
```

报告中的代码断言可作为待复核假设；赛后数字必须重新计算。

## 三、源码与工作区

开工先完整读取仓库 `AGENTS.md` 及其列出的必读文件。随后执行并记录：

```bash
git remote -v
git fetch --all --prune --tags
git status --porcelain=v1
git rev-parse origin/main
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' 3ac86c14fb951b93167d7a24f84a319663a6b9d9
git show -s --format='%H %P %an <%ae> %cn <%ce> %s' bc1189e8f7f6a195075debb3d4bd7dcde3781ed2
```

主目录有既有 staged 文件和 `.workbuddy/`；不得修改、提交、还原、stash 或清理。

从精确生产提交新建干净 worktree：

```text
BASE_SHA = 3ac86c14fb951b93167d7a24f84a319663a6b9d9
WORKTREE = /Users/liudehua/Documents/Projects/W2-workspaces/w2-official-candidate-accuracy-20260909
BRANCH = codex/w2-official-candidate-accuracy-20260909
```

禁止在 `/Users/liudehua/Documents/Projects/` 顶层再创建 W2 工作区。目标路径或分支若已存在，先核身份并复用同一任务资产，不得删除未知内容或另建重复目录。

固定环境：

```text
PYTHON = /opt/homebrew/bin/python3.12
PYTHON_VERSION = 3.12.13
UV_MODE = --offline
```

## 四、任务 A：冻结正式候选自身语料

生产访问仅允许只读，唯一业务入口是：

```text
GET /v1/dashboard/intelligence-workspace
validation.model_forecast.official_recommendations
```

如公开投影缺少时点或身份字段，可对同一 148 条对应表执行严格只读 SQL 补证；不得扩大到其他比赛。数据库连接必须只读、事务只读、无 DDL/DML/临时表；记录已脱敏的查询语句、执行时间、数据库 schema head、release SHA、返回行数及读前读后可核验摘要，不输出凭据或连接串。

逐条冻结：

- evaluation_id；
- fixture_id、kickoff_utc、market、selection；
- exact_line、decimal_odds、evaluated_at、evaluation_slot/checkpoint；
- result_available_at 或 settlement 可知时刻；
- model_forecast_capture_identity_hash；
- quote_identity_hash、opportunity_identity_hash、attempt_identity_hash；
- factor direction、admitted、participants、absent reasons、veto；
- factor 决策对应的输入身份/hash 和其可知时点；
- 模型五态概率、1X2 概率、current_ev、current_ev_minus_se、current_delta；
- lineup status、实际进入计算的 starters/value 数及 numeric contribution；
- 模型 capture 时间、模型年龄/lead bucket；
- final score、五态 settlement、profit_units。

必须独立复现：148 条、111 个 fixture、`-20.375u`、近 10 条 `-3.98u` 和 `6L/2W/1HW/1P`。若任一不一致，先解释去重、排序、市场或结算口径并修正 manifest；不得带着不一致继续输出优化结论。

因子证据必须绑定对应 evaluation 的冻结时点。不能绑定的记录写：

```text
FACTOR_DISPOSITION = UNKNOWN_NOT_RECONSTRUCTIBLE
```

不得把 UNKNOWN 称为 non-conflict，也不得用当前分析卡倒灌成历史因子事实。所有敏感原始导出留在 Git 外；Git 内只保存完成本任务必需的脱敏字段和 canonical hash。

## 五、任务 B：修复正式候选链绕过

重点路径：

```text
src/w2/prematch/analysis_calculator.py
src/w2/prematch/read_model_projection.py
src/w2/prematch/lifecycle.py
src/w2/prematch/candidate_notifications.py
src/w2/api/repository.py
migrations/versions/
```

### B1. AH 语义

以下任一状态存在时，动态评估不得成为 `ANALYSIS_PICK_ACTIVE`：

- `FACTOR_SCORE_UNAVAILABLE`；
- `FACTOR_ADMISSION_FAILED`；
- `FACTOR_EV_DIRECTION_CONFLICT`。

必须落为明确的非候选动态状态，在 blockers 中保留具体码，最终 opportunity 为 `BLOCKED_BY_GATE`。因子方向与 EV 方向一致且因子已准入时，才继续执行原经济准入条件。

不得只在 API/read layer 临时 join 后过滤。因子裁决必须进入动态评估的写入契约，使存储状态本身真实，随后 Dashboard、正式推荐、候选通知和赛后台账自然一致。

### B2. TOTALS 语义

TOTALS 当前没有 factor direction，保持原有独立 Poisson/EV/经济准入逻辑。不得把 AH 因子规则扩散到 TOTALS。

### B3. `official_funnel_eligible`

不得简单改成 `false`。该字段表示评估属于正式漏斗分母，不等于推荐通过。被因子阻断的正式评估仍可保持：

```text
official_funnel_eligible = true
opportunity_state = BLOCKED_BY_GATE
```

但必须保证：

- 不进入正式推荐；
- 不发送候选通知；
- 不新增正式候选盈亏记录；
- 仍在漏斗 denominator 中计为 `BLOCKED_BY_GATE`。

### B4. 身份、迁移与历史兼容

为新 evaluation payload 增加版本化裁决字段，至少包括：

- factor_decision_status；
- factor_direction；
- ev_direction；
- factor_veto_code；
- factor_input_identity/hash。

新 evaluation/attempt identity 必须绑定因子裁决身份；必要时新增向后兼容的 Alembic migration，但不得覆盖、重写或删除历史 evaluation、opportunity、result、ledger 或 raw。旧 payload 必须继续可读，并明确返回“历史无因子裁决身份”，不能默认为通过。

## 六、任务 C：逐场分析近 10 条中的 6 场 LOSS

逐场形成根因表，不接受统一套模板。只使用冻结赛前证据，不用赛后信息解释赛前决策。

### C1. 四场 AH 冲突 LOSS

- 斯图加特 vs 科隆；
- 热那亚 vs 科莫；
- 伊普斯维奇 vs 利物浦；
- 埃尔切 vs 皇家社会。

逐场回答：

- 因子方向与 EV 为什么相反；
- 实际参与因子的方向、原值、标准化值、权重和缺失项；
- current EV 为什么仍约为 `+0.17` 至 `+0.41`；
- 模型五态中 LOSS/HALF_LOSS 概率为何偏低；
- 修复后是否会被明确阻断；
- 若历史 factor 身份不可重建，必须明确写 UNKNOWN，不得假定。

不允许把“把方向反过来可能盈利”当正式证据。

### C2. 一场 AH 同向 LOSS

乌迪内斯 vs 拉齐奥：factor=HOME、EV=HOME 0、最终 1-2。检查有限因子参与、F5 缺失、阵容数值贡献为零、模型/报价年龄与五态过度自信；判断是因子信息质量不足、模型输入陈旧、概率失准或多项共同作用。没有证据时不得单因归责。

### C3. 一场 TOTALS LOSS

卡利亚里 vs 莱切：OVER 2.25、最终 1-0、`current_ev≈+0.275283`、模型 WIN 概率约 64.22%、`lineup_input_hash=null`、T-15 仍形成正式候选。

检查四字段 xG、最终 lambda、模型 capture 距开赛时间、是否复用数日前 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`、T-15 报价是否搭配过旧模型、未确认阵容为何未阻断，以及五态分布为何如此自信。

## 七、任务 D：只用 148 条做结果导向校准

这是本轮实际准确率优化，不得只修候选链后结束。

### D1. 时序合同

按 `evaluated_at`、`kickoff_utc` 和稳定 identity 排序。对第 i 条候选，训练数据只能包含在它 `evaluated_at` 之前已经有权威 `result_available_at/settled_at` 的正式候选；仅仅 kickoff 更早但当时尚未结算的记录不可用。

禁止：随机切分、全样本拟合后回算、使用赛后特征、当前分析卡倒灌、未来记录注入或用近 10 条反向选参数。

近 10 条已经被查看，只能标为 `INCIDENT_REPLAY`，不是 blind holdout。

### D2. 唯一允许比较的四轨

1. `INCUMBENT`；
2. `AH_FACTOR_VETO_ONLY`；
3. `ROLLING_TEMPERATURE_ONLY`；
4. `AH_FACTOR_VETO_PLUS_ROLLING_TEMPERATURE`。

不得增加 C1、rho、Elo、身价、F5、其他模型族、阈值搜索或事后分桶。

`AH_FACTOR_VETO_ONLY` 对三类 AH 否决状态均阻断；TOTALS 不受影响。历史因子为 UNKNOWN 的记录不得假设一致：主报告按 `NOT_ESTIMABLE_FACTOR_IDENTITY` 单列并减少该轨可评估覆盖，另给“UNKNOWN 全部阻断”的保守边界；不得选择对结果最有利的处理。

### D3. 温度校准预注册

AH 与 TOTALS 分开滚动，只改变原选择对应的完整五态概率形状，不改选边、exact line、赔率、原 factor 状态或原 cashflow edge。

对五态概率 `p_j`：

```text
q_j(T) = exp(log(max(p_j, 1e-12)) / T) / Σ_k exp(log(max(p_k, 1e-12)) / T)
```

候选网格固定为：

```text
T = 0.70, 0.71, ..., 2.00
```

训练目标固定为：

```text
mean_multiclass_log_loss + 0.10 * (log(T) ** 2)
```

同分依次选择：最接近 `1.00`、再选择数值较小者。每个市场轴历史可用记录少于 20 条时固定 `T=1.00`；达到 20 条后按上述规则滚动重估。此规则在查看四轨结果前固定，不得事后修改网格、20 条门槛或惩罚项。

完整五态重新归一化并继续通过 `1e-9` 合同。使用原 exact line 和 decimal odds 调用仓库唯一 canonical Decimal 五态 EV 权威；不得复制第二套结算或 EV 公式。校准后：

```text
calibrated_ev_se = original_ev_se
calibrated_ev_minus_se = calibrated_ev - original_ev_se
```

不得让不确定性小于原值；原 `ev_se` 缺失则该校准经济准入为 `NOT_ESTIMABLE`。经济准入继续使用原 cashflow price edge 与现有生产合同；温度只允许让原选择继续或被阻断，不得翻转方向。

### D4. 必须分层和报告

分别报告：AH、TOTALS、factor conflict/consistent/unknown、模型年龄/lead bucket、checkpoint、lineup 真正参与/未参与、factor participant count、EV 区间、模型预测 LOSS 概率区间。

同场双市场相关，所有区间按 111 个 fixture 聚类。固定 bootstrap seed 由任务 ID 的 canonical v2 hash 推导，10,000 次；逐次以 fixture 为抽样单位，保留同 fixture 的全部市场记录。两次运行必须 byte-identical。

每轨至少输出：

- emitted count、coverage；
- WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS 全状态计数；
- full LOSS rate；
- graded hit rate（WIN=1、HALF_WIN=0.5、PUSH 排除、HALF_LOSS=0、LOSS=0）；
- profit_units；
- 五态 log loss、multiclass Brier、calibration error；
- fixture-cluster bootstrap interval；
- 最大连续亏损、最大回撤。

同时输出全 148 条、前 138 条、近 10 条事故集。不得用“不推荐任何比赛”制造 100% 命中；任何结果必须同时给覆盖率、收益和未估计原因。

## 八、实现边界

必须完成两类交付：

1. 生产链修复：AH 因子裁决进入动态候选写入状态，覆盖 Dashboard、正式推荐、候选通知和赛后台账；
2. 离线校准候选：只放在 `src/w2/quant_research/`、`scripts/quant/`，不接生产链，不得以环境变量或默认配置暗中启用。

本轮允许本地 commit。不得 push、开 PR、部署或改 Obsidian。

## 九、最低测试矩阵

至少覆盖：

1. AH factor unavailable + 经济条件通过 → `BLOCKED_BY_GATE`；
2. AH factor admission failed + 经济条件通过 → `BLOCKED_BY_GATE`；
3. AH factor/EV conflict + 经济条件通过 → `BLOCKED_BY_GATE`；
4. AH factor/EV consistent + 经济条件通过 → `EVALUATED_CANDIDATE`；
5. TOTALS 行为不变；
6. 被阻断 AH 不进入 official recommendations；
7. 被阻断 AH 不产生 candidate notification；
8. 被阻断 AH 不新增正式候选盈亏记录；
9. 被阻断 AH 仍计入正式漏斗 denominator；
10. 历史 payload 向后兼容并显式标出因子身份缺失；
11. evaluation/attempt identity 包含新因子裁决身份；
12. 148 条 incumbent 精确复现 `-20.375u`；
13. 近 10 条 incumbent 精确复现 `-3.98u`；
14. Owner 标注的事故重放精确得到保留 5 条、`-0.88u`，但证据标签不得越级；
15. 未来记录、赛后特征、尚未在 evaluated_at 前结算记录注入时必须失败；
16. 同 fixture 双市场始终作为一个 cluster；
17. 五态温度输出归一化并通过 `1e-9`；
18. canonical Decimal EV 与 settlement 只调用现有唯一权威；
19. 两次完整运行 byte-identical；
20. 旧 evaluation、opportunity、result 与 ledger 行不被改写。

不得删除、skip、xfail 或弱化既有测试。测试必须包括至少一个不导入生产 serializer 的独立结果复算器；同源测试不能作为唯一 oracle。

## 十、交付物

交付包：

```text
docs/review_packages/W2_OFFICIAL_CANDIDATE_ACCURACY_REMEDIATION_20260909/
```

至少包含：

- `DISPATCH.md`（本执行令原文及 SHA-256）；
- `SOURCE_IDENTITY.json`；
- `OFFICIAL_148_MANIFEST.jsonl`；
- `LAST10_INCIDENT_REPLAY.json`；
- `LOSS_ROOT_CAUSE_REPORT.md`；
- `FACTOR_BYPASS_REPAIR_REPORT.md`；
- `CALIBRATION_COMPARISON.json`；
- `METRICS.json`；
- `TEST_RESULTS.md`；
- `REPORT.md`；
- `HASHES.sha256`。

敏感只读原始响应、凭据、连接信息不得入 Git。manifest 中只保留必要的非敏感身份、概率、盘口、时点、结算和 hash。

## 十一、完成标准

最终只能返回：

```text
DONE_CHAIN_FIXED_MODEL_CANDIDATE_READY
```

或：

```text
DONE_CHAIN_FIXED_NO_SAFE_MODEL_CANDIDATE
```

不得因为“需要更多数据”停在 PENDING，不得新增门禁或要求 Owner 再做普通技术选择。第二种终态也必须完成：链路修复、148 条完整诊断、近 10 条事故复现、四轨比较，以及现有证据为何不足以支持概率参数改动。

`MODEL_CANDIDATE_READY` 只表示存在可交 Codex 独立验收的本地离线候选，不表示已证明未来盈利、已获部署授权或可以开启正式推荐。

## 十二、硬边界

```text
REAL_PROVIDER_CALLS = 0
PUBLIC_HTTP_FETCH = 0
PRODUCTION_DB_READS = READ_ONLY_OFFICIAL_148_ONLY
PRODUCTION_DB_WRITES = 0
PRODUCTION_CONFIG_WRITES = 0
DEPLOYMENT_EXECUTED = false
SCHEDULER_RESTARTED = false
OBSIDIAN_WRITES = 0
GITHUB_PUSH = 0
PR_CREATED = false
REAL_MONEY_ACTIONS = 0
```

Claude Code 不修改 Obsidian。Obsidian 由 Codex 在独立验收后更新最终状态。

## 十三、一次性回执

回执必须一次交代：

```text
FINAL_STATE
BASE_SHA
TASK_COMMIT
TASK_BRANCH
PRODUCTION_REFERENCE_SHA
OFFICIAL_148_REPRODUCED
LAST10_REPRODUCED
CHAIN_FIX_STATUS
FACTOR_IDENTITY_COVERAGE
INCUMBENT_METRICS
FACTOR_VETO_ONLY_METRICS
CALIBRATION_ONLY_METRICS
COMBINED_METRICS
RECOMMENDED_NEXT_ACTION
PROVIDER_CALLS
PRODUCTION_DB_READS
PRODUCTION_DB_WRITES
DEPLOYMENT_EXECUTED
PUSH_EXECUTED
HASH_CHECK
TEST_RESULTS
CHANGED_FILES
MAIN_WORKSPACE_STATUS_BEFORE_AFTER
```

完成后停止，交 Codex 独立验收；不得自行部署。
