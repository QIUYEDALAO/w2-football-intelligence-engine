# W2 Next Action

## Current gate

The dynamic EV and confirmed-lineup lifecycle is locally verified on exact code
implementation `d44db97abd46c4e78814e4787d61db41ffc2acb7`, based on PR #370
head `c62fa82d883633f3b33ff44810a5fbc294b215c5`.

Local gates passed: 1438 Python tests (4 environment-dependent skips), Ruff,
Mypy, Web typecheck and the SQLite migration roundtrip. The implementation adds
append-only evaluation versions, supersession projection, `LINEUP_CONFIRMED`,
`T-30m_VALIDATION_LOCK`, as-of lineup identity/value features and the
post-lineup fresh-odds gate.

This is not staging or live-lineup acceptance. There was no provider call and
no real confirmed-lineup window, so operational status is
`WAITING_FOR_REAL_LINEUP_WINDOW`. Numeric lineup adjustment remains zero and
advisory-only.

## Next execution

1. Update the existing Draft PR #370 with this implementation and require its
   normal CI checks to pass. Do not mark the PR ready for review.
2. Only after CI is green, deploy the exact accepted implementation SHA to
   staging while keeping the scheduler and provider refresh switches disabled.
3. Rebuild upcoming-fixture state read-only. If a real lineup window exists,
   run one controlled lineup + odds event canary for that fixture; otherwise
   retain `WAITING_FOR_REAL_LINEUP_WINDOW`.
4. Restore provider calls, scheduler and future-fixture refresh to disabled,
   then run 20 public reads and prove zero provider-call and DB-write deltas.
5. Update the machine evidence with actual staging SHA and canary results.

Formal recommendation, recommendation lock, OFFICIAL capture, champion switch
and Production remain unauthorized. Manual approval is required for any of
those transitions.
