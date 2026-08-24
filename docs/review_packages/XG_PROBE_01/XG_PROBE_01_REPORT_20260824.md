# XG-PROBE-01 — 有界 Provider 重试探针

Status: `A_ALL_STILL_NULL_NO_529_ROLLOUT`

## 结论

10/10 仍无 numeric xG，按预注册分支 A：不应铺开 529 场重试；这些历史缺口进入 Provider 不可得 / fail-closed 设计。

这是 Provider 可得性探针，不写 `raw_payload`、`team_xg_match`、Provider ledger 或任何业务表。Provider calls / production writes / deploy / model changes / EV-SE changes = `10 / 0 / 0 / 0 / 0`。

## 执行门与额度

- 临场门：`2026-08-24T02:11:27.754468+00:00` 至 `2026-08-24T03:11:27.754468+00:00`，正式档位 `0`。
- 执行前额度：daily `7376/7500`，burst `298/300`，authority at `2026-08-24T02:00:08.113522+00:00`。
- 第 10 次响应后额度：daily `7367/7500`，burst `290/300`。
- 样本从冻结的 902 场集合中选；先要求 kickoff `< 2026-08-18T00:00:00Z`，再要求原响应两队 xG 都为 null。联赛内按 `md5(fixture_id || ':XG-PROBE-01')` 排序，禁止按本次结果挑样。

## 10 行对照

| fixture | league | kickoff | original captured_at | original xG | current xG | probe captured_at |
|---|---|---|---|---|---|---|
| `1334458` | `argentina_primera` | 2025-04-12T21:00:00+00:00 | 2026-08-16T19:09:57.631962+00:00 | `null / null` | Barracas Central=null / Tigre=null | 2026-08-24T02:11:29.226725Z |
| `1491872` | `argentina_primera` | 2026-02-08T01:15:00+00:00 | 2026-08-16T19:20:11.340422+00:00 | `null / null` | Newells Old Boys=null / Defensa Y Justicia=null | 2026-08-24T02:11:29.658115Z |
| `1334500` | `argentina_primera` | 2025-04-27T22:00:00+00:00 | 2026-08-16T19:10:51.207579+00:00 | `null / null` | Lanus=null / San Martin S.J.=null | 2026-08-24T02:11:30.086075Z |
| `1492028` | `argentina_primera` | 2026-04-19T16:30:00+00:00 | 2026-08-16T19:24:11.560903+00:00 | `null / null` | Aldosivi=null / Racing Club=null | 2026-08-24T02:11:30.518790Z |
| `1334327` | `argentina_primera` | 2025-02-08T01:15:00+00:00 | 2026-08-16T19:06:06.461577+00:00 | `null / null` | Independ. Rivadavia=null / Estudiantes L.P.=null | 2026-08-24T02:11:30.941878Z |
| `1334461` | `argentina_primera` | 2025-04-14T21:00:00+00:00 | 2026-08-16T19:10:09.188183+00:00 | `null / null` | Central Cordoba de Santiago=null / Huracan=null | 2026-08-24T02:11:31.356539Z |
| `1376436` | `eredivisie` | 2025-05-29T18:00:00+00:00 | 2026-08-17T01:53:20.838495+00:00 | `null / null` | Telstar=null / Willem II=null | 2026-08-24T02:11:31.822994Z |
| `1375155` | `eredivisie` | 2025-05-17T14:30:00+00:00 | 2026-08-17T01:52:50.261377+00:00 | `null / null` | ADO Den Haag=null / Telstar=null | 2026-08-24T02:11:32.255094Z |
| `1375859` | `ligue_1` | 2025-05-29T18:30:00+00:00 | 2026-08-17T00:42:46.245068+00:00 | `null / null` | Reims=null / Metz=null | 2026-08-24T02:11:32.704983Z |
| `1545418` | `bundesliga` | 2026-05-25T18:30:00+00:00 | 2026-08-17T00:14:15.063021+00:00 | `null / null` | SC Paderborn 07=null / VfL Wolfsburg=null | 2026-08-24T02:11:33.126023Z |

## 按联赛恢复率与 529 场估算

| league | recovered / n | recovery rate | historical gap | estimated recovery |
|---|---:|---:|---:|---:|
| `argentina_primera` | 0/6 | 0.0% | 494 | 0.00 |
| `eredivisie` | 0/2 | 0.0% | 17 | 0.00 |
| `ligue_1` | 0/1 | 0.0% | 4 | 0.00 |
| `bundesliga` | 0/1 | 0.0% | 4 | 0.00 |

529 场中，抽样联赛覆盖历史缺口 `519` 场；未抽样的 `10` 场来自 `eliteserien, primeira_liga`。后者的估算只能外推本次 pooled recovery rate，不能冒充逐联赛实测。完整铺开额度是逐场一次、共 `529` 次；本报告不授权铺开或生产写入。

## 可复现与失败条件

`python scripts/run_xg_provider_retry_probe.py --check` 只读取冻结 raw probe，不访问生产或 Provider；它重建本 JSON 和本报告并逐字段比较。样本数、联赛配额、902 来源集合、临场门、10 次调用、每行 fixture 绑定、quota header 与表内任一数值漂移都会失败。
