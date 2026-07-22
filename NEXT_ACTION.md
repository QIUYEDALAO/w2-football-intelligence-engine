# W2 Next Action

## Current gate

W2_DYNAMIC_PREMATCH_V1 is `locally_verified`.

The dynamic EV and confirmed-lineup lifecycle is locally verified on exact code
implementation `d44db97abd46c4e78814e4787d61db41ffc2acb7`, based on PR #370
head `c62fa82d883633f3b33ff44810a5fbc294b215c5`.

Local gates passed: 1438 Python tests (4 environment-dependent skips), Ruff,
Mypy, Web typecheck and the SQLite migration roundtrip. The implementation adds
append-only evaluation versions, supersession projection, `LINEUP_CONFIRMED`,
`T-30m_VALIDATION_LOCK`, as-of lineup identity/value features and the
post-lineup fresh-odds gate.

Draft PR #370 normal CI passed on verified head
`d284c12f9ecac7d3cb92149fed3c9d7b2a77c6ec` (run `29897588312`):
`verify`, `staging-parity` and `predeploy-e2e` are green.

This is not staging or live-lineup acceptance. The staging read-only preflight
was blocked because the server rejected the available SSH public keys, so no
deployment, provider call or real-lineup-window inspection occurred. Operational
status is `STAGING_SSH_AUTH_UNAVAILABLE`; lineup numeric adjustment remains zero
and advisory-only.

## Next execution

W2_DYNAMIC_PREMATCH_STAGING is authorized only after the existing Draft PR #370
passes its normal CI checks; this does not authorize Formal, Lock or Production.

1. Restore authorized SSH access to the existing staging host; do not mark PR
   #370 ready for review.
2. Deploy the exact accepted implementation SHA to
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
