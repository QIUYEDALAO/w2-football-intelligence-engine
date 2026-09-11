# Admission relative-accuracy audit protocol

Status: frozen post-hoc diagnostic protocol. It is not a preregistered model-validation protocol and cannot grant calibration authority.

Extraction time is `2026-08-30T21:25:00Z`. The cohort is every enabled-competition fixture-market whose final official evaluated opportunity at that time is `EVALUATED_CANDIDATE`, `EVALUATED_NO_EDGE`, or `BLOCKED_BY_GATE`, with an authoritative result confirmed by extraction time and a bound model forecast capture. No provider calls or production writes are permitted.

The frozen evaluation supplies the selected side, exact line, odds, five-state model distribution, model effective probability, persisted `current_delta`, EV, and EV-SE. Market probability is reconstructed as `model_effective_probability - persisted_current_delta`, exactly matching the lifecycle admission input rather than re-pairing a different quote from the market table.

The realized scalar target follows the repository's effective-settlement-probability contract: `WIN=1`, `HALF_WIN=0.5`, `PUSH=0.5`, `HALF_LOSS=0`, `LOSS=0`. For model and market separately report Brier loss and absolute error against this target. This scalar audit diagnoses the admission comparator; it is not a replacement for five-state cashflow scoring.

Report separately for AH and TOTALS, and for final candidate versus non-candidate. Bin persisted delta into `[0,0.05)`, `[0.05,0.10)`, `[0.10,0.15)`, `[0.15,0.25)`, and `[0.25,+inf)`. Also bin persisted EV using the same boundaries. For each bin report N, model error, market error, and paired difference `model loss - market loss`.

The inverse-selection hypothesis is supported only if, within a market, higher divergence bins show materially worse model-relative-to-market loss and candidate rows are worse than non-candidate rows. Report cluster-bootstrap 95% confidence intervals by fixture for candidate-versus-non-candidate and high-versus-low divergence differences. No threshold or parameter may be selected from these outcomes.

Separately trace every previously reported edge/delta inconsistency using the persisted payload and the exact code paths. A recomputation under a different quote-pairing contract is a measurement discrepancy, not evidence that the persisted gate was bypassed.
