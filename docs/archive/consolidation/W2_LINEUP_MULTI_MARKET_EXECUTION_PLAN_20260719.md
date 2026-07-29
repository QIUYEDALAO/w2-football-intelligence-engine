# W2 首发变化与多市场决策全量任务清单 — 2026-07-19

## 状态与边界

- 状态：`planned`，尚未实施、尚未本地验收、尚未部署。
- 本地基线：`main@8e171dc05efc2fc3a512fff2c334d123d01db922`。
- GitHub 只作此前只读数据源核验；本计划不执行 `fetch/pull/push`，不创建 PR。
- 当前 staging 已验收的 Dashboard 实现为
  `01f8a75aa87cfaf58d0db3635eefc02016830d87`；布局保持不变。
- 本计划会改变数据契约、统计或运行时决策，因此部署后连续三个 09:00
  只读周期必须从 `0/3` 重新计算。
- `RECOMMEND`、lock、OFFICIAL、champion、production 写操作和联赛开关不因本计划开放。

## 已确认的产品决策

1. 首发名单不能只换算为双方首发总身价；总身价只作低权重背景。
2. 真正使用的是“本场首发相对该队赛前常用首发的变化”：关键缺席、位置替换、
   客串、阵型偏移、组合连续性和替补深度。
3. 首发影响必须拆成两个独立信号：
   `lineup_ah_adjustment` 与 `lineup_totals_adjustment`。
4. 让球和大小球独立评估，不允许因为数组顺序固定选择让球。
5. Dashboard 保持当前布局；展示全部合格比赛。每场显示主推荐，第二市场只有独立
   通过门槛且相关性护栏通过时才作为次推荐展示。
6. 推荐比分必须服从最终市场和方向；没有最终 pick 时不显示方向性比分。
7. 五大联赛必须有正式首发和完整的首发身份覆盖后才能产生分析推荐。
8. 其他联赛不把首发设为统一硬门；按照真实数据覆盖等级使用可选首发增强。

## 数据源纪律

### Transfermarkt GitHub 数据集

允许离线、版本化读取以下表：

- `players`：`player_id`、`position`、`sub_position`、惯用脚、身高、俱乐部和身价；
- `player_valuations`：带日期的历史身价；
- `game_lineups`：逐场首发/替补、本场位置、号码、队长；
- `games`：逐场双方阵型、教练、赛季和比赛日期；
- `appearances`：出场分钟、进球、助攻和纪律数据。

原始文件不提交仓库。只保存经过裁剪的版本 manifest、SHA-256、schema version、
来源 URL、抓取时间和审计统计。

### 临场数据

- API-Football 继续提供正式首发、临场阵型和球员身份。
- 公开 Dashboard/analysis-card 请求不得触发 provider、模型重算或全局扫描。
- provider 调用只允许在受控 scheduler 采集窗口发生，继续遵守日配额、dedup 和 ledger。

### 身价补齐

- 优先使用同一版本的 Transfermarkt 数据集。
- 五大联赛缺失球员可通过离线人工审核的 Transfermarkt 页面补齐；记录来源、观察时间、
  审核人和内容 hash。
- 若以后购买 FootballTransfers/SciSports 等正式 API，必须作为独立 valuation source；
  不得把不同估值模型的欧元值直接拼成同一套首发总值。
- SofaScore、Flashscore 等网页展示不作为运行时抓取源。

## LMM0 — 基线冻结与覆盖审计

- 冻结当前 DecisionCard、DayView、Dashboard、analysis-card、tracking、replay 的产品 hash。
- 冻结当前让球/大小球盘口身份、新鲜度和 ledger 分轨统计。
- 以当前赛季注册阵容、最近十场首发和最近五场实际出场为三个分母，重新计算每联赛：
  - 球员身份映射率；
  - 常用位置覆盖率；
  - 历史首发覆盖率；
  - 当前/赛前身价覆盖率；
  - 临场阵型与首发接口可用率。
- 禁止继续使用“所有历史球员中非空身价比例”代表首发覆盖率。
- 产出机器可读 `league_lineup_coverage.v1.json` 和人类可读审计报告。

验收：分母、赛季、数据版本和缺失原因均可追溯；provider call 为 0。

## LMM1 — 球员身份与估值映射

- 新增版本化球员 identity：API-Football player/team/league/season 与 Transfermarkt
  player/club/competition 的显式映射。
- 自动候选只能使用规范化姓名、球队、出生日期、国籍和位置；姓名不能作为唯一键。
- 一对多、跨队、出生日期冲突或转会时间冲突一律 `IDENTITY_CONFLICT`，禁止猜测。
- 人工补齐使用 append-only reviewed mapping；旧映射不覆盖，只关闭 validity window。
- 身价查询必须满足 `valuation.observed_at <= fixture.as_of`，禁止未来信息泄漏。
- 对五大联赛建立当前阵容缺失清单，目标是比赛当日正式首发 22/22 身份可解释、
  22/22 使用同一估值体系。

验收：重复导入幂等；冲突 fail closed；同一 as-of 查询确定性相同。

## LMM2 — 赛前常用阵容基线

- 只使用比赛开球前已存在的历史比赛，构建最近十场指数衰减基线。
- 为每名球员计算：
  - 最近十场/五场首发率；
  - 最近十场分钟占比；
  - 档案常用位置与逐场经验位置；
  - 各位置出场分布和位置多样性；
  - 队长/门将/中卫/后腰/组织者/中锋等关键角色标记。
- 为球队计算：
  - 常用首发十一人；
  - 常用阵型分布；
  - 门将、中卫组合、中场组合和锋线组合连续性；
  - 替补席位置覆盖和同位置替换深度。
- 样本不足返回 `BASELINE_INCOMPLETE`，不使用全局或未来比赛补齐。

验收：时间切片回放无泄漏；同一输入重复物化 hash 相同。

## LMM3 — 临场首发与阵型变化特征

- 将正式首发投影为版本化 `LineupSnapshot`，至少包含 fixture/team/player identity、
  starter/substitute、formation、provider position、grid/slot（如 provider 提供）、
  captured_at 和 provenance。
- 将临场首发与 LMM2 基线比较，生成：
  - `missing_regular_starters`；
  - `replacement_strength_delta_by_position`；
  - `out_of_position_count/severity`；
  - `formation_deviation`；
  - `lineup_continuity`；
  - `defensive_unit_disruption`；
  - `attacking_unit_disruption`；
  - `bench_depth_delta`。
- 阵型名称只表示结构，不直接把 `5-4-1` 等同小球、把 `4-3-3` 等同大球。
- T-60 开始检查，T-45/T-30 重试；正式首发变化产生新 snapshot 和新 artifact hash。

验收：门将缺席、中卫重组、无锋阵、球员客串和大轮换均有确定性测试。

## LMM4 — 让球与大小球的独立阵容影响

- 建立一个共享 lineup evaluator，但输出两个独立、有符号、有限幅的结果：
  - `lineup_ah_adjustment`：双方相对实力和让球覆盖方向；
  - `lineup_totals_adjustment`：预期总进球和比赛开放度方向。
- 初始权重只能通过固定离线快照和按时间切分评估确定，禁止人工写死“身价高必让球”。
- 普通变化保持小幅影响；主力门将、多名中卫、核心中场或主力锋线同时变化时允许
  触发高影响事件和重新计算。
- 身价使用同队/同联赛百分位、常用首发贡献和位置替代差，不把绝对欧元值直接当概率。
- 首发公布后比较盘口更新前后变化，用于判断信息是否已被市场吸收；不能把市场已完全
  反映的阵容信息重复计权。
- 首轮进入 shadow 对照，报告有/无 lineup adjustment 的 log loss、Brier/RPS、ECE、
  AH/OU 分市场 coverage、稳定性和 paired bootstrap 区间。

验收：未证明增量前不得替换 champion；不得扩大 RECOMMEND/lock。

## LMM5 — 多市场独立准入与择优

- 保留让球、大小球各自的 quote identity、freshness、model/market divergence、
  signal strength、lineup adjustment 和 data quality。
- 删除 `next(first PICK)` 造成的让球顺序优先。
- 引入可比较的 `market_decision_score`，只能比较已经通过本市场完整性门的候选。
- 选择规则：
  - 只有让球通过：主推荐让球；
  - 只有大小球通过：主推荐大小球；
  - 两者都通过：得分较高者为主推荐；
  - 次市场独立过更高门槛且相关性护栏通过时，可作为次推荐；
  - 两者都不通过：WATCH/NOT_READY，不制造 pick。
- 平分时使用显式确定性 tie-break，不再依靠数组顺序。
- correlation guard 阻止同一模型误差被包装成两个看似独立的推荐。
- `ANALYSIS_PICK` 可支持 AH/OU；正式 `RECOMMEND` 路径保持关闭且不在本阶段扩市场。

验收：AH-only、OU-only、both、neither、tie、conflict 六类契约测试全部通过。

## LMM6 — Decision Contract、比分与 Dashboard

- Decision Contract 增加主/次市场 provenance，但旧 wire 字段保持兼容。
- DayView、analysis-card、Dashboard、tracking、replay 和 ledger 读取相同的最终市场选择。
- 推荐比分按最终市场过滤：
  - AH：只保留满足选择方向和盘口结算语义的比分；
  - OVER：只保留总进球超过所选线的比分；
  - UNDER：只保留总进球低于所选线的比分；
  - 亚洲四分之一盘需按 WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS 正确分类。
- 没有最终 pick 时不显示“1万次模拟推荐比分”。
- 保持当前 Dashboard 布局，不恢复三场上限，不把技术字段放回首屏。
- 现有“盘口/市场概率”列显示真正被选中的 AH 或 OU；右侧证据说明阵容变化的具体原因，
  不只显示总身价。

验收：同一 fixture 跨端点的 tier、market、selection、line、比分和 hash 一致。

## LMM7 — 联赛分级政策

### 五大联赛严格门

- Premier League、La Liga、Serie A、Bundesliga、Ligue 1 设置
  `lineup_policy=REQUIRED`。
- 正式首发、阵型、22/22 identity、同源 valuation 和新鲜盘口任一缺失，统一
  `NOT_READY/WATCH`，不得产生分析 pick。

### 其他联赛增强门

- `A`：阵容身份/位置覆盖 >=90%，历史和临场首发稳定；首发可强增强，但本轮仍非硬门。
- `B`：覆盖 50%–90%；有首发则使用，缺首发仍可按其他完整信号产生分析 pick，必须
  标注“未确认正式首发”。
- `C`：覆盖 <50%；禁用球员身价与阵容强度数值，只用盘口、赔率新鲜度、xG、状态、
  伤停、主客场和已验证模型。
- 等级来自 LMM0 的机器审计，不写死对瑞典超、挪超、巴甲等联赛的主观结论。
- 临场首发到达后必须重算；高影响变化可以修改或撤销先前分析 pick。

验收：每个联赛都能解释为何 REQUIRED/A/B/C；覆盖下降自动降级，不静默继续。

## LMM8 — Gate、一次部署与稳定周期

### 本地与隔离 Gate

- 专项测试：identity、as-of、阵型、位置、AH adjustment、OU adjustment、市场择优、
  比分结算、跨端点和 ledger。
- 完整 pytest 不低于执行时最新基线；Ruff、Mypy、TypeScript、Web build、Playwright、
  acceptance、tracked-output、secret scan、`git diff --check` 全通过。
- 数据文件只在临时/隔离环境导入；验证原子发布、幂等、旧 schema 和缺失 artifact。
- 隔离 parity/predeploy 证明 public request 的 provider/model/global-reader 调用为 0。

### Staging canary

- 全阶段通过后只部署一次，不为每个小项分别部署。
- canary 前后冻结 release、四服务镜像、Alembic、provider、业务表、ledger、queue、
  lock/三轨、产品 hash、RSS 和 restart/OOM。
- scheduler canary 期间保持部署前约定状态；失败恢复 release、镜像、`current` 和
  scheduler 精确状态。
- 对五大 fixture 使用冻结/隔离样本验 strict gate；对当前在赛非五大 fixture 验证
  optional lineup 不错误阻塞。

### 三周期

- 这是数据契约和运行时决策变更，staging 接受后从 `0/3` 重新开始。
- 三个不同北京时间自然日 09:00 巡检必须使用同一 implementation SHA 和镜像。
- 任何身份、统计、运行时或市场选择修复再次清零；纯文案不清零。

## 完成定义

本计划只有同时满足以下条件才算完成：

- 五大联赛首发硬门和 22/22 可解释覆盖可验证；
- 其他联赛按真实覆盖等级运行且不会被统一首发门误伤；
- 让球不再因数组顺序优先，大小球可独立成为主推荐；
- 阵容变化对 AH/OU 的影响分开、有界、可回放、无未来泄漏；
- Dashboard 不改布局，显示的数据与最终 Decision Contract 一致；
- 全量 Gate、一次 staging canary 和随后三个稳定周期通过；
- `RECOMMEND`、lock、OFFICIAL、champion 和写入型 production 仍保持原状态。

