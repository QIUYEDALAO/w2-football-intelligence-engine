# F0 报告 —— AH 四因子方向准确率主线的范围与证据冻结

```text
TASK_ID      W2_AH_FACTOR_ACCURACY_F0_SCOPE_AND_EVIDENCE_FREEZE_20260910
主线         AH-FACTOR-ACCURACY-V1     当前 F0，下一 F1
FINAL_STATE  F0_ACCEPTED_F1_BLOCKED_BY_MATRIX
```

## 1. 148 条里哪些是 LOSS

```text
LOSS        66      HALF_LOSS   8
WIN         55      HALF_WIN    6
PUSH       13      合计       148
```

逐条名单在 `OFFICIAL_148_LOSS_WIN_ROSTER.jsonl`（148 行，不是摘要），
每行含 `evaluation_id / fixture_id / kickoff_utc / 主客队中文名 / market /
selection / exact_line / score / settlement / profit_units / is_ah_factor_scope`，
可直接按任一字段筛出五种结算与两个市场。

## 2. 哪些属于 AH，哪些属于 TOTALS

```text
                行数    LOSS  HALF_LOSS  WIN  HALF_WIN  PUSH    盈亏
ASIAN_HANDICAP    84      34       8      32      6       4    -8.655
TOTALS            64      32       0      23      0       9   -11.720
合计             148      66       8      55      6      13   -20.375
```

AH 84 条的方向分布：`AWAY 55 / HOME 29`；盘口从 `-0.5` 到 `+2.75` 共 13 种。

TOTALS 一条半输半赢都没有，但**不是因为没有四分之一球盘**——这批里有 10 条
（2.25×2、2.75×3、3.25×4、3.75×1）。逐条核对后原因是：四分之一盘只有在总进球
恰好落在靠近的那条半球线上才会半结算，而这 10 场的总进球没有一场落在那个点上
（例：2.75 盘需要总进球恰为 3，实际是 1 和 6）。这是样本巧合，不是盘口性质，
不应写成"TOTALS 不会半结算"。

**亏损的大头在 TOTALS**（-11.72 对 -8.655），但四因子调权只能碰 AH 那 -8.655。
这一点必须在 F2 之前记住：**修好 AH 方向也解释不了一半以上的亏损。**

## 3. 为什么 TOTALS 不能纳入四因子调权

F3/F5/F6/F9 产出的是**主客方向**信号——体能差、近期让分覆盖、交手历史、真实 xG 差，
四者都在回答"哪一边更强"。TOTALS 的方向是 OVER/UNDER，问的是"总进球会不会超过某条线"。
把主客强度权重套到大小球上，等于用一个不适用的坐标系解释结果：
即使拟合出来数字变好，那也只是过拟合，不是发现。

因此 TOTALS 64 条在 roster 里标 `is_ah_factor_scope=false` 保留在册，
但**不进入** `AH_84_FACTOR_MATRIX_READINESS.jsonl`（有测试锁定该文件恒为 84 行，
且 64 个 TOTALS `evaluation_id` 与矩阵交集为空）。
TOTALS 的 32 条 LOSS 需要单独的 xG / lambda / 市场链诊断，那是另一条线的任务。

## 4. AH 84 条的分层

```text
全输 LOSS        34      半输 HALF_LOSS    8
全赢 WIN         32      半赢 HALF_WIN     6
走盘 PUSH         4
```

即 AH 的**决胜局**（排除 4 条走盘）为 80 条，其中获得正收益的 38 条、负收益 42 条。
按 graded 口径（半赢计 0.5）命中率为 43.75%，与全体 42.96% 接近，
**AH 并没有比 TOTALS 明显更差**——这也是"AH 方向不是唯一问题"的第二个提示。

### 埃尔切 vs 皇家社会（必须单列）

```text
fixture_id      1570366
UTC kickoff     2026-09-07T19:30:00Z
北京时间        2026-09-08 03:30
market          ASIAN_HANDICAP
原推荐          主队 +0.25（selection=HOME, exact_line=0.25, decimal_odds=1.99）
确认检查点      T-60m
实际比分        2-3
结算            LOSS，profit_units = -1.0
evaluation_id   dqe-e29e2309d353103e3908b8052320f6df64c6fd4e579c5c3560477c34b1c990d9
```

**可以列为失败案例。** 主队让 0.25 球输 2-3，方向判错，没有争议。

**但不能据此反推"应该给客队多少权重"。** 理由不是保守，是证据不存在：
这一场的 F3/F5/F6/F9 赛前分数、状态、权重、参与情况在冻结证据里全部是
`NOT_RECONSTRUCTIBLE`（见 §5）。在不知道当时四个因子各自说了什么的情况下，
任何"把客队权重调高 X"的结论都只是在拟合这一个已知结果——
那正是 §禁止事项 里的逐场结果泄漏。

## 5. 四因子历史分数和权重能不能重建

**不能。**

```text
FACTOR_MATRIX_STATUS = NOT_RECONSTRUCTIBLE_FROM_FROZEN_148
84 / 84 行 matrix_row_status = NOT_RECONSTRUCTIBLE
EXACT_PIT_RECONSTRUCTIBLE = 0
SOURCE_ONLY_POST_CAPTURE  = 0
```

证据本身就是这么写的，不是我推断的。冻结包 148/148 行里：

```text
factor_disposition       = UNKNOWN_NOT_RECONSTRUCTIBLE   148/148
factor_direction         = NOT_RECONSTRUCTIBLE           148/148
factor_weights           = NOT_RECONSTRUCTIBLE           148/148
factor_participants      = NOT_RECONSTRUCTIBLE           148/148
factor_veto_code         = NOT_RECONSTRUCTIBLE           148/148
factor_verdict_identity  = NOT_RECONSTRUCTIBLE           148/148
factor_absent_reasons    = NOT_RECONSTRUCTIBLE           148/148
```

根因是已经查实并已修复的那个缺陷：生产的 `dynamic_prematch_evaluations`
payload **从未写入过任何因子字段**（全表 `ilike '%factor%'` 命中 0 行），
分析卡又是读时投影、库里没有对应表。因子裁决的持久化是在
`7bc1f73b` 才补上的——**那之后写入的评估才会有身份，这 148 条在那之前**。

所以矩阵里 84 行 × 4 因子 × 6 个字段全部写 `NOT_RECONSTRUCTIBLE`，
**没有一个 0，没有一个用当前注册表权重（33.33/16.67/16.67/33.33）顶替，
没有一个从赛果反推**。生成器有 AST 测试锁定：计算因子格子的函数
不读取行里的任何字段，能产出的值只有缺失标记或固定因子名。

## 6. F5 捷报数据现在算什么

```text
F5_SOURCE_STATUS = NOT_INGESTED_POST_EVENT_SOURCE_NOT_PIT_PROVABLE
```

四选一里它既不是"已验证"也不是"可重建"，而是**尚未接入的事后来源**：

- **不是已验证**：本任务没有抓取，冻结包里没有任何 F5 原始值或来源 hash；
- **不是可重建**：捷报页面是赛后页面，页面上"近期让分覆盖"的统计随时间滚动，
  今天抓到的窗口不等于 `evaluated_at` 当时的窗口；
- **是事后来源**：它能提供数据，但要作为赛前证据使用，必须先冻结来源合同、
  身份、盘口符号、结算口径和 PIT 合同，并能证明取到的值在预测时点之前可见。

在此之前把捷报接进来，就是"事后页面冒充当时赛前证据"，F0 合同明令禁止。

## 7. 为什么不能直接按输局调权

三条独立的理由，任何一条成立就足够：

1. **没有自变量。** 调权是调 F3/F5/F6/F9 的相对份额。这 84 条里四个因子当时各自
   给了什么分、参没参与、权重是多少，全部不可重建。不知道输入就调系数，
   调的不是模型，是结果。
2. **那是逐场拟合，不是校准。** "让这 34 条 LOSS 翻过来"必然要求每场朝不同方向推，
   而权重是一套全局参数。能同时把 34 条 LOSS 翻正又不破坏 32 条 WIN 的全局权重，
   如果存在，必须是搜出来并在时序 holdout 上验住的；直接按输局改，
   得到的一定是过拟合。
3. **AH 只占亏损的 42.5%。** -8.655 / -20.375。把 AH 方向调到完美，
   剩下 TOTALS 的 -11.72 一分不动。以为调权能解决亏损，是范围上的误判。

## 8. F1 的进入条件

F1 必须对 AH 84 条逐场产出可审计的赛前矩阵，每场每因子六项齐全：
signed score、status、原始 weight、参与状态、证据时点（须早于 `evaluated_at`）、来源 hash。

按当前证据，**F1 无法从这 148 条冻结数据开始**——矩阵 84/84 不可重建。
可行的路只有两条，都需要 Owner 另行授权，本任务不选择也不启动：

- **A｜前瞻采集**：用已修复的因子持久化链，从今往后记录新的正式候选，
  攒够样本后在真实赛前身份上做 F1。代价是等待，好处是 PIT 天然成立。
- **B｜历史重建可行性调查**：先证明存在某个独立、可 PIT 证明的来源，
  能还原这 84 场当时的四因子输入。在证明之前，B 不是任务而是假设。

## 9. F2/F3 为什么必须等 F1

F2 是全局权重搜索，F3 是时序 holdout 验证。两者都以 F1 的矩阵为唯一输入：

- 没有 F1，F2 没有自变量可搜，只能对着结算标签搜——那是直接拟合赛果；
- 没有 F1，F3 无法划分"训练期/验证期"，因为因子值本身没有时点，
  也就无法判断某个值在验证期是否属于未来信息。

所以顺序不是流程偏好，是依赖关系：`F1 → F2 → F3`，中间不能跳。
在 F1 通过前启动 F2 权重搜索或 F3 holdout，产出的任何数字都不可采信。

## 10. 本阶段终态

```text
FACTOR_MATRIX_STATUS      = NOT_RECONSTRUCTIBLE_FROM_FROZEN_148
WEIGHT_CALIBRATION_STATUS = BLOCKED_BY_FACTOR_MATRIX
FINAL_STATE               = F0_ACCEPTED_F1_BLOCKED_BY_MATRIX
```

F0 的交付是完整的：范围冻结、口径复算、148 条逐条名单、84 行矩阵就绪度评估。
结论是 F1 目前被证据挡住。这是合法终态，不是任务失败，
也**不是** `MODEL_CANDIDATE_READY`——F0 不产出候选。
