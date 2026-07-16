# W2 Public Edge Acceptance V1

Status: ACTIVE STAGING GOVERNANCE  
Scope: staging observer classification only; it does not change product or model rules.

## Observers

Server diagnostics cover direct API and the staging host's isolated nginx. They prove
the application and inner proxy layers, but do not represent the public SLO.

Public blocking evidence requires at least two independent no-proxy observers. Each
observer records its stable ID, environment, network-provider label, IP protocol,
validated remote IP, connection mode, timings, HTTP version, response bytes and the
sanitized request ID. Proxy samples remain diagnostic and never enter direct-route
percentiles.

The target user route is currently `UNDECLARED`. A single development host must not
be treated as representative of all users. Production review must separately declare
the actual target region.

## Thresholds

- warm keep-alive p95: at most 1.5 seconds;
- next page p95: at most 3 seconds;
- cold p50/p95: at most 4/8 seconds;
- cold maximum: strictly below 12 seconds;
- timeout, 502 and 504: zero.

Thresholds are evaluated per observer, IP protocol and connection mode. Values from
different groups are never averaged, and failed samples are never removed.

## Adjudication

- `GLOBAL_PUBLIC_EDGE_BLOCKED`: two independent observers fail, or the same failed
  layer is reproduced across them.
- `TARGET_ROUTE_BLOCKED`: the declared target route fails, regardless of other routes.
- `ROUTE_SPECIFIC_WARNING`: server diagnostics pass, at least two independent public
  observers pass, and only one non-target route fails without server 5xx, OOM or restart.
- `OBSERVER_COVERAGE_INSUFFICIENT`: fewer than two independent public observers exist,
  or the available evidence cannot satisfy another classification.
- `ALL_BLOCKING_OBSERVERS_PASS`: at least two independent public observers pass and
  none fails.

Only the all-pass and route-specific-warning states permit final staging acceptance.
The warning continues to block production. The machine source of truth is
`config/operations/public_edge_acceptance_v1.json`.

## Layer diagnosis

Evidence is classified as DNS, TCP connect, TLS handshake, outer edge/proxy,
staging nginx, nginx-to-API, API build or response transfer. High client TTFB with
low nginx request time is an outer-route signal; only high upstream response time
reopens API investigation. The current staging endpoint is HTTP IPv4, so DNS, TLS,
IPv6 and `--resolve` are recorded as `NOT_APPLICABLE` where no such layer exists.

## Evidence safety

Runtime reports omit query strings, request/response headers, cookies, authorization
and credentials. Only the sanitized request ID is retained for correlation with nginx
and API timing. No provider request or business write is part of this check.

## Current evidence status · 2026-07-16

PRs #324 and #325 are merged at `main@b303588d6a3a2e7288c46877206f7f5ef31eeb87`.
The first post-merge GitHub-hosted and current-external-host artifacts are
non-qualifying because every retained `request_id` is empty and samples omit their
timestamp. Workflow completion or a preliminary latency result does not override
the evidence schema. The formal classification remains
`OBSERVER_COVERAGE_INSUFFICIENT` until the observer-only collector fix merges and
two independent complete matrices are rerun. Stable staging remains
`c89555b98cbcf2c41ecf999eefce9f5c0a9627f5`; this status does not authorize a
deployment, timeout change, or product/model gate change.

## Evidence V2 gate

Formal evidence must use report schema `w2.public_edge_latency.v2`, sample schema
`w2.public_edge_latency.sample.v2`, and collector version
`w2.public_edge_observer.v2`. The validator rejects V1 reports, missing success
correlation, duplicate request IDs, unproved no-proxy state, IP-family mismatch,
invalid connection facts, unsafe Server-Timing metadata, and indeterminate sample
pairing. Transfer failures remain factual failure samples and fail their observer;
they are not dropped because correlation did not reach the API.
