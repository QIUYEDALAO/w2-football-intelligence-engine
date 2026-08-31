# V1 模型修复进度与证据边界

状态：`IN_PROGRESS`（本地只读分析；Provider 0；生产写入 0；未部署）

## 已确认的真实进展

- 按冻结预注册截点导出 `team_xg_match`，得到 `19,102` 行 / `9,551` 场；
  SHA-256 `16fcaaad812e8007c7e828c964d7029bc223e361cdac87b122c56eba9e8e3522`，
  与既有冻结来源一致。
- 按严格“目标开赛前、双方各至少 5 场历史”重建训练集，得到 `8,659` 场。
- 按预注册公式 `adjusted_delta = raw_delta_scale × raw_delta + 0.30`、
  现有 total/lambda clamps、Dixon-Coles rho `0.0` 和确定性 golden-section，
  训练集拟合值为 `raw_delta_scale=1.102038`。
- 10 折 rolling-origin OOF（warmup `1,500`）拟合值范围 `1.113134–1.166136`，
  OOF 净胜球回归斜率 `1.028712`、截距 `0.022801`。这些是开发诊断，
  不是授权或上线判据。

## 发现并撤回的 283 场证据

旧 `A1_PIT_EVIDENCE_REDO.json` 的 `teams.xg_for/xg_against` 实际来自目标比赛自身
的 `team_xg_match` 行，而不是目标开赛前滚动状态。例：fixture `1490136` 的目标行
为 `0.87/0.40`，旧 A2 因此产生 X 轨 `lambda_home=0.97 / lambda_away=0.38`。
这违反 PIT 规则；不能用于候选模型验收。按完整历史 xG 严格重建时，105 场 rebuild
中只有 `81` 场双方均有至少 5 条先前记录，`24` 场输入不足，详见
`A1_PIT_REBUILD_COVERAGE_AUDIT.json`。

因此现有 `A2_SIMULATION_OUTPUTS.json` 和基于它的 market-shape 数字已撤回，不能
支持“候选优于现役”或任何部署决定。正确后续是先由 Owner 确认 24 场输入不足的
排除/最低历史规则，再用严格 PIT 输入重跑 X/Y/Z 三轨。

## 治理边界

- `raw_delta_scale=1.102038` 仅为冻结 TRAIN 开发拟合结果，未写入生产参数、ledger
  或白名单，也未改变当前推荐行为。
- 121 条已结算候选仅用于诊断，不用于选择该值；283 场市场集同样不用于最终认证。
- V1 不引入 Elo、身价或首发；这些属于 V2 独立轨道。
