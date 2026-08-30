# V1 admission relative-accuracy and contract audit

## Decision

The retrospective evidence supports the inverse-selection mechanism for both production markets. The admission rules preferentially retain rows where the model disagrees with the market, but in those retained/high-divergence rows the model is less accurate than the market. This is a common upstream defect; the AH strength-slope defect remains real but cannot repair TOTALS.

This is a post-hoc diagnostic over already observed results. It does not certify a replacement gate, select a threshold, grant calibration authority, or prove prospective profitability.

## Frozen evidence

- Protocol SHA-256: `9b7d2caa5f7eca8511da4725c5d90d8b0dde9953db928f550ef0c8fa53163fef`
- Extraction SQL SHA-256: `80ca204b58a6307c16ab78515f5145b609568bc25ce1ba54bde173c203a7b148`
- Extraction time: `2026-08-30T21:25:00Z`
- Snapshot SHA-256: `e3a3cccf24ec751a6bca0fff5c6f6f6ff9cbb6896adb1a9747bb6b1f0ed72883`
- Audit JSON SHA-256: `783af0742951c6efbaf94e53b5bd6e299a7d33b31c5b786c6d45c036c8bd7239`
- Cohort: `354` final official fixture-market evaluations / `177` fixtures; exactly `177 AH + 177 TOTALS`; final states `110 CANDIDATE / 111 NO_EDGE / 133 BLOCKED`.
- All rows have a frozen evaluation payload, bound model capture, enabled competition identity, and result confirmed no later than extraction time.
- Export used server-side `COPY ... TO STDOUT WITH CSV HEADER`, with no `LIMIT` or client pagination. The export process exited and the post-export active-COPY count (excluding the inspection session) was `0`.
- Provider calls `0`; production writes `0`; no deployment, migration, parameter, ledger, allowlist, or GitHub operation.

## Measurement

The market probability is recovered exactly from the persisted lifecycle operands:

```text
market_probability = model_effective_probability - persisted_current_delta
```

The realised target follows the repository's scalar effective-settlement contract: `WIN=1`, `HALF_WIN=0.5`, `PUSH=0.5`, `HALF_LOSS=0`, `LOSS=0`. Model and market are compared by Brier loss and absolute error. Positive `model_minus_market_brier` means the model was worse than the market on the same frozen selected-side evidence.

Fixture-cluster bootstrap uses `5,000` deterministic resamples and keeps AH/TOTALS observations from the same fixture in one cluster.

## Results

### Economic-pass selection

| Market | Economic pass N | Fail N | Pass model-minus-market Brier | Fail model-minus-market Brier | Pass-minus-fail | Fixture-cluster 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| AH | 97 | 80 | +0.059618 | -0.007419 | **+0.067037** | **[+0.032949, +0.102071]** |
| TOTALS | 70 | 107 | +0.035473 | +0.001577 | **+0.033896** | **[+0.005200, +0.061057]** |

The lifecycle economic pass is the actual persisted numeric rule: `EV>0`, `delta>=0.05`, and `EV-SE>0`, independent of calibration authority and other technical blockers. In both markets the interval is entirely above zero: the pass subset is materially worse relative to the market than the fail subset.

The alternative cashflow-edge rule gives the same direction:

| Market | Cashflow pass-minus-fail Brier contrast | Fixture-cluster 95% CI |
|---|---:|---:|
| AH | +0.052046 | [+0.022603, +0.083047] |
| TOTALS | +0.029772 | [+0.007663, +0.050582] |

### Divergence gradient

For `delta>=0.10` versus lower delta, the model's relative Brier deterioration is:

| Market | High-minus-low contrast | Fixture-cluster 95% CI |
|---|---:|---:|
| AH | **+0.103616** | **[+0.056238, +0.147835]** |
| TOTALS | **+0.073865** | **[+0.022297, +0.123638]** |

The detailed bins show the mechanism directly. AH model-minus-market Brier moves from `-0.011849` at delta `[0.05,0.10)` to `+0.033120`, `+0.092916`, and `+0.284880` in the next three higher bins. TOTALS moves from `+0.000477` to `+0.037555` and `+0.173649`; the final `>=0.25` bin has only three observations and is not interpreted.

The protocol also froze EV bins. They independently show the same high-score failure mode:

| Market | EV bin | N | Model-minus-market Brier |
|---|---|---:|---:|
| AH | `<0` | 32 | -0.012250 |
| AH | `[0,0.05)` | 22 | +0.001233 |
| AH | `[0.05,0.10)` | 19 | -0.003018 |
| AH | `[0.10,0.15)` | 24 | -0.010292 |
| AH | `[0.15,0.25)` | 34 | +0.021579 |
| AH | `>=0.25` | 46 | **+0.111411** |
| TOTALS | `<0` | 43 | +0.001650 |
| TOTALS | `[0,0.05)` | 35 | -0.004179 |
| TOTALS | `[0.05,0.10)` | 38 | +0.010434 |
| TOTALS | `[0.10,0.15)` | 25 | +0.021345 |
| TOTALS | `[0.15,0.25)` | 22 | +0.010727 |
| TOTALS | `>=0.25` | 14 | **+0.111508** |

Intermediate EV bins are not monotonic, so they are not used to choose a cutoff. The highest-EV bin is nevertheless the worst model-relative-to-market bin in both markets, consistent with the primary delta and lifecycle-pass contrasts.

### Final candidates

| Market | Candidate N | Candidate model Brier | Candidate market Brier | Model-minus-market | Non-candidate model-minus-market | Candidate-minus-non-candidate 95% CI |
|---|---:|---:|---:|---:|---:|---:|
| AH | 58 | 0.280773 | 0.220243 | +0.060530 | +0.014106 | [-0.000837, +0.094299] |
| TOTALS | 52 | 0.252376 | 0.211568 | +0.040808 | +0.004239 | **[+0.004301, +0.068799]** |

Candidate state is confounded by the calibration-authority deployment and technical gates, so the economic-pass and divergence contrasts above are the primary evidence. TOTALS candidates independently retain a positive interval; AH candidates have the same point direction but their candidate-state interval narrowly includes zero.

## Admission-contract path audit

### Persisted delta: no bypass

All `110/110` final candidates have persisted `current_delta>=0.05`; the minimum is `0.050605`. The earlier `105/110` claim was created by an audit-script defect: raw AH observation line signs were treated as a stable two-sided pairing identity. Correct pairing for the five disputed rows reproduces the persisted delta exactly. Those five rows did not bypass the lifecycle delta gate.

The corrected opposite-direction audit derives the authoritative market probability from the persisted model probability and delta rather than re-pairing raw signed AH lines. It still finds `0/110` opposite directions with both positive EV and cashflow edge at least 5%, so the direction-selector hypothesis remains rejected under the corrected method.

### Cashflow edge: two real contract-drift rows

Two final candidates have recomputed five-state cashflow edge below 5%:

| Fixture | Evaluation | Market/side | EV | EV-SE | Persisted delta | Cashflow edge |
|---|---|---|---:|---:|---:|---:|
| 1492348 | `dqe-ada31d6…a311c` | AH AWAY | +0.046605 | +0.003523 | +0.069219 | **+0.046622** |
| 1493078 | `dqe-2d64ca9…b0adbe` | AH AWAY | +0.040345 | +0.003596 | +0.066370 | **+0.045971** |

This is deterministic contract drift, not rounding:

1. `analysis_evidence._side_evidence()` admits on EV, cashflow edge, and EV-SE; it records delta but explicitly marks it non-admission.
2. `market_candidate._best_evaluated_side()` returns the best evaluated side even if its `_admission_eligible` flag is false.
3. `read_model_projection._dynamic_evaluation_side()` consumes that selected/ready side and passes model probability, market probability, EV, and EV-SE into lifecycle without requiring `analysis_direction_allowed` or `ev_eligible`.
4. `lifecycle.classify_evaluation()` admits on EV, delta, and EV-SE and never receives/checks cashflow edge.

Therefore both rows legitimately pass the lifecycle contract while failing the market-candidate cashflow contract. The system does not currently have one authoritative four-gate definition.

## Required next decision

Do not ship only `raw_delta_scale` and call EV fixed. The evidence supports this sequence:

1. Define one authoritative admission contract and one persisted evidence schema. Whether delta, cashflow edge, or a model-versus-market relative-accuracy gate has decision authority must be preregistered; do not silently combine or raise thresholds from this retrospective result.
2. Design a prospective market-relative-accuracy gate for both AH and TOTALS, with fixture-cluster scoring and a frozen evaluation date/sample size. The current audit identifies the failure mechanism but cannot choose its production threshold.
3. Continue AH slope recalibration as a market-specific correction, while explicitly excluding TOTALS from its repair claim.
4. Keep TOTALS as a separate model/admission workstream. Its total-goal mean may be unbiased while its selected high-divergence subset is still worse than the market.

## Reproduction

```bash
PYTHONPATH=src python3 scripts/audit_admission_relative_accuracy.py \
  --input docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/admission_relative_accuracy_20260830T212500Z.csv \
  --output /tmp/admission_relative_accuracy.json

PYTHONPATH=src python3 scripts/audit_settled_candidate_directions.py \
  --evaluations docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/settled_candidate_snapshot_20260830T211257Z_evaluations.csv \
  --market docs/review_packages/V1_RECALIBRATION_EVIDENCE_01/settled_candidate_snapshot_20260830T211257Z_market.csv \
  --output /tmp/settled_direction_analysis.json
```
