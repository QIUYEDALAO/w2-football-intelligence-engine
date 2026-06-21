# W2 Evaluation Policy V1

Stage 8 compares models on the same fixture set where possible:

- uniform
- Elo
- simple Poisson
- Stage 6 POWER market baseline
- Stage 6 Dixon-Coles market baseline
- Stage 7 best independent model
- Stage 7 calibrated independent model
- residual or blend research-only layer

Metrics include log loss, RPS, Brier, ECE, reliability, exact-score log score, OU/BTTS metrics,
paired bootstrap confidence intervals, and competition/year/favorite/neutral/phase slices.

AH remains `HISTORICAL_AH=FORWARD_ONLY`.
