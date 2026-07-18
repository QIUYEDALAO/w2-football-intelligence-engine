from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

CONTAINER_ID = re.compile(r"[0-9a-f]{12,64}\Z")
METRIC_VALUE = re.compile(r"^w2_checkpoint_lag_seconds\s+([-+0-9.eE]+)$", re.MULTILINE)
CommandRunner = Callable[[Sequence[str]], str]


def validate_loopback_metrics_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("metrics URL must be loopback HTTP")
    return url


def subprocess_runner(command: Sequence[str]) -> str:
    return subprocess.check_output(command, text=True, timeout=30).strip()


def parse_checkpoint_lag(metrics_text: str) -> float | None:
    match = METRIC_VALUE.search(metrics_text)
    return float(match.group(1)) if match is not None else None


def _container_evidence(
    container_id: str,
    *,
    runner: CommandRunner,
) -> dict[str, Any]:
    if CONTAINER_ID.fullmatch(container_id) is None:
        raise ValueError("compose returned an invalid container ID")
    inspection = json.loads(runner(["docker", "inspect", container_id]))
    if not isinstance(inspection, list) or len(inspection) != 1:
        raise ValueError("docker inspect must return exactly one container")
    state = inspection[0].get("State")
    if not isinstance(state, dict):
        raise ValueError("docker inspect state is unavailable")
    health = state.get("Health")
    health_status = health.get("Status") if isinstance(health, dict) else "unavailable"
    rss_text = runner(
        [
            "docker",
            "exec",
            container_id,
            "sh",
            "-c",
            "awk '/^RssAnon:/ {sum += $2} END {print sum * 1024}' "
            "/proc/[0-9]*/status 2>/dev/null",
        ]
    )
    return {
        "container_id": container_id,
        "status": str(state.get("Status") or "unknown"),
        "health": str(health_status or "unavailable"),
        "restart_count": int(inspection[0].get("RestartCount") or 0),
        "oom_killed": state.get("OOMKilled") is True,
        "exit_code": int(state.get("ExitCode") or 0),
        "rss_bytes": int(rss_text),
    }


def capture_runtime_evidence(
    *,
    compose_prefix: Sequence[str],
    services: Sequence[str],
    baseline: dict[str, Any],
    scheduler_expected: str,
    metrics_text: str,
    runner: CommandRunner = subprocess_runner,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if scheduler_expected not in {"running", "stopped"}:
        raise ValueError("scheduler_expected must be running or stopped")
    service_evidence: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    baseline_services = baseline.get("services")
    if not isinstance(baseline_services, dict):
        raise ValueError("baseline services are required")
    for service in services:
        container_id = runner([*compose_prefix, "ps", "-aq", service]).strip()
        if not container_id:
            service_evidence[service] = {"status": "absent"}
            if service != "scheduler" or scheduler_expected == "running":
                failures.append(f"{service}:absent")
            continue
        evidence = _container_evidence(container_id, runner=runner)
        service_evidence[service] = evidence
        baseline_item = baseline_services.get(service)
        if not isinstance(baseline_item, dict):
            failures.append(f"{service}:baseline_missing")
        elif evidence["restart_count"] > int(baseline_item.get("restart_count") or 0):
            failures.append(f"{service}:restart_increment")
        if evidence["oom_killed"]:
            failures.append(f"{service}:oom_killed")
        if evidence["exit_code"] == 137:
            failures.append(f"{service}:exit137")
        expected_status = scheduler_expected if service == "scheduler" else "running"
        status_matches = (
            evidence["status"] in {"exited", "created"}
            if expected_status == "stopped"
            else evidence["status"] == expected_status
        )
        if not status_matches:
            failures.append(f"{service}:status_{evidence['status']}")
        if expected_status == "running" and evidence["health"] not in {
            "healthy",
            "unavailable",
        }:
            failures.append(f"{service}:health_{evidence['health']}")

    queue_text = runner(
        [*compose_prefix, "exec", "-T", "redis", "redis-cli", "-n", "1", "LLEN", "celery"]
    )
    queue_length = int(queue_text)
    baseline_queue = int(baseline.get("queue_length") or 0)
    if queue_length != baseline_queue:
        failures.append("queue:length_changed")
    checkpoint_lag = parse_checkpoint_lag(metrics_text)
    if checkpoint_lag is None:
        failures.append("checkpoint_lag:unavailable")

    return {
        "schema_version": "w2.runtime-release-evidence.v1",
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "result": "FAIL" if failures else "PASS",
        "scheduler_expected": scheduler_expected,
        "queue_length": queue_length,
        "checkpoint_lag_seconds": checkpoint_lag,
        "services": service_evidence,
        "failures": failures,
    }
