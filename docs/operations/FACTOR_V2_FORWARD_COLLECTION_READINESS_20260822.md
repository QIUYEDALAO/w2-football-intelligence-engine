# Factor V2 前向影子采集上线准备报告（2026-08-22）

结论：`LOCAL_SELF_REVIEW_PASS / PRODUCTION_DEFERRED`。本地实现、反向合同测试与生产只读输入兼容性核对通过；这不等于 PostgreSQL 角色实测、容器运行验收或生产上线。生产仍为 release `4114034243173d18b572bce82fc564a5d292fda2`、schema `0069_outcome_ledger_run_state`，尚未迁移、未部署、未写入任何 V2 forward row。按 Owner 裁定避开 08-23，首次生产动作只能在之后的静默窗口进行。

## 2026-08-23 自我审查

本轮没有沿用“测试通过即验收通过”的口径。逐路径审查发现并修复以下问题：

- 预注册与 collection artifact 原先只做自洽 hash 校验，运行时未钉死 Owner 冻结版本；现在同时固定预注册文件 SHA、artifact 文件 SHA、artifact canonical SHA，并交叉核对 split/preprocessing/calibration/ablation hash、F3/F7 active factors、F6 排除状态及所有禁影响标志。任一字节或绑定变化都在数据库访问前 fail closed。
- 忙时延期原先先执行 writer 全表权限审计，再检查 V1 checkpoint；现在未来 60 分钟存在正式档位时只执行 read-only checkpoint 查询，不创建 writer 路径、不做全表权限扫描、零 V2 写入。
- 静默窗口现在不是批跑开始时的一次性检查：每场计算前、整批写入前及每条写事务前都会按真实当前时间重查；窗口关闭时保留已提交的 append-only V2 行、停止后续写入并延期，下一批只补未写 capture，避免长任务越过初始 60 分钟边界。
- 原先直接信任 V1 capture payload；现在逐条核对 payload SHA、capture identity SHA、列与 payload 的 fixture/competition/time/model/hash 绑定、four-field xG 总体与双侧 identity hash、禁 candidate/exact-quote 标志。任何损坏均在 V2 写入前停采集并关闭开关。
- 前向输入来自已冻结的 V1 capture，因此运行时对 xG 实际执行更严格的 captured-at 点时规则；每条 V2 payload 同时记录预注册 `SOURCE_KICKOFF_ONLY`、实际 `STRICT_CAPTURED_AT` 与方法版本，避免把注册语义和有效执行语义混写。
- 原先所有 capture 被排除仍可能返回 `PASS`；现在零产出且存在 eligible capture、PIT 泄漏、非预期排除或写入错误都会标 anomaly、零写入并关闭开关。
- 前向完赛配对原先使用裸 fixture join 且 `count(*)`；现在使用 canonical fixture SQL helper、仅计 `FT/AET/PEN`，并按 distinct canonical fixture 计数。
- 生产写入新增不可变 release identity 与 Provider isolation 前置审计：Git/build/release/image 三种 digest 不得为占位值且 digest 必须一致；collector 环境不得包含 API-Football key，Provider calls 必须关闭、Provider scheduler 必须关闭。

反向测试已覆盖冻结文件篡改、忙时禁止 role audit、损坏 V1 capture 写前阻断、canonical alias 重复赛果去重、release/Provider 环境 fail closed。

## 预注册

- 文件：`docs/operations/FACTOR_V2_FORWARD_COLLECTION_PREREGISTRATION_20260822.json`
- 文件 SHA-256：`cad4b549bc8a00d56ad29f1913bc8ebd582a21ee8524b86a4fb7e24480f936c1`
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

二次只读核验时刻：`2026-08-22T20:23Z`。

- 生产仍为 schema 0069，V2 writer role 尚不存在，V2 表与 forward row 尚未上线。
- 冻结 cohort 起点后的 eligible V1 capture 为 17 条，17/17 均为 `w2.model_forecast_capture.v2`；capture hash 字段、source xG hash、fixture/competition identity、captured/kickoff 时间轴及禁影响标志的 SQL 结构核对均为 0 mismatch。
- 生产现有 ledger integrity 为 `invalid_capture=0 / invalid_outcome=0 / missing_data_version=0`；当前库可重导 143 条、不可重导 10 条，后者按既有合同不等于冻结账本 invalid。
- 数据库为 PostgreSQL `16.15`；migration 登录账号当前具备 `SUPERUSER/CREATEROLE`，满足创建受限角色的迁移前提，但不替代 migration 0070 后的 live privilege audit。

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
- 本机没有 Docker/PostgreSQL，4 个 PostgreSQL 定向用例仍为 skip；生产角色、真实 `SET ROLE`、表级权限和写入拒绝矩阵均必须在 migration 0070 后现场实测。
- 独立容器的真实 release identity、Provider isolation 与静默延期报告尚未形成生产回执。

这些项目必须在 08-23 之后的静默窗口逐项验收；在此之前不得把本报告解释为“生产验收通过”或“已上线”。

## 审查后的任务清单

- [x] 冻结 prereg/artifact 的运行时精确绑定与篡改反向测试。
- [x] 忙时探针收敛为单一 checkpoint 只读查询。
- [x] V1 capture/xG 完整性、写前全批验证与零产出 fail-closed。
- [x] 完赛配对 canonical alias、terminal status 与 distinct fixture 口径。
- [x] release identity / Provider isolation 前置审计与 Compose 环境绑定。
- [x] 生产只读核对现有 V1 capture 兼容性、schema 与迁移账号前提。
- [ ] `2026-08-23T00:05Z` 先完成 08-22 全天 Provider timeout/BLOCKED 报告；不得与 V2 部署合并。
- [ ] 08-23 全日继续只观察、不部署；确认 coverage run 与 V1 周末链正常。
- [ ] 08-23 之后首个静默窗口保存 V1 前快照，再执行 migration 0070。
- [ ] migration 后逐表实测 writer `SELECT/INSERT` 与全部非授权 DML 拒绝；任何一项不符即不启用 collector。
- [ ] 在 `DISABLED` 下运行容器并证明零写入，再启用一次；核对 exact release/digest、Provider 0、PIT 0、V2 新增与 V1 后快照。
- [ ] 形成首个生产回执后再决定是否启用 timer；Gate 2、outcome/evaluation、candidate、通知、正式盈亏继续关闭。

## 本地验证

- Ruff 全仓通过；本次改动模块 Mypy 通过。
- 自我审查后的 V2 forward、Gate 0、消融、compose、架构矩阵与迁移定向测试：`116 passed / 4 skipped`。4 个 skip 均要求本地未提供的 PostgreSQL 测试实例。
- 最终全量 Pytest：`2872 passed / 14 skipped / 1 failed`。唯一失败来自 Git 忽略的用户学习记录触发既有敏感信息扫描，与本次改动无关；本轮未修改该记录。
- 全量 Mypy 检查 291 个 source 文件，仅保留改动前已有的 `src/w2/ingestion/future_refresh_repository.py:653` union-attr 问题；本次改动文件无 Mypy 错误。
- 本机无 Docker/PostgreSQL 测试实例，因此 writer 角色 live privilege audit 只能在 08-23 之后的生产静默窗口执行；在该项通过前维持 `PRODUCTION_DEFERRED`。
