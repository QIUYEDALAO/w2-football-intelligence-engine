# W2-FACTOR-INCREMENTAL-INFO-MEASURE 预注册

状态：`FROZEN_BEFORE_FIRST_MEASUREMENT`

冻结时间：`2026-09-02T19:00:37Z`。本文件与同目录 JSON 必须先形成独立 docs-only commit，之后才允许读取任何本任务结果。

## 问题与族

本任务只问四个因子能否改善当前生产 λ 的 1X2 概率质量，不要求因子含有“市场不知道的信息”。族固定为：`F3_REST_FITNESS`、`F5_RECENT_AH_COVER`、`F1_MARKET_MOVEMENT`、`F2_BOOKMAKER_INTENT`；族大小固定为 4，不增删。单因子 α=0.05，Bonferroni 后 α=0.0125。

主指标是 multiclass Brier；次指标是 log-loss、classwise 10-bin ECE，以及 one-vs-rest Brier 分解的 reliability/resolution。改善定义为 `baseline - candidate`，正数有利。

## 划分与 one-look

- TRAIN：2024 calendar year，只用于模型/方向筛选。
- VALIDATION：2025 calendar year，只确认一次。
- HOLDOUT 2026：完全不读。
- `historical_replay_cutoff=2026-08-21T19:18:10.674088Z` 不变。
- penaltyblog 已烧的 2012/13–2016/17 永不作为 holdout。

复用 F6 的物理日历边界与目标 fixture identities，但不读取 F6 字段、F6 结果或 F6 既有评估。因此不消耗 F6 的 one-look 预算；本任务单独消耗四个列明因子的 TRAIN 筛选与一次 VALIDATION 确认。每个因子使用自己的 complete-case paired cohort；不以均值、默认值或先验填补。TRAIN 少于 300 或 VALIDATION 少于 100，直接 `FAIL_NOT_MEASURABLE`。

## 冻结模型

基线为当前 `calibrate_lambdas` 默认参数，optional Elo/身价/首发输入为空或关闭；由严格 PIT 四字段 xG 产生 λ，再以 0..10 球 exact independent Poisson 矩阵聚合 HOME/DRAW/AWAY。

每个因子只有一个标准化标量 X 和一个系数 β，无截距、交互、特征工程或超参搜索。F5、F1、F2 只允许进入 home-away `delta` residual。F3 预先允许 `delta` 或 `total` 两种轴，用固定五折 TRAIN fixture-cluster OOF Brier 选择，完全相同则选 `total`；VALIDATION 不参与选择。β 只在训练数据上用固定区间和固定迭代的确定性 golden-section log-loss 最小化估计；命中边界只报告，不扩区间重跑。

F3 的 X 是 `clip((home_rest_days-away_rest_days)/4,-1,1)`；F5 是 canonical AH facts 的双方 cover-rate 差；F1 是 AH open-to-current movement score；F2 是 AH intent signal strength 按 HOME/AWAY 加正负号，BALANCED/CONFLICTED 为真实 0，证据不足或泄漏阻断为 missing。

## 推断与停止

VALIDATION 上按 fixture ID 成簇做 10,000 次 paired bootstrap，seed `20260903`；每个 fixture 的三类分量始终一起抽样。单侧 95% 下界为改善分布的第 5 百分位；p=`(1 + 改善<=0 的次数)/(10000+1)`。

PASS 必须同时满足：Brier 点改善为正、单侧 95% 下界 >0、p<0.0125。其余全部 FAIL。完成一次即停止，不因结果不理想改变族、划分、标量、方向、模型、缺失规则、指标、bootstrap 或门槛。

完整机器可读合同以 `PREREGISTRATION.json` 为准。
