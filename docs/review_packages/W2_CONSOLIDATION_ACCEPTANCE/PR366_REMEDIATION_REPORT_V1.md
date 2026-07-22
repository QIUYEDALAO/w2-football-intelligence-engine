# PR366 Remediation Report V1

- Start SHA: `601fd55c4f0bbe67faaa8df04535c945bd42fef4`.
- Generation head before staging block report commit: `d4876dd0b6028469fd0980e18d0a7bdd1af22820`.
- Source remediation local checks: PASS.
- GitHub verify: PASS.
- GitHub staging-parity: PASS.
- GitHub predeploy-e2e: PASS.
- Staging acceptance: BLOCKED because target `W2_ENVIRONMENT` was `unset`, not `staging`.
- Formal, lock and production capabilities remain disabled.
