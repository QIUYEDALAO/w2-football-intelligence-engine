# SCHED-PEAK-02 — 单任务耗时归因

## 结论

巴甲 8-plan 任务的 `548.38s` 不是 Provider 慢，也不是 13×13 精确比分矩阵慢。主因是投影写链对 6 个 source event 执行了两轮完整 build；每轮 build 又各算两次 analysis card，因此总计 **24 次完整分析、1,097 次 SQL**。post-write rebuild 与初次 build 几乎等价昂贵：coverage 下分别 `271.921s` 与 `267.618s`。

同一冻结输入、同一镜像和同一隔离数据库上：plain `518.490s`，coverage `540.385s`，墙钟倍率 `1.042229×`；CPU `135.083s → 159.143s`，倍率 `1.178112×`。coverage 完整演练复现了生产 `548.38s` 的 `98.5421%`，仅少 `7.995s`，其余是本演练刻意不执行的本地 clone 写入/commit 与运行噪声。因此 08-28 撤 coverage 只能回收次要开销，不能解决单任务设计成本。

## 冻结批次与可复现边界

- authority：release `d05ab74217e37af2e85732ac3a63ee4d9e214aa1`，image `sha256:c6015c...79e271`，schema `0070_notification_delivery_routing`。
- 输入：08-23 18:30Z 巴甲 8 plans；实际产生 6 个投影事件（5 个 `ODDS_CHANGED`、1 个 `LINEUP_CHANGED`）。另外两个 lineup 响应为空，不产生事件。
- PIT：event time 固定为原 capture time，materializer `projected_at` 也固定为 `2026-08-24T00:00:00Z`。
- 完整只读投影契约：`build → validate → rebuild → validate`。这覆盖生产 write path 的全部计算和读取，只排除对隔离 clone 的 evaluation/checkpoint 写入与 commit。
- plain 与 coverage 六个 artifact hash 逐个一致；任一不一致时 assemble 直接失败。
- Provider `0`、outcomes 读取 `0`、生产数据库写入 `0`、部署 `0`。

## 逐段耗时

以下 stage 是嵌套计时，不能相加；例如 simulation 与 matrix 包含在 analysis card，SQL 又分布在两轮 build 中。

| 阶段 | calls | plain s | coverage s | 倍率 | 判定 |
|---|---:|---:|---:|---:|---|
| 完整批次 | - | 518.490 | 540.385 | 1.0422× | coverage 增加 21.895s |
| 初次 artifact build | 6 | 259.213 | 267.618 | 1.0324× | 第一半完整投影 |
| post-write rebuild（只读等价） | 6 | 258.425 | 271.921 | 1.0522× | 与初次 build 同量级，属重复成本 |
| 数据库 driver | 1,097 | 389.491 | 388.069 | 0.9963× | 约占 coverage 总墙钟 71.8%；差异为运行噪声 |
| analysis card | 24 | 16.215 | 34.030 | 2.0987× | coverage 明显放大 Python 分析链 |
| simulation | 24 | 2.318 | 6.688 | 2.8852× | 仍非总耗时主项 |
| 13×13 exact matrix | 24 | 0.047 | 0.208 | 4.3899× | 倍率高但绝对仅 0.208s |
| 10,000 deterministic sampling | 24 | 0.134 | 0.393 | 2.9355× | 绝对仅 0.393s |
| dynamic evaluation projection | 24 | 0.001 | 0.003 | 2.1464× | 可忽略 |
| artifact validation | 12 | 0.849 | 0.843 | 0.9931× | 纯校验不慢 |
| canonical hashing | 52,436 | 2.852 | 3.424 | 1.2005× | 次要；调用数显示 payload 很大 |
| canonical serialization | 24 | 0.326 | 0.316 | 0.9673× | 次要 |

按 8 plans 摊分：plain `64.811s/plan`，coverage `67.548s/plan`，生产 `68.548s/plan`。Provider 最大仅 `335ms`，且生产最后 Provider response 后仍有 `545.005s`，与本轮 coverage 完整投影 `540.385s` 对齐。

## 为什么会有四次 analysis card

每个 source event 的 initial build 先计算 projected card，再用相同冻结输入计算 read-time reference，形成 shadow reconciliation。进入 `write_frozen_analysis_artifacts` 后，draft 先校验并写 evaluation；随后为了验证写后 source identity 没漂移，materializer 在 session 内完整 rebuild，rebuild 又重复 projected/read-time 两次计算。

所以放大链为：

`6 events × 2 builds/event × 2 cards/build = 24 analysis cards`

冻结演练还测得：

`1,097 SQL / 6 events = 182.83 SQL/event`，即每轮 build 约 `91.42 SQL/event`。

两轮 build 的输出 hash 在冻结、无写场景下完全一致，但当前实现仍支付两轮完整读取成本。

## 异常性判定

单任务耗时异常，扩容只能止血：

- 无 coverage 仍需 `518.49s`，已经占 900 秒正式窗口的 `57.6%`；coverage 不是根因。
- 同时段六个串行任务生产总计约 `1,383s`，天然超过 900 秒窗口。
- post-write rebuild 耗时是 initial build 的 `101.6%`，说明一致性校验实现成了第二次完整生产，而不是有界校验。
- 13×13 矩阵、采样、序列化均已被排除为主瓶颈；优化它们不会 materially 改变容量。

代码中没有一条明确的单任务 latency SLO，但 claim lease 与业务窗口共同给出了硬上界。一个联赛批次在无排队时就消耗过半窗口，且成本随 event 数线性增加，不符合峰值槽设计需要。

## 优化方向（本轮不实现）

1. 保留 shadow reconciliation，但让同一 build 的 projected/read-time 两次计算共享冻结 repository read set；不得降低 PIT 或一致性检查强度。
2. 重构 post-write 校验：只重读会受 session 写入影响的 lifecycle/identity 字段，或复用同一冻结输入并对受影响字段做定向验证；避免再次执行整张 analysis card。任何方案必须证明 artifact/source hash 与现合同一致。
3. 按 task 批量预取 fixture-scoped observations、xG、ratings、values、lineup 与 registry authority，再按 event time 做 PIT 选择；避免每 event、每 card 新开同形查询。
4. 在 worker 增加 `initial_build / validation / post_write_rebuild / SQL count` 指标。先证明查询数与 wall 同时下降，再讨论矩阵微优化。

## 08-28 coverage 撤除后的容量重测

不得早于 `2026-08-28T04:37:34Z`，先确认 worker command line 已无 `coverage run`。`concurrency=2` 在此之前和重测期间只记作临时止血值，不写长期基线。

重测使用同形 18:30Z 峰值槽，原样记录 due plan 数、联赛分组、event 数和档位，不用低负载槽替代。至少记录：queue、claim→finish、task wall、per-plan、window margin、worker CPU/RSS、DB connections/query time、Provider calls/max latency、claim identity mismatch 与各档位终态。先观测临时 concurrency=2 的真实峰值，再用冻结 replay 比较 1/2 worker，不在线上来回切容量。

长期值只在无 coverage 的多个可比峰值均满足以下行为条件后由 Owner 裁定：T-30 全部在窗口内终态、无 lease/claim identity mismatch、queue+run 有正 margin、内存/DB 连接/Provider burst 未越运行边界。当前证据不授权任何长期 concurrency 数字。
