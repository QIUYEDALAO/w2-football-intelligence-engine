# W2-FACTOR-COHORT-FEASIBILITY

状态：`NO_USABLE_UNOBSERVED_EVALUATION_COHORT`

本报告只回答“有没有可用评估集”。未拟合系数、未写预注册、未实现新因子，未打开
HOLDOUT、已烧 cohort 或赛果评估产物。审计基线为
`1de3c1ef554d00a408577f59f4864e04f1d341da`。

## 1. 结论

**当前没有可用的、未被观察过的评估集。**

- 已有因子语料的 2026 HOLDOUT 已被观察，不能再充当终验集。
- 派发合同列明的 6,222 场未烧 Football-Data 池有市场价、xG 与赛果，但没有 W2
  所需的球队历史链，无法形成本任务八因子的 PIT 输入。
- F6 已在冻结预注册门下裁决为 `EXCLUDED_BY_PREREGISTERED_THRESHOLD`；不得因当前
  `factor_registry.v1.json` 仍写 `ACTIVE` 就重启。
- 本地实际赛程权威没有可用于从今天开始估速的 fixture：本地只读数据库
  `fixtures=0 / future fixtures=0`，且 14 个 competition profile 中只有
  `world_cup_2026` 配置为 enabled；该配置不含逐场 kickoff 清单。
- 所以 Q2 所需的样本目标 N 与实测合格比赛频率 r 都不成立。完成时间不是“约几个月”，
  而是 `NOT_IDENTIFIABLE / 0（不可计算）`。

## 2. 数据集边界

| 数据集/来源 | 球队历史 | 市场价 | 赛果 | 未观察 | 可用于本任务 |
|---|---|---|---|---|---|
| 已有因子语料 TRAIN 2024 / VALIDATION 2025 / HOLDOUT 2026 | 有 | 部分 | 有 | 否；2026 已观察 | 否 |
| F6 2022/2023 回补后的 9,094 场 | 有 H2H | 非本裁决所需 | 有 | 否；已执行并裁决 | 否；F6 冻结排除 |
| 6,222 场未烧 Football-Data 池 | **无 W2 球队历史** | 有 | 有 | 是 | 否；八因子输入不闭合 |
| 当前本地 runtime fixture authority | 无行 | 无行 | 无行 | 不适用 | 否；`fixtures=0` |
| 从 2026-09-02 起新前向 cohort | 尚未形成 | 尚未形成 | 尚未形成 | 是 | 当前不存在；需另行授权采集与冻结协议 |

“Football-Data 池未烧”只保护了市场/结果终验边界，不会凭空补出比赛前已知的球队历史、
阵容 first-seen、PIT 身价或 rating snapshot。把比赛按日期排序后临时从同一池重建历史，
也会改变该池的预定用途和数据合同，不能在本只读任务中把它升级为新因子终验集。

## 3. 八因子逐项可行性

### 3.1 `h2h(近5年)` / F6

- 输入：双方在 as-of 前五年内的直接交锋、kickoff、主客身份、90 分钟进球、稳定球队
  identity；每场必须可证明在目标比赛前已存在。
- 实现：`src/w2/features/team_factors.py:301 h2h_factor`；调用组装在
  `src/w2/features/engine.py:89`。当前实现读取 prior meetings 并以平均净胜球映射分数。
- 未观察 cohort：**无**。
- 冻结约束：强约束。2022/2023 回补已执行，TRAIN/VAL/HOLDOUT 覆盖为
  `60.33% / 74.12% / 79.03%`，TRAIN、三个 TRAIN 联赛与漂移门同时失败；状态保持
  `EXCLUDED_BY_PREREGISTERED_THRESHOLD`。不得降门槛、默认填补、零系数占位或借新名称重试。
- 冲突：`config/factors/factor_registry.v1.json:9` 的 `ACTIVE` 是落后于冻结裁决的旧状态，
  不构成授权。

### 3.2 `recent_ah_cover(赢盘率)` / F5

- 输入：每支球队 as-of 前的 canonical AH line、side、报价 identity、90 分钟赛果、
  quarter-line settlement（WIN/HALF_WIN/PUSH/HALF_LOSS/LOSS）及球队 identity。
- 实现：`src/w2/features/team_factors.py:151 recent_ah_cover_factor`；只接受
  `canonical_historical_ah_fact`，在 `:228-290` 做去重、冲突排除和 settlement→cover 映射。
- 未观察 cohort：**无**。已有 canonical 因子语料属于已观察链；6,222 池没有 W2 球队
  历史链，不能直接产生滚动 PIT rate。
- 冻结约束：受已观察 2026 HOLDOUT 与既有 canonical AH identity 合同约束；不得把
  普通赛果或 xG proxy 当 AH settlement。

### 3.3 `over_under_rate(大小球率)`

- 输入：每队历史 totals 主线、O/U side、quarter-line、成对赔率、capture/as-of、90 分钟
  总进球与五态 settlement；还需固定窗口和最小历史场数。
- 实现：**未实现**。仓库没有该因子定义或 FeatureSet 注册项。
- 工程成本：约 `3–5 人日`（数据合同与五态 settlement 1–2、PIT materializer 1–2、
  feature/test 1）；不含新数据等待、预注册与独立验收。
- 未观察 cohort：**无**。实现代码不会创造评估集。
- 冻结约束：不能读取/重分已观察 2026 因子 cohort；不能把 6,222 池改作新因子终验而不
  先取得新协议授权。

### 3.4 `ah_win_rate(让球胜率)`

- 输入：与 F5 相同的 canonical AH facts，但必须先冻结“胜率”是否含 HALF_WIN、PUSH
  分母和主客/受让方向；否则它只是 F5 的改名重复。
- 实现：**未作为独立因子实现**。现有 F5 是 cover/no-cover 差，不是另一个已定义的
  `ah_win_rate`。
- 工程成本：若复用 F5 canonical facts，约 `2–3 人日`（语义合同、单一计算、测试）；
  若另建盘口口径则 `4–6 人日`。不含数据等待。
- 未观察 cohort：**无**。
- 冻结约束：不得为制造“新因子”重解释已烧 F5 数据，亦不得把同一 AH fact 同时作为
  两个独立信号而不处理共线/重复计数。

### 3.5 `rest_fitness` / F3

- 输入：双方 as-of 前最近一场（更完整方案还需旅行、加时、轮换）的 kickoff；稳定球队
  identity。当前实现只用休息日差。
- 实现：`src/w2/features/team_factors.py:84 rest_fitness_factor`。
- 未观察 cohort：**无**。6,222 池没有球队历史，既有因子语料已观察。
- 冻结约束：受 PIT/as-of 与 2026 HOLDOUT 已观察边界约束；不能用目标比赛后的赛程回填。

### 3.6 `strength_form` / F7

- 输入：目标比赛前的 `TeamRatingSnapshot`，至少含 elo、attack strength、defence strength、
  form index、observed_at 与 provenance；底层需要球队历史。
- 实现：`src/w2/features/team_factors.py:352 strength_form_factor`；rating 生成参考
  `src/w2/ratings/elo.py:8 rating_from_history`。
- 未观察 cohort：**无**。
- 冻结约束：受 PIT rating snapshot、2026 HOLDOUT 已观察和 V2 挂起边界约束。不能在看到
  目标赛果后重算 rating 再回填。

### 3.7 `lineup(首发)` / F10

- 输入：官方确认首发、替补、阵型、captured_at/first_seen、历史预期首发 baseline、球员
  identity/position、PIT 价值、市场 snapshot 与赛果。
- 实现：`src/w2/lineups/intelligence.py:443 derive_lineup_change_features`，PIT valuation 选择
  在 `:627`，确认首发时间校验在 `:669`；离线 paired evaluation 接口在
  `src/w2/lineups/evaluation.py:36`，其最小门为 500 validation fixtures / 3 competitions。
- 未观察 cohort：**无**。历史首发内容可取，不等于历史 first-seen 可恢复；任务 3 已证明
  生产采集器尚未部署，当前没有新 temporal-availability cohort。
- 冻结约束：`config/evaluations/lmm_offline_increment.v1.json` 的 split/500 样本/2000
  bootstrap 协议已冻结，且 2026 HOLDOUT 已观察；不得复用其终验结论。

### 3.8 `squad_value(身价)` / F8

- 输入：目标 as-of 前的完整 roster membership、player identity、player valuation
  observation、球队/Transfermarkt club crosswalk 与 source hash；不能拿当前价值回填历史。
- 实现：`src/w2/features/team_factors.py:409 squad_value_factor`；严格 as-of materializer 在
  `src/w2/lineups/value_identity.py:264 materialize_team_value_asof`。
- 未观察 cohort：**无**。任务 4 的当前 `players.csv.gz` append/as-of 落地只证明当前快照
  可保存；不是历史 PIT valuation cohort，且启用范围为国家队而 R2 是俱乐部快照，映射链未闭合。
- 冻结约束：禁止当前身价历史回填；2026 HOLDOUT 已观察；V2 挂起期间不得借 F8 名义重启
  因子拟合。

## 4. Q1 / Q2 / Q3

### Q1 是否有未观察 cohort 同时具备球队历史 + 市场价 + 赛果？

**没有。** 当前可识别候选中，已观察因子语料不再未观察；6,222 池缺球队历史；新前向
cohort 尚未形成。

### Q2 从今天前向积累要多久？

**`NOT_IDENTIFIABLE / 0（不可计算）`，不能诚实给出天数。**

实测清点而不是“12 场/天”估算：

- `config/competitions/` 有 14 个 profile，仅 `world_cup_2026` 的 `enabled=true`。
- `world_cup_2026.v1.json:2-8` 只给 league/season；没有逐场 kickoff 清单。
- 当前本地只读 runtime DB：`league_profile=0`、`fixtures=0`、
  `kickoff >= 2026-09-02` 的 future fixtures 为 0。
- 本地 `CompetitionRegistry` 因 DB authority 空而 fail closed：
  `COMPETITION_DB_AUTHORITY_UNAVAILABLE`，不能把静态 14 个 profile 虚报成当前运行赛程。
- 本任务没有获授权调用 Provider，也没有可复核的生产 schedule snapshot，因此实际合格
  fixture/day 为 `0（不可计算）`，不是 12。
- 同时没有为这八因子冻结新的目标样本 N。公式只能写成
  `days = ceil(N / verified_eligible_fixtures_per_day)`；N 和分母都未识别。

要得到天数，至少先由独立任务授权并完成：启用哪些 competition、前向收集哪些输入、
冻结目标 N/分层/缺失规则，然后对真实 schedule 连续观察。那是新预注册任务，不在本任务范围。

### Q3 有不重开冻结裁决的现成评估路径吗？

**没有。** 对“八因子一起评估”尤其不存在：F6 本身已冻结排除。对其余七因子，未来全新
prospective cohort 在概念上可以避免复用已观察 HOLDOUT，但今天尚未存在，也未获预注册、
采集或启用联赛授权，所以不能把“未来可能建立”写成当前可用路径。

## 5. 与 V2 的关系

这不是与 V2 无关的新方法。V2 的核心问题正是多因子输入、PIT materialization、冻结切分、
独立评估与是否进入数值模型。本任务只是用更便宜的只读审计先回答“有没有终验集”，没有
提供新的识别策略、数据源或未观察 cohort。

因此：

- V2 仍是挂起，不是取消；本报告不删除其资产。
- 本报告也不以另一个任务名重开 V2。
- 若未来建立新 prospective cohort，仍需新的方法学授权与冻结协议；不能沿用已观察 2026
  HOLDOUT，也不能覆盖 F6 现有裁决。

## 6. 治理冲突与后续门

`config/factors/factor_registry.v1.json:9` 的 F6 `ACTIVE` 与后置冻结裁决冲突；按本任务合同，
有效状态必须是 `EXCLUDED_BY_PREREGISTERED_THRESHOLD`。本 docs-only 任务不改 registry，
但任何未来 runtime/研究入口都不得把该旧字段解释为重新启用。

若 Owner 以后只要求七个非 F6 因子的全新前向评估，最低前置门是：

1. 明确不含 F6，且不读取已观察 HOLDOUT。
2. 冻结 competition、PIT 输入、市场/赛果口径、样本 N、分层与缺失规则。
3. 先证明 lineup first-seen 和 historical valuation 真正被前向保存。
4. 以真实 eligible fixture/day 更新耗时，不复用 12 场/天。

这些是未来授权条件，不是本报告的实施建议或预注册草案。

## 7. 验证结果

- 定向因子/lineup/competition 测试：`50 passed`
- canonical：`18 passed`
- package matrix：`5 passed`
- Ruff：`PASS`
- 全量：`2950 passed / 9 skipped / 4 failed`
- 父提交 `1de3c1ef` 相同 4 node ID：`4/4` 原样失败
  - Compose 2 个：本机缺 Compose 子命令
  - staging parity 2 个：macOS Docker UID/GID 行为差异
- 任务相关失败：0

## 8. Stop-line 对账

- 拟合：0
- 预注册：0
- 代码实现/修改：0
- HOLDOUT / 已烧 cohort 读取：0
- Provider 调用：0
- 生产写：0
- ledger：0
- migration：0
- 部署：0
- 参数 / `CALIBRATION_VERSION`：0
- GitHub / GHCR：0

本报告不改变 calibration authority；identity 仍为
`21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`，verdict 仍为
`APPROVED_VALIDATED`。
