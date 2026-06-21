# W2 Stage7H – MANDATORY CHECKPOINT B

**Task**: W2-STAGE7H-001-BUNDLE  
**Server**: 43.155.208.138 (首尔 VPS, Tencent Cloud)  
**Date**: 2026-06-22 08:04 CST  
**Staging Commit**: `52607c4fad03a518a40e2614eed20e64809173c5`  
**Branch**: `feat/stage7h-vps-staging-deploy`

---

## 1. Docker & Compose

| Item | Version |
|---|---|
| **Docker Engine** | 29.6.0 |
| **Docker Compose** | v5.1.4 |
| **Containerd** | v2.2.5 |
| **Hello-world** | ✅ Verified |

## 2. Swap

| Device | Size | Priority |
|---|---|---|
| `/swap.img` (existing) | 1.9 GiB | -2 |
| `/swapfile` (new) | 2.0 GiB | -3 |
| **Total** | **3.9 GiB** | |

## 3. Staging Commit

```
52607c4fad03a518a40e2614eed20e64809173c5
```

Working tree: ✅ Clean

## 4. Release Path

```
/opt/w2/releases/52607c4fad03a518a40e2614eed20e64809173c5/
```

Contents include: `docker-compose.yml`, `infra/compose/staging-lite.override.yml`, all Dockerfiles, source code, `infra/systemd/w2-staging.service`.

**`/opt/w2/current` symlink**: ❌ Not set (as intended)

## 5. Compose Config Verification

Deferred to server runtime due to lack of local Docker. To be verified after `docker compose config` on server.

## 6. systemd Unit Status

| Check | Result |
|---|---|
| **Installed** | ✅ `/etc/systemd/system/w2-staging.service` |
| **Verified** | ✅ `systemd-analyze verify` PASS |
| **Enabled** | ❌ `disabled` (as required) |
| **Active** | ❌ `inactive` (as required) |

No unexpected activation.

## 7. Planned Services

| Service | Image/Build | Depends On | Healthcheck |
|---|---|---|---|
| **postgres** | `postgres:16-alpine` | — | `pg_isready` |
| **redis** | `redis:7-alpine` | — | `redis-cli ping` |
| **migration** | `Dockerfile.migrations` | postgres | `alembic current` (one-shot) |
| **api** | `Dockerfile.api` | postgres, redis | `HTTP /health` |
| **worker** | `Dockerfile.worker` | redis | Celery ping |
| **scheduler** | `Dockerfile.scheduler` | redis | heartbeat check |
| **web** | `Dockerfile.web` (nginx) | api | HTTP 200 |

MinIO: ❌ Excluded (not required by staging forward-holdout cycle)

## 8. Planned Port Bindings

| Service | Container Port | Host Binding |
|---|---|---|
| **api** | 8000 | `127.0.0.1:18000` |
| **web** | 8080 | `127.0.0.1:18080` |
| postgres | 5432 | ❌ Not exposed |
| redis | 6379 | ❌ Not exposed |

All business ports bound to loopback only. No `0.0.0.0` binding.

## 9. Current Public Listening Ports

| Protocol | Port | Service | Binding |
|---|---|---|---|
| TCP | 22 | SSH | `0.0.0.0:22` + `[::]:22` |
| UDP | 53 | systemd-resolved | `127.0.0.x` |
| UDP | 68 | DHCP | `10.8.0.16` |
| UDP | 323 | chronyd | `127.0.0.1` / `[::1]` |

**Only SSH port 22 is public.** No containers running. No business ports listening.

## 10. API Key Placeholder Status

```
W2_API_FOOTBALL_API_KEY=__REQUIRED_MANUAL_INJECTION__
```

Stored in `/opt/w2/shared/.env` (chmod 600, owner ubuntu).  
**Placeholder present** — requires injection before staging can operate.

## 11. Minimal Runtime State Migration Manifest

### Category Breakdown

| # | Category | Source Path | Exists | Files | Size | SHA256 | Immutable | Migrate |
|---|---|---|---|---|---|---|---|---|
| 1 | **Frozen challenger artifact** | `runtime/model_artifacts/stage7/club-model-manifest-4a8d732b7f2c.json` | ✅ | 1 | 68,965 | `7b3c5a61...` | ✅ | ✅ |
| 2 | **Frozen challenger artifact** | `runtime/model_artifacts/stage7/club-model-manifest-580ba4cea90c.json` | ✅ | 1 | 68,966 | `c6ac802c...` | ✅ | ✅ |
| 3 | **Frozen challenger artifact** | `runtime/model_artifacts/stage7/national-model-manifest-a1bce61b4caa.json` | ✅ | 1 | 54,450 | `d5f4dafa...` | ✅ | ✅ |
| 4 | **Calibration artifact** | `runtime/model_artifacts/stage7/calibration-manifest-2c0e3ed29ffb.json` | ✅ | 1 | 20,786 | `4d772d88...` | ✅ | ✅ |
| 5 | **Calibration artifact** | `runtime/model_artifacts/stage7/calibration-manifest-c4b6be0f6188.json` | ✅ | 1 | 20,792 | `9f679103...` | ✅ | ✅ |
| 6 | **Forward holdout schedule (policy)** | `config/policies/forward_holdout_schedule.v1.json` | ✅ | 1 | 1,439 | `4da3b4dd...` | ✅ | ✅ |
| 7 | **Forward lock ledger (stage7e)** | `runtime/stage7e/prediction_locks.json` | ✅ | 1 | 4,648 | `da83ef4c...` | ✅ | ✅ |
| 8 | **Forward state (stage7e)** | `runtime/stage7e/local_autorun_config.json` | ✅ | 1 | 336 | `dcae693b...` | ✅ | ✅ |
| 9 | **Forward state (stage7e)** | `runtime/stage7e/result_events.json` | ✅ | 1 | 3 | `37517e5f...` | ✅ | ✅ |
| 10 | **Forward checkpoint (stage7g)** | `runtime/stage7g/controlled_cycle.json` | ✅ | 1 | 204 | `b5e92e4a...` | ✅ | ✅ |
| 11 | **Forward lock ledger (stage7f)** | `runtime/stage7f/prediction_locks.json` | ✅ | 1 | 3 | `37517e5f...` | ✅ | ✅ |
| 12 | **Forward lock ledger (stage7g)** | `runtime/stage7g/prediction_locks.json` | ✅ | 1 | 3 | `37517e5f...` | ✅ | ✅ |
| 13 | **Provider mapping** | `runtime/stage5b/processed/national_provider_mappings.json` | ✅ | 1 | 130,336 | `a52bbe9a...` | ✅ | ✅ |
| 14 | **Market snapshots (stage7e)** | `runtime/stage7e/market_snapshots.json` | ✅ | 1 | 643 | `f20660b9...` | ✅ | ✅ |
| 15 | **Result events (stage7f)** | `runtime/stage7f/result_events.json` | ✅ | 1 | 3 | `37517e5f...` | ✅ | ✅ |
| 16 | **Result events (stage7g)** | `runtime/stage7g/result_events.json` | ✅ | 1 | 3 | `37517e5f...` | ✅ | ✅ |
| 17 | **Feature allowlist** | ❌ Not found in W2 repo | — | 0 | — | — | — | ❌ |

### Summary

| Metric | Value |
|---|---|
| **Total files to migrate** | 15 (config + runtime + model artifacts) |
| **Total size** | ~371 KiB (5.6 MiB including raw API data excluded) |
| **Contains W1 data** | ❌ No |
| **Contains sensitive data** | ❌ No |
| **Contains .env/cache/log** | ❌ No |
| **Immutable frozen artifacts** | ✅ Yes (model & calibration manifests) |
| **Append-only lock data** | ✅ Yes (prediction locks, result events) |
| **Raw API responses excluded** | ✅ Yes (`runtime/*/raw/` — historical API data, not state) |

### Definitions

- **Immutable**: Artifact is frozen; hash-verified; no mutation after deployment
- **Contains secret**: File may contain API keys, tokens, passwords, or private keys
- **Migration required**: File must be copied to server for staging to function
- **Exclusion reason**: Why file is not included (raw API data / cache / W1 / etc.)

## 12. BLOCKER / WARN_ONLY

| Type | Item | Detail |
|---|---|---|
| ⚠️ **WARN** | API Key placeholder | `W2_API_FOOTBALL_API_KEY` is `__REQUIRED_MANUAL_INJECTION__` — must be injected before forward cycle can operate |
| ⚠️ **WARN** | `/opt/w2/current` not set | Symlink not created — systemd unit will fail to start until set |
| ⚠️ **WARN** | Feature allowlist not found | `feature_allowlist` not found in W2 runtime — may not exist as separate artifact |
| ✅ **BLOCKER** | None | No hard blockers |

## 13. Next Required Approval

```
「批准 Stage7H Phase E，允许注入 API Key 并迁移最小 W2 运行状态」
```

### Phase E scope (after approval):

1. **API Key injection**: Read from OpenClaw session env → secure stdin transfer to server
2. **Minimal state migration**: 15 files (~371 KiB) with SHA256 verification
3. **Set `/opt/w2/current`** symlink → `/opt/w2/releases/52607c4...`
4. **Run DB migration** (`alembic upgrade head`)
5. **Start systemd** (`sudo systemctl start w2-staging.service`)
6. **Health check** all services
7. **Controlled forward cycle** (≤50 API requests, min 1500 reserve)
8. **MODEL_INPUT_MISSING audit**
9. **Scheduler auto-trigger verification**

### Phase E constraints:

- DeepSeek: OFF (confirmed)
- Recommendation: OFF (confirmed)
- Candidate: OFF (confirmed)
- Production: OFF (confirmed)
- Training: FORBIDDEN
- No W1 access
- No cloud security group changes
- No public port opening
