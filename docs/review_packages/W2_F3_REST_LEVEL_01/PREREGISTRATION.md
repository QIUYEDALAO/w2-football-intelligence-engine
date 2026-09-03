# W2-F3-REST-LEVEL-REMEASURE 预注册

状态：`FROZEN_BEFORE_FIRST_MEASUREMENT`

冻结时间：`2026-09-03T02:12:25Z`。本文件与同目录 JSON 必须先形成独立 docs-only
commit；该 commit 之前不得读取任何业务数据。

## 第二次检验与结论边界

这是对 F3 的第二次检验，换了标量构造与作用轴；动机是“共同疲劳可能压低总进球”这一
具体物理机制，不是在同一假设上反复搜索显著性。任务 A 的 FAIL 仍成立，但适用范围只限
封顶的主客休息天数差作用于 DELTA。

本任务是 **SCREENING ONLY，不是确认**。结论只回答两个休息水平构造是否值得进入未来
确认，不得作为准入依据，不得据此改 F3 或接入模型。确认必须等待开球晚于
`2026-09-03` 的干净前向集积累后另行预注册。

## 族、数据与 loader

族固定为两个新构造，均只作用于 TOTAL：

- `F3L_MIN_REST = min(home_rest_days, away_rest_days)`；
- `F3L_MEAN_REST = (home_rest_days + away_rest_days) / 2`。

两者均不封顶、不裁剪，只做 fitting-fold 内标准化。族大小 2，Bonferroni
`0.05/2 = 0.025`。

数据只允许 TRAIN 2024。VALIDATION 2025 一次都不读取或评估；HOLDOUT 2026 全程不碰；
penaltyblog 2012/13–2016/17 排除。在任何数据访问前必须先建 boundary-first loader，先
过滤再暴露，并断言 `count(year != 2024)==0`、
`count(penaltyblog burned season)==0`。结构检查只返回字段名、计数、排除和断言结果，
不返回行内容；之后也禁止临时数据读取。

## 模型、评估与推断

基线、单标量单系数形式、`[-2,2]` 黄金分割 96 次、lambda clamp、概率、指标与缺失策略
沿用任务 A `00eb9556`。每个构造只改变 TOTAL，DELTA 不变；没有截距、交互、特征工程、
轴选择或超参搜索。边界解只报告，不扩区间重拟合。

评估固定为 TRAIN-2024 内部 5 折 fixture-cluster OOF，fold=
`int(sha256(fixture_id)[:8],16)%5`。每折只在其余四折拟合均值、总体标准差和 β，在留出折
评分；池化每个 fixture 唯一一份 OOF 预测。可用 fixture 少于 300 时
`FAIL_NOT_MEASURABLE`；任一必需 fitting cohort 的总体标准差为 0 时
`FAIL_NEAR_CONSTANT`。

主指标是 multiclass Brier；次指标是 log-loss、classwise 10-bin ECE、Murphy
reliability/resolution。TRAIN pooled OOF paired bootstrap 10,000 次，seed `20260905`；
单侧 95% 下界取第 5 百分位，`p=(1+改善<=0次数)/(10000+1)`。只有点改善 >0、下界 >0
且 p<`0.025` 才筛入未来确认；筛入仍不等于准入。

报告必须特别给出 `min_rest` 下尾。若短休息样本极少，须明确写明共同疲劳检验功率不足，
不得因此调整构造重跑。还必须与任务 A 的“休息差/DELTA”结果并列，并明确
VALIDATION 2025 未消耗。

完成一次即停止。完整机器可读合同以 `PREREGISTRATION.json` 为准。
