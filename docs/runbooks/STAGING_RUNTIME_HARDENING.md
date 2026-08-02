# W2 Staging Runtime Hardening

This runbook covers staging-only recovery for the lightweight VPS. It does not
apply to production.

Set `W2_SSH_TARGET` and `W2_DEPLOY_ROOT` from the approved operator
configuration. `W2_SSH_TARGET` must name a non-root key-only account. Do not
commit their resolved values.

## Safety Rules

- Do not print or copy `${W2_DEPLOY_ROOT}/shared/.env`.
- Do not run database migrations as part of runtime recovery.
- Do not call providers.
- Do not delete Docker volumes.
- Do not use staging seed or demo data.

## Diagnose

```bash
scripts/diagnose_staging_runtime.sh "${W2_SSH_TARGET}"
```

The diagnostic script is read-only. It collects host load, memory, disk, Docker
disk usage, compose status, container stats, local HTTP probes, and recent
`w2-staging.service` journal lines.

## Recover

Default recovery only restarts the staging stack and probes local health:

```bash
scripts/recover_staging_runtime.sh "${W2_SSH_TARGET}"
```

If dangling images are clearly consuming disk, prune dangling images:

```bash
scripts/recover_staging_runtime.sh "${W2_SSH_TARGET}" --prune-images
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

Deployment is pull-only and requires immutable Python and Web digest references:

```bash
scripts/deploy_stage7h_staging.sh \
  "${W2_SSH_TARGET}" \
  ghcr.io/qiuyedalao/w2-football-intelligence-engine/python@sha256:<digest> \
  ghcr.io/qiuyedalao/w2-football-intelligence-engine/web@sha256:<digest>
```
