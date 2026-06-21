# W2 Odds and Settlement V1

Supported Stage 3 market families:

- ONE_X_TWO
- ASIAN_HANDICAP
- TOTALS
- BTTS

`OddsObservation` stores market, selection, line, decimal odds, bookmaker,
suspended, live, stale, provider update time, capture time, raw label,
canonical selection, and settlement rule.

`line` and `decimal_odds` use Decimal values. Quarter lines are split by the
domain library before settlement. Asian Handicap and totals support win,
half-win, push, half-loss, and loss outcomes. 1X2 and BTTS canonicalization are
implemented, but Stage 3 does not create betting recommendations.

Settlement requires both an existing `Result` and an existing `Recommendation`.
Results are separated from pre-match feature snapshots.

