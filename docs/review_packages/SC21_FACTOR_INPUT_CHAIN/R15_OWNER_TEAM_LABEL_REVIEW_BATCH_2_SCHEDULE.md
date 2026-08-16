# R15 Owner 球队译名审定 · 当前赛程一次性收口

Owner 于 2026-08-16 明确授权剩余球队一次性审定，不再拆批。原“剩余 35 支”是旧赛程快照；重新读取线上 2026-08-16 与 2026-08-17 workspace 后，当前真实并集为 44 支。44 支全部进入同一权威配置并标记 `APPROVED`，不再保留后续批次。

| 联赛分组 | 旧快照 | 当前赛程并集 | 状态 |
|---|---:|---:|---|
| 阿根廷甲级联赛 | 8 | 13 | 全部 `APPROVED` |
| 荷兰甲级联赛 | 8 | 8 | 全部 `APPROVED` |
| 西班牙联赛 | 4 | 6 | 全部 `APPROVED` |
| 美国职业足球大联盟 | 10 | 8 | 全部 `APPROVED` |
| 葡萄牙联赛 | 5 | 9 | 全部 `APPROVED` |
| **合计** | **35** | **44** | **当前赛程缺口全部关闭** |

逐条 provider team id、canonical identity、中文名和依据来源保存在 `config/identity/public_team_labels.zh-CN.v1.json`；该配置是公开译名运行时权威。本页只记录审定批次与口径变更，避免形成第二套映射表。

## 已审定：挪威超级联赛 8 支

| Provider team id | Canonical identity | 中文名 | 依据来源 |
|---:|---|---|---|
| 2149 | `w2:team:api_football:2149` | 费德列斯达 | LiveScore 中文球队页 |
| 319 | `w2:team:api_football:319` | 布兰 | Sofascore 中文球队页 |
| 325 | `w2:team:api_football:325` | 特罗姆瑟 | LiveScore 中文比赛页 |
| 326 | `w2:team:api_football:326` | 瓦勒伦加 | LiveScore 中文球队页 |
| 329 | `w2:team:api_football:329` | 莫尔德 | LiveScore 中文比赛页 |
| 332 | `w2:team:api_football:332` | 桑纳菲尤尔 | 新浪体育中文球队页 |
| 333 | `w2:team:api_football:333` | 萨尔普斯堡08 | 新浪体育中文球队页 |
| 757 | `w2:team:api_football:757` | 阿勒桑 | LiveScore 中文球队页 |

状态：8 条均为 `APPROVED`；线上 2026-08-16 workspace 均为 `CHINESE_LABEL_READY`，待审计数为 0。
