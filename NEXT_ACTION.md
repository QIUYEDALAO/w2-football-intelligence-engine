# W2 Next Action

## Current gate

Implement and accept **R0.2 canonical readiness 503**.

## Next implementation

R0.1c passed local gates and direct staging acceptance at
`58ca49793f2011148e5bfc7d2f1ac5c9062ffbf8`. The canonical Decision Contract
now guarantees that every non-ready surface has no pick, recommendation,
executable odds, lock eligibility or outcome tracking.

R0.2 must make `/health` pure liveness and make root `/ready` the canonical
readiness surface. Critical DB, Redis, schema, artifact-manifest or core-mount
failures must deterministically return 503. `/v1/ready` must share the exact body
and status while adding deprecation and canonical Link headers. Runtime probes
must use root `/ready`; fault injection stays isolated from staging dependencies.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
