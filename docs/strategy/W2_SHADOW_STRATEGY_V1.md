# W2 Shadow Strategy V1

`W2_SHADOW_STRATEGY_V1` is a shadow-only strategy policy.

It produces an every-fixture judgment:

- most likely outcome
- primary and optional secondary market direction
- raw grade and Gate-capped published grade
- public decision: NOT_READY, SKIP, or WATCH
- hard-gate reasons and invalidation conditions

It never sets `formal_recommendation=true` and never publishes candidate or
recommendation states. Gate 4 remains `PROVISIONAL_FORWARD_HOLDOUT_PENDING`.
