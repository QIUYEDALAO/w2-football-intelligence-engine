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
| `w2-totals-calibration` | `/opt/w2/deploy/` | Totals calibration snapshot, read-only |
| `w2-registry-gc.service` / `.timer` | `/etc/systemd/system/` | Runs the collection |
| `w2-release-preflight` | `/usr/local/bin/` | Space, base image and layer count before a release |
| `registry-config.yml` | `/opt/w2/deploy/registry/` | Registry with manifest deletion enabled |
| `journald-w2-retention.conf` | `/etc/systemd/journald.conf.d/` | Journal size cap |

`w2-xg-ingest-guard` is deliberately narrower than xG freshness monitoring. It
alarms only when saved raw contains numeric xG for both teams but
`team_xg_match` does not contain exactly two non-null team rows. Provider-null,
not-yet-published, and disabled-competition fixtures do not trigger this guard.
The query is read-only and discovers the enabled set from
`league_season.payload.enabled` at runtime.

## Why each exists

**xG refresh.** `w2-xg-materialize` recomputes snapshots from evidence already
stored; until now nothing fetched the evidence itself. `W2_XG_BACKFILL_ENABLED`
is false by design so one run cannot sweep every competition at once, which
left no path for keeping xG current: `team_xg_match` sat at 18,696 while 144
finished matches carried a result and no xG, and the rolling five-match window
kept reaching further back until the restarted European leagues priced August
fixtures off May evidence. `w2-xg-refresh` walks the whitelist one competition
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

**Release preflight.** A release holds the old image, the running containers,
the build context, the new image and a predeploy dump on disk at once, so
steady-state free space is not what a release costs. It also refuses to run
if the runtime base is missing: a release built on a pre-flatten image cannot
mount, that lineage having passed the overlayfs mount-option limit.

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
