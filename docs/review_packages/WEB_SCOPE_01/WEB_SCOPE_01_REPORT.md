# WEB-SCOPE-01 — 停用联赛对外投影与 release 一致性

状态：`LOCALLY_VERIFIED / NOT_DEPLOYED`

## 结论

泄漏根因在 API 读侧的范围分裂：`_dashboard_competition_ids()` 读取了注册表全部条目，却没有应用 `CompetitionRegistryEntry.enabled`；`/matchday`、`/fixtures` 又经未过滤的 `dashboard_latest_fixtures()` 读取 checkpoint。Web 的联赛中文标签不是范围权威。

修复后，所有比赛类公开入口先经同一条 `league_season.payload.enabled -> CompetitionRegistry.enabled_ids()` 范围过滤。日期条、workspace 的 `active_whitelist_count` 与 `/v1/version` counts 也使用该动态集合，不再含联赛名或联赛数硬编码。

## 生产只读基线与前后对照

冻结时点：`2026-08-24T08:20:00Z`。Provider 调用 0、生产写入 0。

| 对外路径 | 接入前 | 接入后 | 判定 |
|---|---:|---:|---|
| `/v1/matchday?date=2026-08-24` | 11 场 | 10 场 | 移除 `1494253 / allsvenskan` |
| `/v1/dashboard` / DayView / intelligence workspace | 11 场输入 | 10 场输入 | 共同 batched fixture reader 过滤 |
| 雷达 / 重点观察 | 11 场可进入投影 | 10 场可进入投影 | 它们只从 workspace matches 派生，停用行不再有输入 |
| `/v1/fixtures` 与单场子路径 | 停用 checkpoint 可见 | 停用 fixture 不可见 | 列表与单场 projection 均复用同一 scope |
| 赛后推荐 / 战绩 | `1494253` 为 0 条 official opportunity，且已由 `c582ace4` 过滤停用联赛 | 不变 | 本次不重算、不改历史 |
| `/v1/version` fixture/card counts | 320 | 269 | 去掉 allsvenskan 25 + CSL 26 = 51 个 checkpoint |

日期条的 `active_whitelist_count` 从代码常量 13 改为 DB 动态值；本次冻结值为 11。Pydantic 与 TypeScript 合同也从 literal 13 改为非负整数，并保留 `competition_count <= active_whitelist_count` 一致性检查。

## fixture 1494253 的可达性

生产只读事实：

- checkpoint plans：`CAPTURED 3 / SKIPPED_POLICY 11`；三条 CAPTURED 是 T168/T72/T48 的采集事实，不等于推荐。
- dynamic evaluations：6 条，其中 2 条历史 `ANALYSIS_PICK_ACTIVE`，但 `official_funnel_eligible=true` 为 0。
- dynamic opportunities：0；outcome ledger 仅 4 条 `record_type=capture / recommendation_scope=NONE`。
- 当前分析卡：`decision_tier=NOT_READY / candidate=false / formal_recommendation=false / v4_outcome=NOT_READY`。

因此它在修复前可能进入比赛卡、雷达或重点观察的普通投影，但不能进入 official recommendation 或 `c582ace4` 已过滤的正式战绩。修复后，上游比赛范围已先移除该 fixture，历史 CAPTURED/evaluation 行仍完整保留。

## Release 一致性

冻结生产状态为 API `d05ab74217e37af2e85732ac3a63ee4d9e214aa1`、Web `ae5b4d884c9f2f4da98b5c6874e7703fef4d720b`。既有 `scripts/verify_release_sync.py` 对该状态返回 1，证明漂移可检测，但 `deploy-python-only.sh` 没有把它作为发布 gate。

新增 `ops/host/w2-release-sync-preflight`：发布修改 `release.env` 前同时检查 Python/Web 两个 OCI image 的 `org.opencontainers.image.revision`，任一缺失、两者不同或不等于 expected SHA 均返回 2。发布流程必须同时构建两镜像并先运行该 preflight，切换后再运行已有 public release-sync；不再把 Python-only image change 视为完整 release。

## 可复现与验收

```bash
uv run python scripts/run_web_scope_01.py --check
uv run pytest -q tests/unit/test_web_scope_filter.py
```

`--check` 从冻结输入重算全部对照并逐字段比较 evidence，同时静态检查公共读路径不存在固定 13。将 evidence 任一字段（包括 `scope_retention_ratio` 的 `1e-6`）变更后，命令必须返回非 0。

权威文件：

- `WEB_SCOPE_01_FROZEN_INPUT.json`
- `WEB_SCOPE_01_EVIDENCE.json`
- `scripts/run_web_scope_01.py`

本包未部署、未调用 Provider、未写生产数据库。
