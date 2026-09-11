# R19 Provider dispatch 与配额降级收口

测量窗口：2026-08-16 UTC  
边界：Provider calls=0；未调用 Statistics；未修改阈值、联赛、冻结策略或调度 cadence。

## R19-1：135 次真实发出为何只产生 10 次 Provider 计费

不存在本地请求缓存或 payload 新鲜度短路。`ApiFootballClient.request_live()` 在
`urllib.request.urlopen()` 返回之后才写 `provider_request_logs`；`live=true` 的准确契约是
“请求已经真实发往 Provider”，不是“Provider 已计费”。2026-08-16 00:00Z–03:46Z 的
135 行全部为真实网络发出且 HTTP 200，其中 65 次为 `status`、65 次为 `fixtures`、5 次为
`odds`。`status` 是额度观察接口，不扣日额度；65 次 `fixtures` 中 60 次得到
`response_count=0` 的 Free 访问限制响应，且不含日额度响应头，只有 5 次有效 `fixtures`
和 5 次 `odds` 推动 `x-ratelimit-requests-remaining` 从 100 降到 90。因此 HTTP 200 只证明
传输成功，不能单独证明 Provider 计费；判断计费的唯一权威仍是响应头/quota_usage。

零调用数据库证据：

| endpoint | 真实发出 | 不同参数 | 不同 payload | 携带日额度头 | 空响应 |
|---|---:|---:|---:|---:|---:|
| status | 65 | 1 | 7 | 65 | 0 |
| fixtures | 65 | 9 | 9 | 5 | 60 |
| odds | 5 | 5 | 5 | 5 | 0 |

## R19-2：行级语义与降级算法

不新增 `dispatched` DB 列。现有 `provider_request_logs.live` 已逐行准确表达真实网络发出；
再建同义列会制造双重权威。实现改为所有 dispatched 计数显式过滤 `live=true`，并把该契约
写入模型注释和运维文档。

GENERAL 额度判定：

- 权威新鲜：使用 Provider `quota_usage.used`。
- 权威过期：使用 `最后一次 Provider used + last_authority_at 之后 live=true 的发出数`。
- 权威完全缺失：使用当日 `live=true` 发出数。
- run audit 和全部 ledger attempt 只作诊断，不再覆盖计费判定。

这是保守上界：权威过期后的 `status` 或访问限制响应仍可能未计费，但最多造成预期的保守
暂停；不会再把权威时刻之前已被 `used` 覆盖的 135 次全天请求重复相加。

审计新增/明确输出：

- `last_authority_at`
- `authority_age_seconds`
- `dispatched_count`
- `dispatched_since_authority_count`
- `attempt_count`
- `quota_degradation_classification=EXPECTED_DEGRADED`

回归覆盖 attempt=100、dispatched=2 的场景，降级 known_count 为 provider baseline 4 +
authority 后 dispatched 2 = 6，不按 attempt 100 判定超限。

## R19-3：预期降级

`QUOTA_AUTHORITY_DEGRADED` 同时携带 `EXPECTED_DEGRADED`。该状态表示计费权威过期后的
保守暂停，不等于 Provider 日额度耗尽，不升级为 P0。等待下一次自然真实请求带回额度头后，
权威口径会刷新；HTTP 429、日额度耗尽和 expected degradation 继续使用独立状态。

## R19-4：70 / 20 / 10 预算复核

最近三个完整 UTC 日的零调用账目：

| UTC 日 | 本地真实发出 | Provider 计费峰值 | Provider 日限 | GENERAL 70 是否触及 |
|---|---:|---:|---:|---|
| 2026-08-13 | 1007 | 53 | 100 | 否 |
| 2026-08-14 | 590 | 80 | 100 | 是，超 10 |
| 2026-08-15 | 21 | 81 | 100 | 是，超 11 |

三个数字当前并非同一量纲：

- GENERAL 70：Provider billable header 口径，覆盖全 Provider 当日计费总量。
- POSTMATCH 20：W2 内部 request-attempt 口径；每场 `status + fixtures = 2` 次。
- buffer 10：相对 Provider 日限 100 的不可消费计费缓冲。

因此 POSTMATCH 20 是 GENERAL 总计费护栏内的正交 attempt 上限，不能与 GENERAL 的
billable 70 直接相加成真实 Provider 用量。当前启动期 `70 + 20 + 10 = 100` 仍是保守配置
校验，但不是计费账目恒等式。

当前未结算 capture 为 6 条，其中同一结果日最多 5 条，需 10 次 POSTMATCH attempt；即使
9 条同日也只需 18 次，20 仍足够，建议维持。GENERAL 70 在最近三个完整日中有两日过紧。
建议后续由 Owner 决定是否把模型改成“Provider 总计费 cap 90 + 不可用 buffer 10”，并保留
正交 POSTMATCH attempt cap 20；在 Owner 批准前不调整任何额度。

## 结论

R19-1 已解释；R19-2/R19-3 已按现有 `live` 行级契约以最小改动完成；R19-4 仅给数据与建议，
未改变 70 / 20 / 10。POSTMATCH capture 优先与预留保持不变。

本地验证：`2661 passed / 14 skipped`；其中特权测试按契约
`SKIPPED_REQUIRES_PRIVILEGE`，无测试失败。
