# ADR-0013: Read-only API and Operations Console

## Status

Accepted for Stage 10A.

## Context

W2 has live forward holdout operations, model and market reports, replay summaries, and provider
quota artifacts. Operators need a read-only way to inspect these states without enabling candidate
or recommendation workflows.

## Decision

Stage 10A adds two API layers:

- public read API under `/v1`
- operations read API under `/ops`

The APIs use DTO/presenter models and read-model services. Domain models do not depend on frontend
display fields. Operations endpoints are read-only and disabled in production. The React console
consumes these read APIs and displays fixtures, captured market snapshots, independent model
probabilities, data health, provider/quota status, task/alert state, forward holdout progress, and
backtest/Gate state.

No route is added for recommendations, candidates, DeepSeek, rerun, override, edit, delete, approve,
or publish.

## Consequences

Operators can inspect W2 state in local/staging. The system still cannot generate or publish formal
recommendations. Gate 4 remains provisional and Stage 9 remains blocked.
