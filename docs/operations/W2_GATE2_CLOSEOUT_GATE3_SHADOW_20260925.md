# Gate 2 收尾与 Gate 3 离线 Shadow / 只读诊断

日期：2026-09-25
基线：`f93a2455ded5bb7e7f36ea1d4f454f6bb6a8a041`
范围：离线代码、独立导出复算和只读报告；未创建 migration、writer、Provider 调用或生产开关。

## Gate 2 收尾

### 1. AH 双侧身份 fail-closed

`fuse_lambda_level()` 现在只接受带 `line`、`price`、`quote_identity` 的 HOME/AWAY 两侧。入口逐项检查：

* 两侧 line 互为相反数，误差不超过 `0.01`，并与当前 selection 的 expected home line 对齐；
* 两侧 `provider_fixture_id`、`bookmaker_id`、`capture_id` 一致；
* 每侧 market、selection、line、price、observation_id 与外层报价一致。

任一条件不成立抛出 `QUOTE_PAIR_MISMATCH`，不返回部分融合结果。测试覆盖反向线、bookmaker、capture、identity line、selection 和 price 六种错配。

### 2. `MARKET_TOTAL_INFER_V1`

市场 total 反解单独使用版本名 `w2.market_total_infer.v1`，不与冻结的 `TOTAL_INFER_V1` 同名。比例法去水，二分区间 `[0.5, 6.0]`，停止容限 `1e-6`；整数线条件化去除 push，`.25/.75` 按有效胜负暴露计算。目标超出区间或不可达时不钳到边界，返回模型 total，并留下 `MARKET_TOTAL_INFER_NO_SOLUTION` 标记。

### 3. AH DC / Skellam 误差声明

本次 staging 落盘的 `candidate-eval.v2` payload 只有 settlement distribution、quote identity 和 model forecast capture identity；没有可重建 DC 的 `lambda_home/lambda_away/rho` 数值。只读证据：3,024 条 payload 均无上述 Elo 字段，checkpoint 的 `simulation.lambda_home/lambda_away` 也为空。因此无法诚实地抽出 100 场做“同一输入的 DC 与 Skellam 各解一次”。该项状态为 **NOT_ESTIMABLE**，不是零误差，也不构成 Gate 通过。下一次前向 capture 必须追加这三个数及其输入 hash，才允许冻结 max/median delta。

### 4. 缺市场数据

`fusion_ev=None`，不进入档位；展示保留纯模型概率并标注 `无市场锚·不参与档位`。身份错配另标 `QUOTE_PAIR_MISMATCH`。这只改变离线展示输出，不改变 `validation_samples` 或推荐账本。

### 5. 两条合规加速

整数线的市场反解使用 `P(UNDER | not push)`；评估时间不再由结果时间推断。R1 的补采集项写入只读计划：下一批 capture 必须持久化 `evaluated_at`、`captured_at`、`kickoff_utc` 和绑定 identity，缺任一字段标记 `PIT_UNPROVABLE`，不得回填历史。

## Gate 3 F1 分轨诊断

查询在 `root@45.207.194.97 / w2-staging-postgres-1` 的 `BEGIN TRANSACTION READ ONLY` 中完成，随后 `ROLLBACK`。按 fixture×market 最新评估去重得到 664 行；其中 662 行有 FT 结果。独立脚本为 `scripts/quant/run_gate3_shadow_diagnostics.py`，不导入生产结算或推荐代码。

下表是已有结果行的历史诊断，不是 2,500+2,500 密封 validation/test，也不构成切换授权。`bias` 为预测有效成功概率减实际有效成功状态；`profit_units` 使用导出 decimal odds 的纯盈亏。

| 轨道/状态 | n | logloss | Brier | RPS | bias | profit units |
|---|---:|---:|---:|---:|---:|---:|
| AH / ANALYSIS_PICK_ACTIVE | 41 | 0.97750 | 0.60973 | 0.24221 | +0.08918 | +1.49 |
| AH / NO_EDGE_CURRENT | 48 | 1.00736 | 0.63289 | 0.24130 | +0.10441 | -7.36 |
| AH / BLOCKED_BY_FACTOR | 206 | 1.05575 | 0.65811 | 0.25255 | +0.08308 | -3.51 |
| TOTALS / ANALYSIS_PICK_ACTIVE | 73 | 0.97103 | 0.61228 | 0.24250 | +0.04631 | +9.26 |
| TOTALS / NO_EDGE_CURRENT | 157 | 0.98625 | 0.62180 | 0.24173 | +0.08587 | -18.43 |

该快照的市场双侧报价覆盖（同 capture、bookmaker=4、同线）为合法三态 399/526 行：AH 170、TOTALS 229；与 Gate 2 的 399 行严格 eligible 一致。因未把市场概率和结算结果拼成同一独立导出，本报告不宣称 logloss/Brier 相对 Pinnacle 的通过或不劣化；待下一批带完整双侧 identity 的导出后再计算 paired delta 和 bootstrap 区间。

## Gate 3 F2/F3 消融设计（不接入模型）

* `internal_elo_v1` 的来源链为 242/242 完整；kickoff 前双方覆盖 209/332（62.95%），严格 evaluated_at PIT 双侧覆盖 1,902/3,024（62.90%）。当前实际入模证据为 0/3,024：forecast payload 没有 Elo 字段，checkpoint 标记 `ratings_used_in_lambda=false`。
* F2 shadow 每日只读计算 `xG baseline` 与 `xG + internal_elo_v1` 的配对输出，要求双方 snapshot `observed_at <= evaluated_at`；缺快照的 37.10% 行保留为 `ELO_UNAVAILABLE`，不以前后数据填补。
* F3 在同一 fixture、同一 capture、同一时间切分加入 rolling form；先做 F2 已入场与未入场的配对消融，报告 AH/TOTALS 五态 logloss、Brier、RPS、bias 和 bootstrap CI。只有增量 CI 不含 0 才进入新预注册，当前不改 λ 或因子门。

## R2/R3/R4 只读诊断

* R2 固定排序：样本量（降序）→绝对 bias（降序）→logloss（降序）→盘口、方向、联赛、档位、edge 桶、赔率带、移动方向的字典序。每格输出 `n`、唯一 fixture、缺失率；`n < 20` 显示“证据不足”，不做结论。`gate3_readonly_diagnostics.py:attribution_top3()` 只从证据充足格取 Top 3。
* R3 只计算 7/30 日 rolling bias、Platt 观测斜率、logloss vs 市场和 CUSUM；窗口、阈值、最小样本量冻结在报告配置中，告警只读、只提示人工，不拟合、不调参、不发 Bark。
* R4 的离线登记文件为 `W2_GATE3_STRATEGY_CHANGE_LOG_20260925.json`，列出策略版本、旧值、新值、预注册 ID、生效时间和 T+7/T+30 描述性对照。尚未生产生效的字段保持 `null`；不得把前后对照当因果证据。三项均未创建生产表或写入生产。
* OU 意图门阈值 `MIN_INTENT_SIGNAL_STRENGTH_FOR_PICK = 0.55` 尚未被 Owner 批准，已登记进 R4 迭代登记处（`change_id: gate3-intent-signal-threshold-0.55-20260926`）。R2/R3 复盘纪律要求按 0.55 上下分桶验证 TOTALS 意图门两侧的 bias；未通过前不得把 0.55 当作生产阈值。

## 测试

```text
58 passed
ruff check: passed
```

包含 AH quote identity fail-closed、`.25/.75`、零概率、极端赔率 fallback、缺市场展示、五态独立诊断和 Gate 3 分层指标测试。

## 结论

Gate 2 的五项离线收尾已实现并有测试；Gate 3 当前交付是可复算的 shadow 诊断，不是 F1 通过证明。密封样本、市场 paired baseline、AH DC/Skellam 100 场误差和 Elo/F3 消融仍是前向数据到齐后的待办，生产推荐链路保持不变。
