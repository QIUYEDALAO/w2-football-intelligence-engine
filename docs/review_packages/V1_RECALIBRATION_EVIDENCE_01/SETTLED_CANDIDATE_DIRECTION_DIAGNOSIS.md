# 已结算候选逐注方向反事实诊断

## 快照与边界

- 抽取时刻：`2026-08-30T21:12:57Z`（UTC）。生产在此之后仍会结算，因此本报告不是对用户此前看到的 108 注快照的追溯；本地未保留那一刻的 CSV。该快照实际为 **110 注 / 81 场**，包含此前 108 注以及抽取时已自然新增的记录，不能与 108 注混算。
- Provider 调用：0；生产写入：0；未部署、未改参数、未改 ledger/白名单。
- 导出使用服务端 `COPY (...) TO STDOUT WITH CSV HEADER`，无 `LIMIT` 或客户端分页；导出后进程已退出，生产 `pg_stat_activity`（排除当前检查会话）active `COPY` 为 0。
- 评价 CSV SHA-256：`da64955c4d97444b4253994f6e5560a4fc126d3af0ccc9d2e9212913c2a87554`
- 报价 CSV SHA-256：`9132606a9481ccf2bfe63ac7a51f007aeb09703dfdfcb79b9c0aa494c3b9d1fd`
- 逐注分析 JSON SHA-256：`00317832d251d4558de84343df61d9205e910ffa499b99271b798601d748dfec`

可复核命令：

```bash
PYTHONPATH=src python3 scripts/audit_settled_candidate_directions.py \
  --evaluations docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/settled_candidate_snapshot_20260830T211257Z_evaluations.csv \
  --market docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/settled_candidate_snapshot_20260830T211257Z_market.csv \
  --output /tmp/settled_direction_analysis.json
```

## 复算口径

逐注使用评价 payload 的完整五态 `model_settlement_distribution`（因此与生产 `current_ev` 的绝对差均值约 `2.5e-7`）。AH 原始 observation 的 line 符号不能稳定充当双边配对身份；旧版脚本按 raw line 配对会把 `HOME +x / AWAY -x` 配错，已明确作废。修正版以生产持久化的 `current_delta` 和模型有效概率恢复当时 proportional-devig 市场概率，再由选中侧赔率反解同一双边 overround 下的反向赔率。AH 结算仍按 `HOME -x ↔ AWAY +x`，TOTALS 共用同一总进球线。

反方向分布由五态互补得到：`WIN↔LOSS`、`HALF_WIN↔HALF_LOSS`、`PUSH` 不变。这比 capture 中低精度的 deterministic ladder 更准确，因为评价 payload 已包含生产不确定性混合后的分布。

生产持久化的 evaluation 没有反方向的 `EV_SE` 或 lambda sigma；因此报告对反方向明确标记 `reverse_ev_se_status=NOT_PERSISTED_IN_CAPTURE`，不伪造第四门。反方向是否“全门通过”只能在已有三项经济值上判定，EV-SE 需生产补充持久化字段后才能独立复核。

## 结果

| 市场 | 注数 | 推荐 WIN/HALF_WIN | 推荐 LOSS/HALF_LOSS | 推荐 EV 均值 | 反方向 EV 均值 | 推荐 edge 均值 | 反方向 edge 均值 |
|---|---:|---:|---:|---:|---:|---:|---:|
| AH | 58 | 26 | 30 | 0.258039 | -0.397959 | 0.281646 | -0.435136 |
| TOTALS | 52 | 25 | 26 | 0.166526 | -0.265556 | 0.190309 | -0.306364 |
| 合计 | 110 | 44 | 56 | 0.214778 | -0.335368 | 0.238469 | -0.374262 |

结算分布：`WIN 40`、`HALF_WIN 4`、`PUSH 10`、`HALF_LOSS 7`、`LOSS 49`。按既有 `WIN_UNITS` 结算，本快照 P&L 为 **-17.045 单位**（仅症状展示，不用于调参）。

最关键的反事实结果：

- 推荐方向出现不利结算（`LOSS/HALF_LOSS`）共 **56 注**；反方向确实结算为 `WIN/HALF_WIN`，但按生产持久化 devig 恢复，反方向 **0/110** 通过 EV>0 与 edge≥5% 两项硬门。因此没有证据表明“选择器本来应选另一边但选错了”；证据指向模型概率在高分歧子集失真。
- 推荐记录的持久化 delta≥5% 实为 **110/110**，原先的 105/110 来自错误 AH raw-line 配对，已作废。cashflow edge≥5% 仍为 **108/110**：`1492348 AH AWAY` 与 `1493078 AH AWAY` 的 edge 分别约 `4.66% / 4.60%`。代码路径确认 lifecycle 只检查 EV、delta、EV-SE，而 `analysis_evidence/market_candidate` 检查 EV、cashflow edge、EV-SE；这是两个真实的 admission contract 漂移样本。

## “为什么会选这一边、改哪里会切换”

逐注 JSON 保留了 `lambda_inputs`（四字段 xG）、盘口、赔率、calibration version/status、推荐与反方向的 EV/fair odds/edge/delta 及实际结算。对 56 个不利结算逐注复核后，反方向不是一个当时已具备正 EV 的候选；要让它切换，必须改变模型分布（主要是 xG 生成的 λ 主客差、主场项/实力差缩放或输入质量），而不是只改选择器排序。由于这 110 注赛果属于已参与开发的数据，不能据此直接选常数或阈值。

下一步应分别验证：

1. 在同一冻结赛前输入上，补持久化 lambda sigma，才能完整计算反方向 EV-SE；
2. 统一动态评价、`analysis_evidence`、`market_candidate` 三处经济门，避免 edge/delta 门漂移；
3. 用独立、未参与参数选择的前向样本验证 AH spread 校准。仅凭本快照不能宣称 EV 已修复或生产有效性已验证。
