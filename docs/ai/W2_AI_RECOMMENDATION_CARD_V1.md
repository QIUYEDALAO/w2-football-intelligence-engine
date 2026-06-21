# W2 AI Recommendation Card V1

AI 判断在前，系统数据作为证据在后。

RECOMMEND order: match header, AI grade/confidence/risk/data/lock, final recommendation, current reference odds and valid price range, one-line conclusion, match judgment, why this direction, market understanding, rejected alternatives, main script, reference scores, main risk, invalidation conditions, system data summary, odds timeline/evidence/model detail links.

WATCH first screen must clearly show “尚未形成正式推荐”, may show one observed candidate, and must show what data is still awaited. SKIP shows no official direction, must show skip reason and failed hard conditions, and must not hide SKIP with a negative style.

Example RECOMMEND card:

```text
┌────────────────────────────────────────────────────────────┐
│ 虚构超级联赛 · Regular Season   DeepSeek AI · T-1h 最终分析 │
│ 北桥竞技 VS 河岸城             2099-05-18T19:00:00Z        │
│                                                            │
│ [AI主推 A] [信心 0.72] [风险 MEDIUM] [已锁定]             │
│                                                            │
│ AI最终推荐: 北桥竞技 AH HOME -0.25                         │
│ 当前参考赔率: 1.94             建议有效区间: >=1.88        │
│ 市场态度: PARTIAL_AGREE                                    │
│ AI一句话结论: 合同示例：AI 倾向主队让球方向                │
│ AI比赛判断: 主队更可能掌握节奏                             │
│ AI为什么选择: 候选与模型和市场证据一致                     │
│ AI对盘口理解: 价格接近边界，需守住失效条件                 │
│ AI比较方向: 放弃 1X2 主胜                                  │
│ AI预计剧本: 参考 1-0 / 1-1                                 │
│ AI风险: 节奏下降会收窄优势                                 │
│ AI改变观点条件: 价格跌破区间或数据 BLOCKED                 │
│ 系统验证: 证据、候选、快照和模型 run 可追溯                │
└────────────────────────────────────────────────────────────┘
```

WATCH and SKIP examples are rendered from `examples/watch/card.json` and `examples/skip/card.json`.
