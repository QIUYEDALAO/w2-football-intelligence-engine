# V1 历史收盘盲测独立验收回执

验收任务：`V1-RECALIBRATION-MULTIROUND-INDEPENDENT-ACCEPTANCE-01`

验收对象：`codex/v1-recalibration-evidence-01@b1db55fe4ef6661c9aa021ca8bf0780b5b269bab`

## 裁决

```text
SCIENTIFIC_EVIDENCE_VERDICT = PASS
RELEASE_ELIGIBILITY_VERDICT = REJECTED_NOT_DEPLOYABLE
```

独立历史盲测证据链可接受，但固定 AH component-share 与 TOTALS axis 候选均被拒绝。当前没有可部署的 V1 EV 修复；`858` 场已完成唯一查看，不得继续用于选参，不得为 identity `f98d4ef0c2b158a80eeba60ca979250736831583612ad126b6ae9010262dbc91` 登记 calibration grant，不得部署。

## 独立复核结果

- HEAD、分支、干净工作树和 `1de3c1ef` 基线血缘通过；五组预注册、runner、预测冻结、评分口径冻结和结果提交顺序均成立。
- 六个冻结文件 SHA-256 全部吻合；预测和结果两份 artifact 均逐字节复现。
- xG 为 `1123/1123 COMPLETE` 且 identity 唯一；最终 AH/TOTALS 均为 `858` 场，歧义映射 `0`，双方各 5 场历史严格早于目标 kickoff。未发现目标赛果、结算结果、自身或未来 xG 泄漏。
- 独立实现五态标量概率、proportional devig、Brier、log-loss 和 fixture-level paired bootstrap 后，八个点估计逐位复现，八个 one-sided 95% 上界均大于 `0`。AH 对现役的点估计改善不能替代置信上界门。
- 当前版本为 `w2.formal.lambda_totals_axis.v2`；新 identity verdict 为 `None`，运行状态为 `BASELINE_PRIOR`。ledger 仍只有旧 `21960a86…` grant，未顺延、未放宽白名单。
- 定向 `7 passed`、canonical `18 passed`、package matrix `5 passed`、Ruff 通过；全量 `2967 passed / 9 skipped / 5 failed`。五个失败独立确认为宿主限制，任务相关失败 `0`。
- `ea95230f..b1db55fe` 没有 `src/`、`config/` 或 migration 变化，未发现结果后调参或继续搜索该 cohort。

## 验收发现

1. `31` 场并非全部缺 Pinnacle 收盘列：真实缺列 `9` 场，另 `22` 场为 Paris Saint-Germain 名称映射链只执行一次导致未匹配。该问题不改变裁决；修复只能用于未来新预注册，禁止在本 cohort 补跑。
2. 另有 `234` 场因双方严格更早历史不足而排除，但 builder 没有把该桶写入 `excluded` 计数。计数闭合为 `1123 - 31 - 234 = 858`。
3. scorer 实现与结果同在 `ea95230f` 首次出现，未在读赛果前冻结。评分 supplement 已前置冻结完整机械口径，且独立重实现复现全部门，因此不改变本次证据裁决。
4. scorer 将 `8000` 次与 seed base `20261001` 硬编码，未解析 supplement 强制一致。当前实测一致；未来协议应把口径绑定成代码门。
5. `25d498d3` 在结果后更换 fetcher 的 source payload 哈希算法，现版 fetcher 不能重现冻结 JSONL 内该字段。冻结文件哈希、xG 数值与预测复现不受影响。
6. 有效预注册的 `frozen_at=2026-09-01T08:15:00Z` 晚于引入提交时间。内容实际更早冻结，方向保守，但时间记账不一致。

## 运行与发布边界

- 生产继续是 `1de3c1ef554d00a408577f59f4864e04f1d341da`。
- Provider、生产数据库写入、ledger、白名单、migration、V2、GitHub 和部署均不因本验收改变。
- 本地未发现注册或运行中的 `w2-v1` 自动化；应记录为“不存在/未注册”，而不是声称已确认 `PAUSED`。
- 本地分支包含已被盲测拒绝的 TOTALS 默认参数实现，因此不能作为 release；独立验收不授权回滚、登记或部署动作。
