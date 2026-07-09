# W2 World Cup Replay Backtest 10 Result - 2026-07-09

## 1. 定位说明

这是一次 replay / backtest rehearsal，不是统计验证。10 场比赛不能证明模型长期有效，也不能证明 production 推荐准确率。本报告的目标是“每场对答案”：在隔离环境里冻结赛前卡片，再读取赛后 FT / AET / PEN 结果，观察系统真实行为、泄漏防护、shadow direction 与纸面结算是否能闭环。

## 2. 数据隔离说明

- output_dir: `/tmp/w2_wc_replay_backtest_10_20260709T021544Z/20260709T021544Z`
- provider_calls_actual: 11
- endpoints: fixtures / odds only
- forward_ledger_unchanged: true
- forward_ledger_performance_unchanged: true
- db_writes: 0
- staging_deploy: false
- production_deploy: false
- direction_allowed_changes: []
- runtime reports committed: false
- raw provider payload committed: false

## 3. 总览指标

| 指标 | 数值 |
| --- | ---: |
| fixture_count | 10 |
| FT | 8 |
| AET | 1 |
| PEN | 1 |
| recommendation_count | 0 |
| shadow_direction_count | 10 |
| watch_count | 10 |
| not_ready_count | 0 |
| missing_settlement_count | 0 |
| data_leakage_fail_count | 0 |
| CLV | N/A |

## 4. 关键结论

- 本次没有正式推荐，因此不能计算正式 recommendation hit rate。
- 系统对 10 场全部停留在 shadow direction / WATCH 观察层。
- 可以看 shadow direction 与赛果的纸面对照，但不能包装成 production 推荐准确率。
- CLV=N/A，因为回测不可回收时间线，CLV 只能由前向采集产生。
- 本轮价值是验证 replay 闭环、冻结卡片顺序、FT/AET/PEN 读取、纸面结算和隔离边界，而不是证明模型。

## 5. 每场明细表

| fixture_id | kickoff | teams | outcome_bucket | decision_tier | shadow_direction | pick / non_pick | model_family | card_hash | actual_result | paper_result | clv | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1562586 | 2026-07-02T00:00:00+00:00 | USA vs Bosnia & Herzegovina | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 1.50 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | e0b861c42483fe9a79d1e5cf34770882364fa2f2ce57f0164f7eeab4c1020ac4 | FT 2:0 | WIN (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1567311 | 2026-07-02T19:00:00+00:00 | Spain vs Austria | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 1.40 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 7f65cdd21db1404ca239b05d2ca8eaddeb0589527112496d587060c6c7be43db | FT 3:0 | WIN (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1567309 | 2026-07-02T23:00:00+00:00 | Portugal vs Croatia | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 2.15 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 94726531c52125246f179ba72191a1c8a2ec76d408e80d1424f90d2eb297a021 | FT 2:1 | PUSH (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1567312 | 2026-07-03T03:00:00+00:00 | Switzerland vs Algeria | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 2.40 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | fe7141bfac5178c992709ad1988ac941fce2e7f096194f61dad817c79f44b745 | FT 2:0 | WIN (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1565178 | 2026-07-03T18:00:00+00:00 | Australia vs Egypt | PEN | WATCH | ASIAN_HANDICAP HOME 0 @ 2.30 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 7429c1318bb778619cbd876d70f16e2b1f9e651ec158de1d8f095b4e3478fcfa | FT 1:1; PEN 2:4 | PUSH (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1565179 | 2026-07-03T22:00:00+00:00 | Argentina vs Cape Verde Islands | AET | WATCH | ASIAN_HANDICAP HOME -2 @ 1.73 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 104198fde224c735114b913c0979b84c684e4ec40f3f564e638fa20d87607cdc | FT 1:1; AET goals 3:2; ET 2:1 | LOSS (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1567310 | 2026-07-04T01:30:00+00:00 | Colombia vs Ghana | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 1.65 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 96b5ada089e904e18efaf16730d3dff8c3b985a6a9eb8f9818dba10cc2d1ce50 | FT 1:0 | PUSH (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1567824 | 2026-07-04T17:00:00+00:00 | Canada vs Morocco | FT | WATCH | ASIAN_HANDICAP HOME 0 @ 3.25 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | fdd0011fd07ca07f1e8e3b4ef076f0d58023c2849bf9b4b31beda00b8a7dcae3 | FT 0:3 | LOSS (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1569870 | 2026-07-04T21:00:00+00:00 | Paraguay vs France | FT | WATCH | ASIAN_HANDICAP HOME 2 @ 1.73 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | 2996da7cc029768a942f93d01bede4c4091f956f6922b2bcb2f5293f686b1ba2 | FT 0:1 | WIN (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |
| 1568100 | 2026-07-05T20:00:00+00:00 | Brazil vs Norway | FT | WATCH | ASIAN_HANDICAP HOME -1 @ 2.30 | pick=N/A; non_pick=EDGE_INSUFFICIENT | REPLAY_REHEARSAL | be7d04d0d04e8c67235dff7cc53108fcb0149b2fc619291dbacc94cfbf2b11aa | FT 1:2 | LOSS (shadow_only_not_recommendation) | N/A | shadow-only evidence; not a production recommendation |

## 6. 风险和后续

- 需要前向 ledger 才能产生 CLV；replay 只能做纸面对照。
- 需要真实 future fixtures 才能评估 live recommendation。
- 如果要看推荐准确率，需要未来产生 `recommendation_count > 0`，且必须按预注册口径结算。
- Retrospective provider archive 不能证明真实历史盘口时间片，因此 replay_quality=LIMITED。
- 这次价值是验证流程闭环，不是证明模型。
