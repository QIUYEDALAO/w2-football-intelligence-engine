# W2 PR370 Real Uncertainty Source and Staging Approval Context

Date: 2026-07-21

Repository: QIUYEDALAO/w2-football-intelligence-engine

Branch / PR: PR #370, Draft

Verified remote head:

```text
75dcf125011786a5b2cdeb3a3b52ed2d42573dbd
```

## User Approval Captured

The user approved both controlled provider access and deployment to the cloud staging server for this acceptance round.

This approval is scoped to:

```text
staging exact-SHA release
controlled provider fresh quote window
analysis-only validation
```

It does not approve:

```text
production deployment
formal recommendation enablement
lock creation
OFFICIAL writes
continuous provider refresh
scheduler restart
```

Required standing controls:

```text
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
W2_PROVIDER_CALLS_DISABLED=true after the controlled window
staging scheduler remains stopped
```

## External Acceptance Clarification

The previous PR #370 code round fixed several gates and contracts, including:

```text
analysis uncertainty gate code
primary-market resolution
bounded V3 fail-closed behavior
V3 core/envelope hash
listed-table 20-read zero-write audit
```

However, the remaining analysis blocker is not only stale quotes. The runtime simulation input chain still needs a real uncertainty source.

The exact failure to fix is:

```text
ReadModelService builds SimulationInputs without real lambda_sigma_home/lambda_sigma_away.
The defaults are 0.0 and lambda_uncertainty_method becomes none.
Fresh quote alone would still return MODEL_UNCERTAINTY_NOT_READY.
```

## Required Real Uncertainty Source

Use existing real provider xG rows from `team_xg_match`.

For fixture as-of before kickoff:

```text
SE(team attack xG)  = sample_std(xg_for) / sqrt(n)
SE(team defence xG) = sample_std(xg_against) / sqrt(n)

sigma_home =
0.5 * sqrt(
    SE(home attack)^2
  + SE(away defence)^2
)

sigma_away =
0.5 * sqrt(
    SE(away attack)^2
  + SE(home defence)^2
)
```

Rules:

```text
each sample group n >= 3
only use real provider xG before fixture as-of
no arbitrary constant floor
no odds proxy
no score proxy
no shots proxy
save input fixture IDs, sample counts, sample variance, as-of, method version and input hash
pass positive sigma explicitly into SimulationInputs
```

Analysis-ready output:

```text
lambda_uncertainty_method=empirical_xg_standard_error.v1
lambda_uncertainty_status=ANALYSIS_READY
lambda_sigma_home>0
lambda_sigma_away>0
```

If any required sample group is missing, too small or zero-variance, the analysis chain must remain fail-closed with a truthful blocker instead of inventing sigma.

Formal readiness remains separate and requires future approved validation:

```text
lambda_uncertainty_status=APPROVED_VALIDATED
```

## Remaining Fixed Scope

This round must complete only the following:

```text
1. Wire real xG uncertainty source to SimulationInputs.
2. Freeze unknown-fixture public API contract.
3. Strengthen safety evidence for cohort/OFFICIAL invariants and missing expected audit tables.
4. Deploy exact SHA 75dcf125011786a5b2cdeb3a3b52ed2d42573dbd to staging.
5. Run real alembic upgrade head and verify current == heads.
6. Keep scheduler and continuous provider refresh disabled.
7. Open one controlled provider quote window for upcoming Allsvenskan fixture(s), then disable provider calls again.
8. Run public API/live DB/frozen parity canary.
```

Allowed final analysis outcomes:

```text
NO_EDGE
ANALYSIS_PICK
MODEL_UNCERTAINTY_NOT_READY with truthful source blocker
ANALYSIS_CHAIN_STAGING_EXECUTION_FAILED with evidence
```

Do not force a pick.

