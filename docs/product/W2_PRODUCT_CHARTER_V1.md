# W2 Product Charter V1

Superseded by `docs/product/W2_PRODUCT_CHARTER_V2.md` for the analysis-grade
recommendation product scope.

W2 is “一个多联赛、可回测、可审计，基于赛前数据、独立概率模型与盘口时序分析的足球比赛筛选和 AI 推荐系统。”

W2 is multi-event and multi-league. It can support the World Cup, the five major leagues, and expandable top national leagues. Raw data is traceable, predictions are reproducible, recommendations are lockable, and postmatch audit is append-only. Models and markets are strictly separated; system evidence and AI judgment are strictly separated. W2 may choose not to recommend.

W2 is not a simple score predictor, not a rule script that recommends whenever odds move, not a DeepSeek free-form chatbot, not a content system forced to recommend daily, not a system that rewrites prematch judgment after results, not hit-rate-only, and not a repackaging of market probability as independent advantage.

V2 scope clarification: W2's core output is analysis-grade match screening and
`ANALYSIS_PICK`, not a claim of guaranteed profit or stable market-beating edge.
`RECOMMEND` remains reserved for a separately proven +EV path and is disabled by
default.
