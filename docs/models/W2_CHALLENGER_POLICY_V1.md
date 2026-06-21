# W2 Challenger Policy V1

The national challenger may compare:

- existing time-decay attack-defence
- regularized multiclass logistic
- gradient boosting or LightGBM-style models
- Elo plus Poisson stacking
- hierarchical attack-defence
- constrained ensemble

Selection may use train, validation, and nested walk-forward only. The frozen 214-row audit set is
`AUDIT_ONLY`.

Forbidden inputs remain odds, market probability, line, bookmaker, future ranking, current-match
post-match statistics, lineup leaks, and future results.
