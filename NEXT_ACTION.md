# W2 Next Action

## Current gate

R0.3 is **PASS**. The authorized next phase is R0.4.

## Next implementation

R0.3 passed local, isolated and direct staging acceptance at
`7e383e2f21fcd0b488ffc95cd58c6c6394291855`. Public Dashboard, DayView,
fixture detail, analysis-card, odds timeline and probability reads now use
fixture/team-scoped bounded dependencies. Injected global observation, raw and
xG readers were never called.

Implement R0.4 in a separate branch: materialize deterministic analysis-card
sidecars for fixtures `1576804`, `1494701` and `1494210` into a versioned canary
checkpoint namespace. Do not switch public reads during R0.4.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
