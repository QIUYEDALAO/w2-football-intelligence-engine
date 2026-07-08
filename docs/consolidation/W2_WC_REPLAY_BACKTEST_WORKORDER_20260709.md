# W2 工单 · 世界杯 10 场回放式回测(Replay Backtest)· 2026-07-09

**定位(先读这段,防跑偏)**:对已完赛比赛做"假装赛前"的全链路重放——出卡、结算、验证、报告。它证明的是**管道**(数据组装→DecisionCard→影子方向→结算→报告在真实完赛数据上闭环)和**国际赛外分布行为**(模型/就绪门在 WC 上的真实表现),外加给老板一个诚实的可看物。它**不是**模型验证(n=10 噪声级)、**不是**战绩(事后选样,无 CLV 资格)、**不得**写入 forward ledger 真实轨。所有产物带 `BACKTEST_REPLAY` 标记。

**时间敏感**:API-Football 对已完赛场次的赛前 odds 留存窗口约 7 天。样本含 07-02 场次,已在窗口边缘——Phase 1 采集须在本周内执行,否则赛前盘口永久不可得。

## 0. 样本(确定性规则,预注册,不许换)

规则:本地缓存(sprint 07-06 快照)中已完赛 WC 场次按 kickoff 降序取 10 场。即:

Portugal–Spain(07-06)、Mexico–England(07-06)、Brazil–Norway(07-05)、Paraguay–France(07-04)、Canada–Morocco(07-04)、Colombia–Ghana(07-04)、**Argentina–Cape Verde(AET)**、**Australia–Egypt(PEN)**(07-03)、Switzerland–Algeria(07-03)、Portugal–Croatia(07-02)。

AET/PEN 两场是特意保留的:检验 FIX-F 的 90 分钟 fulltime 结算路径。某场若赛前 odds 取不回 → **不许换场**,该场标 `MODEL_FALLBACK` 照跑(回退层行为本来就是测试目标),报告如实列覆盖率。

## Phase 0 · 零额度清点(先做,$0)

盘点本地缓存 + staging runtime 挂载对这 10 场已有什么:fixtures(✓ 已有)、S14 探针 odds(league=1 两条,核对是否命中样本)、07-08 起 market_timeline/forward ledger 快照(若样本里有 07-08 后完赛场次则直接有 T-24/T-1h 真快照)、statistics/lineups 覆盖。产出缺口清单:`每场 × {prematch_odds, lineups, statistics(仅用于赛后结算与对手历史), 双方此前各场}` 的有/无矩阵。

## Phase 1 · 受控采集补缺(需单独批准;预算 ≤50 calls)

- 端点仍限 allowlist(`fixtures,odds,lineups`+statistics);每场至多 odds×1 + lineups×1 + statistics×1,重试预算 20。
- **与日常积累共享 120/日硬顶**:执行前查当日 provider ledger 用量,预测超限则分两天跑或挑低谷时段;绝不为回测挤掉正在积累的 T-24/T-1h 快照。
- odds 探测结果如实三态:`PREMATCH_ODDS_RETRIEVED / RETENTION_EXPIRED / NEVER_OFFERED`,进报告。

## Phase 2 · 离线重放出卡($0)

- 每场两个评估时点 `as_of ∈ {kickoff−24h, kickoff−1h}`,走**与线上完全相同的代码路径**(`build_decision_contract_fields` + 契约字段全套),禁止 fork 逻辑。复用 `run_stage13a_world_cup_dry_run.py` / S14 探针的组装封装。
- **防泄漏三道闸(验收重点)**:①输入白名单——任何进入特征/盘口的 payload,其数据时间戳必须 < as_of(fixtures 状态字段改用赛前视角构造,禁止把 FT 状态传进就绪门);②复用 replay 守卫("closing 不得进早期阶段");③每张卡记录 `input_provenance[]`(payload 来源+时间戳),验收抽 3 场逐项核。
- 特征历史:队史窗口不足(小组赛早期)→ 就绪门如实 INSUFFICIENT → 回退/降档照真实逻辑走,这本身是观察目标,不许为回测放宽 `MIN_HISTORY`。
- 输出:`runtime/wc_replay_backtest/{fixture_id}/cards.jsonl`(T-24 与 T-1h 各一张),每条带 `"backtest_replay": true, "not_a_recommendation": true`。**绝不写 `runtime/forward_outcome_ledger/`。**
- `direction_allowed` 保持 False:卡片主输出是市场概率 + 分歧 + `shadow_pick` 方向;另渲染一列"假设性方向(若已放行)",标注 `HYPOTHETICAL_NOT_RELEASED`。

## Phase 3 · 验证与报告($0)

- 结算:复用 FIX-B 结算函数(`settle_asian_handicap` + 90' fulltime),对 `shadow_pick` 与假设性方向分别结算,写 `runtime/wc_replay_backtest/outcomes.jsonl`(独立命名空间,同样不进 forward ledger)。
- 指标:每场一行——对阵 / T-1h 市场概率(去 vig POWER)/ 模型概率与 `model_family` / 分歧(线差)/ shadow 方向 / 90' 比分 / 结算结果 / reason codes;汇总:模型 LL vs 市场 LL(n=10,附"±0.1 级噪声"声明)、shadow 方向命中 x/10、AET/PEN 两场结算正确性、readiness/回退分布。
- CLV:样本大多无 T-24 真快照 → **CLV 列全体 N/A 并写明原因**("回测不可回收时间线,CLV 只能由前向采集产生")——这句话顺便向老板解释了为什么前向 ledger 无可替代。
- 报告:`docs/consolidation/W2_WC_REPLAY_BACKTEST_REPORT_2026_07.md`,头部效度声明四条:n=10;国际赛未验证(外分布);事后选样不构成战绩;与前向证据体系物理隔离。

## Phase 4 · 展示(可选,默认不做)

如老板要看:dashboard 加"回测演示"独立区,数据源只读 `wc_replay_backtest/`,全卡 `BACKTEST` 角标;绝不进"赛后验证"真实区、绝不进联赛表现、绝不进命中率。无审批不做。

## 验收(硬)

1. 泄漏审计:抽 3 场(含 1 场 AET),卡内 `input_provenance` 全部时间戳 < as_of;把某场 FT 统计混入 as-of 输入的构造测试必须被闸门拒绝。
2. 隔离审计:`runtime/forward_outcome_ledger/` 在整个回测前后 diff 为空;`forward_ledger_performance` 输出数字不因回测改变。
3. AET/PEN 两场按 90' 比分结算正确(单测 + 实跑双证)。
4. 覆盖率如实:odds 三态计数 + 每场 probability_source 列表。
5. 预算:Phase 1 实际 calls 数进报告,≤50,当日总量 <120。
6. 复现:同输入重跑,卡片哈希逐张一致。

## 边界重申

不 enable、不动 production、不放行方向、不改线上决策路径、EV 腿不动;回测产物不进 git(runtime 下,.gitignore 覆盖确认);台账由执行会话追加一条回测条目。
