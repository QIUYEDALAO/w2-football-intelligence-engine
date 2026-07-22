# P352-A0：瑞典超错误样本冻结

代码基线：`3e3766dcc24ad0ab960034aafa223cd65d084005`（PR #352 head）

本文件只记录已在该基线的 staging 只读检查中确认的样本；不调用 provider，
不写业务数据库、ledger、queue 或 lock。

| fixture_id | 比赛 | 开球（UTC） | 最后赛前捕获 | 基线问题 |
| --- | --- | --- | --- | --- |
| 1494210 | IF Elfsborg vs Sirius | 2026-07-19 14:30 | 2026-07-19 14:18:57Z | AH/OU authoritative pair 已完整且新鲜，但 V3 为 `NOT_READY/DATA_NOT_READY` |
| 1494212 | Halmstad vs BK Hacken | 2026-07-19 14:30 | 2026-07-19 14:18:57Z | 同上 |
| 1494213 | Hammarby FF vs Degerfors IF | 2026-07-19 14:30 | 2026-07-19 14:18:57Z | 同上 |

冻结语义：三场均为 `allsvenskan`，不是五大联赛；首发未确认只能是
`LINEUPS_NOT_CONFIRMED_ADVISORY`。基线错误由三项共同造成：analysis context
错误回退到 `world_cup_2026`、未形成 selected-line model/market evidence、以及
`PARTIAL` 被 V3 统一投影为 `NOT_READY`。

验收不变量：fixture/provider/bookmaker/captured_at/line/opposite selections 必须来自
同一 authoritative quote pair；formal AH/OU、LMM numeric adjustment、lock 与 production
均保持关闭。
