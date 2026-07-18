# W2 Next Action

## Current gate

R2 is `staging_accepted` at local candidate
`6f300d028939bb227683cc644461a7dc67988a77`. R3 is authorized only for
append-only forward shadow evidence. No GitHub synchronization is authorized.

## Next implementation

Build R3 without changing public decision authority:

1. Freeze fixture identity, quote provenance and settled outcome in an
   append-only shadow ledger.
2. Accumulate at least 200 canonical settled fixtures; report push separately
   and exclude it from the decisive hit-rate denominator.
3. Report coverage, missingness, stale rate, log loss, Brier/RPS, ECE,
   research-only ROI, league/market strata and paired bootstrap intervals.
4. Complete at least three consecutive acceptance cycles with artifact, provider,
   model, queue, lock, RSS and restart/OOM evidence.

Reaching 200 fixtures does not promote the candidate. Identity gaps, drift or
insufficient evidence keep R3 in shadow. Champion, thresholds, league scope,
RECOMMEND/lock, OFFICIAL and production remain unchanged until their separate R4
human approval gates.

No GitHub synchronization is authorized.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
