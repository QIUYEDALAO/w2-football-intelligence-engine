# ADR-0014: Observability, Security, and Recovery

## Status

Accepted for Stage 11A local/staging foundation.

## Decision

W2 adds local/staging abstractions for metrics, structured logs, tracing correlation, internal
alerts, drift diagnostics, RBAC policy scaffolding, security auditing, and backup/restore drills.

Production deployment, external alerting, DeepSeek, candidate output, and recommendation output
remain disabled.

## Consequences

Operators can inspect local/staging health and recovery readiness without changing model, Gate, or
recommendation state. Thresholds that need real calibration are explicitly marked
`CALIBRATION_REQUIRED`.
