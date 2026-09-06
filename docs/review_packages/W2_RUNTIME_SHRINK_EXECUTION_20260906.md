# W2 运行主链瘦身执行回执

基线：`9ac18e2166e6c6d64cecf596a37f1d213b89a2fe`
状态：本地完成，未部署

## 保留的唯一对外链

`API/读模型 -> F9 rolling xG + 市场候选 -> canonical EV -> 已保存 RecommendationDecisionV4 -> API/dashboard/notification`。

采集、回填、物化和结算 worker 继续保留；它们不产生第二个对外推荐出口。

## 已执行

- 删除未实现的 matchday CLI / dry-run orchestrator / DailyMatchdayCycle 执行入口及脚本入口。
- 保留 `intake_v2` 的采集、回填、manifest 和 identity 公共契约；移除其 `execute_matchday_intake` 执行入口，避免误认为它是当前推荐入口。
- F7/F8 从独立评分因子集合、权威信号组和运行时 feature 构造移除；保留历史数据模型、旧快照和审计文件。
- analysis lambda 不再消费 Elo、身价、阵容强度及其调整字段；兼容字段仍可读取，但不会改变概率。
- dashboard/API 缺少 V4 时不构造新的 V4 决策；返回 NOT_READY、无 pick、无 candidate/formal recommendation。
- 新增 V4 解码器，读取已保存 V4 时只验证 hash，不重新跑定价或准入。
- 删除对外 V3 payload；历史 V3 数据仍由历史/回放层保留。
- 测试改为验证已删除路径不会复活，并验证 F7/F8 旧 READY payload 不能重新进入评分。

## 验收

- 单元测试：`2527 passed, 3 skipped, 2 warnings`。
- 采集/持久化集成回归：`89 passed, 1 warning`。
- Web TypeScript typecheck：通过。
- Ruff：通过。
- compileall：通过。
- `git diff --check`：通过。
- Provider calls：0；生产写入：0；部署：0；正式推荐：OFF。

## 未做

- 未删除历史表、raw、ledger、migration、settlement 或回放证据。
- 未部署到线上；线上仍为 `9ac18e21…`。
- 未宣称模型准确性或盈利能力。
