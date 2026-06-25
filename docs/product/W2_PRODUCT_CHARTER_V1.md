# W2 Product Charter V1

W2 is “一个多联赛、可回测、可审计，基于赛前数据、独立概率模型、盘口时序与多因素分析的足球比赛筛选和分析级推荐系统。”

W2 is multi-event and multi-league. It can support the World Cup, the five major leagues, and expandable top national leagues. Raw data is traceable, predictions are reproducible, recommendations are lockable, and postmatch audit is append-only. Models and markets are strictly separated; system evidence and AI judgment are strictly separated. W2 may choose not to recommend.

W2 is not a simple score predictor, not a rule script that recommends whenever odds move, not a DeepSeek free-form chatbot, not a content system forced to recommend daily, not a system that rewrites prematch judgment after results, not hit-rate-only, and not a repackaging of market probability as independent advantage.

## Analysis-Grade Recommendation Scope

W2's core product output is W2 multi-factor analysis: match screening plus analysis-grade market views with reasons, risks, invalidation conditions, and the required disclaimer "分析参考·非稳赢". This output is useful for research and review; it does not claim stable profit, guaranteed outcomes, or market-beating edge.

The output ladder is:

- `NOT_READY`: required system state or data is absent.
- `SKIP`: data is insufficient or coverage is unavailable; no market view is emitted.
- `WATCH`: enough context exists to monitor, but no analysis pick is warranted.
- `ANALYSIS_PICK`: W2's normal product-level analysis view. It is explainable, risk-labelled, and non-formal.
- `RECOMMEND`: reserved for a separately proven positive-EV regime. It remains disabled by default and is not required for the W2 analysis product.

`candidate=true` and `formal_recommendation=true` remain reserved for formally proven recommendation workflows. Analysis cards must keep both flags false.
