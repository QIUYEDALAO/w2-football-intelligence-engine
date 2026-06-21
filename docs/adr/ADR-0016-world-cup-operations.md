# ADR-0016: World Cup Operations Profile

Status: Accepted for Stage 13A.

## Context

W2 needs a competition operations profile before any tournament period. The
profile must be generic enough for future tournament competitions and specific
enough to dry-run World Cup 2026 local/staging readiness.

## Decision

Stage 13A adds a configuration-driven tournament operations model. Python and
TypeScript do not hardcode World Cup teams, fixtures, groups with teams, or
fixture IDs. The World Cup 2026 profile lives in versioned JSON configuration.
It defines provider mapping, season, host context, neutral-site policy, stages,
groups, knockout rounds, 90-minute result semantics, collection phases, lineup
window, settlement timing, model/calibration references, and freeze policy.

The strategy version is fixed to `NOT_AVAILABLE_GATE4`. Match importance context
is structured but marked `EXPLANATORY_ONLY_UNVALIDATED` and is not available as a
model feature.

## Consequences

Local/staging can inspect readiness and generate offline phase plans from
existing Stage5B local fixture data. Production deployment, live Shadow runtime,
DeepSeek, CANDIDATE, and RECOMMEND remain disabled.
