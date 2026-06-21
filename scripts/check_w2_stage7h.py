#!/usr/bin/env python3
"""
W2 Stage7H – Post-deployment health check.

Usage (on server):
    python3 scripts/check_w2_stage7h.py

Or via SSH:
    ssh server 'cd /opt/w2/current && python3 scripts/check_w2_stage7h.py'
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    print(f"  ❌ {msg}")
    raise SystemExit(1)


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def run(*args: str, **kwargs) -> subprocess.CompletedProcess:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 30)
    return subprocess.run(args, **kwargs)  # noqa: S603


def main() -> None:
    print("=" * 60)
    print("W2 Stage7H Post-Deployment Check")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print("=" * 60)

    # ── 1. Release info ─────────────────────────────────────
    current = Path("/opt/w2/current")
    if current.is_symlink():
        revision = current.resolve().name
        ok(f"/opt/w2/current -> {revision}")
    else:
        fail("/opt/w2/current is not a symlink")

    dep_rev = current / "DEPLOYMENT_REVISION"
    if dep_rev.exists():
        ok(f"DEPLOYMENT_REVISION: {dep_rev.read_text().strip()}")
    else:
        warn("DEPLOYMENT_REVISION file not found")

    # ── 2. Docker compose ps ─────────────────────────────────
    r = run("docker", "compose", "ps", "--format", "json")
    if r.returncode != 0:
        fail(f"docker compose ps failed: {r.stderr.strip()}")

    services: list[dict] = []
    for line in r.stdout.strip().splitlines():
        if not line.strip():
            continue
        try:
            services.append(json.loads(line))
        except json.JSONDecodeError:
            warn(f"Cannot parse compose ps line: {line}")

    expected = {"postgres", "redis", "api", "worker", "scheduler", "web"}
    running_services = set()
    for svc in services:
        name = svc.get("Name", svc.get("Service", "?"))
        status = svc.get("Status", svc.get("State", ""))
        running_services.add(name.rsplit("-", 1)[0] if "-" in name else name)
        health = svc.get("Health", "")
        port_str = svc.get("Ports", "")
        if "Up" in status:
            ok(f"{name}: {status}" + (f" health={health}" if health else ""))
            if port_str and "0.0.0.0" in port_str:  # noqa: S104 — this is a port AUDIT check
                warn(f"{name}: public 0.0.0.0 port detected: {port_str}")
        else:
            warn(f"{name}: NOT running ({status})")

    missing = expected - running_services
    if missing:
        fail(f"Missing services: {missing}")

    # ── 3. Port check (public) ───────────────────────────────
    r = run("ss", "-lntup")
    if r.returncode == 0:
        public_ports = [
            line for line in r.stdout.splitlines()
            if "0.0.0.0:" in line and ":22" not in line
        ]
        if public_ports:
            warn("Public non-SSH ports detected:\n" + "\n".join(public_ports))
        else:
            ok("No public business ports (only SSH :22)")

    # ── 4. Environment verification ──────────────────────────
    env_file = Path("/opt/w2/shared/.env")
    if env_file.exists():
        mode = env_file.stat().st_mode
        if mode & 0o077:
            warn(f".env permissions too permissive: {oct(mode)}")
        else:
            ok(f".env permissions: {oct(mode)}")
        content = env_file.read_text()
        if "REQUIRED_MANUAL_INJECTION" in content:
            warn("API_FOOTBALL_KEY still has placeholder value")
    else:
        warn(".env file missing")

    # ── 5. Docker health ─────────────────────────────────────
    r = run("docker", "system", "df")
    if r.returncode == 0:
        ok("Docker system df available")

    r = run("docker", "info", "--format", "{{.ServerVersion}}")
    if r.returncode == 0:
        ok(f"Docker Engine: {r.stdout.strip()}")

    # ── 6. systemd unit ──────────────────────────────────────
    r = run("systemctl", "is-enabled", "w2-staging.service")
    enabled = r.stdout.strip() if r.returncode == 0 else "unknown"
    r2 = run("systemctl", "is-active", "w2-staging.service")
    active = r2.stdout.strip() if r2.returncode == 0 else "unknown"
    ok(f"w2-staging.service: enabled={enabled}, active={active}")

    # ── 7. Feature flags (environment audit) ─────────────────
    env_vars = os.environ
    for key, expected_val in [
        ("W2_ENVIRONMENT", "staging"),
        ("W2_DEEPSEEK_ENABLED", "false"),
        ("W2_RECOMMENDATION_ENABLED", "false"),
        ("W2_CANDIDATE_ENABLED", "false"),
        ("W2_PRODUCTION_RELEASE", "false"),
        ("W2_FORWARD_HOLDOUT_AUTORUN", "true"),
        ("W2_FORWARD_HOLDOUT_NETWORK", "true"),
        ("W2_EXTERNAL_ALERTING", "false"),
    ]:
        # Read from process env (this script needs to run inside container or with env)
        actual = env_vars.get(key, "<NOT SET>")
        if actual != expected_val:
            warn(f"{key}={actual} (expected {expected_val})")
        else:
            ok(f"{key}={actual}")

    # ── Summary ──────────────────────────────────────────────
    print("")
    print("=" * 60)
    print("Stage7H Check Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
