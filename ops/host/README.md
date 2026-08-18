# Host operations

What has to exist on the machine but is not part of the application, kept
here so a new host can be brought up without reconstructing it from memory.

| File | Installs to | Purpose |
|---|---|---|
| `w2-disk-guard` | `/usr/local/bin/` | Hourly disk and inode check |
| `w2-disk-guard.service` / `.timer` | `/etc/systemd/system/` | Runs the guard |
| `w2-release-preflight` | `/usr/local/bin/` | Space and base-image check before a release |
| `registry-config.yml` | `/opt/w2/deploy/registry/` | Registry with manifest deletion enabled |
| `journald-w2-retention.conf` | `/etc/systemd/journald.conf.d/` | Journal size cap |

## Why each exists

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
