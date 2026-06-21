# ADR-0004: Data Ingestion Foundation

## Status

Accepted for W2 Stage 4A.

## Context

Stage 3 established the unified football data model. Stage 4A needs an offline
ingestion foundation that can parse API-Football shaped fixtures, preserve raw
payloads, normalize identities and odds, and rehearse Gate 2 without calling any
live provider.

## Decision

Implement provider ports, an API-Football adapter, raw payload store, replay
service, normalizer, quota manager, retry/backoff/circuit breaker, freshness
evaluator, snapshot scheduler, and ingestion persistence tables.

Network access is disabled by default. A live request would require an explicit
`--live` flag and a later checkpoint approval, but Stage 4A scripts and tests do
not execute live calls.

Raw payload references are append-only and SHA256-addressed. Odds observations
are stored per bookmaker and deduplicated by fixture, bookmaker, market,
canonical selection, line, provider update time, and capture time. Pre-match
odds after kickoff are rejected. Closing snapshots are represented as their own
scheduler phase.

## Consequences

Gate 2 can be rehearsed as `PROVISIONAL` with脱敏 fixture payloads through
`RAW -> NORMALIZED -> FEATURE`. No recommendation, model, AI, or live ingestion
capability is enabled.

