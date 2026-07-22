# W2 PR #370 Acceptance Remediation Result

Generated: 2026-07-21

## GitHub Context

- Starting PR head checked with `git ls-remote`: `29b23c801f30d029a24c3b33cf2a27d3625793e2`
- Scope: address external acceptance blockers without enabling formal, lock, production, or OFFICIAL.
- PR remains Draft.

## Fixed In This Pass

### CI / Mypy

Fixed the alias cache lookup mypy error in `src/w2/api/repository.py`.

Alias handling now uses deterministic tuple ordering:

```text
requested fixture id
derived api_football alias
```

If both aliases resolve to different fixture payload identities, lookup fail-closes instead of silently choosing one.

### Canonical Projection Adapter

Added read-only adapter methods for:

- `matchday_fixture_identities`
- `canonical_team_match_history`
- `team_rating_snapshots`
- provider-to-W2 projected rolling xG snapshots

When a valid fixture identity exists, `ReadModelService` now uses:

```text
provider fixture ID
→ matchday_fixture_identities
→ home_w2_team_id / away_w2_team_id
→ canonical_team_match_history
→ team_rating_snapshots
→ audited provider-ID-to-W2 xG projection
→ FeatureContext with W2 team IDs
```

F3 now reads canonical history in the canonical path.

F7 now reads persisted `team_rating_snapshots` in the canonical path. It does not use rolling-xG proxy ratings when canonical identity is active.

### Provider Attempt Accounting

The remediation runner now counts provider attempts before sending the HTTP request.

HTTP failures are persisted/audited instead of being skipped.

Exceptions are audited with `status_code=0` and an error code.

### F9 Readiness Reporting

Remediation summary no longer marks F9 `READY` merely because `xg_rows > 0`.

Fixture-level F9 now requires both home and away rolling snapshots with at least 3 real xG matches.

Otherwise:

```text
XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE
```

## Staging Read-Only Probe

Validated with a temporary container against real staging PostgreSQL:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
```

No provider requests were made.

| Fixture | Source | Tier | Odds Rows | F3 Source | F7 Source | F9 | AH/OU Model |
| --- | --- | --- | ---: | --- | --- | --- | --- |
| 1494218 | db_feature_materialized_analysis | WATCH | 315 | canonical_team_match_history | team_rating_snapshots | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE | NOT_READY |
| 1494224 | db_feature_materialized_analysis | WATCH | 325 | canonical_team_match_history | team_rating_snapshots | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE | NOT_READY |

Current remaining blockers:

```text
F9 rolling xG sample insufficient
AUTHORITATIVE_QUOTE_INCOMPLETE
model_probability=NOT_READY
market_probability={}
```

No `NO_EDGE` or `ANALYSIS_PICK` was produced.

## Local Verification

Targeted verification:

```text
ruff: passed
mypy: passed for modified core files
pytest: 31 passed for related tests
```

Full local verify:

```text
scripts/check_w2_all.py: PASS
pytest: 1383 passed, 4 skipped
```

The skipped tests require local Docker/PostgreSQL fixtures.

## State

```text
MARKET_OBSERVATION_READ_PROJECTION_REPAIRED
CANONICAL_HISTORY_AND_RATING_PROJECTION_REPAIRED
F9_INSUFFICIENT_SAMPLE_BLOCKER_EXPLICIT
MODEL_PROBABILITY_STILL_NOT_COMPUTABLE_FOR_SMOKE_FIXTURES
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
