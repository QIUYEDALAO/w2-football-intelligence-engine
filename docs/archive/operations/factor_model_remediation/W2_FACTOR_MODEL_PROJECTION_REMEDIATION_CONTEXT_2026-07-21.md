# W2 Factor Model Projection Remediation Context

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Remote head checked with `git ls-remote`: `ca594e7a9aaac8c0410cd7f72970132d5040287f`
- Base integration branch checked with `git ls-remote`: `d6dcf92e5c65e43420c139b8108e0156c5b6f235`
- This file is a context sync artifact only.
- No production deploy is authorized by this context update.
- No official recommendation or lock is authorized by this context update.

## Remediation Scope

Continue from the staging finding:

```text
READ_MODEL_FACTOR_PROJECTION_NOT_CONSUMING_MATERIALIZED_STAGING_FACTS
XG_SAMPLE_INSUFFICIENT_FOR_SMOKE_FIXTURES
```

The next implementation step is limited to:

- Repairing the read model / factor projection consumption chain so staged canonical odds and materialized factors are visible to the analysis probability path.
- Making F9 insufficient provider xG sample an explicit blocker/gate result instead of a silent generic NOT_READY.

Still prohibited:

- Production deploy
- Formal recommendation enablement
- Lock enablement
- OFFICIAL write
- Provider calls outside an explicitly controlled staging run
