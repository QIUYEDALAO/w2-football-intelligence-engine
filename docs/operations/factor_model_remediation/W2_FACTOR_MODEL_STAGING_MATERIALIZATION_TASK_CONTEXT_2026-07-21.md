# W2 Factor Model Staging Materialization Task Context - 2026-07-21

## User Acceptance Baseline

PR #370 code foundation is `CONDITIONAL PASS`.

Factor remediation is not complete until staging real PostgreSQL and controlled provider execution materialize:

- canonical provider-primary team identity
- canonical match history
- F3 rest fitness
- F7 ratings
- provider statistics/xG probe with no proxy xG
- F9 rolling xG or real provider source blocker
- F6 H2H or NO_H2H_HISTORY
- model probability, market devig probability, delta, EV, uncertainty
- V3 NO_EDGE or ANALYSIS_PICK when model chain is complete

F5 and F8 may remain warning/formal blockers but must not block foundational analysis-chain validation.

## Required GitHub Baseline

Use `git ls-remote` for PR #370 current remote head before execution.

Observed remote head:

```text
a33022826d92b937581c70d2361d364ccc45d608 refs/heads/codex/w2-factor-model-remediation-master
```

Base branch observed:

```text
d6dcf92e5c65e43420c139b8108e0156c5b6f235 refs/heads/codex/w2-analysis-recommendation-closure
```

## Execution Constraints

- Do not continue schema development as a substitute for staging execution.
- Do not deploy production.
- Keep staging scheduler stopped.
- Enable controlled provider calls only for the bounded backfill window.
- After provider calls, set `W2_PROVIDER_CALLS_DISABLED=true` and keep scheduler stopped.
- recommendation, lock, OFFICIAL writes must remain zero.

## Required Final State

One of:

- `ANALYSIS_RECOMMENDATION_CHAIN_VALIDATED`
- `ANALYSIS_CHAIN_XG_SOURCE_UNAVAILABLE`
- `ANALYSIS_CHAIN_STAGING_EXECUTION_FAILED`

Always:

- `FORMAL_DISABLED`
- `LOCK_DISABLED`
- `PRODUCTION_DISABLED`
- `MANUAL_APPROVAL_REQUIRED`
