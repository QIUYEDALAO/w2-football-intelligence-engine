# V1 模型修复进度与证据边界

状态：`PARTIAL_ROOT_FIX_IMPLEMENTED_CANDIDATE_REJECTED`（本地；Provider 0；生产读写 0；未部署）

## 已完成的确定性修复

V1 的四字段 xG 点估计使用最近 5 场，但原
`empirical_xg_standard_error.v1` 对仓库返回的最多 20 场计算标准误。点估计和不确定性
因此描述了不同估计量。冻结协议
`V1_XG_UNCERTAINTY_WINDOW_CORRECTION_20260901.json` 后，代码只在既有 PIT、source、
digest 和 kickoff 检查全部通过后保留最近 5 场，并将方法身份提升为
`empirical_xg_standard_error.v2_latest_five`。点估计、模型参数、准入阈值、ledger 和
白名单均未改变。

这修复了 EV-SE 置信度链的真实缺陷，但不能单独证明模型点概率或全部 EV 已修复。

## 斜率候选的最终裁决

严格 PIT `8,659` 场开发集上，现役 `scale=1.0` 的净胜球回归 slope/intercept 为
`1.184837/-0.011194`；固定候选 `1.102038` 为 `1.075132/0.021717`。此前转述的
`1.848 [1.758, 1.939]` 没有生成脚本或不可变逐行 artifact，不能从仓库证据复现；若把
`1.848` 直接作为 scale，严格 PIT 结果反而是 slope `0.642919`、mean NLL
`2.993250392`，劣于现役 `2.960601796`。

rolling-origin OOF（warmup `1,500`、10 折、`7,159` 场）结果：

- 现役 slope/intercept：`1.173055/-0.020455`；
- 候选 slope/intercept：`1.028712/0.022801`；
- 候选改善 `7/10` folds；
- paired NLL candidate-current 均值 `-0.000415741`；
- 95% bootstrap CI `[-0.001435234, +0.000619995]`。

CI 上界仍高于 0，未通过预先冻结的 OOF 门。因此 `raw_delta_scale=1.102038` 保持
`REJECTED`：未写入生产参数、未递增 calibration version、未登记 ledger、未授权、未部署。

## 市场证据的解释更正

旧 283 场 A2 使用目标比赛自身赛后 xG，已作废。严格 PIT 市场重跑只有
`178 snapshot + 81 rebuild = 259` 场；24 场因赛前历史不足而排除。

旧市场门先用市场盘口定义 favorite，再计算模型与市场的差，属于条件选择：市场噪声越极端，
越容易被选为“强队侧”。因此 favorite-conditioned `0.349609` 只保留为开发诊断，不能当作
outcome-validity 或强迫模型复制盘口的部署门。signed HOME fair-minus-market 均值为
X `0.176641`、Y `0.005792`、Z `0.014479`；市场只参与价格比较，不是预测真值。

## 121 注已结算候选能证明什么

- evaluation→model capture identity 与 model-input manifest 均为 `121/121` 一致；
- 保存 EV 可由 evaluation 自己冻结的五态分布和赔率在 `1e-6` 内 `121/121` 复现；
- 原推荐方向与较高有效概率方向 `121/121` 一致；
- 决定性方向：AH `32/64=50.0%`，TOTALS `19/47=40.4%`，合计
  `51/111=45.9%`。

这些结果说明没有发现展示层 EV 算错或方向选择器拿错另一边；模型概率方向本身表现差。
该 cohort 已被查看，只能解释错误，不能选参或充当验证集。更早的 capture ladder 和后来覆盖的
latest checkpoint 都不能替代 evaluation 当时冻结的五态分布。

## 治理边界

- V1 只使用 Football-API 四字段 xG、主场项、Poisson/Dixon-Coles 与 AH/TOTALS 经济链；
  Elo、身价、首发属于 V2，不进入本修复。
- 当前可交付代码修复只有 xG uncertainty latest-five 对齐；它仍为本地待独立验收。
- 不得把本状态写成“EV 已完全修复”。新的点概率候选必须另立预注册和未查看验证证据，
  不能回头使用这 `8,659/259/121` 场挑参数。
