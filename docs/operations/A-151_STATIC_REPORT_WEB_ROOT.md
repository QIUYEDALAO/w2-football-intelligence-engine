# A-151 Static Report Web Root

## Status

Implemented. This is the web-root contract for the accepted static daily report.

## Problem

The current static daily report can be generated correctly, but the last deployment required copying the generated HTML into the running `web` container. That is a runtime artifact, not a deployable contract. If the container is recreated, the image can revert to the bundled React shell and the public dashboard can silently lose the accepted static report surface.

This is the same failure class as the earlier dashboard rollback: manual runtime state survived only until the next container rebuild.

## Implementation

The web container keeps the bundled React shell as a boot fallback, but nginx
serves `/static-report/index.html` before the image `index.html`. Staging compose
mounts:

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

Container rebuilds preserve the accepted public report as long as the shared
runtime directory remains mounted. A missing static report is still visible via
the watermark guard because nginx falls back to the React shell only as a boot
fallback, not as an acceptable release state.

## Contract

- Public `/` serves the accepted static daily report surface.
- The report includes the current renderer watermark, currently `w2.html_dashboard.v6`.
- Container rebuilds must preserve the accepted public report surface.
- The deploy flow must fail or alert if the public page falls back to the React shell.
- `runtime/reports` remains runtime data and must not be committed to git.
- This does not change FORMAL gates, EV thresholds, AH selector logic, settlement, lock capture, or provider refresh policy.

## Required Deployment Guard

Every deploy that touches `web` must publish the current static report and then
run:

```bash
uv run --python 3.12 python scripts/publish_w2_static_report.py \
  --base-url http://43.155.208.138 \
  --runtime-root runtime
curl -fsS http://43.155.208.138/ | grep -c 'w2.html_dashboard.v6'
curl -fsS http://43.155.208.138/ | grep -c '命中率\\|胜率\\|ROI\\|必中\\|必胜\\|稳赢\\|稳赚\\|可买\\|庄家开错\\|跟庄\\|照这个买\\|方向未识别\\|正式推荐字段不完整'
curl -fsS http://43.155.208.138/v1/version
```

Acceptance:

- renderer watermark count is at least `2`
- forbidden-term count is `0`
- API SHA matches the deployed main SHA

If any check fails, the deployment is not accepted and the static page must be regenerated from the same authoritative dashboard payload before user-facing use.

## Relationship To Future Cleanup

A-151 is a prerequisite for the offseason web cleanup track that removes the old
SPA shell from the production path. Until that cleanup lands, the SPA remains a
container boot fallback only; the public release contract is the static report
under `runtime/reports/public/index.html`.
