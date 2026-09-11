# R10 —— R9 闭环复核执行结果

线上最终测量时刻：`2026-08-15T08:05:55Z`

## 结论

- `R10-1`、`R10-2`、`R10-3`、`R10-4` 均已关闭。
- `R9-3` 余下 `3116 -> 3118` 两次自然调用已纳入同一账目并对平。
- 线上终态仍为 `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`；这只证明管道闭环，
  不证明模型质量。
- 本任务未调用 Provider、未新增 Statistics、未改 cadence、阈值或联赛，未启动
  Formal、Lock、Production 或 Round4。

## 最终代码与线上身份

- 最终 source commit：`f39f2f2529be0be57371e8b0af6be7776d8961a1`
- 最终 tree：`41367dcb5653292a6570946878b30d5e2dcb36ac`
- source archive SHA-256：`62bd25573e32cef7968306ea2a19809850de5d0dd76239a66c97483894e3f4b5`
- Python image：`sha256:7c190154b86989363939808b443628788833f72902e0710263155dee3a3034b7`
- Web image：`sha256:5677f953bbb8291d1e4f35e14d941c692f4049528e9bdf1875b5dd71f7b75d03`
- Alembic：`0056_floor_model_forecast_lead_time`
- `/ready`：`READY`，schema/artifacts 均 PASS；`/v1/version` 与 `/meta.json` 均为
  `f39f2f2529be0be57371e8b0af6be7776d8961a1`。

实现分为三个最小提交：

1. `d7bfad5f7cfae2b6fd5d01e2df421e99a921177f`：配额池、缓冲、lead-time 分层、
   privileged test 隔离；
2. `eb4f01aad200e58795a703ba821c4b9ff1e75159`：修正历史 lead-time 的整秒取整；
3. `f39f2f2529be0be57371e8b0af6be7776d8961a1`：把 lead-time 字段接入 Dashboard
   响应 schema 与前端类型。

## R10-1：对所有注册配额池求和

唯一注册表为 `REGISTERED_PROVIDER_DAILY_QUOTA_POOLS`。当前注册池：

| pool | 环境变量 | 上限 |
|---|---|---:|
| GENERAL | `W2_PROVIDER_DAILY_HARD_CAP` | 70 |
| POSTMATCH_RESULT | `W2_POSTMATCH_RESULT_DAILY_HARD_CAP` | 20 |

`config_from_policy()` 遍历注册表读取所有池，再调用
`provider_daily_budget_contract()` 对注册池总和与未分配缓冲统一求和。因此未来新增第三个
注册池会自动进入校验，不需要追加另一条硬编码条件。

线上零 Provider 验证：临时只覆盖 `GENERAL=100`、`POSTMATCH=20`、`BUFFER=10`，
`config_from_policy(allsvenskan)` 在任何 Provider 请求前以退出码 1 fail closed：

`PROVIDER_DAILY_BUDGET_EXCEEDS_KNOWN_FREE_PLAN_LIMIT`

## R10-2：70 + 20 + 10

当前 Free 套餐预算契约为：

| 项目 | 数量 | 可否被请求使用 |
|---|---:|---|
| 通用池 | 70 | 是 |
| POSTMATCH 专属池 | 20 | 仅 POSTMATCH_RESULT |
| 未分配缓冲 | 10 | 否 |
| Provider 已知日限 | 100 | 上限 |

配置中的 `daily_unallocated_buffer=10` 与运行时
`W2_PROVIDER_DAILY_UNALLOCATED_BUFFER=10` 一致。预算判定始终使用 billable calls：
Provider ledger / Provider quota usage；审计同时输出 `billable_calls_today`、
`successful_calls_today` 和 `budget_basis=BILLABLE_PROVIDER_CALLS`。

`successful_calls_today` 只表示 transport HTTP 2xx，不表示业务 payload 可用；例如
Free plan 返回的 payload error 仍是 billable。任何预算结论均不使用 successful count。

## R10-3：lead-time 契约与真实 9 条分层

契约明确为 `FIRST_ELIGIBLE_FREEZE_IMMUTABLE`：首次满足四字段 xG 与身份硬门时冻结，
同一 `(fixture_id, model_family, model_version)` 不更新、不覆盖。未来如引入多次冻结，
必须改变 capture 身份契约并追加新记录，不能覆盖既有记录。

历史迁移最初暴露了 PostgreSQL `numeric -> bigint` 四舍五入问题：例如
`34610.530820` 被写为 `34611`，而运行时使用 `int(timedelta.total_seconds())=34610`。
`0056` 将历史值统一为 floor 整秒，并同步 Outcome；payload、payload SHA、capture/outcome
identity 均未改动。最终完整性为 capture `0 invalid`、outcome `0 invalid`。

| fixture_id | kickoff_utc | captured_at | lead_time_seconds | bucket |
|---|---|---|---:|---|
| 1494244 | 2026-08-14T17:00:00Z | 2026-08-14T07:23:09.469180Z | 34610 | H6_TO_LT_24H |
| 1523240 | 2026-08-15T11:35:00Z | 2026-08-14T07:23:09.469180Z | 101510 | D1_TO_D3 |
| 1494248 | 2026-08-15T13:00:00Z | 2026-08-14T07:23:09.469180Z | 106610 | D1_TO_D3 |
| 1494241 | 2026-08-16T12:00:00Z | 2026-08-14T07:23:09.469180Z | 189410 | D1_TO_D3 |
| 1494242 | 2026-08-16T12:00:00Z | 2026-08-14T07:23:09.469180Z | 189410 | D1_TO_D3 |
| 1494243 | 2026-08-16T12:00:00Z | 2026-08-14T07:23:09.469180Z | 189410 | D1_TO_D3 |
| 1494245 | 2026-08-16T14:30:00Z | 2026-08-14T07:23:09.469180Z | 198410 | D1_TO_D3 |
| 1494247 | 2026-08-16T14:30:00Z | 2026-08-14T07:23:09.469180Z | 198410 | D1_TO_D3 |
| 1494246 | 2026-08-17T17:00:00Z | 2026-08-14T07:23:09.469180Z | 293810 | GT_3D |

Capture 分布为 `H6_TO_LT_24H=1 / D1_TO_D3=7 / GT_3D=1 / LT_6H=0`。
Outcome 只有 `1494244`，属于 `H6_TO_LT_24H`。概率指标接口不再输出跨 bucket
总均值，只输出四个 bucket：

- `H6_TO_LT_24H n=1`：Brier `0.682903900178`、LogLoss `1.104112386514`、
  RPS `0.308951688937`；
- 其余三个 bucket：`n=0`，均值为 null。

## R10-4：默认测试不再请求 sudo

真实主机 observer-once 用例已标记 `requires_privilege`，只有
`W2_RUN_PRIVILEGED_TESTS=1` 时才运行；默认摘要明确显示
`SKIPPED_REQUIRES_PRIVILEGE`。无人值守默认完整套件现可到达终态。

- 完整套件：`2643 passed, 14 skipped, 2 warnings`；
- privileged 默认跳过：`1` 条，原因 `SKIPPED_REQUIRES_PRIVILEGE`；
- Mypy：277 source files PASS；Ruff：PASS；Web TypeScript：PASS。

其余 skip 为缺少 Docker 或未配置 `W2_TEST_POSTGRES_URL` 的显式环境前提，不含 sudo
交互。

## R9-3：3116 -> 3118 对账

| requested_at UTC | endpoint | 参数 | HTTP | raw_payload | SHA-256 |
|---|---|---|---:|---|---|
| 2026-08-15T06:06:47.679477Z | status | `{}` | 200 | 无 endpoint raw 行 | 不适用 |
| 2026-08-15T06:06:49.092743Z | fixtures | `{id:1493072}` | 200 | 2026-08-15T06:06:51.255265Z | `b3247e5a81afde7b088b4426d4623f7dd3ff056c6b0bf5e211d92acfaea6176e` |

request hash 分别为
`bdc60fbcb64c35a88f4665822cb63a1e204e8669272e39b2f9b12b75fe3f469e` 与
`c577ecf43b12c3d51d95c6586b504b7b30427ebefbacd803ba2a64dca1a7417d`。
因此 Provider `3116 -> 3118`、raw fixtures `166 -> 167`、raw Statistics
`141 -> 141` 全量对平。

## 线上回归与公开页面验收

第一次部署 lead-time 投影时，公开接口因 API response schema 未声明三个新字段而返回
500。该回归由真实公开 URL 截图发现，未被本地测试冒充通过。最终提交补齐后：

- `GET /v1/dashboard/intelligence-workspace?...`：HTTP 200，30 matches；
- 两条当天已冻结记录在线返回 `lead_time_bucket=D1_TO_D3`；
- 公开 Dashboard 正常渲染；最终截图 SHA-256：
  `3ee7dda6683668db3325ea3f3cf2712e4b4463ac882c7b9524bb228714ca891b`。

部署与复核窗口固定口径：Provider logs `3118 -> 3118`、raw fixtures
`167 -> 167`、raw Statistics `141 -> 141`、captures `9 -> 9`、outcomes `1 -> 1`。

## Canary 与模型质量边界

最终 canary：`9 / 9 / 1 / 1`，`RAW_STATISTICS_RESTORE_HASH_MATCH=true`，
ledger integrity `0/0`，状态精确为 `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`。

模型表现仍为 `INSUFFICIENT_SAMPLE`：n=1，低于
`MIN_BUCKET_SAMPLES_FOR_RATE=30` 与 `SAMPLE_TARGET=200`，且唯一 LogLoss 高于均匀先验。
Owner 决定保持：不购买、不续开 Pro。
