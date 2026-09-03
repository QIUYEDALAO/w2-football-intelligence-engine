# W2-SIGNAL-GROUP-BLAST-RADIUS · B2' 生产只读报告

状态：`DONE`（docs-only；B2 原指令已撤回且未执行）

分支：`codex/w2-factor-registry-drift-01`

父提交：`d5c18b5d`（B1 验收 PASS）

## 1. 边界与口径

本次只测量生产公共读取实际使用的 `analysis-card:shadow:v1:*` checkpoint。每个
`checkpoint_key` 对应一个唯一 fixture，因此不会把同一 fixture 的 frozen/shadow 两张
card 重复计数。

接受的生产快照：

- transaction timestamp：`2026-09-03T01:44:40.224085Z`
- transaction isolation：`REPEATABLE READ`
- `transaction_read_only`：`on`
- 当前 shadow fixture/card：`452`

实际分布直接读取 `pricing_shadow.independent_signal_count` 与
`independent_signal_groups`。反事实不修改配置，而是对每张 card 已持久化的 READY
`pricing_shadow.factors[]` 重新执行以下既有筛选语义：

1. factor ID 属于既有允许集合；
2. `status = READY`；
3. `is_independent_signal = true`；
4. `source_group` 属于既有 authoritative groups；
5. 仅在反事实中排除指定的 F6/F7。

重算的当前组数与持久化 `independent_signal_count` 在 `452/452` 张 card 上一致，差异
为 `0`。

## 2. 当前实际分布与 DATA_INSUFFICIENT

| independent_signal_count | fixture 数 |
|---:|---:|
| 0 | **427** |
| 1 | 0 |
| 2 | 0 |
| 3 | **16** |
| 4 | **9** |
| 5 | 0 |
| 合计 | **452** |

按 `match_decision.py` 的既有判定顺序，当前 `DATA_INSUFFICIENT` 为 **427** 场。其
reason 细分为：

- `INSUFFICIENT_INDEPENDENT_FACTORS`：**427**；
- `INDEPENDENT_SIGNAL_COUNT_BELOW_MINIMUM`：**0**。

这里必须保留判定顺序差异：427 张 card 的 pricing shadow 已先命中
`INSUFFICIENT_INDEPENDENT_FACTORS`，所以不会继续落到 count `< 3` 的后一个 reason。

## 3. 当前实际信号组组合

| 组数 | independent_signal_groups | fixture 数 |
|---:|---|---:|
| 0 | 空 | **427** |
| 3 | `ratings + team_fixture_history + xg` | **16** |
| 4 | `h2h + ratings + team_fixture_history + xg` | **9** |

因此，在当前达到最低 3 组的 25 场中：

- 第三组仅由 `ratings` 补足：**16**；
- 同时具有 `h2h` 与 `ratings`、达到 4 组：**9**；
- 仅由 `h2h` 补足第三组、没有 `ratings`：**0**。

当前 452 张 card 中没有任何 `squad_value` 组。

## 4. 反事实 A：F6 与 F7 都不计入 scoring_factors

| 反事实 independent_signal_count | fixture 数 |
|---:|---:|
| 0 | **427** |
| 1 | 0 |
| 2 | **25** |
| 3 | 0 |
| 4 | 0 |
| 5 | 0 |
| 合计 | **452** |

结论：`452/452` 场全部低于现有最低 3 组。原 B2 若执行，确实会使当前全部 fixture
进入 `DATA_INSUFFICIENT`。其中 427 场仍为零组；其余 25 场只剩
`team_fixture_history + xg` 两组。

## 5. 反事实 B：只移除 F7、保留 F6

| 反事实 independent_signal_count | fixture 数 |
|---:|---:|
| 0 | **427** |
| 1 | 0 |
| 2 | **16** |
| 3 | **9** |
| 4 | 0 |
| 5 | 0 |
| 合计 | **452** |

结论：只移除 F7 时，**443/452** 场低于最低 3 组；只有同时具有
`h2h + team_fixture_history + xg` 的 **9** 场仍达到 3 组。

## 6. F7 `elo_delta = 0.14 × raw_delta` 恒等式复核

验收方推断在当前生产数据上**不成立**。

测量只使用同一张 card 中 READY F7/F9 已持久化 inputs：

```text
elo_delta = ((home_elo - away_elo) / 400) × 0.28
raw_delta = (home_xg_net - away_xg_net) / 2
```

结果：

| 项目 | 结果 |
|---|---:|
| READY F7 且 READY F9 的 card | **25** |
| 在 `1e-9` 容差内满足恒等式 | **0** |
| 不满足恒等式 | **25** |
| 最小绝对误差 | `0.00007` |
| 最大绝对误差 | `0.13776` |

F7 factor 的生产 `source` 为 `team_rating_snapshots`，其 home/away artifact provenance
中的 `source_model` 均为 `internal_elo_v1`，不是 `rolling_xg_proxy`。

确定性反例 `analysis-card:shadow:v1:1494236`：

```text
home_elo / away_elo        = 1653 / 1323
home_xg_net / away_xg_net  = 0.47 / -0.862
elo_delta                  = 0.231
raw_delta                  = 0.666
0.14 × raw_delta           = 0.09324
absolute error             = 0.13776
```

所以不能继续把当前 READY F7 表述为“xG 的确定性回声”，也不能以该恒等式为依据选择
甲、乙或丙。此结果只否定精确恒等式；它不反向证明 F7 已通过统计独立性或增量信息验证。
F7 的后续处置须重新讨论，本报告不预先授权任何一条路径。

## 7. 结论

1. 原 B2 的 blast radius 判断成立：同时移除 F6/F7 后，当前 `452/452` 场均低于 3 组。
2. 当前达到 3 组的 16 场全部依赖 `ratings` 作第三组；另外 9 场同时具有 F6/F7 对应组。
3. 只移除 F7 也会令 `443/452` 场低于 3 组，只剩 9 场过门。
4. 但“F7 的 `elo_delta` 恒等于 `0.14 × raw_delta`”被生产数据 `25/25` 反例否定；
   因此“F7 是 xG 确定性回声”的处置前提不成立。
5. 本报告只提供数据，不选择甲、乙、丙，也不修改安全门槛。

## 8. Stop lines 与身份

| 项目 | 本次结果 |
|---|---|
| 生产写 | 0；所有生产查询均在 `REPEATABLE READ READ ONLY` 事务中执行并 `ROLLBACK` |
| ledger | 0 |
| migration | 0 |
| 部署 | 0 |
| GitHub / GHCR | 0 |
| `CALIBRATION_VERSION` | 0 改动 |
| 参数 / 权重 | 0 改动 |
| `factor_registry.v1.json` | 0 改动 |
| `INDEPENDENT_SIGNAL_MINIMUM` / signal group 常量 | 0 改动 |
| λ / split | 0 改动 |
| Football Provider | 0 调用 |
| identity | 代码与参数未修改；按 M4 未重新实测 |
