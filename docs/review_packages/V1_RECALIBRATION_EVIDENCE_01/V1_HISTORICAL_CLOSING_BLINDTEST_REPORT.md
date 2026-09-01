# V1 独立历史收盘盲测报告

裁决：`REJECTED`。固定 AH component-share 与 TOTALS axis 候选均未通过预注册门，禁止在本 cohort 换参数、登记授权或部署。

## 防泄漏与覆盖

- 有效预注册：`10f8020b`，SHA-256 `5d300f56bb5d255b3f7400ff0fdc57b37d67844fed4052c7f8bf640c359c6afe`
- 评分补充协议：`132804ed`，SHA-256 `aa39ce46ff230684df71caf90b5a51c329d6b857a4649e6453c5de6fee5e856d`
- 预赛果预测冻结提交：`1829a3fb`
- 预赛果预测 artifact：SHA-256 `33ae870095e1c27e8797ff0f86bc3e1b0c2b2bdcddebba69b911a8a84731defb`
- 赛果只在上述提交落地后读取；`git log` 固化了先预测、后结算顺序。
- API-Football xG：`1123/1123 COMPLETE`、fixture identity `1123/1123` 唯一；目标场只使用双方各 5 场严格更早 xG。
- Provider 调用：任务累计 `1172 <= 6000`；最后观测 remaining `6069 > 1500`。采集完成后新增 Provider 调用 `0`。
- 完整市场映射且双方有 5 场历史：`858` 场；歧义映射 `0`；Pinnacle AH/TOTALS 收盘列缺失排除 `31` 场。AH 与 TOTALS 均超过最低 `500` 场。
- Football-Data 只作为 Pinnacle closing/aggregate benchmark，不冒充 T-30/T-15 可执行报价。

## 强制门

差值均为 candidate minus comparator；负数更好。每一项要求 one-sided bootstrap 95% 上界 `<= 0`。

| 市场 | 指标 | 均值差 | upper 95 | 结果 |
|---|---|---:|---:|---|
| AH | Brier vs production | -0.000933899 | +0.000184033 | FAIL |
| AH | log-loss vs production | -0.002062107 | +0.000292851 | FAIL |
| AH | Brier vs closing market | +0.009631931 | +0.015627116 | FAIL |
| AH | log-loss vs closing market | +0.020700713 | +0.033354963 | FAIL |
| TOTALS | Brier vs production | +0.000100592 | +0.002005070 | FAIL |
| TOTALS | log-loss vs production | +0.000147893 | +0.003997267 | FAIL |
| TOTALS | Brier vs closing market | +0.005039591 | +0.009400888 | FAIL |
| TOTALS | log-loss vs closing market | +0.010113111 | +0.019500193 | FAIL |

AH 候选点估计略优于现役，但置信上界跨 0，且明确弱于收盘市场。TOTALS 候选点估计同时弱于现役与收盘市场。因此两者都不能形成可部署修复。

## 诊断（不构成门）

| 市场/模型 | Brier | log-loss | ECE-10 | closing edge>=5% 后注数 | P&L units |
|---|---:|---:|---:|---:|---:|
| AH production | 0.214212330 | 0.714115046 | 0.100791790 | 700 | -7.935 |
| AH candidate | 0.213278431 | 0.712052940 | 0.087243901 | 686 | -7.790 |
| AH closing market | 0.203646500 | 0.691352227 | 0.019087078 | - | - |
| TOTALS production | 0.243145087 | 0.679288982 | 0.010294523 | 568 | +10.900 |
| TOTALS candidate | 0.243245679 | 0.679436875 | 0.014949652 | 559 | -8.680 |
| TOTALS closing market | 0.238206088 | 0.669323764 | 0.023790015 | - | - |

P&L 仅展示，不参与参数、阈值或裁决选择。

## 独立复核

```bash
PYTHONPATH=src:. .venv/bin/python scripts/build_v1_historical_closing_predictions.py \
  --manifest docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_FIXTURE_MANIFEST_PRE_RESULT.json \
  --xg docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_XG_ROWS_PRE_RESULT.jsonl \
  --source-root /Users/liudehua/.hermes/data/w2/football-data-co-uk \
  --protocol docs/operations/V1_HISTORICAL_CLOSING_BLINDTEST_PREREGISTRATION_20260901B.json \
  --output /tmp/V1_HISTORICAL_CLOSING_PREDICTIONS_PRE_RESULT.json
cmp -s /tmp/V1_HISTORICAL_CLOSING_PREDICTIONS_PRE_RESULT.json \
  docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_CLOSING_PREDICTIONS_PRE_RESULT.json

PYTHONPATH=src:. .venv/bin/python scripts/score_v1_historical_closing_blindtest.py \
  --predictions docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_CLOSING_PREDICTIONS_PRE_RESULT.json \
  --source-root /Users/liudehua/.hermes/data/w2/football-data-co-uk \
  --supplement docs/operations/V1_HISTORICAL_CLOSING_BLINDTEST_SCORING_SUPPLEMENT_20260901.json \
  --output /tmp/V1_HISTORICAL_CLOSING_BLINDTEST_RESULT.json
cmp -s /tmp/V1_HISTORICAL_CLOSING_BLINDTEST_RESULT.json \
  docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/V1_HISTORICAL_CLOSING_BLINDTEST_RESULT.json
```

诚实边界：该结果拒绝两组固定候选；它不证明现役模型已修复、盈利或优于实时市场，也不授权再用这 858 场搜索另一组参数。

## 自验收

- 定向测试：`7 passed`。
- canonical serialization：`18 passed`；package matrix：`5 passed`；治理回归合计
  `23 passed`。
- 全量命令：`PYTHONPATH=src:. .venv/bin/pytest -q`。
- 全量结果：`2967 passed / 9 skipped / 5 failed / 5 warnings`，耗时 `353.41s`。
- 任务相关失败：`0`。剩余 5 个均为既有宿主限制：Docker Compose 插件缺失 2、系统无裸 `python` 导致 SC18 未启动 1、macOS 无法构造容器 UID/GID 所有者目录 2。
