# Gate 2 `candidate-eval.v2` 前向样本门槛计数

- 查询窗口：`2026-09-25 06:48–07:18 UTC`（期间原始 v2 评估最大 `evaluated_at` 未变化）
- 查询位置：`root@45.207.194.97` 的 `w2-staging-postgres-1`
- 查询方式：所有统计包在 `BEGIN READ ONLY` 事务中执行，最后 `ROLLBACK`；没有生产写入。
- 身份：`dynamic_prematch_evaluations.evaluation_policy_version='candidate-eval.v2'`。
- PIT 绑定：`model_forecast_capture_identity_hash → model_forecast_capture.capture_identity_hash`；PIT 为 `captured_at <= evaluated_at < kickoff_utc`。
- 双侧盘口：`matchday_market_observations` 使用 `provider_fixture_id=e.fixture_id`、同 `capture_id`、Pinnacle `bookmaker_id=4`、同 `canonical_market`。TOTALS 要求 OVER/UNDER 同 exact line；AH 的 `exact_line` 是评估选边的带符号线，反向侧须取**相反符号**（HOME `-0.25` 对 AWAY `+0.25`），不能把 AWAY `-0.25` 错配为反向赔率。

核心零写证据（查询在只读事务中执行）：

```sql
SELECT evaluation_policy_version, count(*), count(DISTINCT fixture_id)
FROM dynamic_prematch_evaluations GROUP BY evaluation_policy_version;
-- candidate-eval.v2 | 3024 | 332

SELECT count(*) FILTER (WHERE m.capture_identity_hash IS NOT NULL),
       count(*) FILTER (WHERE m.captured_at <= e.evaluated_at
                         AND e.evaluated_at < m.kickoff_utc)
FROM dynamic_prematch_evaluations e
LEFT JOIN model_forecast_capture m
  ON m.capture_identity_hash=e.model_forecast_capture_identity_hash
WHERE e.evaluation_policy_version='candidate-eval.v2';
-- 3024 | 3024
```

最新去重使用 `DISTINCT ON (fixture_id, market) ORDER BY evaluated_at DESC`；双侧检查的 join 字段见本报告开头，特别使用 `provider_fixture_id`，没有把带 `api_football:` 前缀的 `fixture_id` 当作市场观察 join 键。生产 `formal_recommendation.py:288-290` 也要求 AH `home_line + away_line ≈ 0`；只读库里的同号 HOME/AWAY 行虽然都存在，却不是同一两面盘口。

AH 配对 SQL 表达式为 `home_line = CASE WHEN e.selection='AWAY' THEN -e.exact_line ELSE e.exact_line END`；HOME 观察的 `mo.line=home_line`，AWAY 观察的 `mo.line=-home_line`。TOTALS 两侧均为 `mo.line=e.exact_line`。这是本报告 2,408 行双侧完整与 399 行最新 eligible 的可复算关键；若误用同号 AH 双侧，会把不相同的赌注当作一个市场。

## 原始评估行

| 口径 | 行数 | 唯一 fixture | AH | TOTALS |
|---|---:|---:|---:|---:|
| v2 全部 | 3,024 | 332 | 1,512 | 1,512 |
| ANALYSIS_PICK_ACTIVE | 538 | — | 193 | 345 |
| NO_EDGE_CURRENT | 933 | — | 209 | 724 |
| BLOCKED_BY_FACTOR | 946 | — | 946 | 0 |
| NOT_READY_QUOTE_INCOMPLETE | 607 | — | 164 | 443 |

forecast capture 绑定和时间字段：3,024/3,024；`model_forecast_capture.captured_at <= evaluated_at < kickoff_utc` 成立 3,024，时间序不成立 0，缺时间字段 0。另按同 `provider_fixture_id + capture_id + market` 取市场观察快照最大 `captured_at` 验证**赔率 PIT**，3,024 行都有市场观察且 `quote_captured_at <= evaluated_at < kickoff_utc` 成立 3,024；缺盘口观察 0、报价晚于评估 0、报价缺时点 0。按正确的 AH 反向符号配对，双侧 Pinnacle 完整 **2,408** 行，缺侧 **616** 行（AH 完整 906/缺 606；TOTALS 完整 1,502/缺 10）。有快照不等于有可用的 Pinnacle 同盘口双侧价。

## 按 fixture×market 最新评估去重

cohort contract 若按每个 fixture×market 取 `evaluated_at DESC`，3,024 行折成 664 行（332 fixture×2 market）：

| 最新状态 | 行数 | 双侧完整 | 可 eligible |
|---|---:|---:|---:|
| ANALYSIS_PICK_ACTIVE | 115 | 97 | 97 |
| NO_EDGE_CURRENT | 205 | 193 | 193 |
| BLOCKED_BY_FACTOR | 206 | 109 | 109 |
| NOT_READY_QUOTE_INCOMPLETE | 138 | 133 | 0 |
| **合计** | **664** | **532** | **399** |

市场分解：AH 332 行，双侧 202；TOTALS 332 行，双侧 330。故当前严格“最新 fixture×market + 三态 + PIT + 双侧”的可证明 eligible 为 **399 行 / 261 个唯一 fixture**。原始不去重、三态、双侧口径为 1,830 行 / 270 个 fixture；该数不能替代 cohort 去重数。

## 每日新增速度（最新去重口径，UTC 日期）

```text
2026-09-02 1, 09-03 4, 09-04 12, 09-06 0, 09-07 10,
09-09 11, 09-10 12, 09-11 1, 09-12 47, 09-13 7,
09-14 2, 09-15 1, 09-16 4, 09-17 3, 09-18 42,
09-19 84, 09-20 149, 09-21 6, 09-22 2, 09-24 1
```

合计 399 条，19 个有新增的 UTC 日，平均 **21.0 条/活跃日**；按 2026-09-02 至 2026-09-24 的 23 个日历日为 **17.35 条/日**。这只是现有 v2 评估库的观测速度，不是密封 validation/test 的资格证明。若速度保持不变，2,500 条约需 119 个活跃日；validation+test 共 5,000 条约需 238 个活跃日，不能据此承诺上线日期。

若额外要求 `evaluated_at` 严格晚于 ERRATA ④ 决策时点 `2026-09-24 01:55+08`，现有 v2 库只有 **6 条评估 / 1 个 fixture / 2 个 market**；它们是同场三个检查点。最新去重后 2 行：TOTALS/NO_EDGE_CURRENT 有双侧价，AH/BLOCKED_BY_FACTOR 缺双侧价，因此只有 **1 条候选 market 行 / 1 个 fixture** 符合上面的技术条件。该行仍不能宣布进入 v5 的密封 validation，因为 Gate 1 R0 的新预注册尚未冻结，T0 与排除清单未登记。查询时点之后（2026-09-25 UTC）没有新的 `candidate-eval.v2` 行；正式前向新增 eligible 速度目前**不可估计**。

## F2 `internal_elo_v1` 复核

- `team_rating_snapshots`：242 行、242 个 team；每行的 `source_history_hashes` 全部能绑定 `canonical_team_match_history`，时间字段完整，来源比赛时间不晚于 snapshot `observed_at`：**242/242 来源链完整**。这不单独证明任意评估时点可用。
- 当前 v2 的 332 个 fixture 中，按 `matchday_fixture_identities.provider_fixture_id` 关联并取 `observed_at <= kickoff_utc` 的双方 rating 可得 **209/332 = 62.95%**；这是 kickoff 前的粗覆盖率，不是严格评估 PIT，也不是实际入模率。
- 逐评估行以 `observed_at <= evaluated_at` 取双方快照，再逐个核对其所有来源 history hash、最大来源 `captured_at <= evaluated_at`：**1,902/3,024 = 62.90%** 双侧可证明 PIT；已选到双侧快照的 1,902 行中来源时间倒挂 0。其余 1,122 行缺评估时点前的双侧 rating，不能当作 PIT 通过。
- 3,024 个 v2 forecast payload 的 `model_version` 全为 `w2.formal.exact_dc_poisson.v1`，payload 没有 `elo_home/elo_away/elo_diff/internal_elo_v1` 字段；`dynamic_prematch_evaluations` 也没有这些字段：当前可审计的实际入模率 **0/3,024 = 0%**。隐藏在 hash 内的输入无法由现有落盘证据证明，故不把 62.95% 当作入模率。

## 重复计价检查

静态证据：`src/w2/strategy/calibration.py:69-72` 的函数接口支持 Elo delta，但 `src/w2/strategy/simulate.py:122-132` 明确向该路径传入 `home_elo=None, away_elo=None`，并写出 `ratings_used_in_lambda=False`（约 522-551 行）。另一方面 `src/w2/features/team_factors.py:422-463` 的 F7 使用 `internal_elo_v1` 评级作为因子展示/门控输入。当前 v2 capture 是纯 `EXACT_DC_POISSON` 四字段 xG 载荷，未发现“同一 internal_elo 同时进入 λ delta 和 F7”的落盘证据；重复计价 **未确认**。若以后将 209 个可用 rating 接入 λ，必须先注册并明确从 F7 排除或证明正交性。

## 限制

这些数字是 2026-09-25 查询时点的 staging 数据快照，不是 2,500+2,500 密封前向 cohort；生产切换仍被 `PIT`、新增 eligible 数、密封验收和独立复算门槛阻塞。
