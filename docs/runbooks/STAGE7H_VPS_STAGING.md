# W2 Stage7H – VPS Staging Runbook

**Task**: W2-STAGE7H-001-BUNDLE  
**Server**: 43.155.208.138 (首尔 VPS, Tencent Cloud)  
**Spec**: 4 vCPU / 8 GiB / 120 GiB SSD  
**OS**: Ubuntu 24.04 LTS

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Host: 43.155.208.138 (public)                  │
│  UFW: inactive  │  SSH: :22                     │
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
│  /opt/w2/                                        │
│    ├── current → releases/<SHA>                  │
│    ├── releases/<SHA>/                           │
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
sudo docker compose -f /opt/w2/current/infra/compose/compose.staging.yml ps

# View logs
sudo journalctl -u w2-staging.service -f
sudo docker compose -f /opt/w2/current/infra/compose/compose.staging.yml logs --tail=100 -f api
sudo docker compose -f /opt/w2/current/infra/compose/compose.staging.yml logs --tail=100 -f worker
sudo docker compose -f /opt/w2/current/infra/compose/compose.staging.yml logs --tail=100 -f scheduler
```

## Deployment

```bash
# From local workspace
bash scripts/deploy_stage7h_staging.sh ubuntu@43.155.208.138
```

The deployment script assumes `/opt/w2/shared/.env` has already been provisioned
with mode `600`. It must not print or rewrite sensitive values.

## Static Daily Report Guard

Until A-151 makes the static daily report a first-class web root artifact, any
web container recreate or rebuild can fall back to the bundled React shell. After
every deploy that touches `web`, run these checks before accepting the release:

```bash
curl -fsS http://43.155.208.138/ | grep -c 'w2.html_dashboard.v5'
curl -fsS http://43.155.208.138/ | grep -c '命中率\|胜率\|ROI\|必中\|必胜\|稳赢\|稳赚\|可买\|庄家开错\|跟庄\|照这个买\|方向未识别\|正式推荐字段不完整'
curl -fsS http://43.155.208.138/v1/version
```

Acceptance:

- renderer watermark count is at least `2`
- forbidden-term count is `0`
- API SHA matches the deployed main SHA

If the watermark check fails, the public dashboard has likely reverted to the
React shell. Regenerate the static report from the authoritative dashboard
payload and do not accept the deploy until the checks pass.

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
sudo docker compose -f /opt/w2/current/infra/compose/compose.staging.yml ps
sudo docker stats --no-stream

# Full check
python3 /opt/w2/current/scripts/check_w2_stage7h.py
```

## Rollback

```bash
# Stop stack
sudo systemctl stop w2-staging.service

# Point current to previous release
ls /opt/w2/releases/
ln -sfn /opt/w2/releases/<PREVIOUS_SHA> /opt/w2/current

# Restart
sudo systemctl start w2-staging.service
```

Rollback does not:
- Delete new release
- Delete volumes
- Roll back lock/result append-only data

## Security Notes

- API key stored in `/opt/w2/shared/.env` (chmod 600)
- PostgreSQL credential auto-generated (32-byte hex)
- No Docker group membership for `ubuntu`
- All business ports bound to 127.0.0.1 only
- SSH is the only public port
- No cloud security group modifications
