# XG-INGEST-01 — saved-raw 入库缺口复核

Status: `ROOT_CAUSE_CONFIRMED_PROVIDER_ZERO_REPLAY_BLOCKED_NO_NUMERIC_RAW_PRODUCTION_CHANGE_NOT_AUTHORIZED`

## 结论

根因已确定：缺口不是 numeric xG 在写入事务里丢失，而是 **两队 `expected_goals` 字段存在、值却为 JSON `null` 的 statistics 响应被错误当成永久 cache hit**。解析器对这类 payload 正确地产出 0 行；错误发生在其后续状态语义——`raw_statistics_fixture_ids()` 只凭 `parameters.fixture` 判定“已缓存”，后续采集从此不再请求。529 场均未到达 `upsert_team_xg_matches()`，因此球队身份解析、批次写入和事务回滚不是这 529 场的原因。

冻结口径下，真正的“numeric saved raw 已存在但未物化”是 `0`。所以现存 raw 的 Provider 0 重放可新增 `0` 场，不能把 529 个 `null` 变成数值。执行虚假的数据库回补会违反非空数值契约；实际补齐需要 Owner 另行批准有界 Provider 重试及生产写入，本轮均未执行。

Provider calls / production writes / outcomes reads: `0 / 0 / 0`。

## 精确分类

- null 响应被终态缓存、需要重新采集：`529` 场。
- 历史 payload 原本无 `expected_goals` 字段：`11` 场，不是入库缺陷。
- 2026-08-18 后仍在 Provider 发布窗内：`15` 场，单列，不算残余丢失。
- 当前启用集合内，2026-08-18 后已经发布并落库：`54` 场。
- Provider 落库滞后统计沿用核验方的全体已物化口径：p50 / p90 / max = `18.2h / 80.8h / 127.8h`（n=`56`）。该 n 比当前启用集合的 54 场多 2 场，二者不是同一分母，绝不混算覆盖率。
- 核验方已确认 `9,423` 场每场恰好 2 行、单边和空字段均为 0；按 Owner 补丁不重复投入。原 869 是精确值，不是下界。

## 逐联赛回补前后

不计算整体覆盖均值。`Provider 0 后` 是真实可重放结果，不是假设 Provider 已发布；因此本冻结样本中与回补前相同。`null cached` 是需要重新请求 Provider 的历史缺口，`provider pending` 是尚在正常发布窗内的比赛，`source absent` 是历史 payload 根本没有 xG 字段；三者不得合并为残余入库丢失。

| competition | finished | persisted | null cached | source absent | provider pending | Provider 0 additions | coverage before | coverage after Provider 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `argentina_primera` | 847 | 347 | 494 | 3 | 3 | 0 | 0.409681 | 0.409681 |
| `brasileirao_serie_a` | 608 | 604 | 0 | 2 | 2 | 0 | 0.993421 | 0.993421 |
| `bundesliga` | 481 | 477 | 4 | 0 | 0 | 0 | 0.991684 | 0.991684 |
| `eliteserien` | 377 | 371 | 6 | 0 | 0 | 0 | 0.984085 | 0.984085 |
| `eredivisie` | 501 | 482 | 17 | 0 | 2 | 0 | 0.962076 | 0.962076 |
| `la_liga` | 590 | 590 | 0 | 0 | 0 | 0 | 1.000000 | 1.000000 |
| `ligue_1` | 485 | 481 | 4 | 0 | 0 | 0 | 0.991753 | 0.991753 |
| `mls` | 852 | 839 | 0 | 5 | 8 | 0 | 0.984742 | 0.984742 |
| `premier_league` | 578 | 578 | 0 | 0 | 0 | 0 | 1.000000 | 1.000000 |
| `primeira_liga` | 492 | 488 | 4 | 0 | 0 | 0 | 0.991870 | 0.991870 |
| `serie_a` | 586 | 585 | 0 | 1 | 0 | 0 | 0.998294 | 0.998294 |

## 采集日血缘

“含 expected_goals”必须区分字段存在与数值存在。原交接数字对应前者；只有后者能进入非空 Float 列。

| captured date | statistics raw | field on both sides | numeric on both sides | materialized | field present but null |
|---|---:|---:|---:|---:|---:|
| 2026-07-21 | 103 | 102 | 52 | 52 | 50 |
| 2026-08-04 | 38 | 31 | 18 | 18 | 13 |
| 2026-08-16 | 5500 | 5489 | 4719 | 4719 | 770 |
| 2026-08-17 | 4584 | 4583 | 4554 | 4554 | 29 |
| 2026-08-18 | 5 | 5 | 5 | 5 | 0 |
| 2026-08-23 | 95 | 82 | 75 | 75 | 7 |

## 防复发

1. cache 命中条件改为“两队 numeric xG 完整”，null/缺字段保持 retryable；该代码变更只在本地验证，未部署。
2. 独立 guard 只在“numeric saved raw 已存在但 team_xg_match 不是恰好两条非空行”时报警；Provider pending 不混入该报警。
3. 529 场历史补齐需要新的 Provider 权限与生产写入决策。没有授权前，报告保持 blocked，不自行执行。

## 可复现边界

- production release: `d05ab74217e37af2e85732ac3a63ee4d9e214aa1`; schema: `0070_notification_delivery_routing`; observed at: `2026-08-23T15:40:00Z`。
- scope 动态读取 `league_season.payload.enabled`，没有固定联赛数量。
- SQL 是 `REPEATABLE READ READ ONLY`；不读取 outcomes。
- `--check` 逐字比较 JSON 与 Markdown，单字段 1e-6 变异会失败。
