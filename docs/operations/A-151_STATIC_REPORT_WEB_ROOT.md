# A-151 Static Report Web Root

## Status

Planned. This is an immediate follow-up to the July 4 matchday dashboard deployment risk.

## Problem

The current static daily report can be generated correctly, but the last deployment required copying the generated HTML into the running `web` container. That is a runtime artifact, not a deployable contract. If the container is recreated, the image can revert to the bundled React shell and the public dashboard can silently lose the accepted static report surface.

This is the same failure class as the earlier dashboard rollback: manual runtime state survived only until the next container rebuild.

## Goal

Make the static daily report the formal web root in the deployment flow.

Acceptable implementation paths:

- Serve `runtime/reports` directly from nginx, with the current football-day HTML as `index.html`.
- Or inject the generated daily report into the web image during build/deploy as an explicit artifact.

Either path must remove the manual `docker cp` step.

## Contract

- Public `/` serves the accepted static daily report surface.
- The report includes the current renderer watermark, currently `w2.html_dashboard.v5`.
- Container rebuilds must preserve the accepted public report surface.
- The deploy flow must fail or alert if the public page falls back to the React shell.
- `runtime/reports` remains runtime data and must not be committed to git.
- This does not change FORMAL gates, EV thresholds, AH selector logic, settlement, lock capture, or provider refresh policy.

## Required Deployment Guard

Until A-151 is implemented, every web container recreate or rebuild must be followed immediately by:

```bash
curl -fsS http://43.155.208.138/ | grep -c 'w2.html_dashboard.v5'
curl -fsS http://43.155.208.138/ | grep -c '命中率\\|胜率\\|ROI\\|必中\\|必胜\\|稳赢\\|稳赚\\|可买\\|庄家开错\\|跟庄\\|照这个买\\|方向未识别\\|正式推荐字段不完整'
curl -fsS http://43.155.208.138/v1/version
```

Acceptance:

- renderer watermark count is at least `2`
- forbidden-term count is `0`
- API SHA matches the deployed main SHA

If any check fails, the deployment is not accepted and the static page must be regenerated from the same authoritative dashboard payload before user-facing use.

## Relationship To Future Cleanup

A-151 is a prerequisite for the offseason web cleanup track that removes the old SPA shell from the production path. Until A-151 lands, the old SPA can still reappear after image rebuilds.
