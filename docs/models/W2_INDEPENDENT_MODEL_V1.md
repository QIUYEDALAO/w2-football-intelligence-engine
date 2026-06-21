# W2 Independent Model V1

Stage 7 implements odds-free probability models.

## Tracks

- National: 1081 results, with 1074 paired market rows for Stage 6 POWER comparison.
- Club: 5270 five-league results, compared only with non-market baselines because historical market
  odds coverage is insufficient.

National and club tracks do not share production parameters.

## Candidate Families

- Time-decay Elo
- Independent Poisson
- Historical Dixon-Coles
- Bivariate Poisson
- Negative Binomial
- Hierarchical or shrunk attack-defence
- Time-decay attack-defence
- Validation-only constrained ensemble hooks

## Output Contract

Each prediction carries 1X2 probabilities, expected goals, normalized score matrix, OU probability,
BTTS probability, uncertainty interval, model version, data cutoff, and provenance.

No output is a candidate, recommendation, stake, or edge.
