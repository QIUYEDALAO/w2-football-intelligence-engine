# R15 Owner 球队译名审定 · 第一批（瑞超 2 支）

状态：`PENDING_OWNER_REVIEW`。本表提交候选，不构成 Owner 批准；在明确审定前不得进入 `APPROVED` 权威集。

| 联赛 | Provider team id | Canonical identity | 候选中文名 | 依据来源 |
|---|---:|---|---|---|
| 瑞典超级联赛（Allsvenskan） | 2170 | `w2:team:api_football:2170` | 哥德堡盖斯 | Provider/本地 crosswalk 原名 `Gais`；[GAIS 官网](https://www.gais.se/?page_id=10)确认俱乐部身份及 Allsvenskan；[球天下中文球队页](https://data.qtx.com/qiudui/vJ6YrwDWM5.html)采用“哥德堡盖斯” |
| 瑞典超级联赛（Allsvenskan） | 377 | `w2:team:api_football:377` | AIK索尔纳 | Provider/本地 crosswalk 原名 `AIK Stockholm`；[Sofascore 中文球队页](https://www.sofascore.com/zh/football/team/aik/1764)采用“AIK索尔纳”；[中文维基球队页](https://zh.wikipedia.org/wiki/AIK%E8%B6%B3%E7%90%83%E9%9A%8A)用于 Solna 身份交叉核对 |

Owner 审定动作仅允许二选一：将单条状态改为 `APPROVED`，或退回并保留 `PENDING_OWNER_REVIEW` 后修订候选。不得以部署或页面显示代替审定。

