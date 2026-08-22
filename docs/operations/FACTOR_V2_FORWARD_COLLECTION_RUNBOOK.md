# Factor V2 前向影子采集运行手册

状态：仅批准采集；Gate 2 关闭；禁止影响推荐、通知与正式盈亏。

## 运行架构

- `factor-v2-forward-collector` 是每日一次的独立短生命周期容器，不使用 Celery、Redis 或生产 worker。
- 容器只读取 V1 已落库的 `model_forecast_capture`、saved raw 与相关权威只读表；Provider 调用固定为 0，容器环境不注入 API-Football key。
- V1 reader 连接被设为 PostgreSQL read-only session；V2 writer 连接先执行 `SET ROLE w2_factor_shadow_v2_writer`。
- provider league ID 从生产 DB 权威 `league_profile/league_season` 读取；运行时不得读取 competition 安装 seed 文件，也不得经实时 fixture identity 表兜底。
- writer 角色只拥有五张 V2 表的 `SELECT/INSERT`，其他表没有 `SELECT/INSERT/UPDATE/DELETE/TRUNCATE`。
- `captured_at` 与 `feature_as_of` 都严格等于配对 V1 capture 的 `captured_at`；`computed_at` 是延迟批跑时刻，必须不早于 `captured_at`。
- 定时器每小时 `:05` 只做静默窗口探测，`Persistent=false`；宿主状态文件保证实际批计算每天最多一次。任务检查未来 60 分钟所有正式 checkpoint 的 `scheduled_at`，并阻断任何与该时段重叠的 PLANNED/DUE 有效窗口（包括 `scheduled_at` 已刚刚越过但状态尚未推进的计划）；存在即返回 `DEFERRED_FOR_V1_CHECKPOINT_SLOT`，只执行计划查询、零 V2 写入。首个静默探测成功后记录当天完成状态，其余探测直接返回 `ALREADY_COLLECTED_TODAY`。

## 无需重新部署的停采集开关

宿主机位置：`/opt/w2/shared/runtime/factor-v2/enabled`

- 内容严格为 `ENABLED` 才允许采集。
- 改成 `DISABLED` 后，在当前 fixture 事务结束、下一 fixture 事务开始前生效。
- 异常、PIT 泄漏或 writer 权限审计失败时，程序会原子写入 `DISABLED`。
- 停止定时触发可另行执行 `systemctl disable --now w2-factor-v2-forward-collector.timer`；数据库 migration 不需要回退。

每日完成状态文件：`/opt/w2/shared/runtime/factor-v2/last-success-utc-date`。它只控制“每天最多一次”，不是授权开关；不得手工提前写入未来日期。

## 首次上线前置条件

只能在 08-23 之后的静默窗口执行；若与 V1 有任何冲突，放弃 V2 窗口。

1. 确认 API、worker、scheduler、web 四个业务容器均 healthy。
2. 确认未来 60 分钟没有正式临场档位。
3. 保存 V1 上线前快照：四容器状态、当天临场 `CAPTURED/matured`、V1 权威表行数。
4. 验证预注册文件 SHA-256 与 Obsidian《重要决定》完全一致。
5. 执行 migration 0070；确认 schema 仅从 0069 前进到 0070，六张新增表存在，既有 V1 表行数不变。
6. 以 writer 会话执行 live privilege audit，必须满足：
   - `current_user = w2_factor_shadow_v2_writer`
   - 角色 `NOLOGIN/NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS`
   - 登录角色 membership 为 `INHERIT FALSE, SET TRUE, ADMIN FALSE`
   - 五张 V2 表仅 `SELECT/INSERT=true`、`UPDATE/DELETE/TRUNCATE=false`
   - 其他 public 表 `SELECT/INSERT/UPDATE/DELETE/TRUNCATE=false`
7. 先在 `DISABLED` 状态运行一次，必须返回 `COLLECTION_DISABLED` 且零写入。
8. 原子切换为 `ENABLED`，只运行一次 collector。
9. 保存 V1 上线后快照并与上线前对照；任一 V1 权威表计数下降或临场 CAPTURED 率下降，立即停采集。

## 每日自证

每次运行报告写入 `/opt/w2/shared/runtime/factor-v2/reports/`，至少包含：

- 本次 V2 新增行数与 UTC 当日 V2 新增行数；
- 当日 V1 T60/T45/T-30m/T15 `CAPTURED/matured/rate`；
- V1 capture、opportunity、evaluation、outbox、outcome ledger、endpoint capture、result 等权威表行数；
- Provider 调用数（必须为 0）；
- PIT 排除与泄漏计数（泄漏必须为 0）；
- candidate、notification、official P&L 输出数（必须全部为 0）；
- writer live privilege audit 与静默窗口审计。

采集器不写 `factor_shadow_forecast_outcome`，因此不会在预注册日期前形成中途指标；达到预注册样本量也不得提前查看。

## 硬隔离核对

V2 仅允许新增 `factor_shadow_forecast_capture`。以下 V1 表在批跑前后必须保持只读：

- `model_forecast_capture`
- `dynamic_prematch_opportunities`
- `dynamic_prematch_evaluations`
- `candidate_notification_outbox`
- `outcome_ledger`

同时禁止 Bark、正式推荐、candidate/opportunity 影响与官方盈亏；历史 replay 行不得计入 `FORWARD_SHADOW` 完赛配对数。
