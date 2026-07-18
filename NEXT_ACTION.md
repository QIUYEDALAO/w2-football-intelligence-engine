# W2 Next Action

## Current gate

Resolve the **R0.1a staging canary hard blocker** without mixing invariants.

## Next implementation

R0.1a merged in PR #349 at
`5849374e61bc7b7fe91b6da41c637b5c65a4b9fb`, with all three CI jobs passing.
Its staging canary preserved DayView recommendation output but the public
analysis-card probe triggered an API OOM, exit 137 and two restarts. Staging was
automatically rolled back to `b5cfd6575ba7274692714c9fc814916a00c13e36`.

R0.1a must:

- project identity from authoritative `FutureMarketObservationModel` rows;
- report `COMPLETE`, `INCOMPLETE` or `CONFLICT` with blockers;
- preserve existing display, pick and tier outputs;
- prove Fresh, Stale and Compatibility fixtures are explainable;
- pass full local checks and all three GitHub CI jobs.

Provider calls during acceptance were zero. The quote projection cannot be accepted
through the public path while that path still performs the known unbounded read-time
rebuild.

Do not begin R0.1b or restore historical feature batches. Fixing the blocker requires
either an explicit canary-scope ruling or resequencing the already planned bounded or
frozen read invariant; both require a plan decision because they change the approved
phase order.
The complete phase contract is in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
