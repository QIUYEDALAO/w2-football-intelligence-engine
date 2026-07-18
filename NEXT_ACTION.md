# W2 Next Action

## Current gate

Complete review, merge and staging canary of **R0.1a quote identity observation**.

## Next implementation

R0.0 merged in PR #348 at
`37767123313483ecd8dc9607b4bb085d7cb6db36`. R0.1a is implemented on
`codex/w2-r0-1a-quote-identity-observation` from that main.

R0.1a must:

- project identity from authoritative `FutureMarketObservationModel` rows;
- report `COMPLETE`, `INCOMPLETE` or `CONFLICT` with blockers;
- preserve existing display, pick and tier outputs;
- prove Fresh, Stale and Compatibility fixtures are explainable;
- pass full local checks and all three GitHub CI jobs.

After merge, its staging canary must confirm that the audit projection is present,
provider calls during acceptance remain zero, and recommendation output is unchanged.

Do not begin R0.1b or restore historical feature batches before R0.1a is merged and
its staging canary passes.
The complete phase contract is in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
