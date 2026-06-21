# W2 Ablation Policy V1

Ablations remove one feature family at a time and are selected only on train or validation data.

Required removals:

- Elo
- rolling form
- rest days
- match importance
- neutral-site adjustment
- calibration
- market residual layer

Lineup, weather, and travel remain `DISABLED_INSUFFICIENT_COVERAGE`.
