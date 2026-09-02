# W2-F6-F7-REGISTRY-CORRECTION · B1 调查报告

状态：`DONE`（docs-only 调查；未执行 B2）

分支：`codex/w2-factor-registry-drift-01`

生产基线：`1de3c1ef554d00a408577f59f4864e04f1d341da`

## 1. 调查边界与方法

本报告独立复核两类事实：

1. 本地基线代码中的 registry → pricing shadow → 下游消费调用链；
2. 生产 PostgreSQL `read_model_checkpoint` 中 analysis-card 的 F6/F7 聚合计数。

生产取数时刻为 `2026-09-02T19:58:18.057126Z`。查询只读取：

- `checkpoint_key`、`created_at`；
- `payload.analysis_card.pricing_shadow.factors[]` 中的 `id`、`status`、`score`。

查询不选择 fixture 比分、赛果、结算字段、概率、EV、命中率或模型表现；不调用 Football Provider。数据库操作仅为 `SELECT`。

核心聚合口径等价于：

```sql
FROM read_model_checkpoint r
CROSS JOIN LATERAL json_array_elements(
  coalesce(r.payload->'analysis_card'->'pricing_shadow'->'factors', '[]'::json)
) f
WHERE r.checkpoint_key LIKE 'analysis-card:%'
  AND f.value->>'id' = 'F6_H2H'
  AND f.value->>'status' = 'READY'
```

“非零”定义为 `abs(coalesce((score)::numeric, 0)) > 0`。analysis-card checkpoint 以唯一 `checkpoint_key` 计数；同一 fixture 的 frozen 与 shadow checkpoint 是两张不同的 card。

## 2. 生产计数

| 因子 | READY analysis cards | 非零 READY cards | 唯一 fixtures | 非零唯一 fixtures | checkpoint `created_at` 范围 |
|---|---:|---:|---:|---:|---|
| `F6_H2H` | **18** | **13** | 11 | 8 | `2026-08-08T10:14:18.588486Z` → `2026-08-23T08:30:53.773723Z` |
| `F7_STRENGTH_FORM` | 55 | 55 | 37 | 37 | `2026-08-08T10:14:18.588486Z` → `2026-08-23T09:02:13.352623Z` |

F6 的 18 张 card 由 9 张 `analysis-card:frozen:v1:*` 与 9 张 `analysis-card:shadow:v1:*` 组成。上述计数确认“18 张生产 analysis card 含 READY F6，其中 13 张 F6 score 非零”的 card 口径事实；它不是 18 个唯一 fixture 的口径。

## 3. Registry 与 team score

当前 registry 中 `F6_H2H`、`F7_STRENGTH_FORM` 均为：

- `lifecycle = ACTIVE`
- `roles` 含 `SCORING`
- `numeric_effect_enabled = true`
- `independent_evidence_eligible = true`

`src/w2/domain/factor_registry.py:53-59` 的 `is_scoring_factor()` 要求前三项同时成立。`src/w2/pricing/team_score.py:37-44` 对 READY factors 调用它，再结合 independent/source-group 条件形成 `scoring_factors`；`team_score.py:111-156` 用这些 factors 的 score、side、weight 计算归一化主客 team score。

`src/w2/pricing/shadow.py:23-25` 调用 `independent_team_scores()`，并在 `:61-87` 持久化/投影 factors、`team_score`、权重审计、独立信号计数与信号组。simulation 非 READY 时，`:41-53` 还会用 team score 生成 fallback `fair_ah` 与 `edge_ah`；simulation READY 时，`:35-40` 的 `fair_ah/fair_ou` 取 simulation 输出，而不是 team score fallback。

因此，READY F6/F7 在当前 registry 下是 team-score 数值输入；即使某个 score 为 0，它仍进入归一化分母与 factor/signal 审计。非零 score 还进入对应侧的加权分子。

## 4. 两条消费路径

### 4.1 下注路径

真实下注方向门位于 `src/w2/strategy/formal_recommendation.py`，调用链为：

```text
is_scoring_factor
  → independent_team_scores / team_score
  → build_pricing_shadow / pricing_shadow.team_score
  → formal_recommendation._factor_leader (:714-724)
  → factor_side (:170)
  → is_reverse_value_recommendation (:171-176, :727-743)
  → _direction_supported (:178-179, :756-761)
  → _reverse_value_supported (:180-181, :764-766)
  → 不满足时返回 WATCH
```

`factor_side` 会参与 reverse 判定；方向不支持时返回 `SIMULATION_DIRECTION_CONTRADICTION`，反向价值强度不足时返回 `REVERSE_FACTOR_VALUE_NOT_STRONG_ENOUGH`。这是对推荐决策的真实影响。

生产 API 容器实测 `W2_FORMAL_RECOMMENDATION_ENABLED=false`。代码在 `formal_recommendation.py:226-235` 也会在未启用时返回 WATCH、不给 recommendation。因此当前没有启用正式下注输出；方向门代码及其 WATCH 行为仍然存在。

### 4.2 分析路径

`src/w2/strategy/analysis_recommendation.py` 不读取 `pricing_shadow`、`team_score` 或 `factor_side`。它在 `:284-287` 的 `_signal_strength()` 中只统计 `FeatureSet.contributions` 的 READY 数量：

```text
coverage_bonus = min(ready_count / 10, 0.25)
```

每个额外 READY factor 在未触及 `0.25` 上限前增加 `0.1` coverage bonus；因子的 score 数值、HOME/AWAY 方向和 registry 的 `numeric_effect_enabled` 不参与这项计算。

另有一条与 `analysis_recommendation.py` 不同的分析展示路径：`src/w2/analysis/market_movement.py:295` 的 `build_market_divergence()` 调用该文件自身的 `_factor_leader()`（`:620-630`），输出 `factor_leader` 与 `factor_leader_team`。它会读取 `pricing_shadow.team_score`，因而会反映 F6/F7 对 team score 的数值影响。

派发包列出的 `market_movement.py:_factor_leader → formal_recommendation.py` 不是源码中的直接调用链：两个模块各自定义了同名函数。前者服务 market-divergence 分析展示；后者服务正式推荐方向门。这是两个并行消费者。

## 5. 下注退役后的实际影响面

在正式下注未启用的当前状态下，F6/F7 的影响面为：

- **正式下注输出：0 个已启用输出面。** 当前开关为 false，不产生 formal recommendation；保留代码中的方向门仍可在构造流程中形成 WATCH/blocker。
- **pricing shadow 数值与审计：仍然存在。** F6 已出现在 18 张 READY card（13 张非零），F7 已出现在 55 张 READY card（55 张非零）；它们进入 team score、factor count、weight/signal-group 审计，并在 simulation 非 READY 时进入 fallback `fair_ah/edge_ah`。
- **market-divergence 分析展示：仍然存在。** 它读取 team score 并输出 `factor_leader` 标签。
- **analysis recommendation：只有 READY 计数影响。** F6/F7 的数值与方向不参与分析推荐；READY 状态只可能通过 capped coverage bonus 改变 `signal_strength`。

以上为当前代码与生产聚合事实，不包含 registry 修改建议；B2 未开始。

## 6. 验证

- canonical serialization：`18 passed`；额外 regression guard `1 passed`。
- package matrix：`5 passed`。
- Ruff：PASS。
- 全量 pytest：`2949 passed / 9 skipped / 5 failed`。

5 个失败均已在本次 docs-only 改动的父提交 `1de3c1ef` 上按同 node ID 单独复跑，结果同样失败：

1. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path0]` — 宿主 Docker 无 Compose 插件；父提交同样失败。
2. `tests/contract/test_compose_env_dedup.py::test_compose_expansion_matches_authorized_runtime_delta[path1]` — 宿主 Docker 无 Compose 插件；父提交同样失败。
3. `tests/contract/test_sc18_input_authority.py::test_sc18_authority_artifacts_are_complete_and_self_checking` — 宿主没有裸 `python` 命令；父提交同样失败。
4. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_fails_root_0700_runtime_for_worker_uid` — macOS 不支持测试所需的 Linux UID/GID ownership 行为；父提交同样失败。
5. `tests/integration/test_future_refresh_staging_parity.py::test_preflight_passes_worker_owned_0750_runtime` — macOS 不支持测试所需的 Linux UID/GID ownership 行为；父提交同样失败。

## 7. Stop lines 与身份

| 项目 | 本次结果 |
|---|---|
| 生产写 | 0 |
| ledger 写 | 0 |
| migration | 0 |
| 部署 | 0 |
| GitHub / GHCR | 0 |
| `CALIBRATION_VERSION` | 0 改动 |
| 模型参数 / 权重 | 0 改动 |
| factor registry | 0 改动 |
| λ / `historical_replay_cutoff` / split | 0 改动 |
| Football Provider | 0 调用；remaining 未读取 |
| HOLDOUT | 未读取 2026 赛果、赛果函数统计、概率或模型表现 |
| identity | 代码与参数未修改；按 M4 未重新实测。冻结 identity 仍记录为 `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71` / `APPROVED_VALIDATED` |
