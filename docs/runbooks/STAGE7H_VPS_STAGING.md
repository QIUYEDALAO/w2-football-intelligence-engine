# W2 Stage7H – VPS Staging Runbook

**Task**: W2-STAGE7H-001-BUNDLE  
**Server**: `${W2_VPS_HOST}` (approved runtime configuration)
**Spec**: runtime-provided
**OS**: Ubuntu 24.04 LTS

---

## Runtime infrastructure inputs

Set `W2_VPS_HOST`, `W2_SSH_TARGET`, and `W2_DEPLOY_ROOT` from the approved
operator configuration. `W2_SSH_TARGET` must name a non-root key-only account.
Do not commit their resolved values.

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Host: ${W2_VPS_HOST} (runtime-injected)         │
│  Host firewall: default-deny ingress             │
│                                                  │
│  systemd: w2-staging.service                     │
│  ┌───────────────────────────────────────┐       │
│  │  Docker Compose (staging profile)     │       │
│  │                                       │       │
│  │  postgres:5432 ←──── migration        │       │
│  │     ↓                                  │       │
│  │  api:8000   → 127.0.0.1:18000          │       │
│  │  web:8080   → 127.0.0.1:18080          │       │
│  │  worker (celery, concurrency=1)        │       │
│  │  scheduler (heartbeat)                 │       │
│  │  redis:6379                            │       │
│  └───────────────────────────────────────┘       │
│                                                  │
│  ${W2_DEPLOY_ROOT}/                                        │
│    ├── deploy/                                   │
│    │    ├── compose.staging.yml                  │
│    │    ├── watch_staging_runtime.sh             │
│    │    └── check_w2_stage7h.py                  │
│    └── shared/                                   │
│         ├── .env (chmod 600)                     │
│         ├── state/                               │
│         ├── data/                                │
│         ├── logs/                                │
│         ├── backups/                             │
│         └── runtime/                             │
└─────────────────────────────────────────────────┘
```

## Port Mapping

| Service | Container Port | Host Binding |
|---|---|---|
| API | 8000 | `127.0.0.1:18000` (enforced) |
| Web | 8080 | `127.0.0.1:18080` (enforced) |
| PostgreSQL | 5432 | Not exposed |
| Redis | 6379 | Not exposed |

**No 0.0.0.0 business ports.** Compose is standalone `compose.staging.yml` — does not inherit base docker-compose.yml port definitions.

## Resource Budget

| Service | Estimate |
|---|---|
| postgres | ~1.25 GiB |
| redis | ~256 MiB |
| api | ~768 MiB |
| worker (concurrency=1) | ~1.5 GiB |
| scheduler | ~512 MiB |
| web | ~256 MiB |
| System reserve | ~2 GiB |
| **Total** | **~6.5 GiB / 8 GiB** |

## Service Control

```bash
# Start full stack
sudo systemctl start w2-staging.service

# Stop full stack
sudo systemctl stop w2-staging.service

# Restart
sudo systemctl restart w2-staging.service

# Status
sudo systemctl status w2-staging.service --no-pager
sudo docker compose -f "${W2_DEPLOY_ROOT}/deploy/compose.staging.yml" ps

# View logs
sudo journalctl -u w2-staging.service -f
sudo docker compose -f "${W2_DEPLOY_ROOT}/deploy/compose.staging.yml" logs --tail=100 -f api
sudo docker compose -f "${W2_DEPLOY_ROOT}/deploy/compose.staging.yml" logs --tail=100 -f worker
sudo docker compose -f "${W2_DEPLOY_ROOT}/deploy/compose.staging.yml" logs --tail=100 -f scheduler
```

## Deployment

```bash
# From local workspace
bash scripts/deploy_stage7h_staging.sh \
  "${W2_SSH_TARGET}" \
  ghcr.io/qiuyedalao/w2-football-intelligence-engine/python@sha256:<digest> \
  ghcr.io/qiuyedalao/w2-football-intelligence-engine/web@sha256:<digest>
```

The deployment script assumes `${W2_DEPLOY_ROOT}/shared/.env` has already been provisioned
with mode `600`. It must not print or rewrite sensitive values.

## Dashboard Web Root

S14 makes the React boss-view dashboard the public web root. The web container
still mounts `runtime/reports/public` at `/usr/share/nginx/html/static-report`
for archived static daily reports, but nginx serves the bundled React shell at
`/` and `/index.html`.

After every deploy that touches `web`, run these checks before accepting the
release:

```bash
ssh -N -L 18080:127.0.0.1:18080 <staging-host-alias>
curl -fsS http://127.0.0.1:18080/ | grep -c '<div id="root">'
curl -fsS http://127.0.0.1:18080/v1/version
curl -fsS http://127.0.0.1:18080/meta.json
```

Acceptance:

- React root count is at least `1`
- static renderer watermark count on `/` is `0`
- API SHA and Web SHA match the deployed main SHA

The archived static report remains available under `/static-report/` when
`runtime/reports/public/index.html` exists. Do not repair web-root behavior with
a manual `docker cp` into the running web container; the accepted surface is the
built React app plus the `/static-report/` archive mount.

## Compose Preflight

Do not save or print expanded `docker compose config` output because it can
include interpolated sensitive values. Use the structural port checker instead:

```bash
uv run python scripts/check_compose_staging_ports.py
```

The checker reads only `infra/compose/compose.staging.yml` and validates
`services.*.ports`. It does not parse or print `environment`.

## Health Checks (on server)

```bash
# API
curl -fsS http://127.0.0.1:18000/health
curl -fsS http://127.0.0.1:18000/ready
curl -fsS http://127.0.0.1:18000/metrics

# Web
curl -I http://127.0.0.1:18080/

# Docker
sudo docker compose -f "${W2_DEPLOY_ROOT}/current/infra/compose/compose.staging.yml" ps
sudo docker stats --no-stream

# Full check
python3 "${W2_DEPLOY_ROOT}/deploy/check_w2_stage7h.py"
```

## Rollback

```bash
# Stop stack
sudo systemctl stop w2-staging.service

# Point current to previous release
ls "${W2_DEPLOY_ROOT}/releases/"
ln -sfn "${W2_DEPLOY_ROOT}/releases/<PREVIOUS_SHA>" "${W2_DEPLOY_ROOT}/current"

# Restart
sudo systemctl start w2-staging.service
```

Rollback does not:
- Delete new release
- Delete volumes
- Roll back lock/result append-only data

## Security Notes

- API key stored in `${W2_DEPLOY_ROOT}/shared/.env` (chmod 600)
- PostgreSQL credential auto-generated (32-byte hex)
- No Docker group membership for `ubuntu`
- All business ports bound to 127.0.0.1 only
- SSH is the only public port
- No cloud security group modifications
