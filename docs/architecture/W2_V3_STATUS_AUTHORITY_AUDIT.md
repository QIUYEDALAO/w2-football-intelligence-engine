# W2 RecommendationDecisionV3 — 状态权威来源审计

**冻结基线：** `600ddc9fa244ca0014bb82248708b53597a592ab`

**范围：** V3-00；本文件只描述现状，不改变推荐、模型或结算语义。
**原则：** 同一字段只能有一个权威生产者；兼容投影不得反向驱动权威状态。

## 字段权威矩阵

| 字段/状态族 | 权威来源 | 兼容来源 | 主要消费端 |
|---|---|---|---|
| `decision_tier`、`pick`、`non_pick`、`card_hash` | `domain/decision_card.py` 的 `DecisionCard`，由 `decision_adapter.build_decision_contract_fields` 生成 | `legacy_decision_shim.py` 只读映射历史 `formal_recommendation` 等字段 | API repository、DayView、Web normalizer、tracking/replay、settlement |
| `data_status`、缺失/过期字段、reason/action/next eval | `readiness/data_gate.evaluate_data_readiness` | `build_data_readiness_from_legacy_payload` | decision adapter、dashboard readiness、Web card |
| 分析盘口 primary/secondary 与 `NO_EDGE` | `strategy/analysis_recommendation.build_multi_market_analysis` 和 `strategy/market_selector.select_analysis_markets` | 旧 card 的市场字段仅作输入 | decision adapter、pricing、Dashboard |
| 正式推荐和 lock eligibility | `strategy/formal_recommendation.build_formal_recommendation` 与 `domain/decision_policy` | legacy shim 可显示历史状态，但不产生正式推荐 | lock snapshot、tracking、settlement |
| AH/OU 估值与解释因子 | `pricing/shadow.build_pricing_shadow`、`pricing/team_score.independent_team_scores` | Dashboard 平铺的 `pricing_shadow` | analysis/formal recommendation、Web 展示 |
| 首发确认、身份映射、估值覆盖与数值调整 | `lineups/intelligence.LineupGate`、coverage/identity/adjustment 数据结构 | 旧 `lineup_injury_factor` 仅历史兼容，不是 V3 scoring authority | data gate、pricing、Dashboard |
| Dashboard 卡片与 DayView 分类 | `api/repository.py` 的 canonical dashboard projection；`dashboard/day_view.py` 只读派生 | staging seed / read-model checkpoint | `/dashboard`、`/dashboard/day-view`、Web normalizer |
| 赛前锁定、追踪、结算 | lock snapshot → tracking/replay → `settlement`；均以 immutable capture identity 为准 | 历史恢复 manifest 只能明确标记恢复来源 | forward ledger performance、审计视图 |
| canonical performance cohort、联赛胜率与 CLV | `tracking/forward_ledger_performance.forward_ledger_performance` | legacy recovery manifest 仅补充被唯一证明的历史 capture | API performance、Dashboard 联赛表 |

## 禁止的反向依赖

- Web 文案、legacy shim、staging seed 和 DayView 不得覆盖或升级 `decision_tier`、`data_status`、`lock_eligible`。
- `generated_at` 不得替代盘口 capture time；参考/过期盘口不得进入 EV、正式推荐或锁定。
- performance cohort 的排除、恢复与 canonical eligible 集合互斥；CLV 样本必须是 eligible fixture 的子集。
- 正式推荐仍受 capability/environment gate 控制；本基线中的 staging `formal_recommendation=false`，OU formal、production、锁单均未开放。

## V3 后续改造锚点

V3-01 以此矩阵登记 capability；V3-02 将 decision contract 设为跨端权威；V3-03 至 V3-05 只能替换权威生产者，不能让兼容投影继续拥有决策权。每次替换都必须同时验证 API、DayView、Web、lock/tracking/settlement 与 cohort。
