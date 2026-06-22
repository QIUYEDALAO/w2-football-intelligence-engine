# ADR-0023 Shadow Strategy Engine

Status: Accepted for local/staging shadow operation.

Stage 9A adds a strategy layer that can rank real market opportunities, lock
shadow-only decisions, replay them, and evaluate outcomes later. It does not
publish formal recommendations and does not enable production.

The engine consumes already validated market/model inputs, applies hard gates,
adjusted minimum odds, risk-adjusted EV, grade caps, and correlation policy. With
Gate 4 still pending, A/B raw grades are capped to published grade C and public
states remain limited to NOT_READY, SKIP, and WATCH.

Append-only locks are keyed by fixture, phase, and strategy version. Supersession
and settlement are recorded as events rather than in-place mutation.
