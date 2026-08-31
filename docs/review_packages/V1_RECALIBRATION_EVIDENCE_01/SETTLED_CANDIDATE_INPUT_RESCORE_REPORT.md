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

导出 SQL：`settled_candidate_rescore_export.sql`，SHA-256=`9035ba87350a57b3c4b093c3e4e18dbd34b798272d6cb545d48252e74f27c35c`；诊断 JSON SHA-256=`75523d53a2e238f36f9e8889b4760bf787ae9ad841b47eaad060f73e0998aae1`。

## 生产链重放结果

每注均能从 evaluation 自身恢复冻结的五态分布、赔率、EV、EV-SE、delta、盘口线和方向；其绑定的 immutable model capture 恢复四字段 xG 身份。按既有结算函数得到 `WIN 46 / HALF_WIN 5 / PUSH 10 / HALF_LOSS 7 / LOSS 53`，P&L `-15.145` 单位；P&L 仅作症状展示，不作调参依据。

| 市场 | 注数 | P&L | WIN | HALF_WIN | PUSH | HALF_LOSS | LOSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| AH | 66 | -3.825 | 27 | 5 | 2 | 7 | 25 |
| TOTALS | 55 | -11.320 | 19 | 0 | 8 | 0 | 28 |
| 合计 | 121 | -15.145 | 46 | 5 | 10 | 7 | 53 |

AH 方向：主队 20、客队 46；TOTALS：大 22、小 33。输注不是简单方向选择器把另一边漏掉：此前同盘口反方向反事实审计为 `0/110` 同时通过 EV 与 edge 硬门；本次 121 注也应把“方向翻转”视为待验证假设，而不是直接修复。

## 输入事实与证据边界

121 注绑定的 immutable capture 均保存了完整四字段 xG 与其组成身份，这是本审计能证明的 V1 输入事实。旧 JSON 中的 λ、readiness 与 feature status 来自该场后来覆盖的 latest shadow checkpoint，只能作为非权威时点差异诊断，不能冒充历史 evaluation 的冻结输入。

V1 按设计由 xG 四字段、固定主场项和 Poisson/Dixon-Coles 经济链驱动。Elo/身价/首发属于 V2 扩展，不是 V1 的必需输入或缺陷。121 个 first-eligible model capture 均在旧 `BASELINE_PRIOR` 时期冻结；后来 evaluation 的授权状态不能从该 capture 或 latest checkpoint 反推，因此本 cohort 不得被描述成 98/23 两个权威 calibration identity 分组。

此前报告称 35/121 条 capture 与 checkpoint simulation hash 不同，现已撤回：比较的是历史 evaluation 与后来覆盖的 latest shadow checkpoint，而非 immutable child。实测 evaluation→model-capture identity 与 model-input manifest 均为 121/121 一致；latest-checkpoint 差异仅是非权威诊断。

## 当前可支持的根因判断

1. evaluation 的五态分布与赔率能逐注复现保存 EV；没有发现展示层或 EV 算式把另一边选错。
2. AH 决定性方向命中 `32/64`，TOTALS 为 `19/47`；这是被准入后的症状，不是无偏验证集。
3. V1 修复范围是四字段 xG 的 PIT 身份、主客强弱/主场项、比分概率、盘口赔率和准入经济链；不得把 V2 的 Elo/身价/首发扩展列为 V1 修复前提，也不应先调 EV 阈值或把方向反转。
4. 这些 121 注已经是被查看并参与开发诊断的 cohort；本报告不授权选择新常数、权重、阈值或 calibration verdict。任何参数修复必须另行预注册。

## 结论边界

本报告已经完成 121 注的逐注四字段输入身份、evaluation 五态分布、赔率/EV、方向和赛果重放；历史 λ 不能从后来 checkpoint 冒充恢复。它不是“EV 已修复”或“生产有效性已验证”的声明。

方向层的逐注重评分已另行冻结，见
`SETTLED_CANDIDATE_DIRECTION_RESCORE_REPORT.md` 与
`SETTLED_CANDIDATE_DIRECTION_RESCORE.json`。该 artifact 以 evaluation 自身冻结的五态分布
计算 AH/TOTALS 两侧模型方向，并单列 PUSH；不要把本报告的
EV/P&L 汇总误读为方向选择器诊断。
