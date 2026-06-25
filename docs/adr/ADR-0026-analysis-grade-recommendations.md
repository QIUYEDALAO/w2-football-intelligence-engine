# ADR-0026 Analysis-Grade Recommendations

Status: Accepted for U5 governance.

## Context

Earlier W2 stages treated formal recommendation as dependent on proving an edge over market prices. That remains a valid upper bound for a future `RECOMMEND` mode, but it is not the product's normal operating mode. Professional quantitative betting programs struggle to sustain market-beating performance against efficient odds; W2 should not encode a product promise that depends on that proof before it can produce useful analysis.

## Decision

W2's default output is analysis-grade recommendation: `ANALYSIS_PICK` with transparent factors, bookmaker intent, risks, and invalidation conditions. The product must state "分析参考·非稳赢" and must not use certainty language such as guaranteed, sure-win, or must-hit phrasing.

`RECOMMEND` remains a disabled upper tier for a separately proven positive-EV regime. Gate4/Gate5 evidence can still control that tier, but it must not suppress analysis-grade cards when as-of data is available. Analysis cards never set `candidate=true` or `formal_recommendation=true`.

## Consequences

- Multi-market analysis cards can be emitted whenever coverage and as-of inputs are sufficient.
- Missing coverage still degrades honestly to `SKIP`.
- Retrospective evidence may validate machinery but cannot impersonate forward evidence.
- Market-beating verdicts may stay in archived research reports, but active product code must not require them to display W2 analysis.
