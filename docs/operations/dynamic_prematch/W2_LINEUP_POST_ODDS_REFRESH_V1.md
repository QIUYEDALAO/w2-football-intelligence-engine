# W2 Lineup Post-Odds Refresh V1

`LINEUP_CONFIRMED` invalidates the previous lineup/model input and places the fixture in `LINEUP_READY_MARKET_REFRESH_PENDING`. EV is not recalculated until a complete exact quote captured at or after lineup confirmation is available.

Contract result: `LINEUP_POST_MARKET_REFRESH_PASS`. Live canary: `WAITING_FOR_REAL_LINEUP_WINDOW`; no synthetic lineup is reported as live evidence.
