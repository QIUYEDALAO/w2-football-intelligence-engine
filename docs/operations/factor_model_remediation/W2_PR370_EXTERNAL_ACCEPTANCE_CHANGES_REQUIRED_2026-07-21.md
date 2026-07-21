# W2 PR #370 External Acceptance Result

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Remote head checked with `git ls-remote`: `29b23c801f30d029a24c3b33cf2a27d3625793e2`
- Base integration branch checked with `git ls-remote`: `d6dcf92e5c65e43420c139b8108e0156c5b6f235`
- This file is a context sync artifact only.

## Acceptance Result

```text
PR #370: CHANGES REQUIRED
MERGE: BLOCKED
STAGING ACCEPTANCE: FAILED
FORMAL: DISABLED
LOCK: DISABLED
PRODUCTION: DISABLED
MANUAL_APPROVAL_REQUIRED
```

The previous implementation may only be described as:

```text
MARKET_OBSERVATION_READ_PROJECTION_REPAIRED
FIXTURE_PROVIDER_ALIAS_SUPPORTED
F9_INSUFFICIENT_SAMPLE_BLOCKER_EXPLICIT
```

It must not be described as:

```text
FACTOR_MODEL_CHAIN_REPAIRED
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
```

## Required Remediation

Required next steps:

- Fix exact-head CI failure in `src/w2/api/repository.py`.
- Make fixture alias lookup deterministic and fail-closed on alias conflicts.
- Wire canonical materialized tables into `ReadModelService`:
  - `matchday_fixture_identities`
  - `canonical_team_match_history`
  - `team_rating_snapshots`
  - W2-keyed or audited projected rolling xG snapshots
- Fix provider attempted-call accounting and quota preflight.
- Fix F9 summary readiness so `xg_rows > 0` does not mean fixture-level READY.
- Perform controlled xG and fresh odds runs only after code/CI is green.
- Keep recommendation, lock, OFFICIAL, formal, staging release, and production disabled until manual approval.

Final allowed outcomes remain:

```text
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
```

or:

```text
ANALYSIS_CHAIN_XG_SOURCE_UNAVAILABLE
```

Always append:

```text
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
