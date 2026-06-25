# W2 Cross-Market Value V1

The market value engine ranks real executable prices across 1X2, AH, OU, and BTTS. Each candidate
includes executable odds, Hong Kong water, model fair odds, settlement distribution, raw EV,
uncertainty margin, risk-adjusted EV, data quality, market quality, grade, and action.

A fixture always gets a card. If no candidate has positive risk-adjusted EV, the card is grade D and
action SKIP/NO_BET. If data or mapping is blocked, the card is grade X. Gate 4 pending prevents A/B
publication and caps displayed research grade at C.

Highly correlated outputs are not promoted together. A primary direction and one lower-correlation
secondary direction may be shown for research, but no CANDIDATE or RECOMMEND is emitted.
