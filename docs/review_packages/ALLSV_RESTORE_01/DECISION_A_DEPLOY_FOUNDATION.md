# Decision A — 部署 null 重试与动态刷新

Status: `OWNER_DECISION_REQUIRED`

授权范围仅限：

- 部署 `5b926ee8` 等价的 null statistics 不再命中永久缓存逻辑；
- 部署 `4733c76f` 等价的首次可见 team xG 证据保护；
- 安装本分支 `ops/host/w2-xg-refresh`，其范围在运行时读取 `league_season.payload.enabled`；
- release/health/精确版本与脚本内容验收。

不授权 Provider 回补、启用瑞超、改变中超、重开计划或改模型。验收证据必须形成 SHA256，供 Decision C 强制引用。
