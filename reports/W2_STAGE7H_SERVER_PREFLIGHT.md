# W2-STAGE7H Server Preflight Audit

**Date**: 2026-06-22 07:54 CST  
**Task**: W2-STAGE7H-001-BUNDLE  
**Server**: 43.155.208.138 (首尔 VPS)

---

## Local Repository Status

| Field | Value |
|---|---|
| **HEAD** | `8defe3bdd303d2d686a77dbfc9db0adb48453b07` |
| **Branch** | `feat/stage7g-forward-continuity-audit` |
| **Working Tree** | Clean |
| **Origin** | Not configured (allowed) |
| **Latest Commit** | `8defe3b chore(w2): audit forward holdout continuity` |

---

## SSH Status

| Field | Value |
|---|---|
| **SSH Connection** | ✅ Success (interactive auth) |
| **Host Key** | ✅ Confirmed by user |
| **Key Material** | `~/.ssh/id_ed25519_qiuyedalao` (not authorized on server) |
| **SSH Auth** | Auth accepted |

### Host Key Fingerprint

```
ED25519:
SHA256:AoOJApHLjf7kQP+7K9vR9kPtwfWQOQCJL/wYYLDg3xY
```

---

## Server Identity

| Field | Value |
|---|---|
| **Hostname** | `VM-0-16-ubuntu` |
| **Vendor** | Tencent Cloud (CVM) |
| **Virtualization** | KVM |
| **OS** | Ubuntu 24.04.4 LTS (Noble Numbat) |
| **Kernel** | `6.8.0-117-generic` |
| **Architecture** | amd64 |

---

## Resources

| Resource | Value |
|---|---|
| **CPU** | 4 vCPU |
| **RAM** | 7.4 GiB total — 6.6 GiB free — 528 MiB used |
| **Disk** | 118 GiB (vda2) — 5.4 GiB used — 108 GiB available (5% used) |
| **Swap** | 1.9 GiB (`/swap.img`) — 0 B used |

Swap already exists at 1.9 GiB. Slightly below 2 GiB, but sufficient. No swap modification needed unless strict 2 GiB requirement applies.

---

## Network Listeners (Public)

| Protocol | Port | Address | Service |
|---|---|---|---|
| TCP | 22 | `0.0.0.0:22` | SSH |
| TCP | 22 | `[::]:22` | SSH (IPv6) |

**Only SSH port 22 is listening on public interfaces.**

Local listeners:
- `127.0.0.54:53` — systemd-resolved DNS
- `127.0.0.53:53` — systemd-resolved stub
- `127.0.0.1:323` — chronyd NTP

**No public-facing business ports detected.**

---

## Firewall

| Field | Value |
|---|---|
| **UFW** | Inactive (not enabled) |
| **Cloud Security Group** | Not modified (external to server) |

---

## Existing Container Software

| Software | Status |
|---|---|
| **Docker** | ❌ Not installed |
| **Podman** | ❌ Not installed |
| **Containerd** | ❌ Not installed |
| **Docker service** | ❌ Not present |
| **Containerd service** | ❌ Not present |

No container runtimes detected.

---

## Existing W2 Files/Services

| Check | Status |
|---|---|
| `/opt/w2` | ❌ Does not exist |
| `~/*w2*` | ❌ Not found |
| W2 systemd services | ❌ Not present |
| Docker services | ❌ Not present |
| Redis services | ❌ Not present |
| PostgreSQL services | ❌ Not present |

**No pre-existing W2 deployment or related services.**

---

## Apt & Reboot

| Check | Status |
|---|---|
| **Apt locks** | ✅ None |
| **Reboot required** | ❌ No |
| **Pending updates** | Not checked (read-only audit) |

---

## Sudo Status

| Field | Value |
|---|---|
| **sudo NOPASSWD** | ✅ Available |

---

## Planned Modifications (Phase B)

1. **Install Docker** via official Ubuntu repository:
   - `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`
   - Enable + start `docker` service
   - Run `hello-world` verification

2. **Swap** — Already 1.9 GiB present. If strict 2 GiB is required, create additional ~128 MiB or replace the existing 1.9 GiB swap. Otherwise skip.

3. **Firewall** — UFW is inactive. Do not enable. Do not modify cloud security groups.

4. **Directory structure** — Create:
   - `/opt/w2/releases/`
   - `/opt/w2/shared/{runtime,data,logs,backups,state}`

---

## Conflict Assessment

| Item | Conflict | Action |
|---|---|---|
| SSH host key | ✅ None — confirmed | Proceed |
| Existing Docker/containerd | ✅ None | Proceed |
| Existing W2 files/services | ✅ None | Proceed |
| Existing containers/volumes | ✅ None | Proceed |
| Existing PostgreSQL/Redis | ✅ None | Proceed |
| Port conflicts | ✅ None (only 22) | Proceed |
| UFW blocking SSH | ✅ N/A (UFW inactive) | Proceed |
| Swap | ✅ Already present | Consider replacing with 2 GiB |

---

## Verdict

**No BLOCKERs detected.**  
**No WARN_ONLY items.**

### Summary

| # | Item | Status |
|---|---|---|
| 1 | SSH successful | ✅ Yes |
| 2 | Host key confirmed | ✅ Yes |
| 3 | Sudo available | ✅ NOPASSWD |
| 4 | CPU/RAM/Disk/Swap | 4c/7.4G/108G free/1.9G swap |
| 5 | Public listening ports | Only SSH :22 |
| 6 | UFW | Inactive |
| 7 | Docker/Podman/Containerd | None installed |
| 8 | Old W2 files/services | None found |
| 9 | Reboot required | No |
| 10 | System modifications planned | Docker install, dirs setup |
| 11 | BLOCKER | None |
| 12 | WARN_ONLY | None |

**Server has NOT been modified.** All checks were read-only.

---

## References

- Task: W2-STAGE7H-001-BUNDLE
- Baseline: 8defe3bdd303d2d686a77dbfc9db0adb48453b07
