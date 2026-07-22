# W2 Controlled Recommendation Closure Context

Generated: 2026-07-21

## GitHub Context

- PR: #370
- Remote head checked with `git ls-remote`: `951fe7cec095351257a212b7665212ba3b7a46f8`
- This file is a context sync artifact only.
- Latest context-only head after initial sync: `a2960cf52364d299c573fca09350893514b9ee15`.

## User Direction

First execute the parts Codex can control:

- Controlled F9 xG backfill/probe.
- Controlled fresh AH/OU quote refresh.
- Re-run read model, simulation, and analysis chain.
- Generate a new report separating fixed code/execution from remaining provider data gaps.

Do not:

- Merge PR.
- Deploy production.
- Enable formal recommendation.
- Enable lock.
- Write OFFICIAL.
- Fabricate xG, quote freshness, model probability, NO_EDGE, or ANALYSIS_PICK.

Required final report must state whether the result is:

```text
ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED
```

or:

```text
ANALYSIS_CHAIN_XG_SOURCE_UNAVAILABLE
```

Always:

```text
FORMAL_DISABLED
LOCK_DISABLED
PRODUCTION_DISABLED
MANUAL_APPROVAL_REQUIRED
```

## Latest User Instruction Sync

Received: 2026-07-21

User explicitly directed Codex to first solve and execute the parts that are controllable,
then regenerate the report with the remaining data-source issues for expert review.

Execution order for this closure pass:

1. Run the existing code paths that can be run safely in staging.
2. Attempt controlled provider-backed F9 xG materialization and fresh exact AH/OU quote capture.
3. Re-run the read model, simulation, and analysis projection chain.
4. Report only real numbers and real blockers.

This instruction does not authorize:

- More schema-only development as a substitute for execution.
- Fake or proxy xG.
- Recommendation, lock, or OFFICIAL writes.
- Production deployment.
