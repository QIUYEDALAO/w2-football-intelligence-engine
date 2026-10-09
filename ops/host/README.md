# Host operations

What has to exist on the machine but is not part of the application, kept
here so a new host can be brought up without reconstructing it from memory.

| File | Installs to | Purpose |
|---|---|---|
| `w2-backup` | `/usr/local/bin/` | Database dump with retention, every six hours |
| `w2-backup.service` / `.timer` | `/etc/systemd/system/` | Runs the backup |
| `w2-disk-guard` | `/usr/local/bin/` | Hourly disk, inode and backup-age check |
| `w2-disk-guard.service` / `.timer` | `/etc/systemd/system/` | Runs the guard |
| `w2-registry-gc` | `/usr/local/bin/` | Registry retention and collection, weekly |
| `w2-xg-materialize` | `/usr/local/bin/` | Rolling xG snapshot recompute, every six hours |
| `w2-xg-materialize.service` / `.timer` | `/etc/systemd/system/` | Runs the recompute |
| `w2-xg-ingest-guard` | `/usr/local/bin/` | Read-only numeric saved-raw to `team_xg_match` loss alarm |
| `w2-xg-ingest-guard.service` / `.timer` | `/etc/systemd/system/` | Runs the guard hourly |
| `w2-xg-refresh` | `/usr/local/bin/` | Fetch xG for recently finished matches, twice daily |
| `w2-xg-refresh.service` / `.timer` | `/etc/systemd/system/` | Runs the fetch |
| `w2-postmatch-guard` | `/usr/local/bin/` | POSTMATCH_RESULT stall guard (overdue >2h still DUE = 0) |
| `w2-postmatch-guard.service` / `.timer` | `/etc/systemd/system/` | Runs the guard every 30 minutes |
| `w2-totals-calibration` | `/opt/w2/deploy/` | Totals calibration snapshot, read-only |
| `w2-registry-gc.service` / `.timer` | `/etc/systemd/system/` | Runs the collection |
| `w2-release` | Mac 本机（不装到 VPS） | 一条命令完成发布：前置检查 → 备份 → 构建 → 部署 → 回读 → 推送 → 轮转 → 回执骨架 |
| `w2-release-preflight` | `/usr/local/bin/` | Space, base image and layer count before a release |
| `w2-release-sync-preflight` | `/opt/w2/deploy/` | Block mixed Python/Web image revisions before a release |
| `w2-staging-release-sync.conf` | `/etc/systemd/system/w2-staging.service.d/` | Run release-sync before stack activation |
| `registry-config.yml` | `/opt/w2/deploy/registry/` | Registry with manifest deletion enabled |
| `journald-w2-retention.conf` | `/etc/systemd/journald.conf.d/` | Journal size cap |
| `w2-update-v3-monitor` | Mac 本机（repo 侧，由发布 5d 步调用） | Sync the read-only monitor to `/opt/w2/deploy/v3-monitor/` behind the F3 gate |
| `w2-update-xg-scripts` | Mac 本机（repo 侧，由发布 5e 步调用） | Sync `w2-xg-materialize` / `w2-xg-refresh` to `/usr/local/bin/` behind the F3 gate |
| `w2-xg-backfill-window` | `/usr/local/bin/` | Backfill xG only inside prematch guard gaps, never bypassing the gate |

`w2-xg-ingest-guard` is deliberately narrower than xG freshness monitoring. It
alarms only when saved raw contains numeric xG for both teams but
`team_xg_match` does not contain exactly two non-null team rows. Provider-null,
not-yet-published, and disabled-competition fixtures do not trigger this guard.
The query is read-only and discovers the enabled set from
`league_season.payload.enabled` at runtime.

🔴 **部署状态不一致（2026-10-10 实测，登记待处置）**：上表声称
`w2-xg-ingest-guard` 装在 `/usr/local/bin/`、由 hourly timer 驱动，但 VPS 上
**脚本实体与 timer 均不存在**（`systemctl list-timers --all` 无该项，
`find / -name 'w2-xg-ingest-guard*'` 无结果）。该守卫恰好覆盖
「saved raw 已有数值 xG、`team_xg_match` 却没有两行非空」这一失效模式——
即 E1 发现② 中「存量 raw 物化 0 行」的形态。补部署或显式废弃需决策。

## Why each exists

**xG refresh.** `w2-xg-materialize` recomputes snapshots from evidence already
stored; until now nothing fetched the evidence itself. `W2_XG_BACKFILL_ENABLED`
is false by design so one run cannot sweep every competition at once, which
left no path for keeping xG current: `team_xg_match` sat at 18,696 while 144
finished matches carried a result and no xG, and the rolling five-match window
kept reaching further back until the restarted European leagues priced August
fixtures off May evidence. `w2-xg-refresh` walks the database-enabled current seasons one competition
per call, which is the shape that guardrail permits, and defers itself when a
prematch checkpoint is within 45 minutes because a checkpoint window that
closes unserved cannot be reopened.

Its health metric is coverage of matches finished in the last 30 days, not the
`stale_teams` counter the materializer reports. That counter compares snapshots
against stored matches and so read zero throughout the outage, both sides being
equally old. Recency alone is not enough either: one fetched match makes a
competition look current while thirty of its neighbours carry no xG. Chinese
Super League and Allsvenskan sit at 15% and 25% coverage while their newest
match is days old, because the Provider returns statistics for them with
`expected_goals` null.


**Disk guard.** The disk reached 83% while a 914-layer image lineage, three
separate directories of database backups and an orphan PostgreSQL install
accumulated with nothing watching. The guard reports registry storage and
`pg_wal` size alongside the usual figures, because both grow without anyone
noticing.

**备份顶层散件无轮转——磁盘泄漏源（登记 E4 哨兵输入 / E5 运维项）。**
`w2-backup` 的 `KEEP=8` **只轮转 `$DEST/*/` 子目录**（即 `db/`）；落在
`/opt/w2/backups/` **顶层**的 `*.dump` / `*.sql.gz` / `*-predeploy-*` 目录
**不在任何轮转范围内，只增不减**——这是磁盘长期上涨的泄漏源之一。

2026-10-10 实测顶层散件合计 3.24GB，其中 ≥3 周前的 4 项 1.65GB：

```text
2026-09-13  dashboard-predeploy-20260913T182233Z/     542MiB  deploy-config.tar.gz + release.env（非 DB）
2026-09-15  w2_dump_20260915T171510Z.dump             362MiB  pg_dump 自定义格式，dbname=w2，440 TOC ✅
2026-09-15  w2_dump_20260915T194551Z.dump             363MiB  pg_dump 自定义格式，dbname=w2，440 TOC ✅
2026-09-17  w2-notif04-pre-20260917T161002Z.sql.gz    384MiB  明文 SQL，2,741,089 行，结束标记完整 ✅
```

处置记录：①（deploy 配置快照，非 DB）2026-10-10 已删，df 87%→85%。
②③④ 经完整性校验**均完好可用**，且 `db/` 轮转只留 8 份（2026-10-07 起）——
2026-09-15 / 09-17 的库状态**只有这三份**，删除需单独授权，本 README 登记为
**保留**（未删）。

- **E4 磁盘哨兵必须把「顶层散件无轮转」计入泄漏源**，否则哨兵装了仍会反复触发
  （这是本次 93% 无告警的另一半原因：告警通路缺失 + 泄漏源未被识别）。
- **顶层散件轮转修复本身列入 E5 运维项**（让 `w2-backup` 或独立轮转脚本覆盖顶层，
  而不只是 `db/`）。

**coverage 插桩 override 不属于 release 文件集——误带将同时打挂 api+worker+scheduler（2026-10-10 登记）.**

`production-coverage.override.yml` 把 api / worker / scheduler 的 `command` 覆盖成
`coverage run …`，而当前镜像不含 `coverage` 可执行文件。**它不在 `w2-release:642` 的
compose 文件集内**（那行只有 `compose.staging.yml` + `controlled-future-refresh.override.yml`），
任何手工 `compose up` 多带一个 `-f production-coverage.override.yml` 会让三个容器一起
`exec: "coverage": executable file not found in $PATH`。2026-10-10 曾因此打挂 scheduler
约 7 分钟（`docker compose up -d scheduler` 误带该文件，已恢复、零业务影响）。

处置（指令书 D2 修订裁决3，2026-10-10）：文件已移出部署目录 →
`/opt/w2/shared/evidence/production-coverage.override.yml.RETIRED-20261010`（内容保留可回溯）；
同族第二份 `production-coverage.override.pre-concurrency2-20260824T090414Z.yml` 一并移出。
**规则：compose 文件集以 `w2-release:642` 为唯一真源，任何手工 compose 命令先对照该行。**

连带修复（同批发现，P0）：`ops/host/w2-xg-refresh` 的 compose 文件集里**无条件**带着
`-f /opt/w2/deploy/production-coverage.override.yml` ⇒ 文件一旦移出，该脚本
（由 `w2-xg-refresh.timer` 驱动）会直接 `open …: no such file or directory` 而整体失败
（已实测）。该行对本脚本**从无功能作用**（`compose run --entrypoint python` + 显式参数
已覆盖服务自身 `command`），属残留硬依赖，已移除并同步上机（VPS == repo）。
**不得再把它加回任何 compose 文件集。**

**w2-release（下次发布一律用它）.** 把发布收敛成一条命令，在 Mac 本机运行：

```bash
ops/host/w2-release [--target <sha，默认 HEAD>] [--dry-run] [--skip-window-check]
```

它按顺序完成：前置检查（工作区干净/分支正确/target 已提交/线上 release 可读/部署窗口检查）→ 判断是否需要备份（`online..target` 含 `migrations/` 改动才备份）→ 从目标提交 `migrations/versions` 动态取 schema head → 构建（python 在 VPS、web 在 Mac buildx，同 revision）→ 迁移（有迁移时新镜像 `alembic upgrade head`，校验等于目标 head，失败则停止且不切换）→ 部署（compose 切 release.env）→ 回读 8 项（六接口 200 / release_id+sha 一致 / 推荐倒序 / market_radar 抽样 ≥1 / 容器 healthy+StartedAt / 部署后 180s Traceback=0 / outbox 无过期样本 / 逾期>2h 仍 DUE 的 POSTMATCH_RESULT=0）→ 推送 → 备份轮转 → 回执骨架。

切换 release.env 之后任何失败路径都通过 EXIT trap 自动回滚（恢复旧 release.env + recreate + 回读旧 release_id 并写日志），成功后解除。任何一步不通过就打印 `FAIL` 并停下，不推送、不轮转，退出码非 0；回滚本身失败会单独打印 `ROLLBACK_FAILED` 并给出人工恢复命令。`--dry-run` 只打印计划不产生副作用。部署窗口检查：默认查询 `matchday_checkpoint_plans`，未来 15 分钟或过去 5 分钟内有评估档位（T3_ODDS / T60_ODDS_LINEUPS / T45_ODDS / T-30m_VALIDATION_LOCK / T15_ODDS）则拒绝并打印最近可部署时间；可用 `W2_RELEASE_BLOCKED_WINDOW` 手动指定固定时段 HH:MM-HH:MM，`--skip-window-check` 跳过。今后每次发布都用它，不要手工拼 deploy 脚本。

**Release preflight.** A release holds the old image, the running containers,
the build context, the new image and a predeploy dump on disk at once, so
steady-state free space is not what a release costs. It also refuses to run
if the runtime base is missing: a release built on a pre-flatten image cannot
mount, that lineage having passed the overlayfs mount-option limit.

Every release must also run `/opt/w2/deploy/w2-release-sync-preflight <python-image>
<web-image> <release-sha>` before changing `release.env`, then run
`scripts/verify_release_sync.py` against public ingress after the switch. A
Python-only image change is not a complete release: if the Web image does not
carry the same OCI revision, the preflight fails instead of allowing
`release.env` and `/meta.json` to describe different commits. Install
`w2-staging-release-sync.conf` as a systemd drop-in so ordinary service
activation enforces the same check.

**Registry config.** The stock `registry:2` config does not set
`storage.delete.enabled`, so manifests cannot be deleted and the store only
grows. Local `docker rmi` never touches the registry. Retention is current
release, previous release, a known-good release, the pre-flatten baseline and
the runtime base; garbage collection runs offline with the registry stopped,
since a concurrent push during GC can have its layers collected.

Note the registry serves OCI manifest media types. Asking for a digest with
only the docker v2 Accept header returns 404, which reads as "already gone"
and silently deletes nothing.

**Journal retention.** Journals had grown to 507MB with no cap.

**xG snapshot recompute.** The four-field xG gate reads the most recent rolling
snapshot per team, so a newly discovered fixture reuses whatever that team
already has and never goes missing on that account. What it does not do is
notice the team has since played: the window only moves when something
recomputes it, and the only caller of the materialiser sits inside xg_backfill,
which is disabled. Snapshots therefore go stale silently -- the gate keeps
passing while the model reads an older five matches, which is worse than
absence because absence at least blocks and says so. This makes no Provider
calls and asserts two things before reporting success: team_xg_match must not
have moved (this path materialises snapshots from evidence already stored), and
every snapshot must be visible, since as_of_time written into the future once
hid 98.4% of them.

**Backups.** Three directories held 71 dumps between them, written by
different hands, none ever removed and none off this machine. `w2-backup`
writes to one place, keeps a bounded number, refuses to rotate a good dump
out for an implausibly small new one, and records when it last succeeded.
The age of that marker is what the guard watches: a backup that quietly
stopped running looks exactly like one that never had a problem.

Off-site remains a separate step. What lives here is generation and
retention, not a second failure domain -- these dumps are on the same disk
as the database they came from.

## What the numbers were

Recorded so a later reader can tell whether something has regressed rather
than guessing at what normal looks like.

| | Before | After |
|---|---|---|
| Disk | 83% | 56% |
| Registry store | 1.2GB, 186 tags | 619MB, 7 tags |
| Release cost | 530MB flattened | 20MB on the base |
| Image lineage | 914 layers | 10 |
| Journal | 507MB uncapped | 291MB, capped at 300MB |
| Backups | 71 files, 3 directories, none off-host | 8 kept, one directory, verified off-site copy |

## SEC-01 公网访问加固

SSH 只允许密钥、域名 HTTPS + 网页登录密码、直连不经 Cloudflare（80 跳 443，ufw 放行 22/80/443）。

| File | Installs to | Purpose |
|---|---|---|
| `nginx-w2.site.conf` | `/etc/nginx/sites-available/w2` | 80 跳 443；443：HTTP Basic 认证 + 反代 127.0.0.1:18000/18080 |
| `sshd-05-w2-hardening.conf` | `/etc/ssh/sshd_config.d/05-w2-hardening.conf` | 只允许密钥登录（禁密码/键盘交互，root 只允许密钥） |
| `sshd-60-w2-pubkey.conf` | `/etc/ssh/sshd_config.d/60-w2-pubkey.conf` | 启用 PubkeyAuthentication（镜像默认关闭） |

### 网页登录密码（htpasswd 永不入库）

- 密码文件 `/etc/nginx/w2.htpasswd`（`root:www-data`，`chmod 640`）。
- **该文件与明文密码永不进入 git**（`.gitignore` 已忽略 `*.htpasswd`）。
- 明文密码只写在 Mac 的 `~/Desktop/W2文档/W2_网页登录.txt`（`chmod 600`），不进入回执/git/终端。
- 改密码命令：
  ```bash
  PW=$(openssl rand -base64 18)
  printf 'w2:%s\n' "$(openssl passwd -6 "$PW")" > /etc/nginx/w2.htpasswd
  chown root:www-data /etc/nginx/w2.htpasswd && chmod 640 /etc/nginx/w2.htpasswd
  systemctl reload nginx
  # 明文写到 Mac 的 W2_网页登录.txt
  ```

### TLS 证书（certbot 自动续期）

- 证书 `/etc/letsencrypt/live/w2.ai138.top/{fullchain,privkey}.pem`，由 `certbot.timer` 每日自动续期（`--deploy-hook "systemctl reload nginx"`）。
- 续期验证走 80 端口 `/.well-known/acme-challenge/`（该 location `auth_basic off`，root `/var/www/certbot`）。
- 手动校验：`certbot renew --dry-run`。

### 源站直连（ufw 放行 22/80/443）

- 不经 Cloudflare（Cloudflare 记录仅 DNS/灰云），ufw 对 Anywhere 放行 `22/tcp`、`80/tcp`、`443/tcp`（v4 与 v6）。
- 80 端口只做 `301 → https://w2.ai138.top`（`/.well-known/acme-challenge/` 除外，供 certbot 续期）；443 端口承载 HTTP Basic 认证 + 反代。
- 本机脚本/容器只走 127.0.0.1:18000/18080，不经过 80/443。
- TLS 由 443 端口 certbot 自动续期；Cloudflare 侧 SSL/TLS 与边缘证书不再涉及（记录仅 DNS）。
