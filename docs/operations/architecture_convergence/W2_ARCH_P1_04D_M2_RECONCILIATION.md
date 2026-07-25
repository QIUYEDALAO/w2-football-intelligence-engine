# ARCH-P1-04D M2 simulation 对账证据

> 只读对账，未切换读取、未删除任何兼容链、未修改 staging/生产数据。
> PROVIDER_CALLS = 0，DB_WRITES = 0（全部本地纯函数 + 只读读模型端点）。

## 方法

- 对账函数：`w2.prematch.simulation_reconciliation.reconcile_simulation(card)`
  （纯函数），对 canonical 顶层 `card["simulation"]` 与
  `card["pricing_shadow"]["simulation"]` 做 **`canonical_sha256` 完整对象**比较，
  分类为 `MATCH / TOP_LEVEL_ONLY / LEGACY_ONLY / BOTH_UNAVAILABLE / MISMATCH`。
  **禁止**仅比较 `simulations` 数量或部分字段（测试
  `test_reconcile_uses_full_object_not_only_simulations_count` 守卫）。
- Frozen 层数据：staging `read_model_checkpoint` 的 8 条 frozen artifact
  （只读 SSH 导出）。
- Live 层数据：staging 只读读模型端点 `GET /v1/dashboard?date=2026-07-26`
  （captured_at 2026-07-25T13:14:49Z，该端点 provider_calls=0 / db_writes=0）。

## Frozen 层（8 条 frozen artifact，全部 MATCH）

hash 为 `canonical_sha256`（截断）；顶层与 pricing_shadow 完整对象逐条相同。

| fixture_id | src simulation status | top-level simulation hash | pricing-shadow simulation hash | reconciliation |
|---|---|---|---|---|
| 1494217 | READY | `2092cfd327984bac…` | `2092cfd327984bac…` | MATCH |
| 1494218 | READY | `331759fb669d9ba8…` | `331759fb669d9ba8…` | MATCH |
| 1494219 | READY | `618ad78da45cb042…` | `618ad78da45cb042…` | MATCH |
| 1494220 | READY | `0db83774b8c38236…` | `0db83774b8c38236…` | MATCH |
| 1494221 | READY | `1896ead8d61a9863…` | `1896ead8d61a9863…` | MATCH |
| 1494222 | READY | `e5aed5e386ec9755…` | `e5aed5e386ec9755…` | MATCH |
| 1494223 | READY | `5eaf0316dc79a1a3…` | `5eaf0316dc79a1a3…` | MATCH |
| 1494224 | READY | `592970debe19de2a…` | `592970debe19de2a…` | MATCH |

Frozen 分布：`MATCH = 8`。

## Live 层（`/v1/dashboard?date=2026-07-26`，当前可见 13 fixture）

| fixture_id | decision_tier | top-level sim | pricing-shadow sim (status) | reconciliation |
|---|---|---|---|---|
| 1523215 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1523216 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1523217 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494223 | WATCH | — | `5eaf0316dc79a1a3…` (READY) | **LEGACY_ONLY** |
| 1494217 | WATCH | — | `2092cfd327984bac…` (READY) | **LEGACY_ONLY** |
| 1523218 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494710 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494222 | ANALYSIS_PICK | — | `e5aed5e386ec9755…` (READY) | **LEGACY_ONLY** |
| 1494219 | NOT_READY | — | `618ad78da45cb042…` (READY) | **LEGACY_ONLY** |
| 1494715 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494711 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494714 | NOT_READY | — | — | BOTH_UNAVAILABLE |
| 1494709 | NOT_READY | — | — | BOTH_UNAVAILABLE |

Live 分布：`LEGACY_ONLY = 4`（fixture 1494217 / 1494219 / 1494222 / 1494223），
`BOTH_UNAVAILABLE = 9`。

**关键发现**：live LEGACY_ONLY 的 4 条其 pricing-shadow simulation hash 与对应
frozen artifact 的 hash **完全相同**（如 1494217 均为 `2092cfd327984bac…`），说明
**当前 live 读模型路径携带 pricing_shadow.simulation 但未暴露 canonical 顶层
`card["simulation"]`**——即顶层 simulation 存在于 frozen artifact，却未进入当前
live dashboard payload。

## 聚合结果

```text
FROZEN_MATCH     = 8
LIVE_MATCH       = 0
TOP_LEVEL_ONLY   = 0
LEGACY_ONLY      = 4   (live: 1494217, 1494219, 1494222, 1494223)
BOTH_UNAVAILABLE = 9   (live)
MISMATCH         = 0
```

## 迁移前后业务语义对账（old = M2 起始 head，new = M2 新 head）

M2 **不改任何 DayView 投影路径代码**——仅新增 `simulation_reconciliation.py`
（未被 DayView 路径引用）、其测试与只读文档。`day_view.py` /
`decision_contract.py` / `read_model_projection.py` 在 old→new 之间零改动，故
DayView 业务输出逐字节不变：

```text
RECOMMENDATION_TIER_DELTA     = 0
ANALYSIS_PICK_PROMOTION_DELTA = 0
PICK_IDENTITY_DELTA           = 0
SCORELINE_OUTPUT_HASH_DELTA   = 0
```

（结构性成立，可由 `git diff cd42695c..HEAD -- src/w2/dashboard src/w2/domain
src/w2/prematch/read_model_projection.py` 为空验证。）

## 结论与 M3 blocker

- `MISMATCH = 0`：无矛盾对象，不触发停机。
- `LEGACY_ONLY = 4 > 0`：**M2 完成盘点，但标记为 M3 blocker**。当前 live 读模型
  路径不暴露 canonical 顶层 simulation；若此时把 `_scoreline_simulations` 切到
  只读顶层 simulation，这 4 条 live card 将丢失 simulation 数据（变为
  UNAVAILABLE），改变输出。**M3 读切换前，必须先让 live 路径携带 canonical 顶层
  simulation**。
- 因此本轮**不切读、不删除** pricing_shadow fallback / legacy pick /
  legacy shim/adapter，**不声明**任何兼容链零可达。
- `M3_READY = NO`（被 LEGACY_ONLY = 4 阻塞）。
