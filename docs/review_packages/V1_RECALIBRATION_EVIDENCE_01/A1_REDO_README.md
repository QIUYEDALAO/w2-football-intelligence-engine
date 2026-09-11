# A1 重做（coverage-corrected）

上一版 `e649b223` 的 A1 artifact 已作废：market 导出使用了隐含行数上限，
只覆盖 19 个 fixture。该错误是导出方式造成的，不代表生产数据缺失。

本版冻结抽取时刻 `T_EXTRACT=2026-08-30T15:58:43Z`。所有 SQL 使用服务端
`COPY (...) TO STDOUT WITH CSV HEADER`，没有 `LIMIT`、客户端分页或交互式窗口；
market 使用任务允许的紧凑工作集（每 fixture/bookmaker/market/selection/line
保留最新 captured_at）。

## 断言结果

`xg_fixtures=433`、`joined_quote_fixtures=283`、`eligible_quote_fixtures=283`、
`market_rows=118015`、`bookmakers=14`、`snapshot_track=178`、`rebuild_track=105`，
全部与预期相符。SQL 仍未选择任何赛果或比分字段。

Artifact：`A1_PIT_EVIDENCE_REDO.json`
