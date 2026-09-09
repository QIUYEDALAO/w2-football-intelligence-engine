# F1 报告 —— AH 四因子历史重建可行性调查

```text
TASK_ID          W2_AH_FACTOR_ACCURACY_F1_READINESS_20260910
PARENT_COMMIT    f5dd9c23cf90cd836139bacbde559421f6dd59a2
F1_FINAL_STATE   F1_NOT_RECONSTRUCTIBLE_FROM_FROZEN_148
F2_ALLOWED       false        F3_ALLOWED  false
```

## 1. 结论

调查了 **27 个候选来源**，形成 336 行矩阵：

```text
EXACT_PIT_RECONSTRUCTIBLE      0
SOURCE_ONLY_POST_CAPTURE     264      （66 条 evaluation × 4 因子）
NOT_RECONSTRUCTIBLE           72      （18 条 evaluation × 4 因子）
```

**没有任何一行能被证明为 evaluated_at 当时的历史因子值。**

## 2. 三个必答问题

### Q1：是否存在独立来源保存了当时的六项？

**否。** 没有任何来源同时具备 signed score、status、original weight、
participated、evidence_time 与 source_hash。

逐项看，最好的情况是"两个来源各有一半，但没有一个能对齐到评估时刻"：

| 来源类型 | 覆盖 | score | weight | participated | evidence_time | 绑定 evaluation |
|---|---:|:-:|:-:|:-:|:-:|:-:|
| 按 evaluation 键控的诊断 | 66/84 | 否(全 null) | 否 | 否 | 否 | **是** |
| 赛前分析卡归档（t5） | 9/84 fixture | **是** | **是** | **是** | 否 | 否 |
| 源码权重默认值 | 全部 | 否 | **是** | 否 | 是（提交时间） | 否 |

**没有一行的六项能凑齐**，因为最关键的 `evidence_time` 在所有来源里都不存在：
逐因子证据时点从未被序列化。代码里 `FeatureContribution` 确实有 `observed_at`
字段（`team_factors.py` 的 F3 会写入），但分析卡的 `feature_contributions`
序列化里没有这一项——实测其可用字段为
`collection_status / coverage_profile_status / id / inputs / is_independent_signal /
proxy_of / score / side / source / source_group / status`，**没有 observed_at**。

### Q2：能否证明每个 evidence_time 严格早于 evaluated_at？

**不能，因为 evidence_time 本身不存在。**

唯一能测的是来源的**文件级/检查点级**时点，两类都不合格：

- **按 evaluation 键控的诊断**：其 `latest_checkpoint.created_at` 在
  **66/66** 条 AH 上都 **晚于或等于** `evaluated_at`（已逐条实测，非抽样）。
- **赛前卡归档**：9 场里最好的一批早于 `evaluated_at` **66–68 小时**。
  严格说满足"早于"，但那是三天前的另一次观测，不是评估当时的值——
  三天里对手打了别的比赛，F3 休息天数、F9 xG、F7 状态都会变。
  且这些卡**不含任何 `dqe-` 评估身份**（实测 430 张卡中与我们 AH 评估绑定的为 **0** 张），
  无法证明它就是那次评估用的输入。

### Q3：能否形成完整、可审计的 84 × 4 矩阵？

**能形成矩阵，但不能形成可用于 F2 的矩阵。** 336 行齐备且可审计，
每行都写明了来源、来源 hash、provenance 与不可估计原因；
但 exact PIT 行数为 0。

## 3. 为什么会这样：机制已在代码中确认

因子分数存在 `read_model_checkpoint.payload` 里，而该表：

```text
src/w2/infrastructure/persistence/api_models.py:15
  UniqueConstraint("checkpoint_key", name="uq_read_model_checkpoint_key")

src/w2/prematch/read_model_projection.py:1190-1215
  按 checkpoint_key 查已存在行；存在则就地覆盖 payload
```

**每个 fixture 只有一行，每次重新投影就地覆盖。** 赛后刷新会把赛前的
`factor_score` 直接写掉。这不是丢数据的意外，是这张表的设计。

这一点在 2026-09-04 的 T8a 任务里已被识别并触发了应急归档
（`~/Desktop/W2文档/w2-t5-evidence/tier0_archive/`），原文写着
「赛后刷新可能覆盖赛前 factor_score……今晚这批是第一批暴露面」。
那次归档只抢救了当晚 T5 窗口的比赛，**不覆盖我们这 84 条中的 75 条**。

诊断文件的实测数据正是这个机制的直接证据：66/66 条 AH 的检查点
`created_at` 都晚于 `evaluated_at`，且四个因子的 `score` 全部为 `null`。

## 4. 一个重要的旁证：那时四因子基本没有数据

按 evaluation 键控的诊断（覆盖 66/84）显示，在它读到的那个检查点上：

```text
F3_REST_FITNESS     INSUFFICIENT_DATA   66/66
F5_RECENT_AH_COVER  UNAVAILABLE         66/66
F6_H2H              UNAVAILABLE         66/66
F9_TRUE_XG          UNAVAILABLE         66/66
```

**证据等级说明**：这是**赛后检查点**的状态，不能直接当作 evaluated_at 当时的状态。
但它值得记录，因为它指向一个对整条主线更重要的可能性：
**这 148 条候选可能根本不是"四因子给错了方向"，而是"四因子当时没有参与"。**

这与 F0 已确认的链路事实一致：这 148 条走的是动态候选链，
而该链在 `7bc1f73b` 之前**从不查询因子分数**，准入完全由经济条件决定。
换句话说，因子是否给出方向，对这 148 条的发出与否本就没有影响。

**这只是假设，不是结论。** 要证实它，需要的是前瞻数据，不是历史重建。

## 5. 埃尔切 vs 皇家社会：唯一有赛前卡的失败案例

fixture `1570366`，我们的推荐是主队 +0.25 @1.99，评估于
`2026-09-07T18:32:34Z`（T-60m），实际 2-3，LOSS。

2026-09-04T22:00:29Z 的赛前卡归档里有这场：

```text
participants   F3_REST_FITNESS  +0.25   weight 0.10
               F6_H2H           +1.00   weight 0.05
               F7_STRENGTH_FORM +0.0294 weight 0.18
               F9_TRUE_XG       +0.045  weight 0.10
absent         F4 READY / F5 INSUFFICIENT_DATA / F8 UNAVAILABLE
direction      AWAY      margin -0.035349      weight_sum_used 0.43
factor_veto    FACTOR_EV_DIRECTION_CONFLICT   ev_selection=HOME  factor_direction=AWAY
```

**因子指向 AWAY，EV 指向 HOME，因子否决已触发，最后 AWAY 赢了。**

这是对"因子否决被绕过"这一主线假设的一次正面佐证。但必须同时说清它证不了什么：

1. 卡的时点是 **09-04 22:00**，评估是 **09-07 18:32**，相差 **68.5 小时**。
   这不是评估当时的因子状态。
2. 卡里没有 `dqe-` 评估身份，无法证明它与那次评估是同一份输入。
3. `margin` 只有 **-0.035**，是极弱的方向信号；把这样一个数当作"应该反向"的依据，
   属于对噪声过度解读。
4. **n=1。** 一场对上了，不构成任何权重结论。

所以这一场在矩阵里仍是 `NOT_RECONSTRUCTIBLE`，快照值只进
`snapshot_only_*` 列，不进历史列。

## 6. 已登记并排除的来源（27 个，完整清单见 F1_SOURCE_INVENTORY.jsonl）

```text
FROZEN_CORPUS (2)                 148 条语料本身；manifest 的 factor_* 全是 NOT_RECONSTRUCTIBLE
EVALUATION_KEYED_DIAGNOSIS (2)    覆盖 66/84，仅 status，score 全 null，读取时点在评估之后
PREMATCH_ANALYSIS_CARD_ARCHIVE(17) 真实赛前 factor_score，含 score/weight/participated，
                                  但仅覆盖 9/84 fixture、无逐因子证据时点、无评估绑定
REGISTRY (2)                      因子注册表与角色矩阵：只有生命周期/角色，无数值权重、无逐场值
SOURCE_CODE_DEFAULT (2)           F3=0.10 F5=0.05 F6=0.05 F9=0.10，自 2026-07-25 未变，
                                  早于全部 148 次评估；但这是"默认参数"，
                                  不是"该次评估实际生效的权重"，且无 participated 就无意义
LOCAL_SQLITE (1)                  7 个本地库全部 0 字节、0 表；读取前后 SHA-256 未变
PRODUCTION_DATABASE (1)           未访问（本执行令 PRODUCTION_DB_READS=0）；
                                  且 read_model_checkpoint 就地覆盖，赛前值已不存在
```

## 7. 为什么不能就这样进 F2

F2 是全局权重搜索，自变量是四因子的 signed score 与 participated。
现在 336 行里这两项的可用数为 **0**。

在没有自变量的情况下做权重搜索，唯一还能拟合的目标就是结算标签本身——
那不是校准，是直接对赛果拟合。这也是本任务反复设防的原因：
`matrix_rows()` 不接触 settlement/score/profit，且**翻转全部 84 条结算后重跑，
336 行输出逐字节不变**。

## 8. 往前只有两条路

**A｜前瞻采集（推荐）**
因子裁决的持久化已在 `7bc1f73b` 修好并通过验收。从今往后新写入的评估会带
逐场因子身份。攒够 AH 样本后，F1 可以在真正的赛前身份上重做。
代价是等待；好处是 PIT 天然成立，不需要任何重建假设。

**B｜历史重建（当前证据下不可行）**
要让 B 成立，必须同时满足三件事，缺一不可：

1. 存在一个**逐因子**证据时点（今天任何来源都没有）；
2. 存在能把该值绑定到具体 evaluation 的身份（今天 0/430 张卡有）；
3. 覆盖率足以支撑权重拟合（今天最好的赛前卡只有 9/84）。

在这三件事被证明之前，B 是假设不是任务。

**一个可以立刻做、且不需要新授权的补充建议**：把 T8a 那种赛前归档变成常态化的
append-only 快照（含逐因子 `observed_at` 与 evaluation 绑定），
这样"因子被覆盖"这个问题不会在下一批候选上重演。是否执行由验收方裁定。

## 9. 终态

```text
F1_FINAL_STATE            = F1_NOT_RECONSTRUCTIBLE_FROM_FROZEN_148
F2_ALLOWED                = false
F3_ALLOWED                = false
WEIGHT_CALIBRATION_STATUS = BLOCKED_BY_MATRIX
```

F1 的交付是完整的：来源已穷举登记、矩阵 336 行齐备可审计、机制已在代码中定位。
结论是历史重建这条路在当前证据下走不通。这是合法终态，不是任务失败。
