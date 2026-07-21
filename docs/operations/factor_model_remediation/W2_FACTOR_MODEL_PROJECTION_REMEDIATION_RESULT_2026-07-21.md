# W2 Factor Model Projection Remediation Result

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Starting remote head checked with `git ls-remote`: `ca594e7a9aaac8c0410cd7f72970132d5040287f`
- Scope: read model / factor projection consumption and explicit F9 blocker semantics.
- No production deploy was performed.
- No provider calls were made during the remediation validation probe.
- No recommendation, lock, or OFFICIAL write is authorized by this result.

## Code Changes

Implemented:

- Bounded public analysis now accepts fixture id aliases for API-Football provider ids:
  - `1494218`
  - `api_football:1494218`
- Bounded public analysis now prefers rebuilding the DB/materialized analysis card from scoped fixture payload + scoped observations before falling back to stale embedded read-model cards.
- Fixture-scoped observation validation still fail-closes on unrelated fixture rows.
- F9 insufficient xG sample now projects an explicit blocker:

```text
XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE
```

This is attached to:

- `data_readiness.xg_blocker`
- `scoreline_readiness.blocker`

## Staging Validation Probe

Validation was run in a temporary container against real staging PostgreSQL with:

```text
W2_PROVIDER_CALLS_DISABLED=true
W2_PROVIDER_SCHEDULER_ENABLED=false
W2_ENVIRONMENT=staging
W2_STAGING_ENABLED_COMPETITIONS=allsvenskan
```

No provider request was made during this validation.

## Probe Results

| Fixture Query | Source | Decision Tier | Market Observations | Bookmakers | xG Status | xG Blocker |
| --- | --- | --- | ---: | ---: | --- | --- |
| 1494218 | db_feature_materialized_analysis | WATCH | 315 | 10 | INSUFFICIENT_HISTORY | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE |
| api_football:1494218 | db_feature_materialized_analysis | WATCH | 315 | 10 | INSUFFICIENT_HISTORY | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE |
| 1494224 | db_feature_materialized_analysis | WATCH | 325 | 9 | INSUFFICIENT_HISTORY | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE |
| api_football:1494224 | db_feature_materialized_analysis | WATCH | 325 | 9 | INSUFFICIENT_HISTORY | XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE |

This confirms that the read model / factor projection path now consumes the already-materialized staging market facts when the competition is enabled for staging analysis.

## Remaining Blockers

The analysis chain is still not allowed to emit `NO_EDGE` or `ANALYSIS_PICK` for these smoke fixtures because:

1. F9 remains incomplete:

```text
XG_SAMPLE_INSUFFICIENT_FOR_FIXTURE
```

2. The previously captured odds are currently projected as stale/incomplete quote evidence, so AH/OU candidates still report:

```text
AUTHORITATIVE_QUOTE_INCOMPLETE
model_probability=NOT_READY
market_probability={}
```

3. The real staging service environment was updated with the staging-only competition allowlist:

```text
W2_STAGING_ENABLED_COMPETITIONS=brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien
```

This is a staging analysis enablement flag, not production enablement, and does not enable formal recommendation, lock, OFFICIAL output, or provider calls. The running service was not restarted in this step; the setting takes effect for subsequent staging process starts/deploys.

## Verification

Local verification:

```text
.venv/bin/ruff check src/w2/api/repository.py tests/unit/test_analysis_card_xg_materialized.py tests/unit/test_scoreline_independent_xg.py tests/unit/test_public_analysis_card_bounded.py
.venv/bin/pytest -q tests/unit/test_analysis_card_xg_materialized.py tests/unit/test_scoreline_independent_xg.py tests/unit/test_public_analysis_card_bounded.py
```

Result:

```text
ruff: passed
pytest: 27 passed
```

## Final State

```text
READ_MODEL_FACTOR_PROJECTION_CONSUMPTION_REPAIRED
F9_INSUFFICIENT_SAMPLE_BLOCKER_EXPLICIT
MODEL_PROBABILITY_STILL_NOT_COMPUTABLE_FOR_SMOKE_FIXTURES
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```
