# W2 AH/OU Settlement V1

Asian handicap and totals settlement supports whole, half, and quarter lines. Quarter lines split
into two half-stakes, for example `-1.25` becomes `-1` and `-1.5`; `2.75` becomes `2.5` and `3.0`.

Outputs are represented as `FULL_WIN`, `HALF_WIN`, `PUSH`, `HALF_LOSS`, and `FULL_LOSS` in reporting.
The internal legacy enum remains compatible as `WIN`, `HALF_WIN`, `PUSH`, `HALF_LOSS`, and `LOSS`.

EV uses Hong Kong profit `decimal_odds - 1`. Push returns zero. Fair HK water is:

`(P(FULL_LOSS) + 0.5 * P(HALF_LOSS)) / (P(FULL_WIN) + 0.5 * P(HALF_WIN))`

Fair decimal odds are `1 + fair_hk_odds`.
