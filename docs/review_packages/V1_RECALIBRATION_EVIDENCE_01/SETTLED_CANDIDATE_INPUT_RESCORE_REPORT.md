# V1 已结算候选输入重评分诊断

状态：`IMPLEMENTED_PENDING_ACCEPTANCE`（只读审计，未部署）

## 冻结 cohort 与复核边界

在 `2026-08-31T04:40:28Z` 冻结生产只读抽取。严格取开赛前最后一个 `EVALUATED_CANDIDATE`、已存在权威 FT/AET/PEN 赛果的 fixture-market 单元：`121` 注、`91` 场，其中 AH `66`、TOTALS `55`。Provider 调用 0，生产写入 0；服务端 `COPY` 完成后进程退出，active COPY=0。结果字段只在候选 identity 冻结后读取，不用于选择参数。

复核入口：

```bash
PYTHONPATH=src .venv/bin/python scripts/audit_settled_candidate_inputs.py \
  --input /tmp/settled_rescore.csv \
  --output docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/SETTLED_CANDIDATE_INPUT_DIAGNOSIS.json
```

导出 SQL：`settled_candidate_rescore_export.sql`，SHA-256=`9035ba87350a57b3c4b093c3e4e18dbd34b798272d6cb545d48252e74f27c35c`；诊断 JSON SHA-256=`dd15ee863a699225684f34ca8fc6f902e4449ca71a800b76efdad82f2886d713`。

## 生产链重放结果

每注均能从 evaluation 绑定的 immutable model capture 恢复完整五态分布、赔率、EV、EV-SE、delta、盘口线、方向和赛果结算；方向审计不再使用后来覆盖的 shadow checkpoint。按既有结算函数得到 `WIN 46 / HALF_WIN 5 / PUSH 10 / HALF_LOSS 7 / LOSS 53`，P&L `-15.145` 单位；P&L 仅作症状展示，不作调参依据。

| 市场 | 注数 | P&L | 平均 λ主 | 平均 λ客 | 平均预测总进球 / 实际 | 平均预测净差 / 实际 |
|---|---:|---:|---:|---:|---:|---:|
| AH | 66 | -3.825 | 1.431 | 1.284 | 2.715 / 3.000 | 0.135 / 0.303 |
| TOTALS | 55 | -11.320 | 1.429 | 1.317 | 2.746 / 2.855 | 0.126 / 0.273 |
| 合计 | 121 | -15.145 | 1.430 | 1.299 | 2.729 / 2.934 | 0.131 / 0.289 |

AH 方向：主队 20、客队 46；TOTALS：大 22、小 33。输注不是简单方向选择器把另一边漏掉：此前同盘口反方向反事实审计为 `0/110` 同时通过 EV 与 edge 硬门；本次 121 注也应把“方向翻转”视为待验证假设，而不是直接修复。

## 因子输入事实

121 注的真实运行 simulation 都使用四字段 xG，xG 状态 `READY=121/121`。但其它增强因子在实际 λ 中全部未启用：`ratings_used_in_lambda=False`、`squad_value_used_in_lambda=False` 均为 121/121；H2H 与历史 form 均未就绪，lineup 未形成有效输入。feature status 汇总为：F1 市场移动 `UNAVAILABLE=121`、F2 机构分歧 `UNAVAILABLE=121`、F3 休息 `INSUFFICIENT_DATA=121`、F4 比赛重要性 `READY=121`、F5 近期 AH `UNAVAILABLE=121`、F6 H2H `UNAVAILABLE=121`、F7 实力/状态 `INSUFFICIENT_DATA=121`、F8 身价 `UNAVAILABLE=121`、F9 True XG 解释因子 `UNAVAILABLE=121`。

因此当前 V1 推荐按设计由 xG 四字段 + 固定主场项 `0.30` + Poisson/Dixon-Coles 经济链驱动。Elo/身价/首发属于 V2 扩展，不是 V1 的必需输入或缺陷。98 注仍为 `BASELINE_PRIOR` 时期，23 注为 `APPROVED_VALIDATED` 时期；不能跨 calibration identity 合并成一个授权结论。

此前报告称 35/121 条 capture 与 checkpoint simulation hash 不同，现已撤回：比较的是历史 evaluation 与后来覆盖的 latest shadow checkpoint，而非 immutable child。实测 evaluation→model-capture identity 与 model-input manifest 均为 121/121 一致；latest-checkpoint 差异仅是非权威诊断。

## 当前可支持的根因判断

1. AH：平均预测净胜差 `0.135`，实际 `0.303`，再次显示实力差被压缩；这能解释客侧/受让侧假 edge，但不能单独解释 TOTALS 的 `-11.320`。
2. TOTALS：总进球均值预测 `2.746`、实际 `2.855`，偏差远小于 AH 净差轴；亏损更像准入挑选模型与市场分歧最大样本造成的逆向选择，而非已证明的总进球斜率错误。
3. V1 修复范围是四字段 xG 的 PIT 身份、主客强弱/主场项、比分概率、盘口赔率和准入经济链；不得把 V2 的 Elo/身价/首发扩展列为 V1 修复前提，也不应先调 EV 阈值或把方向反转。
4. 这些 121 注已经是被查看并参与开发诊断的 cohort；本报告不授权选择新常数、权重、阈值或 calibration verdict。任何参数修复必须另行预注册，并使用未参与选择的新证据验证。

## 结论边界

本报告已经完成 121 注的逐注输入、λ、模拟、赔率/EV、方向和赛果重放，并定位到“V1 的 xG 主导链、AH 净差压缩”这些可复核事实；它不是“EV 已修复”或“生产有效性已验证”的声明。下一步按独立预注册处理 V1 的 xG/强弱/盘口链。

方向层的逐注重评分已另行冻结，见
`SETTLED_CANDIDATE_DIRECTION_RESCORE_REPORT.md` 与
`SETTLED_CANDIDATE_DIRECTION_RESCORE.json`。该 artifact 以完整比分矩阵计算
AH/TOTALS 两侧模型方向，并单列 PUSH、主场项反事实及未启用因子；不要把本报告的
EV/P&L 汇总误读为方向选择器诊断。
