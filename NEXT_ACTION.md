# W2 Next Action

## Current gate

Complete review and merge of **R0.0 baseline evidence freeze**.

## Next implementation

After R0.0 is merged, create `codex/w2-r0-1a-quote-identity-observation`
from the latest main and implement observation-only quote identity projection.

R0.1a must:

- project identity from authoritative `FutureMarketObservationModel` rows;
- report `COMPLETE`, `INCOMPLETE` or `CONFLICT` with blockers;
- preserve existing display, pick and tier outputs;
- prove Fresh, Stale and Compatibility fixtures are explainable;
- pass full local checks and all three GitHub CI jobs.

Do not begin R0.1b or restore historical feature batches before R0.1a is merged.
The complete phase contract is in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).

