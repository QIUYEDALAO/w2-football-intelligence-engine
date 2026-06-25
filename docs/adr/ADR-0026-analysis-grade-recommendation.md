# ADR-0026: Analysis-Grade Recommendation Product Scope

Status: Accepted by user for WO#12.

## Context

The earlier roadmap emphasized proving whether W2 could beat market prices before
using stronger recommendation language. Real betting markets are hard to beat
consistently, and even professional quantitative operators do not treat stable
edge as a scheduling assumption.

The user has approved a product turn: W2 should provide multi-factor football
match analysis and transparent analysis-grade recommendations. The system should
help users understand why a match is worth skipping, watching, or reviewing as
an analysis lean. It must not imply certain profit.

## Decision

W2 adds `ANALYSIS_PICK` as the core product output tier.

Public tiers are:

- `NOT_READY`
- `SKIP`
- `WATCH`
- `ANALYSIS_PICK`
- `RECOMMEND`

`ANALYSIS_PICK` is an explainable lean with factor contributions, reasons,
risks, and the mandatory disclaimer `分析参考，非保证盈利`.

`RECOMMEND` is reserved for a separate proof path that demonstrates positive
expected value. It is disabled by default and is not part of the W2
multi-factor analysis acceptance criteria.

`candidate=true` and `formal_recommendation=true` remain reserved for the
market-beating proof path. Analysis cards keep both flags false.

## Consequences

- Gate4 model evidence becomes one analysis factor rather than the product's
  primary success claim.
- Market movement, team state, goal rates, fitness, settled cover history, H2H,
  team value, and data availability all contribute transparently.
- Missing H2H or team-value data is disclosed as unavailable and contributes
  zero; the system must not invent data. Team value remains low weight because
  it is usually reflected in market prices.
- Product language must avoid guaranteed-profit claims.
- Historical validation for analysis cards may be descriptive, but must not
  relabel retrospective evidence as forward proof.
