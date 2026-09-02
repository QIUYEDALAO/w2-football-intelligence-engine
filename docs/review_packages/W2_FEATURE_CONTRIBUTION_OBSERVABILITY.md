# W2 Feature Contribution Observability (P1b)

## Scope

This change adds diagnostic-only decomposition to each successful `run_simulation()` result under `simulation.calibration.feature_contributions`. It does not alter calibration parameters, thresholds, calibration version, persistence, provider access, or model eligibility.

Each row includes the raw input value, `as_of`/valid-from metadata when supplied by the caller, missing reason, configured weight, eligibility and reason, and contributions to total and delta. The decomposition is derived from the same calibration components used for `lambda_home` and `lambda_away`; no second model path is used.

## Example and contract checks

The regression tests in `tests/unit/test_simulation_engine.py` verify:

- proxy Elo is explicitly `PROXY_EXCLUDED` with zero delta contribution;
- xG, Elo, squad value, lineup strength, AH lineup and totals lineup rows expose inputs and contributions;
- PIT metadata is preserved (`xg_valid_from`, `elo_valid_from`, `squad_value_valid_from`, `lineup_valid_from`);
- `feature_contribution_liveness_alerts()` emits `NONZERO_WEIGHT_ZERO_CONTRIBUTION` when a configured feature contributes zero across the requested recent window.

The current production-shaped path has proxy Elo and lineup numeric gates contributing zero; this is reported diagnostically and is not treated as evidence that enabling a feature will improve accuracy.

## Verification

- Targeted simulation, materialized-card, and calibration tests: 49 passed.
- Canonical simulation/read-authority set: 18 passed.
- Package matrix: 5 passed.
- Calibration registry plus targeted tests: 49 passed.
- Ruff and `git diff --check`: passed.
- Full suite on this branch: 2951 passed, 9 skipped, 5 failed. All five failures reproduce at parent `1de3c1ef` and are host limitations (Compose plugin 2, bare `python` 1, macOS UID/GID directory behavior 2). Task-related failures: 0.

Calibration identity remains `21960a863fd93dcae01ff8804e73fd0ef9d8360e8f2b8073313f226322e5db71`; verdict remains `APPROVED_VALIDATED`.

Stop-line accounting: Provider 0; production writes 0; ledger 0; migration 0; deployment 0; GitHub 0; `CALIBRATION_VERSION` 0; model parameter values 0.
