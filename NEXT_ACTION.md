# W2 Next Action

## Current gate

Implement and accept **R0.1b quote freshness isolation**.

## Next implementation

R0.1a-B1 passed local gates and direct staging acceptance at
`3fc2412c258b996d4f8af6bd44f2799438f49504`. The public analysis-card now uses a
request-local fixture-scoped observation reader. First, sequential and concurrent
probes completed without OOM or restart; provider, DB, queue, locks and the DayView
product projection were unchanged.

R0.1b must add one quote freshness evaluator using authoritative observation
`captured_at` only. Missing or conflicting identity is INCOMPLETE, age over 30
minutes is STALE, and neither may enter current or executable odds. Generated card
timestamps remain evaluation references only. Do not change pick direction, tier,
thresholds, model or product projection.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
