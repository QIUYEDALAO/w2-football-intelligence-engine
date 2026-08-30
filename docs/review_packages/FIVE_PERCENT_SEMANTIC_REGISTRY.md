# 0.05 语义登记册

当前状态：`PENDING_RECHECK_ON_PRODUCTION_BASELINE`

生产权威：`ea557bb8ff64e06add91bbe32814fe073ec64642 / 0070_notification_delivery_routing`

历史静态基线：`origin/main@3b7f87db / 0051_apply_seven_day_collection_policy`（落后生产 19 个 migration，不是生产权威）

Gate 0B 已确认 `src/w2/markets/analysis_evidence.py` 在生产基线相对该静态快照变更 `+34` 行，`src/w2/prematch/lifecycle.py` 变更 `+339` 行。因此下方既有内容完整保留作为 Gate 0A 历史记录，但在按生产 `ea557bb8` 重核具体行号、caller 和决策角色之前，不得引用为当前生产登记结论。

三个关键常量在两基线的出现次数一致：

```text
MIN_MARKET_ANCHOR_DIVERGENCE = 3 + 0
ACTIVE_DELTA_THRESHOLD = 0 + 6
probability_delta_admission_gate = 1 + 0
```

这只是重核线索，不足以取消 `PENDING_RECHECK_ON_PRODUCTION_BASELINE`。本轮不删除、改写或重排下方现有登记内容。

Gate: `0A_LOCAL_STATIC` / Phase 1 首查项
基线：`origin/main@3b7f87db`
方法：只读静态审计，detached worktree，未修改用户工作树

## 结论

决策相关的 `0.05` 在 `main` 上有 **5 种不同语义、分布于 7 处**。
不得在任何报告、Dashboard、API 或评审文字中统称「5% threshold」。

## 登记表

| # | 位置 | 符号 | 单位 | 决策角色 | 当前 authority |
|---|---|---|---|---|---|
| a | `src/w2/domain/five_state_pricing.py:6` | `MIN_CASHFLOW_PRICE_EDGE` | 结算归一化价格优势 `EV/S` | **当前 public analysis admission** | 现役 |
| b | `src/w2/markets/analysis_evidence.py:25` | `MIN_MARKET_ANCHOR_DIVERGENCE` | 概率百分点 | diagnostic（`probability_delta_admission_gate = False`） | 已降级 |
| c | `src/w2/prematch/lifecycle.py:12` | `ACTIVE_DELTA_THRESHOLD` | 概率百分点 | dynamic evaluation / tracking | legacy 平行合同 |
| d | `src/w2/markets/value_engine.py:239` | `risk_adjusted_ev >= 0.05` | 名义 EV | 评级边界 | 现役 |
| e | `src/w2/matchday/cards.py:84` | `risk_ev >= Decimal("0.05")` | 名义 EV | 卡片展示评级 | 现役 |
| f | `src/w2/analysis/market_movement.py:628` | `abs(diff) < 0.05` | team_score 差值 | 因子领先方 NEUTRAL 带 | 与 EV/概率无关 |
| g | `src/w2/domain/decision_adapter.py:34` | `MIN_MARKET_ANCHOR_DIVERGENCE` | 概率百分点 | **b 的重复常量** | 待删除 |

### 分组

```text
结算归一化价格优势   a
概率百分点          b, c, g   （三份拷贝，两处语义已降级）
名义 EV 评级        d, e
因子分差            f         （完全无关的量）
```

## 需要处置的三点

1. **b / c / g 是同一个概率百分点常量的三份拷贝。** `g` 所在的
   `decision_adapter.py` 在 `main@3b7f87db` 上**仍然存在**；按架构收敛计划
   该文件应在 P1-04C 删除，说明该任务尚未完成或未合并。

2. **f 与其余六处毫无关系**，只是恰好同为 `0.05`。它是 `team_score` 差值的
   中性带宽度。任何自动化的「0.05 常量清点」若不做语义分组会把它误纳入政策讨论。

3. **d 与 e 是同一评级语义的两份实现**，应在 Phase 3 的 EV 合同收敛中
   验证数值等价或合并。

## 与 Phase 4 的关系

Phase 4 的政策评价对象是 **a**（`MIN_CASHFLOW_PRICE_EDGE`），
即 `EV/S_asof >= 0.05`。

- **b / c / g** 只能作为 legacy diagnostic 记录，不得与 a 平级评价
- **d / e** 属于展示评级，不是 admission policy，不得混入 Phase 4 estimand
- **f** 不得出现在 Phase 4 的任何字段中

## 建议的登记字段（供后续维护）

```text
symbol
module:line
value
unit
mathematical definition
decision role
current authority (现役 / 已降级 / legacy / 待删除 / 无关)
```
