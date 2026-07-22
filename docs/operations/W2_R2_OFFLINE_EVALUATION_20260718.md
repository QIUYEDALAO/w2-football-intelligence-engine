# W2 R2 offline correction evaluation

Status: **locally verified; shadow candidate only**.

## Fixed evidence

- Input: `tests/fixtures/gate4/dixon_coles_matches.json`
- Input SHA-256: `309e4b36c8c4eace13899d9960386b7008c9d5989262c2e13af5937245c2bf70`
- Split: chronological fixed holdout, 12 warm-up fixtures and 12 validation fixtures
- Model: `TIME_DECAY_ATTACK_DEFENCE`
- Bootstrap: paired, 1,000 samples, seed 7
- Machine-readable result: `docs/operations/W2_R2_OFFLINE_CORRECTION_EVALUATION_20260718.json`

## Result

| Metric | Legacy-state simulation | R2 candidate | Delta | Paired 95% interval |
| --- | ---: | ---: | ---: | ---: |
| Log loss | 0.961123 | 0.961123 | 0.000000 | [0.000000, 0.000000] |
| Multiclass Brier | 0.572094 | 0.572094 | 0.000000 | [0.000000, 0.000000] |
| RPS | 0.193735 | 0.193735 | 0.000000 | [0.000000, 0.000000] |
| ECE | 0.147009 | 0.147009 | 0.000000 | [0.000000, 0.000000] |
| Coverage | 1.000000 | 1.000000 | 0.000000 | not applicable |

The R2.1 correction changes rolling-form features on all 12 validation rows. The
selected model currently does not consume those features, so no probability row
changes and all paired metric deltas are exactly zero. R2.2 constrains an API
contract without changing the implemented half-goal calculation. R2.3 changes
heuristic naming and display semantics, not numerical model output.

These results are fixture-level offline regression evidence. They are not a
production hit-rate claim and do not authorize champion replacement,
RECOMMEND/lock, OFFICIAL, or production. The R2 result remains a shadow candidate
pending the later R3 evidence and R4 human review gates.
