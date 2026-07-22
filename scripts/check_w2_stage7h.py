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
from typing import Any, NoReturn
from urllib.error import URLError
from urllib.request import urlopen

COMPOSE_FILE = "/opt/w2/current/infra/compose/compose.staging.yml"
ENV_FILE = "/opt/w2/shared/.env"
RELEASE_ENV_FILE = "/opt/w2/shared/release.env"
COMPOSE_PROJECT = "w2-staging"
CORE_RUNNING_SERVICES = {"postgres", "redis", "api", "worker", "web"}
SCHEDULER_SERVICE = "scheduler"


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def fail(msg: str) -> NoReturn:
    print(f"  ❌ {msg}")
    raise SystemExit(1)


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def run(*args: str, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    kwargs.setdefault("timeout", 30)
    return subprocess.run(args, **kwargs)  # noqa: S603


def docker_command(*args: str) -> tuple[str, ...]:
    prefix = ("docker",) if os.geteuid() == 0 else ("sudo", "-n", "docker")
    return (*prefix, *args)


def load_json(url: str) -> dict[str, Any]:
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed loopback URL
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        fail(f"cannot read {url}: {exc}")
    return payload if isinstance(payload, dict) else {}


def compose_services(output: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    services: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            warn(f"Cannot parse compose ps line: {line}")
            continue
        if isinstance(item, dict):
            services.append(item)
    return services


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
    r = run(
        *docker_command(
            "compose",
            "--project-name",
            COMPOSE_PROJECT,
            "--env-file",
            ENV_FILE,
            "--env-file",
            RELEASE_ENV_FILE,
            "-f",
            COMPOSE_FILE,
            "ps",
            "--format",
            "json",
        )
    )
    if r.returncode != 0:
        fail(f"docker compose ps failed: {r.stderr.strip()}")

    services = compose_services(r.stdout.strip())

    scheduler_intentionally_stopped = (
        os.environ.get("W2_PROVIDER_SCHEDULER_ENABLED", "false").lower() != "true"
    )
    expected = set(CORE_RUNNING_SERVICES)
    running_services = set()
    for svc in services:
        name = svc.get("Service", "?")
        status = svc.get("Status", svc.get("State", ""))
        state = svc.get("State", "")
        health = svc.get("Health", "")
        port_str = svc.get("Ports", "")
        if state == "running" and health in {"", "healthy"}:
            running_services.add(name)
            ok(f"{name}: {status}" + (f" health={health}" if health else ""))
            if port_str and "0.0.0.0" in port_str:  # noqa: S104 — this is a port AUDIT check
                warn(f"{name}: public 0.0.0.0 port detected: {port_str}")
        else:
            warn(f"{name}: NOT running ({status})")

    missing = expected - running_services
    if missing:
        fail(f"Missing services: {missing}")
    if SCHEDULER_SERVICE not in running_services:
        if scheduler_intentionally_stopped:
            ok("scheduler: intentionally stopped for controlled staging")
        else:
            fail("scheduler is stopped while W2_PROVIDER_SCHEDULER_ENABLED=true")

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
    r = run(*docker_command("system", "df"))
    if r.returncode == 0:
        ok("Docker system df available")

    r = run(*docker_command("info", "--format", "{{.ServerVersion}}"))
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

    # ── 8. Dashboard performance cohort contract ─────────────
    dashboard = load_json(
        "http://127.0.0.1:18000/v1/dashboard/day-view?window=future&timezone=Asia%2FShanghai"
    )
    performance = dashboard.get("performance", {})
    ledger = performance.get("forward_ledger", {}) if isinstance(performance, dict) else {}
    cohort = ledger.get("performance_cohort", {}) if isinstance(ledger, dict) else {}
    if ledger.get("schema_version") != "w2.forward_ledger_performance.v3":
        fail("forward ledger performance schema is not v3")
    required = {
        "validation_count",
        "processed_count",
        "eligible_count",
        "excluded_count",
        "pending_count",
    }
    if not required <= set(cohort):
        fail(f"performance cohort fields missing: {sorted(required - set(cohort))}")
    if cohort["validation_count"] != cohort["processed_count"] + cohort["pending_count"]:
        fail("performance cohort validation partition failed")
    if cohort["processed_count"] != cohort["eligible_count"] + cohort["excluded_count"]:
        fail("performance cohort processed partition failed")
    clv = cohort.get("clv", {})
    if not isinstance(clv, dict) or clv.get("sample_count", 0) > cohort["eligible_count"]:
        fail("performance cohort CLV is not an eligible-fixture subset")
    if "closing_within_30m_before_kickoff" not in clv.get("method", ""):
        fail("performance cohort CLV does not enforce the 30-minute closing window")
    if clv.get("sample_count", 0) + clv.get("missing_count", 0) != clv.get(
        "candidate_count", 0
    ):
        fail("performance cohort CLV candidate partition is inconsistent")
    invariants = cohort.get("invariants", {})
    if invariants.get("status") != "PASS":
        fail("performance cohort invariant status is not PASS")
    if cohort.get("integrity_status") != "PASS":
        fail("performance cohort evidence and settlement integrity is not PASS")
    recovery_ids = {
        item.get("fixture_id")
        for item in cohort.get("recoveries", [])
        if isinstance(item, dict)
    }
    exclusion_ids = {
        item.get("fixture_id")
        for item in cohort.get("exclusions", [])
        if isinstance(item, dict)
    }
    if len(recovery_ids) != cohort.get("recovered_count", 0):
        fail("performance cohort recovery count does not match recovery details")
    if recovery_ids & exclusion_ids:
        fail("recovered fixtures overlap exclusions")
    ok(
        "performance cohort: "
        f"eligible={cohort['eligible_count']} excluded={cohort['excluded_count']} "
        f"recovered={cohort.get('recovered_count', 0)} pending={cohort['pending_count']}"
    )

    # ── Summary ──────────────────────────────────────────────
    print("")
    print("=" * 60)
    print("Stage7H Check Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
