# W2-F5-F1-F2-SCREENING 预注册

状态：`FROZEN_BEFORE_FIRST_MEASUREMENT`

冻结时间：`2026-09-03T02:12:25Z`。本文件与同目录 JSON 必须先形成独立 docs-only
commit；该 commit 之前不得读取任何业务数据。

## 性质与结论边界

本任务是 **SCREENING ONLY，不是确认**。结论只回答 F5/F1/F2 是否值得进入未来确认，
不得作为准入依据，不得据此接入任何因子。干净确认集是开球时刻晚于
`2026-08-22` 的 fixture，本任务一行都不读取。

族固定为 `F5_RECENT_AH_COVER`、`F1_MARKET_MOVEMENT`、
`F2_BOOKMAKER_INTENT`，大小 3，冻结后不增删。Bonferroni 校正为
`0.05/3 = 0.016667`。

## 数据边界与 loader

筛选集固定为 UTC 开球日期处于 `2026-01-01` 至 `2026-08-22`（含）且已完赛的
fixture；这是已经暴露并标记为 BURNED 的筛选数据。2024/2025 不用于本任务，
2026-08-22 之后的干净前向集绝对禁止读取，penaltyblog 2012/13–2016/17 排除。

在任何数据访问前必须先建 boundary-first loader。它在向计算层暴露记录前过滤，并断言：

- `count(kickoff UTC date > 2026-08-22) == 0`；
- `count(year in {2024, 2025}) == 0`；
- `count(penaltyblog burned season) == 0`。

结构检查只允许返回字段名、来源计数、装载后逐月计数、排除计数和断言触发计数；不得
返回行内容。禁止临时 `head/jq/cat/grep` 数据读取。只使用任务 A 已存在的固定本地
artifacts 与已知 2026 factor captures，不采集、不补源、不填默认值/均值/先验。

## 模型、评估与推断

三项轴均冻结为 `DELTA`，不做轴选择。基线、单标量单系数形式、fold 内标准化、
`[-2,2]` 黄金分割 96 次、lambda clamp、概率、指标和缺失策略均与任务 A
`00eb9556` 一致；边界解只报告，不扩区间重拟合。

因本任务只有一个 burned screening 集，评估冻结为该集合内部 5 折 fixture-cluster OOF：
fold=`int(sha256(fixture_id)[:8],16)%5`。每折只在其余四折拟合标准化和 β，并只在留出折
评分；最终池化每个 fixture 唯一一份 OOF 预测。可用 fixture 少于 300 时
`FAIL_NOT_MEASURABLE`；任一必需 fitting cohort 的总体标准差为 0 时
`FAIL_NEAR_CONSTANT`。

主指标为 multiclass Brier；次指标为 log-loss、classwise 10-bin ECE、Murphy
reliability/resolution。fixture-cluster paired bootstrap 10,000 次，seed `20260904`；
换 seed 是为了不与任务 A 共用重采样序列。单侧 95% 下界取第 5 百分位，
`p=(1+改善<=0次数)/(10000+1)`。只有点改善 >0、下界 >0 且 p<`0.016667` 才筛入
未来确认；筛入仍不等于准入。

完成一次即停止。看到结果后不得改族、边界、标量、轴、模型、标准化、优化器、指标、
bootstrap、缺失规则或门槛。

完整机器可读合同以 `PREREGISTRATION.json` 为准。
