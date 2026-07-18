# W2 Next Action

## Current gate

R1 is `implemented`; checkpoints R1.1–R1.4 are `locally_verified` and R1.5 is
awaiting the phase-wide local gates. R1 is not yet `staging_accepted`.

## Next implementation

Run the phase-wide R1 Gate: Python, Ruff, Mypy, TypeScript, Web production build,
Playwright, acceptance, tracked-output, credential scan, diff check, isolated
staging-parity and predeploy-e2e. R1 has no database migration, so migration
upgrade/downgrade/upgrade is `NOT_APPLICABLE`.

If every local and isolated Gate passes, freeze formal staging, stop scheduler,
deploy the exact local R1 candidate once, run runtime/product canaries and restore
the scheduler/watchdog state. Any hard failure rolls back to the accepted R0.6
release. Only a successful canary may change R1 to `staging_accepted` and authorize R2.

No GitHub synchronization is authorized. Use local gates, isolated staging-parity,
predeploy-e2e and direct staging canary.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
