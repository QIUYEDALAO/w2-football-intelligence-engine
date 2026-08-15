# R9 CANARY_PASS 独立复核收口

线上测量时刻：`2026-08-15T06:17:54.740482Z`

## 结论

- `FREE_MODE_MODEL_VALIDATION_CANARY_PASS` 成立；它证明管道闭环，不证明模型质量。
- heartbeat `w2-free` 已恢复为 ACTIVE。自然 Scheduler 已于 `06:06:47Z` 首次成功跑通
  fixture-id POSTMATCH 路径；仍需监控其余 8 条 capture 直到逐场明确终态。
- 本轮审计查询 Provider calls 为 0、业务 DB writes 为 0；未调用 Statistics。

## 9 条 capture 逐场状态

Free 日期门最后可用日为开球 UTC 日期的次日；表中“到期”写成下一日 `00:00:00Z`
的排他边界。

| fixture_id | 联赛 | kickoff_utc | 当前状态 | POSTMATCH_RESULT | 终局比分 | 分类 | Free 日期门到期 |
|---|---|---|---|---|---|---|---|
| 1494244 | allsvenskan | 2026-08-14T17:00:00Z | FT | CAPTURED | 3-0，Outcome 已生成 | SETTLED | 2026-08-16T00:00:00Z |
| 1523240 | chinese_super_league | 2026-08-15T11:35:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-17T00:00:00Z |
| 1494248 | allsvenskan | 2026-08-15T13:00:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-17T00:00:00Z |
| 1494241 | allsvenskan | 2026-08-16T12:00:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-18T00:00:00Z |
| 1494242 | allsvenskan | 2026-08-16T12:00:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-18T00:00:00Z |
| 1494243 | allsvenskan | 2026-08-16T12:00:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-18T00:00:00Z |
| 1494245 | allsvenskan | 2026-08-16T14:30:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-18T00:00:00Z |
| 1494247 | allsvenskan | 2026-08-16T14:30:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-18T00:00:00Z |
| 1494246 | allsvenskan | 2026-08-17T17:00:00Z | 未开赛 | PLANNED | 否 | NOT_YET_DUE | 2026-08-19T00:00:00Z |

因此 R8 抢救窗口内没有第二条 capture 需要人工抢救；8 条未结算样本全部是正常
`NOT_YET_DUE`，不是 `RESULT_QUOTA_EXHAUSTED` 或 `RESULT_WINDOW_MISSED`。

## 3107 → 3116 的 9 次 Provider 调用对账

raw fixtures 前值为 `161`，9 次调用后为 `166`；raw Statistics 保持 `141`。
所有调用均进入 Provider ledger；`raw persisted=true` 来自 endpoint capture/run audit。

| UTC requested_at | endpoint | 参数 | HTTP/结果 | raw persisted | payload_sha256 |
|---|---|---|---|---|---|
| 2026-08-15T05:22:00.558463Z | fixtures | `id=1494244` | 200，1 条，FT 3-0（成功赛果） | true | `73675d2a6c9c6fc406e35e788e76f9e0c4c95eb440d53543ae4f6bf0fa686bcd` |
| 2026-08-15T05:56:12.561089Z | status | `{}` | 200，1 条 | true | `0a70bd44002fd1d1b3aafc73044da5d8b9d80d7a72ddf207658f33c9392fa5c9` |
| 2026-08-15T05:56:13.528881Z | fixtures | `league=113, season=2026, from=2026-08-14, to=2026-08-15` | 200，0 条，PROVIDER_PAYLOAD_ERRORS | true | `6d439b0d5c4cf28a9ca2e01ff346b37f264324ef0519788dd33517a6a2a2d3ea` |
| 2026-08-15T05:56:16.303357Z | status | `{}` | 200，1 条 | true | `0a70bd44002fd1d1b3aafc73044da5d8b9d80d7a72ddf207658f33c9392fa5c9` |
| 2026-08-15T05:56:17.453070Z | fixtures | `league=103, season=2026, from=2026-08-14, to=2026-08-15` | 200，0 条，PROVIDER_PAYLOAD_ERRORS | true | `7ac6e9355df94bbbf2a620a56b37a867272105baf273d6b26120600aafd77e55` |
| 2026-08-15T05:56:18.054474Z | status | `{}` | 200，1 条 | true | `0a70bd44002fd1d1b3aafc73044da5d8b9d80d7a72ddf207658f33c9392fa5c9` |
| 2026-08-15T05:56:19.897499Z | fixtures | `league=88, season=2026, from=2026-08-14, to=2026-08-15` | 200，0 条，PROVIDER_PAYLOAD_ERRORS | true | `1f3fba021566da4cd1c13c596e40d66ba3f5363893abae186f970dc0b7c9bdbe` |
| 2026-08-15T05:56:21.030781Z | status | `{}` | 200，1 条 | true | `0a70bd44002fd1d1b3aafc73044da5d8b9d80d7a72ddf207658f33c9392fa5c9` |
| 2026-08-15T05:56:21.677404Z | fixtures | `league=94, season=2026, from=2026-08-14, to=2026-08-15` | 200，0 条，PROVIDER_PAYLOAD_ERRORS | true | `ee33aaff13d4a46a7cccb9b326936737cc379b04ad9ec33304ac1b4e5c4592c6` |

成功取回 1494244 的就是第一条；此前报告遗漏了它，造成 `8 + 0 != 9`。

## 自然 Scheduler 的 fixture-id 验收

在 9 次抢救账目之后，线上自然 Scheduler 于 `2026-08-15T06:06:47.679477Z` 和
`06:06:49.092743Z` 对 argentina_primera fixture `1493072` 依次执行：

- `status {}`：HTTP 200、response_count 1；
- `fixtures {id: 1493072}`：HTTP 200、response_count 1；
- raw fixtures SHA：`b3247e5a81afde7b088b4426d4623f7dd3ff056c6b0bf5e211d92acfaea6176e`；
- Provider logs `3116 -> 3118`，raw fixtures `166 -> 167`，raw Statistics `141 -> 141`。

这满足“fixture-id POSTMATCH 专属额度与优先级路径由自然 Scheduler 成功执行至少一次”的
验收，不是人工 Provider 探针。heartbeat 只因 8 条 capture 尚无终态而继续运行。

## 模型质量边界

- n = 1；`MIN_BUCKET_SAMPLES_FOR_RATE=30`，`SAMPLE_TARGET=200`。
- HOME/DRAW/AWAY = `0.331510 / 0.254890 / 0.413600`，真实结果主队 3-0。
- LogLoss `1.104112386514` > `ln(3)=1.098612288668`。
- 结论：`INSUFFICIENT_SAMPLE`。CANARY_PASS 不得改写成模型有效。

## 配额一致性修复与部署

- future-refresh 与 matchday policy baseline：80；staging compose：80；POSTMATCH 独立 cap：20；已知 Free plan limit：100。
- `config_from_policy()` 在生效通用 cap 高于 100 时、任何 Provider 请求前 fail closed 为
  `PROVIDER_DAILY_CAP_EXCEEDS_KNOWN_FREE_PLAN_LIMIT`。
- exact source/tree：`674bd806480bdec83ec8fc0a6ff69363be3e24c2` /
  `b828ed4727924564bb033449de6e23e36226f7f4`。
- Python/Web digest：`sha256:5701ea414d148e3bde5f13326e592bd1b8c6686ac4aeb53d64297325f5e597e4` /
  `sha256:3aa803ee7260f1d678702aad694af3509b2a65ceda08db0637377a5fc18de724`。
- 部署窗口 Provider `3118 -> 3118`、raw fixtures `167 -> 167`、raw Statistics
  `141 -> 141`；部署后 canary 前后 Provider/raw Statistics `3118/141 -> 3118/141`。
- focused/relevant 验证 `144 passed`，Ruff/Mypy PASS。完整套件运行到 95% 时触发仓库既有
  Stage7I 本机 sudo 探测并等待密码；未输入凭据，停止前为 `2567 passed, 13 skipped`，
  不记为完整套件 PASS。
