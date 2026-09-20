# W2 Dashboard 冷缓存诊断与候选复测（2026-09-20）

## 边界

- 数据源：生产 PostgreSQL，只读一次性 API 容器。
- 强制设置：`PGOPTIONS=-c default_transaction_read_only=on`；每轮均回读
  `SHOW transaction_read_only = on`。
- 未部署、未写生产库、未调用 Provider、未启动采集任务。
- 代码边界：只调整 Dashboard 列表/首屏展示投影和单场按需详情读取；推荐、EV、校准和结算链路不变。

## 原始冷缓存诊断

生产基线：

| 端点 | 冷缓存耗时 |
| --- | ---: |
| `/v1/dashboard` | 18.897s |
| `/v1/dashboard/summary` | 18.984s |

90 场完整卡投影约 23.64MB；`/dashboard` 的 `upcoming` 与 `all` 重复后响应约
47.35MB。逐步计时确认完整 JSON 卡读取、逐卡完整投影和 collection/refresh status
是主要耗时。

完整 `analysis_card` 中体积最大的字段如下（90 场合计）：

| 字段 | 合计字节 | 单场最大字节 |
| --- | ---: | ---: |
| `markets` | 4,885,335 | 60,589 |
| `market_candidates` | 4,236,557 | 52,761 |
| `pricing_shadow` | 4,089,879 | 52,442 |
| `dynamic_prematch` | 4,062,868 | 142,823 |
| `simulation` | 3,550,850 | 40,981 |

初版字段级 SQL 仍对每张大 JSON 卡重复解压；90 场摘要查询实测 10.357s。改为
`json_to_record` 单次标量投影，并将非首屏字段固定为“详情未加载”，避免在列表读取
完整卡；日期条也改为只读取所需关系列。

## 候选冷缓存复测

候选镜像在每个端点测量前重启，启动后只调用 readiness（不命中 Dashboard 的 60 秒
响应缓存），再调用目标端点。三次冷测：

| 端点 | 第 1 次 | 第 2 次 | 第 3 次 | 门槛 |
| --- | ---: | ---: | ---: | ---: |
| `/v1/dashboard` | 1.852s | 1.843s | 1.712s | ≤3s |
| `/v1/dashboard/day-view` | 2.211s | 1.908s | 2.113s | ≤5s |

补充端点：

| 端点 | 冷缓存耗时 | HTTP |
| --- | ---: | ---: |
| `/v1/dashboard/summary` | 2.051s | 200 |
| `/v1/dashboard/intelligence-workspace?projection=summary` | 2.057s | 200 |
| `/v1/dashboard/intelligence-workspace/matches/1492380` | 1.426s | 200 |

单场详情响应包含完整 `market_radar` 与 `model_lab`。结论：候选实现满足首开 ≤3s、
day-view ≤5s 的冷缓存门槛。
