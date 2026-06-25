# ADR-0019 Dashboard Live Read Model

## Status

Accepted for local implementation. Staging deployment remains pending approval.

## Context

The staging console rendered an empty shell because the browser called API paths directly from the
web origin while the API service was exposed on a separate localhost port. The API also depended on
older runtime/report files for fixture data, so verified matchday snapshots were not visible through
the read API.

## Decision

The web console uses same-origin `/api/v1/...` and `/api/ops/...` paths. The web container owns an
nginx proxy that maps `/api/` to the API service and strips the prefix by using `proxy_pass
http://api:8000/`.

Verified append-only matchday snapshots are projected into existing `read_model_checkpoint` rows.
The projector validates fixture identity, UTC timing, append-only manifests, artifact hashes,
WATCH/SKIP decisions, and disabled formal recommendation flags before writing display data.

## Consequences

The dashboard can show real read-model data without browser API host hardcoding and without frontend
access to runtime JSON. Staging still requires an explicit deploy approval before the new image and
projector are run on the server.
