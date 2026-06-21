# W2 Feature Policy V1

Independent model features are strictly as-of.

## Allowed Feature Families

- time-decay Elo
- home or neutral site
- competition importance
- opponent strength
- continental or league tier
- rest days
- long inactivity decay
- sparse-team shrinkage
- new-team or promoted-team prior
- historical attack and defence strength
- rolling form, xG, and statistics from previous matches only

## Forbidden Inputs

The core independent model must reject odds, market probability, line, price, and bookmaker fields.

Lineups, injuries, weather, travel, and altitude remain `DISABLED_INSUFFICIENT_COVERAGE` until a
future stage proves reliable as-of coverage.
