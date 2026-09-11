# V1 赛前 AH / TOTALS 市场形状审计

> 结论边界：本报告只比较冻结的赛前模型分布与赛前市场，不读取赛果，不能证明生产有效性或 EV 已完全修复。

- A1 SHA-256: `34c7bf6e7e6babae52daebc57fc0e74a139659a24a169bea8a2ce0ecf1b7bd7b`
- A2 SHA-256: `3842446d5838bffaa721e1fb9d5e11956bcd1ff32140e5df24fa55fd2eb2b2e8`
- market.csv SHA-256: `30a40da45636c3bd6548e0627e45d5903f9b7622184ba3715cc556fb802f3144`
- T_EXTRACT: `2026-08-30T15:58:43Z`
- 实际去水实现：`proportional`；不采用 provenance 中可能出现的 `POWER` 标签。
- 公平盘口：以完整赛前模型分布计算五态现金流，在十进制赔率 2.00 下选择绝对 EV 最接近 0 的 0.25 盘口。

## 强制计数

```json
{
  "fixture_count": 283,
  "snapshot_count": 178,
  "rebuild_count": 105,
  "market_rows": 118015,
  "bookmakers": 14,
  "track_X_count": 283,
  "track_Y_count": 283,
  "clamp_affected_count": 12,
  "AH_ready_count": 283,
  "TOTALS_ready_count": 283
}
```

## 主要对比

| Cohort | Track | AH强队幅度缺口 mean/median | FAVORITE gap mean/median | UNDERDOG gap mean/median | HOME gap mean/median | AWAY gap mean/median | Total公平-市场 mean/median | OVER gap mean/median | UNDER gap mean/median |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all_283 (283) | X | 0.7634 / 0.7500 | -0.1852 / -0.2076 | 0.1197 / 0.1298 | -0.0478 / -0.0638 | -0.0170 / -0.0286 | -0.0910 / -0.2500 | -0.0651 / -0.0775 | 0.0112 / 0.0180 |
| all_283 (283) | Y | 0.7134 / 0.5000 | -0.1749 / -0.2020 | 0.1094 / 0.1333 | -0.0137 / -0.0187 | -0.0511 / -0.0733 | -0.0901 / -0.2500 | -0.0647 / -0.0775 | 0.0107 / 0.0180 |
| snapshot_178 (178) | X | 0.8040 / 0.7500 | -0.1888 / -0.2130 | 0.1244 / 0.1297 | -0.0247 / -0.0202 | -0.0389 / -0.0772 | -0.0660 / -0.2500 | -0.0606 / -0.0673 | 0.0100 / 0.0199 |
| snapshot_178 (178) | Y | 0.7571 / 0.5000 | -0.1802 / -0.2253 | 0.1161 / 0.1400 | 0.0091 / 0.0249 | -0.0725 / -0.1227 | -0.0646 / -0.2500 | -0.0600 / -0.0673 | 0.0094 / 0.0199 |
| rebuild_105 (105) | X | 0.6947 / 0.6250 | -0.1792 / -0.1991 | 0.1116 / 0.1308 | -0.0870 / -0.1148 | 0.0201 / 0.0273 | -0.1333 / -0.2500 | -0.0727 / -0.0821 | 0.0133 / 0.0156 |
| rebuild_105 (105) | Y | 0.6394 / 0.5000 | -0.1658 / -0.1703 | 0.0982 / 0.1238 | -0.0523 / -0.0765 | -0.0147 / -0.0136 | -0.1333 / -0.2500 | -0.0725 / -0.0821 | 0.0131 / 0.0156 |
| clamp_affected_12 (12) | X | 0.0833 / -0.6250 | 0.0505 / 0.1628 | -0.0979 / -0.2326 | 0.2147 / 0.2525 | -0.2621 / -0.3262 | -0.4167 / -0.5000 | -0.1372 / -0.1420 | 0.0961 / 0.0964 |
| clamp_affected_12 (12) | Y | 0.0208 / -0.7500 | 0.0740 / 0.1884 | -0.1192 / -0.2555 | 0.2383 / 0.2769 | -0.2835 / -0.3401 | -0.3958 / -0.5000 | -0.1262 / -0.1237 | 0.0844 / 0.0845 |
| excluding_clamp_271 (271) | X | 0.7938 / 0.7500 | -0.1958 / -0.2130 | 0.1294 / 0.1374 | -0.0595 / -0.0785 | -0.0062 / -0.0143 | -0.0766 / -0.2500 | -0.0619 / -0.0775 | 0.0075 / 0.0180 |
| excluding_clamp_271 (271) | Y | 0.7444 / 0.5000 | -0.1860 / -0.2085 | 0.1197 / 0.1380 | -0.0248 / -0.0300 | -0.0408 / -0.0568 | -0.0766 / -0.2500 | -0.0619 / -0.0775 | 0.0075 / 0.0180 |

## 冻结证据内结论

- AH：市场强队相对模型的平均盘口幅度缺口从 `0.763` 球变为 `0.713` 球；0.30 只缩小其中一小部分，未消除全局实力幅度压缩。
- AH 弱队侧：平均 cashflow price edge 从 `0.229` 降至 `0.207`；客侧/主侧会随主场项移动，但弱队方向的系统性市场偏离仍明显。
- 方向分解：主队为强队时幅度缺口从 `0.638` 降至 `0.474`；客队为强队时反而从 `0.992` 升至 `1.152`。这符合主场常数只移动截距、不能修复强弱幅度斜率的结构。
- TOTALS：公平总进球线相对市场的均值从 `-0.091` 变为 `-0.090`；符合主场项理论上不改变总 λ 的预期，TOTALS 是否可靠不能由 0.12→0.30 得到证明。

## 独立复核命令

```bash
check_dir=$(mktemp -d /private/tmp/v1-market-shape-review.XXXXXX)
PYTHONPATH=src:. python3 scripts/audit_v1_market_shape.py \
  --a1 docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A1_PIT_EVIDENCE_REDO.json \
  --a2 docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/A2_SIMULATION_OUTPUTS.json \
  --market-csv /private/tmp/v1-a1-recheck.jHaT4e/market.csv \
  --output-json "$check_dir/audit.json" --output-report "$check_dir/audit.md"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/MARKET_SHAPE_AUDIT.json "$check_dir/audit.json"
cmp docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/MARKET_SHAPE_AUDIT.md "$check_dir/audit.md"
```

## 解释限制

- 市场一致性可以定位系统性假 edge 的形状，但市场不是赛果真值，不能替代前向概率校准。
- 283 场参与过 0.30 的参数选择；任何结果都不得用于回头调参或调阈值。
- 98 注 / -10.865 单位与 26 场 / 62 pick 目前仍是待独立复算的页面观察值，本报告不将其作为根因前提。
- `APPROVED_VALIDATED` 的既有证据只覆盖 1X2 三侧相对偏差，不自动覆盖 AH、TOTALS、EV 或 EV-SE。
