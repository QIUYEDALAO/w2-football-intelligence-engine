# A-151 Static Report Web Root

## Status

Superseded by S14/S15. Static daily reports remain mounted and archived, but the
public web root is now the React boss-view dashboard.

## Problem

The current static daily report can be generated correctly, but the last deployment required copying the generated HTML into the running `web` container. That is a runtime artifact, not a deployable contract. If the container is recreated, the image can revert to the bundled React shell and the public dashboard can silently lose the accepted static report surface.

This is the same failure class as the earlier dashboard rollback: manual runtime state survived only until the next container rebuild.

## Implementation

The web container serves the bundled React boss-view shell at `/` and
`/index.html`. Staging compose still mounts:

```text
runtime/reports/public -> /usr/share/nginx/html/static-report:ro
```

The accepted daily report is published with:

```bash
uv run --python 3.12 python scripts/publish_w2_static_report.py \
  --base-url http://43.155.208.138 \
  --runtime-root runtime
```

The publisher fetches the authoritative `today` dashboard payload, renders the
HTML report, validates the renderer watermark and forbidden-term guard, then
atomically writes:

- `runtime/reports/w2_day_<football_day>.html`
- `runtime/reports/public/w2_day_<football_day>.html`
- `runtime/reports/public/index.html`

Container rebuilds preserve archived static reports as long as the shared runtime
directory remains mounted. Static report availability is no longer the web-root
acceptance criterion.

## Contract

- Public `/` serves the React boss-view dashboard.
- Static reports remain available under `/static-report/`.
- Container rebuilds must preserve the static report archive mount.
- `runtime/reports` remains runtime data and must not be committed to git.
- This does not change FORMAL gates, EV thresholds, AH selector logic, settlement, lock capture, or provider refresh policy.

## Required Deployment Guard

Every deploy that touches `web` must confirm the React boss-view is the root and
the static report watermark is not served from `/`:

```bash
curl -fsS http://43.155.208.138/ | grep -c '<div id="root">'
curl -fsS http://43.155.208.138/ | grep -c 'w2.html_dashboard.v6'
curl -fsS http://43.155.208.138/v1/version
curl -fsS http://43.155.208.138/meta.json
```

Acceptance:

- React root count is at least `1`
- renderer watermark count on `/` is `0`
- API SHA and Web SHA match the deployed main SHA

If any check fails, the deployment is not accepted.

## Relationship To Future Cleanup

A-151 is preserved as history for the static report archive mount. S14/S15 moves
the public product surface back to the React boss-view dashboard.
