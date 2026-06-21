# ADR-0003: Unified Football Data Model

## Status

Accepted for W2 Stage 3.

## Context

Stage 2 established the engineering foundation. Stage 3 needs a normalized
football data model that can later support ingestion, features, prediction, and
strategy work without importing W1 data or enabling real recommendations.

## Decision

W2 separates pure domain entities, Pydantic schemas, and SQLAlchemy persistence
models. Internal identity uses UUIDs. Provider identities are represented only
through `ProviderEntityMapping`, which stores provider, external ID, source,
confidence, and valid time range.

Business time is explicit and timezone-aware: `event_time`,
`provider_updated_at`, `ingested_at`, `as_of_time`, and `confirmed_at`. Runtime
code rejects naive datetimes and normalizes accepted values to UTC. File mtime is
not a business-time source.

Data layers are explicit: `RAW -> NORMALIZED -> FEATURE ->
PREDICTION_STRATEGY`. Raw payloads are stored through immutable references, not
mutable local JSON identity records.

Stage 3 includes odds canonicalization and settlement primitives for 1X2, Asian
Handicap, Totals, and BTTS, but it does not implement collection, modeling, or
recommendation strategy.

## Consequences

The database can hold normalized football entities and pre-match artifacts while
keeping results and settlements separated from feature snapshots. Gate 0 remains
unable to produce real `RECOMMEND`.

