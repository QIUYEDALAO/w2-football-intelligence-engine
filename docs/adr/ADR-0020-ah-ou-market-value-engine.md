# ADR-0020 AH/OU Market Value Engine

## Status

Accepted for local implementation. Server runtime projection is pending approval.

## Context

Legacy research snapshots exposed value fields that were adequate for simple 1X2 markets but unsafe
for AH and OU lines with push, half-win, and half-loss outcomes. A decimal price with higher payout
cannot be ranked by `1 / P(win)` when part of the stake can push or settle half.

## Decision

All market valuation flows use a common settlement distribution. Internal odds use Decimal decimal
odds, with explicit Hong Kong conversion for display and user audit. AH and OU fair odds are computed
from full/half win and full/half loss probabilities. Push contributes zero EV.

The cross-market engine evaluates 1X2, AH, OU, and BTTS candidates under one ranking policy. Gate 4
pending caps published grades at C and keeps `formal_recommendation=false` and `candidate=false`.

## Consequences

D/X cards remain valid outputs and must not be reworded as positive betting advice. Old matchday
outputs are superseded append-only rather than overwritten.
