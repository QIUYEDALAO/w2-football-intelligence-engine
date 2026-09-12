"""W2 quant-research bounded context.

This package is the only place new quant code may live on the production side
(see `AGENTS.md` and `QUANT_AGENTS.md`). It reaches the operational system
through explicit read-only ports and never the other way round: nothing under
`src/w2/prematch/`, `src/w2/strategy/`, the Scheduler, the Provider allowlist
or `RecommendationDecisionV4` imports this package.

`forward_factor_recording` is the one module here that the production
dynamic-evaluation path reaches, and it is reached by injection: the
composition root that materialises an evaluation hands the recorder in, so a
read-only caller (the public API, the Dashboard) holds no recorder and writes
no factor observation.
"""
