# W2 Staging Runtime Hardening

This runbook covers staging-only recovery for the lightweight VPS. It does not
apply to production.

## Safety Rules

- Do not print or copy `/opt/w2/shared/.env`.
- Do not run database migrations as part of runtime recovery.
- Do not call providers.
- Do not delete Docker volumes.
- Do not use staging seed or demo data.

## Diagnose

```bash
scripts/diagnose_staging_runtime.sh ubuntu@43.155.208.138
```

The diagnostic script is read-only. It collects host load, memory, disk, Docker
disk usage, compose status, container stats, local HTTP probes, and recent
`w2-staging.service` journal lines.

## Recover

Default recovery only restarts the staging stack and probes local health:

```bash
scripts/recover_staging_runtime.sh ubuntu@43.155.208.138
```

If Docker build cache pressure is suspected, prune unused build cache before the
restart:

```bash
scripts/recover_staging_runtime.sh ubuntu@43.155.208.138 --prune-build-cache
```

If dangling images are clearly consuming disk, prune dangling images:

```bash
scripts/recover_staging_runtime.sh ubuntu@43.155.208.138 --prune-images
```

The recovery helper never deletes Docker volumes.

## Watchdog

Deployment installs:

- `w2-staging-watchdog.service`
- `w2-staging-watchdog.timer`

The timer probes local API and web endpoints once per minute. After consecutive
failures, it restarts `w2-staging.service`.

Useful commands:

```bash
sudo systemctl status w2-staging-watchdog.timer --no-pager
sudo journalctl -u w2-staging-watchdog.service --no-pager -n 100
```

## Deploy Stability Probe

By default, `scripts/deploy_stage7h_staging.sh` keeps its original behavior:
it builds and installs the release but does not start the stack.

To start/restart staging and require a post-deploy probe:

```bash
W2_STAGING_START_AFTER_DEPLOY=true \
  scripts/deploy_stage7h_staging.sh ubuntu@43.155.208.138
```

To also prune unused build cache after image build:

```bash
W2_STAGING_PRUNE_BUILD_CACHE=true \
W2_STAGING_START_AFTER_DEPLOY=true \
  scripts/deploy_stage7h_staging.sh ubuntu@43.155.208.138
```
