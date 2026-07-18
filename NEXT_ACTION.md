# W2 Next Action

## Current gate

R0.5 is **PASS**. The authorized next phase is R0.6.

## Next implementation

R0.5 passed local, isolated and direct staging acceptance at
`4b880b49acb0b33376c61d2cf8bba608a8682c47`. The three canary analysis-card
routes now read verified frozen artifacts only. Tripwires proved zero online
rebuild, provider, model and global-reader calls; product semantics remained
unchanged apart from replacing request time with the frozen evaluation reference.

Implement R0.6 in a separate branch: materialize every publicly visible staging
fixture and make DayView, fixture detail, analysis-card, Dashboard, tracking and
replay project one frozen authority. Missing or invalid artifacts must remain
`NOT_READY/WATCH` with no pick, lock, provider call, model call or online rebuild.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
