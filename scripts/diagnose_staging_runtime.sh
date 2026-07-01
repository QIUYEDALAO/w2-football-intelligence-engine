#!/usr/bin/env bash
# Staging runtime diagnostic helper.
#
# This script is intentionally read-only. It does not print environment file
# contents, does not expand docker compose config, and does not call providers.

set -euo pipefail

SSH_HOST="${1:?Usage: $0 <ssh-host>}"
REMOTE_ROOT="${W2_STAGING_ROOT:-/opt/w2/current}"
COMPOSE_FILE="infra/compose/compose.staging.yml"
REMOTE_SCRIPT="$(cat <<'REMOTE'
set -euo pipefail

cd "${REMOTE_ROOT}"

section() {
  printf '\n== %s ==\n' "$1"
}

section "time"
date -u

section "host"
hostname
uptime

section "memory"
free -h

section "disk"
df -h / /opt /var/lib/docker 2>/dev/null || df -h / /opt

section "top-cpu"
ps -eo pid,ppid,stat,pcpu,pmem,comm,args --sort=-pcpu | head -n 15

section "top-mem"
ps -eo pid,ppid,stat,pcpu,pmem,comm,args --sort=-pmem | head -n 15

section "systemd"
systemctl is-active w2-staging.service || true
systemctl --no-pager --plain status w2-staging.service | sed -n '1,30p' || true

section "docker-system-df"
sudo docker system df || true

section "compose-ps"
sudo docker compose \
  --env-file /opt/w2/shared/.env \
  --env-file /opt/w2/shared/release.env \
  -f "${COMPOSE_FILE}" \
  ps || true

section "docker-stats"
sudo docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}' || true

section "local-http"
for url in \
  http://127.0.0.1/ \
  http://127.0.0.1/meta.json \
  http://127.0.0.1:18000/health \
  http://127.0.0.1:18000/ready \
  http://127.0.0.1:18000/v1/version
do
  printf '%s ' "$url"
  curl -fsS --connect-timeout 3 --max-time 8 -o /tmp/w2-staging-probe.body -w 'http_code=%{http_code} connect=%{time_connect} starttransfer=%{time_starttransfer} total=%{time_total}\n' "$url" || true
done

section "recent-journal"
sudo journalctl -u w2-staging.service --no-pager -n 80 || true
REMOTE
)"

ssh "${SSH_HOST}" \
  "REMOTE_ROOT='${REMOTE_ROOT}' COMPOSE_FILE='${COMPOSE_FILE}' bash -s" \
  <<<"${REMOTE_SCRIPT}"
