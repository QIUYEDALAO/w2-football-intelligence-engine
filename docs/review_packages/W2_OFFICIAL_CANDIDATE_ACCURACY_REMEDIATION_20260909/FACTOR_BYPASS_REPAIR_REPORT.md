# 因子否决绕过:确认与修复

## 1. 数据层证据(比代码推断更强)

```sql
select count(*) from dynamic_prematch_evaluations where payload::text ilike '%factor%'
→ 0
```

整张生产表、全部 payload,**没有一行**含 "factor" 字样。因子裁决**从未被写入过**动态评估——
不只是 `lifecycle.py` 不读,是数据层根本没有。

分析卡不持久化(库中无对应表,系读时投影),因此这 148 条的历史因子方向**不可重建**:

```text
FACTOR_DISPOSITION = UNKNOWN_NOT_RECONSTRUCTIBLE     148 / 148
```

## 2. 绕过链路

```text
analysis_calculator.py:5891-5897   因子冲突 → card 的 decision/analysis_decision = WATCH
read_model_projection.py:1481      _dynamic_evaluations(card, ...) 构造 DynamicEvaluationInput
                                   ——从不读 card 的 factor 字段
lifecycle.py:526                   state 纯由 economic_admission_pass 决定
lifecycle.py:311                   official_funnel_eligible=True（对所有状态无条件）
api/repository.py:499              正式漏斗筛 official_funnel_eligible + state==ANALYSIS_PICK_ACTIVE
```

`official_funnel_eligible` 无条件为 true,故该双条件实为**单条件**,唯一闸门是纯经济状态。

## 3. 修复(方案 A:进入写入契约,而非 read layer 过滤)

- `DynamicEvaluationInput` 增 5 个版本化字段:`factor_decision_status` / `factor_direction` /
  `ev_direction` / `factor_veto_code` / `factor_input_identity`;
- 新增状态 `DynamicEvaluationState.BLOCKED_BY_FACTOR`,不在
  `{ANALYSIS_PICK_ACTIVE, NO_EDGE_CURRENT}` 内,故经 `lifecycle.py:297-303` 自然映射为
  `OpportunityState.BLOCKED_BY_GATE`;
- `factor_blocker()` 在**经济准入之前**判定,三种码任一命中即阻断并把具体码写入 blockers;
- **fail-closed**:AH 无因子裁决身份即 `FACTOR_SCORE_UNAVAILABLE`;
- 历史 payload 读回为 `HISTORICAL_NO_FACTOR_VERDICT_IDENTITY`,**显式不视为通过**;
- TOTALS 完全不受影响(`factor_blocker` 对非 AH 直接返回 None);
- `official_funnel_eligible` **不改**,被阻断的 AH 仍计入正式漏斗分母(符合 B3);
- `read_model_projection._factor_verdict()` 把 `card["markets"]` 的 `factor_veto` 与
  `card["market_candidates"]` join 起来——两者本就在同一张卡上,只是从未连过。

## 4. 未完成

B4 要求的 Alembic 迁移与 evaluation/attempt identity 绑定因子裁决身份**未实施**;
候选通知与赛后台账的端到端断言(测试矩阵 6/7/8/11)**未实施**。
