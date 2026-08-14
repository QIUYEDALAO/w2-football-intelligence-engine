# R7 LIVE_SAMPLE_ACCEPTANCE_PARTIAL 复核结果

## 结论

`LIVE_SAMPLE_ACCEPTANCE_PARTIAL` 保留，但理由更正如下：

- R7-2 已修复并完成线上真实样本验收。9 场已有 `ModelForecastCapture` 的比赛，页面 F9 与账本现在同源同值，均为 `READY`。
- R7-1 的旧生产分支确实不可达，但现有 `xg.reason/source_status` 不是 Provider 不支持的权威证据。将它直接接成 `PROVIDER_NOT_AVAILABLE` 会违反“真实 Statistics 响应持续为空才允许确认”的硬规则。因此本项状态为 `BLOCKED_BY_EVIDENCE_RULE`，不能伪造巴甲或挪超截图。
- R7-3 的 `2868` 与 `2876` 没有发生计数回退；它们是同一 VPS、同一数据库、同一全表总数口径下相差 10 分钟的两个时点，文档展示顺序造成了反向阅读。
- R7-4 的 `144` 行仅覆盖 2026-08-14 当日 8 场。当前 2026-08-14 至 2026-08-21 的去重范围为 55 场、990 行，role mismatch 为 0。

当前终态仍不是 `FREE_MODE_MODEL_VALIDATION_CANARY_PASS`。真实 canary 为 `9/9/0/0`，仍被真实赛果与概率指标样本阻断。

## R7-1：Provider 不支持判定

### 复核结论

旧链路只读取 `factor_checklist_inputs.provider_xg_unavailable_confirmed`，生产没有权威 writer，因此 `PROVIDER_NOT_AVAILABLE / STRUCTURAL_PERMANENT` 分支不可达。这个判断成立。

但建议接入的旧 `xg.reason` 同样不能作为 writer：旧值 `PROVIDER_EMPTY_OR_UNAVAILABLE` 在两队都没有已物化比赛和 snapshot 时生成，无法区分以下原因：

- 没有保存 raw Statistics；
- 保存了响应但没有 Expected Goals 字段；
- 保存了 Expected Goals 字段但值为空；
- 身份或 materialization 尚未完成。

当前 VPS 有 141 条 raw Statistics：Allsvenskan 103 条（52 条 xG 非空、50 条字段为空、1 条无字段），中超 31 条（18 条非空、13 条字段为空），FA Cup 7 条（7 条均无字段）。巴甲和挪超没有当前 raw Statistics 响应。没有 exact-13 联赛达到 `PROVIDER_XG_UNSUPPORTED_CONFIRMED` 的证据标准。

### 已完成的最小修复

- 零历史状态从 `PROVIDER_EMPTY_OR_UNAVAILABLE` 改为 `NO_MATERIALIZED_HISTORY`。
- Dashboard 显示 `NO_MATERIALIZED_HISTORY / UNKNOWN`，不再承诺 `UNDER_SAMPLED / SELF_RESOLVING`。
- SC21 离线审计将旧值和新值都归为 `SOURCE_AVAILABILITY_UNVERIFIED`，first break 为 `SOURCE_AVAILABILITY_NOT_DISAMBIGUATED`。
- `PROVIDER_NOT_AVAILABLE` 仍只接受显式 confirmed 事实；本次没有增加伪 writer。

### 未完成且不得伪造的验收

当前不能提供巴甲或挪超的真实 `PROVIDER_NOT_AVAILABLE / STRUCTURAL_PERMANENT` 截图。要使该分支合法可达，未来必须先有一个持久化、可审计的 capability authority，且其证据是同一 league/season/endpoint 的真实 Statistics 响应中 Expected Goals 持续为空。当前 `Provider calls=0` 边界下没有这种新证据。

因此，R7-1 的准确状态是：生产分支不可达已确认；误导性自愈承诺已消除；Provider unsupported 真实样本仍未获得权威确认。

## R7-2：9 场页面与账本一致性

旧线上 release `63469955f9fa2ab17c639c577aa649e7e0f1e227` 对 9 场全部显示：

`MISSING / NO_MATERIALIZED_HISTORY / UNKNOWN / 0 / 0`，而账本为 `CAPTURED`。跨页面与账本冲突成立。

新 release `52095ef1c0aa69736c39b26e09e64e278a05c7da` 将持久化 capture 的 `four_field_xg_identity` 投影到公开 ledger fact；schema 要求 capture/settled 状态必须有 64 位 identity hash、两侧 snapshot identity 和两侧至少 3 场。页面 F9 对已有 capture 的 fixture 直接使用该持久化事实。

| fixture | competition | kickoff UTC | F9 state | cause | permanence | home/away | ledger/model track |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1494241 | Allsvenskan | 2026-08-16 12:00 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494242 | Allsvenskan | 2026-08-16 12:00 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494243 | Allsvenskan | 2026-08-16 12:00 | READY | null | NOT_APPLICABLE | 4/5 | CAPTURED/READY |
| 1494244 | Allsvenskan | 2026-08-14 17:00 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494245 | Allsvenskan | 2026-08-16 14:30 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494246 | Allsvenskan | 2026-08-17 17:00 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494247 | Allsvenskan | 2026-08-16 14:30 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1494248 | Allsvenskan | 2026-08-15 13:00 | READY | null | NOT_APPLICABLE | 5/5 | CAPTURED/READY |
| 1523240 | Chinese Super League | 2026-08-15 11:35 | READY | null | NOT_APPLICABLE | 3/3 | CAPTURED/READY |

完整 identity hash 与逐场证据见 `R7_MODEL_FORECAST_XG_CONSISTENCY.json`。

线上 fixture 1494244 的体检表截图：

`/Users/liudehua/.codex/visualizations/2026/08/14/019ffdcc-f72d-7113-b983-18ab659a09d1/r7-xg-ready-1494244.png`

截图 SHA-256：`a3cf83dc468b04bfc6b73ec13615cf90810bdf2c19a8f3ae5e4c110a4bffc263`。浏览器错误 0，1512px viewport/document 宽度均为 1512。

## R7-3：Provider 日志口径

四个全表序号对应的真实时点如下：

| ordinal | requested_at UTC | endpoint | status |
| --- | --- | --- | --- |
| 2868 | 2026-08-14 08:35:23.590024 | odds | 200 |
| 2876 | 2026-08-14 08:45:24.587991 | fixtures | 200 |
| 2917 | 2026-08-14 10:00:10.969629 | fixtures | 200 |
| 2933 | 2026-08-14 10:30:34.321179 | fixtures | 200 |

`2868 -> 2876` 是正常单调增长。此前报告把较早的 R5 快照放在较晚 heartbeat 之后阅读，产生了“下降 8”的错觉。

全仓库没有运行时 `DELETE`、`TRUNCATE` 或 archive `provider_request_logs` 的路径。唯一可删除整表的是 migration 0003 的显式 downgrade；它不是运行时归档。当前 PostgreSQL `pg_stat_user_tables.n_tup_del=0`。

后续固定报告口径：

1. 同一 VPS、同一 PostgreSQL 容器和数据库；
2. 报告 observation time、全表 count、min(requested_at)、max(requested_at)；
3. 再报告精确半开区间 `[audit_start, audit_end)` 内的 request count；
4. 将自然 Scheduler 的区间外增长与本次读取调用分开。

本次线上 T+7 读取窗口：

- start `2026-08-14T11:17:41.607712Z`，总数 2973；
- end `2026-08-14T11:17:45.579932Z`，总数 2973；
- 区间内新增 0；八个响应的 `provider_calls=0`、`db_writes=0`、`no_call_on_read=true`。

canary 窗口：

- start `2026-08-14T11:18:01.373315Z`，总数 2973；
- end `2026-08-14T11:18:04.749625Z`，总数 2973；
- 区间内新增 0；canary 自报 `provider_calls=0`、`db_writes=0`。

部署前较宽的观察区间曾自然增长 `2964 -> 2973`，这正说明以后不能只拿跨 Scheduler 窗口的两个总数证明一次读取没有调用 Provider。

## R7-4：role 覆盖范围

原 `144` 行结论只覆盖 2026-08-14 的 8 场，即 `8 × 18`。该范围内 mismatch 为 0 的结论保留，但不得写成 T+7 全量。

本次对 2026-08-14 至 2026-08-21 逐日读取后按 fixture 去重：

- fixture 55；
- factor row 990；
- role mismatch 0；
- F9 READY 9；
- F9 `NO_MATERIALIZED_HISTORY / UNKNOWN` 46；
- `PROVIDER_NOT_AVAILABLE / STRUCTURAL_PERMANENT` 0。

`/v1/version.read_model_fixture_count=95` 是当前 read-model 总库存，不是所选 T+7 日期范围的 fixture 数，因此不能用 `95 × 18` 作为本次 role 比对分母。

## 发布与回归

- source/tree：`52095ef1c0aa69736c39b26e09e64e278a05c7da` / `cdb965ee3b6218cdee2fe18c830143710a9b6d22`；
- Python/Web digest：`sha256:83ea2e6b31a881f235d803e6555223498d73eff614ff79ef3712f681a199fa69` / `sha256:e99a5874293454088450ae1e813c23ca4c45be5d40fc1b759fa341e1835e8058`；
- `/ready=READY`，schema `0054/0054`，API/Web exact SHA 一致，API/worker/scheduler/web healthy；
- 完整 Python：2633 passed、13 skipped；focused：135 passed；Ruff、Mypy、Web typecheck/build、diff-check 通过；
- raw Statistics 141、capture 9、outcome 0、team_xg_match 140、rolling snapshot 72；
- `RAW_STATISTICS_RESTORE_HASH_MATCH=true`，账本 invalid capture/outcome 均为 0。

首个 Python overlay 虽然带新 label，但运行时仍从旧 `site-packages` 导入，候选当场被拒绝并回滚到 `63469955...`。最终镜像改为覆盖实际 import path，并在切换前用 `inspect.getfile()` 和源码断言验证后才重新部署。未把错误候选当成发布成功。

## 保持关闭

- Pro：不购买、不续开；
- 新 Statistics 调用：0；
- cadence、模型阈值、联赛：未修改；
- Formal、Lock、Production、Round 4：关闭；
- `PRO_REOPEN_OWNER_DECISION_PACKET`：未生成。
