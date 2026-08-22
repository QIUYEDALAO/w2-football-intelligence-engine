# Factor V2 前向影子采集上线准备报告（2026-08-22）

结论：`LOCAL_READY / PRODUCTION_DEFERRED`。本地实现与定向验证通过；生产仍为 release `4114034243173d18b572bce82fc564a5d292fda2`、schema `0069_outcome_ledger_run_state`，尚未迁移、未部署、未写入任何 V2 forward row。按 Owner 裁定避开 08-23，首次生产动作只能在之后的静默窗口进行。

## 预注册

- 文件：`docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json`
- 文件 SHA-256：`ffc491caf4fe10d47646b1ba2f383eca74d2a99a16a7423489cb99629ccbb662`
- 冻结时刻：`2026-08-22T09:05:33Z`
- 历史 replay cutoff：`2026-08-21T19:18:10.674088Z`
- 第一次且仅一次评估日期：`2028-02-01T00:05:00Z`
- 最小完赛配对样本：5,500；若日期到达但样本不足，不评估，且必须在查看指标前另行冻结新日期。
- 指标：LogLoss、RPS、多分类 Brier、10 个等宽 bin 的 top-label ECE；ECE 对 B0、B2 与配对差值各做 5,000 次 paired-fixture bootstrap 95% percentile CI。
- 禁止中途试看、禁止提前评估。

样本量不是沿用建议值 1,000。Gate 1 HOLDOUT 的逐场配对 LogLoss 差值为 `B2-B0=-0.0092168129`，样本 SD 为 `0.2436879920`；双侧 alpha 0.05、80% power 的正态近似需要 5,487 场，预注册向上取整为 5,500。

## 生产只读输入核验

只读核验时刻：`2026-08-22T09:23Z`。

- 六个运行容器均为 Up，API、Postgres、Redis、scheduler、web、worker 的健康检查均正常。
- `model_forecast_capture` 共 136 行，覆盖 11 个白名单联赛。
- 136/136 都有 home/away API-Football provider team ID。
- 136/136 都有 home/away `component_team_xg_matches` 数组。
- V1 payload 内嵌 `provider_league_id` 为 0/136；采集器因此从生产 DB 权威 `league_profile/league_season` 读取 13 联赛 API-Football 映射，不直接读取安装期 seed JSON，也不经过仅覆盖少量比赛的实时身份表。13 联赛权威行的 canonical hash 与解析结果写入每条 V2 payload/hash，冲突时 fail closed。
- 136 条 capture 的 1,349 个 xG component 中：source kickoff 不早于目标 kickoff 为 0；component captured_at 不早于 V1 captured_at 为 0；目标 fixture 自身进入 xG component 为 0。
- `team_xg_match` 共 18,696 行，`source_system` 唯一值为 `api_football_statistics`，与冻结方法版本 `api-football.expected-goals.statistics.v1` 一致。

## 实现隔离

- 独立 Compose profile 容器与独立 systemd timer；不挂 Celery worker，不使用生产队列。
- 容器没有 Redis/Celery 配置，也没有 Provider API key；Provider 开关固定关闭。
- V1 reader 强制 read-only session；V2 writer 使用单独连接并 `SET ROLE`。
- migration 0070 纯增量创建六张表；forecast 表新增 `computed_at` 与 forward 双时间轴约束。
- 运行时 flag 位于 `/opt/w2/shared/runtime/factor-v2/enabled`，最迟在下一 fixture 事务前生效。
- 每小时 `:05` 轻量探测未来 60 分钟所有正式 checkpoint；有冲突即只读延期，首个静默窗口执行实际批计算，状态文件保证每天最多一次。
- 每次运行输出 V2 当日新增、V1 临场 CAPTURED 率、V1 权威表行数及角色 live privilege audit；异常自动停采集。

## 当前未完成项

- 生产 migration 0070 尚未执行。
- 独立 collector image/service/timer 尚未部署或启用。
- writer 权限尚未在生产 schema 0070 上实测。
- 生产前后 V1 健康快照尚未形成。
- 第一条 V2 forecast 尚未写入。

这些项目必须在 08-23 之后的静默窗口逐项验收；在此之前不得把本报告解释为“已上线”。

## 本地验证

- Ruff 全仓通过；本次改动模块 Mypy 通过。
- V2 forward、Gate 0、消融、compose、架构矩阵与迁移定向测试：`99 passed / 4 skipped`。4 个 skip 均要求本地未提供的 PostgreSQL 测试实例。
- 全量 Pytest：`2865 passed / 14 skipped / 1 failed`。唯一失败仍是 Git 忽略的用户文件 `.learnings/ERRORS.md` 中旧 SSH 错误文本触发 secret guard，与本次改动无关，未修改该文件。
- 全量 Mypy 检查 291 个 source 文件，仅保留改动前已有的 `src/w2/ingestion/future_refresh_repository.py:653` union-attr 问题；本次改动文件无 Mypy 错误。
- 本机无 Docker/PostgreSQL 测试实例，因此 writer 角色 live privilege audit 只能在 08-23 之后的生产静默窗口执行；在该项通过前维持 `PRODUCTION_DEFERRED`。
