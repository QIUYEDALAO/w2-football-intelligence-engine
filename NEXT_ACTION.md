# W2 Next Action

## Current gate

Implement and accept **R0.1c non-READY no-pick invariant**.

## Next implementation

R0.1b passed local gates and direct staging acceptance at
`13183b3eabd9022cada47a76d01fa619648bd01f`. Authoritative observation time now
drives a single freshness evaluator; stale and incomplete quotes retain audit
identity but are excluded from current odds and pricing.

R0.1c must enforce one final Decision Contract postcondition. BLOCKED or
INCOMPLETE/CONFLICT becomes NOT_READY; STALE/PARTIAL becomes WATCH; only READY
with complete provenance may retain a pick tier. Every non-READY output must clear
pick, recommendation, executable odds and recommendation ID, and must set lock and
outcome tracking false. Invalid RECOMMEND prerequisites may not fall back to
ANALYSIS_PICK.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
