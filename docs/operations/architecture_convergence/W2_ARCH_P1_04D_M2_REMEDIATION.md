# ARCH-P1-04D M2 blocker remediation — live canonical simulation projection

> 修复 live Dashboard 返回体丢失 canonical 顶层 simulation 的缺口。仍不切换读取、
> 不删除任何兼容链、不修改 staging/生产数据。PROVIDER_CALLS = 0，DB_WRITES = 0。

## 缺口与修复

`analysis_calculator.ReadModelService._dashboard_card_from_matchday()` 的返回体
携带 `pricing_shadow` 但**遗漏了顶层 `simulation`**，这是 M2 发现的 live
LEGACY_ONLY 的唯一成因。修复为在返回体直接透传来源：

```python
"simulation": card.get("simulation"),
```

- 来源 card 顶层 simulation 是 Mapping → live Dashboard 的 simulation 为相同完整
  对象内容（同一 `SimulationOutput` 序列化结果）。
- 来源 card 无顶层 simulation → `card.get("simulation")` 返回 `None`（明确无值）。
- **禁止且未做**：从 `pricing_shadow.simulation` 回填、`run_simulation_from_shadow`
  写顶层、重新计算、创建第二 writer。方法内既有的
  `run_simulation_from_shadow(card.get("pricing_shadow"))` 仅供 formal
  recommendation，未被本改动触及。
- 来源真实内部状态（`READY` / `INSUFFICIENT_INPUTS`）**原样保留**，不在
  Dashboard 层改写；DayView 的 M1 projection 负责映射 `READY` / `UNAVAILABLE`。

diff 为**纯增量**（`git diff` 于 `src/w2/prematch/analysis_calculator.py`：6 行
新增 = 5 行注释 + 1 行字段，0 行删除），未触及任何业务字段的计算路径。

## 重新执行 live 对账（同一只读端点数据 + 同一分类函数）

staging 端点运行的是已部署代码（不含本分支修复），故本轮以**同一批只读源数据**
（`GET /v1/dashboard?date=2026-07-26` 的 13 fixture + 对应 frozen artifact 源）
在本地通过**修复后的** `_dashboard_card_from_matchday` 复现 live 投影，再用
`reconcile_simulation` 分类：

```text
LIVE_MATCH        = 4   (1494217, 1494219, 1494222, 1494223)
TOP_LEVEL_ONLY    = 0
LEGACY_ONLY       = 0
BOTH_UNAVAILABLE  = 9
MISMATCH          = 0
```

4 条 blocker fixture 全部由 `LEGACY_ONLY` 翻转为 `MATCH`（顶层 simulation 现随源
card 透传，且与 pricing_shadow 完整对象 hash 相同）；9 条无 simulation 的 fixture
保持 `BOTH_UNAVAILABLE`。`LEGACY_ONLY = 0` 且 `MISMATCH = 0`。

> 说明：以上为本地复现修复后代码在真实源数据上的对账结果，用以证明修复有效；
> staging 端点的对应数值需待本分支部署后方会体现（本轮不部署）。

## 业务语义零变化

新增顶层 `simulation` 字段会改变整个 Dashboard payload 的整体 hash——这是**预期的
字段补全**，不声称整体响应 hash 不变。以下业务字段单独证明不变（diff 为纯增量，
未改动任一字段的计算代码；来源权威测试逐条覆盖）：

```text
RECOMMENDATION_TIER_DELTA     = 0
ANALYSIS_PICK_PROMOTION_DELTA = 0
PICK_IDENTITY_DELTA           = 0
SCORELINE_OUTPUT_HASH_DELTA   = 0
FORMAL_OUTPUT_DELTA           = 0
```

涉及字段：`recommendation.decision_tier`、`pick` / `non_pick` identity、
ANALYSIS_PICK fixture 集合、`scoreline_picks`、`scoreline_reference`、
`scoreline_readiness`、`scoreline_simulations`、`current_odds`、
`market_candidates`、formal recommendation / blocker。

## 来源权威测试（`tests/unit/test_dashboard_live_simulation_projection.py`）

1. 顶层 READY 与 pricing_shadow READY 相同 → Dashboard 顶层 simulation 存在、hash
   与来源相同、reconciliation = `MATCH`。
2. 顶层与 pricing_shadow 内容不同 → Dashboard 使用**顶层**对象、不回填
   pricing_shadow、reconciliation = `MISMATCH`（证明来源选择真实有效）。
3. 只有 pricing_shadow、无顶层 → Dashboard 顶层 simulation 不被回填、
   reconciliation = `LEGACY_ONLY`。
4. 顶层状态 `INSUFFICIENT_INPUTS` → Dashboard 原样透传、DayView 映射为
   `UNAVAILABLE`、不提升为 `READY`。
5. 投影前后来源对象 `canonical_sha256` 相同、原 card simulation 未被修改。

## 红线（本轮保持）

未修改 `_scoreline_simulations` 读取顺序；未删除 pricing_shadow fallback /
legacy pick / legacy shim/adapter；未修改 frozen artifact；未修改 staging/生产
数据；未改模型数学 / EV / 阈值 / 安全开关；未启动 M3/M4。

## M3 状态

remediation 证据通过后，M3 blocker 由 `LIVE_LEGACY_ONLY_4` 降级为
`PENDING_EXTERNAL_M3_ENTRY_REVIEW`。**不自行把 M3 标为开始**；M3 读切换须经下一次
外部验收后再启动。
