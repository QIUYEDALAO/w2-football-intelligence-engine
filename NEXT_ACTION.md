# W2 Next Action

## Current gate

R1 is `staging_accepted` at local candidate
`103813d7e8ea422756472cb9b4369e3c80876d09`. R2 is authorized for local,
offline-only implementation. No GitHub synchronization is authorized.

## Next implementation

Implement R2 in separate deterministic offline commits, in order:

1. R2.1 persist rolling-form team state correctly.
2. R2.2 constrain the half-goal model contract to the implemented 0.5 market.
3. R2.3 migrate bookmaker heuristic `confidence` to `signal_strength`, including
   one input-compatibility period and truthful Web copy.
4. R2.4 evaluate the fixed snapshot/split with log loss, Brier, RPS, ECE,
   coverage, strata and paired bootstrap intervals.

Each checkpoint gets focused tests; the phase receives complete local/offline
gates. R2 may create only a shadow candidate and must not change champion,
thresholds, league scope, RECOMMEND/lock, OFFICIAL or production.

No GitHub synchronization is authorized. R2 does not require a staging deployment
for each model checkpoint; deploy only if the completed phase introduces a
runtime boundary that requires staging acceptance.
The complete phase contract remains in
[W2 V3 Correctness Recovery Plan](docs/consolidation/W2_V3_CORRECTNESS_RECOVERY_PLAN_20260718.md).
