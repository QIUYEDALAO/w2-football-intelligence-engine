#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UTC = timezone.utc  # noqa: UP017 - server/local python3 may be older than project runtime.
DEFAULT_BASELINE_REVISION: str | None = None
SERVICES = ["postgres", "redis", "api", "worker", "scheduler", "web"]
CONTAINERS = {name: f"w2-staging-{name}-1" for name in SERVICES}
DEFAULT_RUNTIME = Path("/opt/w2/shared/runtime/stage7i")
DEFAULT_CURRENT = Path("/opt/w2/current")
DEFAULT_GLOBAL_LOCK = Path("/opt/w2/shared/runtime/stage7i/observer-global.lock")
SAMPLE_INTERVAL_SECONDS = 300
OBSERVATION_SECONDS = 24 * 60 * 60


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def run_command(args: list[str], *, timeout: int = 10) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:  # pragma: no cover - defensive for server runtime
        return 127, "", f"{type(exc).__name__}: {exc}"
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def http_probe(url: str, *, method: str = "GET", timeout: int = 5) -> dict[str, Any]:
    if not url.startswith("http://127.0.0.1:"):
        return {"ok": False, "status": None, "error": "NON_LOCALHOST_URL_REJECTED"}
    started = time.monotonic()
    try:
        request = Request(url, method=method)  # noqa: S310 - localhost-only guard above.
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            body = response.read(16_384).decode("utf-8", errors="replace")
            return {
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "body": body if url.endswith(("/health", "/ready")) else "",
            }
    except HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
    except URLError as exc:
        return {
            "ok": False,
            "status": None,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc.reason),
        }


def current_revision(current: Path, baseline_revision: str) -> dict[str, Any]:
    revision_path = current / "DEPLOYMENT_REVISION"
    revision = revision_path.read_text(encoding="utf-8").strip() if revision_path.exists() else None
    link_code, link_out, link_err = run_command(["readlink", "-f", str(current)])
    return {
        "revision": revision,
        "path": link_out if link_code == 0 else None,
        "error": link_err if link_code != 0 else None,
        "matches_baseline": revision == baseline_revision,
    }


def migration_heads(current: Path) -> list[str]:
    versions = current / "migrations" / "versions"
    revisions: set[str] = set()
    down_revisions: set[str] = set()
    if not versions.exists():
        return []
    revision_re = re.compile(r"^revision(?:\s*:\s*[^=]+)?\s*=\s*['\"]([^'\"]+)['\"]")
    down_re = re.compile(r"^down_revision(?:\s*:\s*[^=]+)?\s*=\s*(.+)$")
    for path in versions.glob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            revision_match = revision_re.match(line.strip())
            if revision_match:
                revisions.add(revision_match.group(1))
            down_match = down_re.match(line.strip())
            if down_match:
                raw = down_match.group(1)
                for match in re.finditer(r"['\"]([^'\"]+)['\"]", raw):
                    down_revisions.add(match.group(1))
    return sorted(revisions - down_revisions)


def alembic_head_status(current: Path, expected_head: str) -> dict[str, Any]:
    heads = migration_heads(current)
    return {
        "expected_head": expected_head,
        "heads": heads,
        "matches_expected": expected_head in heads,
    }


def parse_utc(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def validate_selection(
    selection_json: Path,
    *,
    fixture_id: str,
    scheduled_kickoff_utc: str,
) -> dict[str, Any]:
    payload = load_json(selection_json, None)
    if not isinstance(payload, dict):
        raise ValueError("selection JSON must be an object")
    if payload.get("source") != "W2_STAGING_PROVIDER_DATA":
        raise ValueError("selection source must be W2_STAGING_PROVIDER_DATA")
    if payload.get("candidate") is not False or payload.get("formal_recommendation") is not False:
        raise ValueError("selection must keep candidate/formal false")
    selected = payload.get("selected_fixture")
    if not isinstance(selected, dict):
        raise ValueError("selection selected_fixture must be an object")
    if str(selected.get("fixture_id")) != fixture_id:
        raise ValueError("selection fixture_id does not match CLI")
    if selected.get("scheduled_kickoff_utc") != scheduled_kickoff_utc:
        raise ValueError("selection scheduled kickoff does not match CLI")
    if selected.get("status") != "NS":
        raise ValueError("selection fixture status must be NS")
    kickoff = parse_utc(scheduled_kickoff_utc, "scheduled_kickoff_utc")
    generated = parse_utc(str(payload.get("generated_at_utc")), "generated_at_utc")
    if kickoff <= generated:
        raise ValueError("selected kickoff has already occurred")
    mapping = selected.get("provider_mapping")
    if (
        not isinstance(mapping, dict)
        or mapping.get("reliable") is not True
        or mapping.get("conflict") is True
    ):
        raise ValueError("selection provider mapping must be reliable and conflict-free")
    market = selected.get("market_observation")
    if not isinstance(market, dict):
        raise ValueError("selection market_observation must be an object")
    captured = parse_utc(str(market.get("captured_at_utc")), "market captured_at_utc")
    if captured > generated:
        raise ValueError("market captured_at must not be in the future")
    if market.get("fresh") is not True:
        raise ValueError("market observation must be fresh")
    if int(market.get("bookmaker_count", 0)) <= 0:
        raise ValueError("market observation must include bookmakers")
    return payload


def systemd_state() -> dict[str, Any]:
    enabled_code, enabled, _ = run_command(
        ["sudo", "systemctl", "is-enabled", "w2-staging.service"]
    )
    active_code, active, _ = run_command(["sudo", "systemctl", "is-active", "w2-staging.service"])
    return {
        "enabled": enabled,
        "active": active,
        "enabled_ok": enabled_code == 0 and enabled == "enabled",
        "active_ok": active_code == 0 and active == "active",
    }


def inspect_container(name: str) -> dict[str, Any]:
    code, out, err = run_command(
        [
            "sudo",
            "docker",
            "inspect",
            "--format",
            "{{json .State}}",
            name,
        ],
        timeout=10,
    )
    if code != 0:
        return {"container": name, "exists": False, "error": err}
    state = json.loads(out)
    health = state.get("Health", {}).get("Status")
    return {
        "container": name,
        "exists": True,
        "status": state.get("Status"),
        "health": health,
        "restart_count": container_restart_count(name),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "exit_code": state.get("ExitCode"),
    }


def container_restart_count(name: str) -> int | None:
    code, out, _ = run_command(
        ["sudo", "docker", "inspect", "--format", "{{.RestartCount}}", name],
        timeout=10,
    )
    if code != 0:
        return None
    try:
        return int(out)
    except ValueError:
        return None


def container_states() -> dict[str, Any]:
    return {service: inspect_container(container) for service, container in CONTAINERS.items()}


def latest_scheduler_heartbeat_age_seconds(now: datetime) -> int | None:
    code, out, err = run_command(
        [
            "sudo",
            "docker",
            "logs",
            "--since",
            "30m",
            "--timestamps",
            CONTAINERS["scheduler"],
        ],
        timeout=10,
    )
    if code != 0:
        return None
    output = "\n".join(part for part in [out, err] if part)
    latest: datetime | None = None
    for line in output.splitlines():
        if "w2 scheduler heartbeat" not in line:
            continue
        raw_ts = line.split(maxsplit=1)[0]
        normalized = re.sub(r"Z$", "+00:00", raw_ts)
        normalized = re.sub(r"\\.([0-9]{6})[0-9]+", r".\1", normalized)
        try:
            latest = datetime.fromisoformat(normalized).astimezone(UTC)
        except ValueError:
            continue
    if latest is None:
        return None
    return max(int((now - latest).total_seconds()), 0)


def latest_cycle_status(current: Path) -> dict[str, Any]:
    reports = current / "reports"
    scheduler = load_json(reports / "W2_STAGE7E_SCHEDULER_AUDIT.json", {})
    first = load_json(reports / "W2_STAGE7E_FIRST_LIVE_CYCLE.json", {})
    return {
        "scheduler_run_id": scheduler.get("scheduler_run_id"),
        "finished_at": scheduler.get("finished_at"),
        "exit_status": scheduler.get("exit_status"),
        "no_overlap": scheduler.get("no_overlap"),
        "cycle_hash": scheduler.get("cycle_hash"),
        "latest_gate": (
            scheduler.get("cycle_checkpoint") or first.get("checkpoint") or {}
        ).get("gate", {}),
    }


def quota_status(current: Path) -> dict[str, Any]:
    runtime = current / "runtime" / "stage7e"
    quota = load_json(runtime / "quota_usage.json", {})
    usage = load_json(current / "reports" / "W2_STAGE7E_API_USAGE.json", {})
    return {
        "remaining_quota": quota.get("remaining_quota", usage.get("remaining_quota")),
        "requests_used_today": quota.get("requests_used", usage.get("total_requests")),
        "usage_date": quota.get("usage_date"),
        "reset_at": quota.get("reset_at"),
    }


def forward_counts(current: Path) -> dict[str, Any]:
    runtime = current / "runtime"
    stage7e = runtime / "stage7e"
    locks = load_json(stage7e / "prediction_locks.json", [])
    results = load_json(stage7e / "result_events.json", [])
    markets = load_json(stage7e / "market_snapshots.json", [])
    settlements = load_json(
        current / "reports" / "W2_STAGE7E_FIRST_LIVE_CYCLE.json",
        {},
    ).get("checkpoint", {})
    missing = 0
    for path in [current / "reports" / "W2_STAGE7G_ZERO_SAMPLE_DIAGNOSIS.json"]:
        payload = load_json(path, {})
        reasons = payload.get("reason_counts", {}) if isinstance(payload, dict) else {}
        missing += int(reasons.get("MODEL_INPUT_MISSING", 0))
    return {
        "forward_lock_count": len(locks) if isinstance(locks, list) else 0,
        "result_event_count": len(results) if isinstance(results, list) else 0,
        "settlement_count": int(settlements.get("result_event_count", 0) or 0),
        "market_comparable_count": sum(
            1
            for item in markets
            if isinstance(item, dict) and item.get("market_comparable")
        ),
        "model_input_missing_count": missing,
    }


def resource_status() -> dict[str, Any]:
    loadavg_path = Path("/proc/loadavg")
    loadavg = (
        loadavg_path.read_text(encoding="utf-8").split()[:3]
        if loadavg_path.exists()
        else []
    )
    meminfo: dict[str, int] = {}
    if Path("/proc/meminfo").exists():
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, value = line.split(":", 1)
            parts = value.strip().split()
            if parts:
                meminfo[key] = int(parts[0])
    disk_code, disk_out, _ = run_command(["df", "-Pk", "/opt/w2"], timeout=10)
    disk = {}
    if disk_code == 0:
        lines = disk_out.splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 6:
                disk = {
                    "size_kb": int(parts[1]),
                    "used_kb": int(parts[2]),
                    "available_kb": int(parts[3]),
                    "capacity": parts[4],
                    "mount": parts[5],
                }
    return {
        "loadavg": loadavg,
        "memory_kb": {
            "total": meminfo.get("MemTotal"),
            "available": meminfo.get("MemAvailable"),
            "swap_total": meminfo.get("SwapTotal"),
            "swap_free": meminfo.get("SwapFree"),
        },
        "disk": disk,
    }


def listener_policy() -> dict[str, Any]:
    code, out, err = run_command(["sudo", "ss", "-lntH"], timeout=10)
    if code != 0:
        return {"ok": False, "error": err, "public_business_ports": ["UNKNOWN"]}
    public_business: list[str] = []
    localhost_required = {"127.0.0.1:18000": False, "127.0.0.1:18080": False}
    listeners: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local = parts[3]
        listeners.append(local)
        if local in localhost_required:
            localhost_required[local] = True
        host, _, port = local.rpartition(":")
        is_loopback = host.startswith("127.") or host in {"[::1]", "::1"}
        is_public = not is_loopback
        if is_public and port not in {"22"}:
            public_business.append(local)
    return {
        "ok": not public_business and all(localhost_required.values()),
        "api_localhost": localhost_required["127.0.0.1:18000"],
        "web_localhost": localhost_required["127.0.0.1:18080"],
        "public_business_ports": public_business,
        "listener_count": len(listeners),
    }


def gate_status(current: Path) -> dict[str, Any]:
    candidates = [
        current / "reports" / "W2_STAGE7E_FIRST_LIVE_CYCLE.json",
        current / "reports" / "W2_STAGE7F_GATE4_DECISION.json",
        current / "reports" / "W2_STAGE7G_ZERO_SAMPLE_DIAGNOSIS.json",
    ]
    for path in candidates:
        payload = load_json(path, {})
        if isinstance(payload, dict):
            gate = payload.get("gate") or payload.get("decision") or payload.get("gate4")
            if isinstance(gate, dict) and gate:
                return gate
    return {
        "GATE_4_NATIONAL_1X2": "PROVISIONAL_FORWARD_HOLDOUT_PENDING",
        "STAGE_9": "BLOCKED",
        "GATE_4_AH": "BLOCKED_FORWARD_ONLY",
    }


def initial_restart_counts(runtime: Path, containers: dict[str, Any]) -> dict[str, int]:
    path = runtime / "initial_restart_counts.json"
    if path.exists():
        payload = load_json(path, {})
        return {str(k): int(v) for k, v in payload.items()}
    counts = {
        service: int(state.get("restart_count") or 0)
        for service, state in containers.items()
        if isinstance(state, dict)
    }
    write_json(path, counts)
    return counts


def collect_sample(
    runtime: Path,
    current: Path,
    state: dict[str, Any],
    baseline_revision: str,
    fixture_id: str,
    scheduled_kickoff_utc: str,
) -> dict[str, Any]:
    now = utc_now()
    containers = container_states()
    initial_counts = initial_restart_counts(runtime, containers)
    health = {
        "health": http_probe("http://127.0.0.1:18000/health"),
        "ready": http_probe("http://127.0.0.1:18000/ready"),
        "web": http_probe("http://127.0.0.1:18080/", method="HEAD"),
    }
    sample = {
        "timestamp_utc": iso(now),
        "fixture": fixture_sample(current, fixture_id, scheduled_kickoff_utc, now),
        "current": current_revision(current, baseline_revision),
        "systemd": systemd_state(),
        "containers": containers,
        "api": health,
        "worker_health": containers.get("worker", {}).get("health"),
        "scheduler_health": containers.get("scheduler", {}).get("health"),
        "scheduler_heartbeat_age_seconds": latest_scheduler_heartbeat_age_seconds(now),
        "latest_cycle": latest_cycle_status(current),
        "quota": quota_status(current),
        "forward": forward_counts(current),
        "resources": resource_status(),
        "listeners": listener_policy(),
        "gate": gate_status(current),
    }
    sample["blockers"] = evaluate_blockers(sample, initial_counts, state)
    return sample


def fixture_sample(
    current: Path,
    fixture_id: str,
    scheduled_kickoff_utc: str,
    now: datetime,
) -> dict[str, Any]:
    fixture_payload = load_json(current / "runtime/stage7e/fixtures.json", {})
    market_payload = load_json(current / "runtime/stage7e/market_snapshots.json", [])
    result_payload = load_json(current / "runtime/stage7e/result_events.json", [])
    fixture_status = None
    actual_kickoff_source = "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE"
    market_observations: list[dict[str, Any]] = []
    if isinstance(market_payload, list):
        market_observations = [
            item
            for item in market_payload
            if isinstance(item, dict) and str(item.get("fixture_id")) == fixture_id
        ]
    result_events = [
        item
        for item in result_payload
        if isinstance(item, dict) and str(item.get("fixture_id")) == fixture_id
    ] if isinstance(result_payload, list) else []
    if isinstance(fixture_payload, dict):
        raw_status = fixture_payload.get(fixture_id)
        if isinstance(raw_status, dict):
            fixture_status = raw_status.get("status")
    last_market_before_now = None
    for item in market_observations:
        captured = item.get("captured_at_utc") or item.get("captured_at")
        if not isinstance(captured, str):
            continue
        try:
            captured_dt = parse_utc(captured, "market.captured_at")
        except ValueError:
            continue
        if captured_dt <= now:
            last_market_before_now = captured
    return {
        "fixture_id": fixture_id,
        "scheduled_kickoff_utc": scheduled_kickoff_utc,
        "fixture_status": fixture_status,
        "actual_kickoff_source": actual_kickoff_source,
        "last_market_observation_before_now": last_market_before_now,
        "market_observation_count": len(market_observations),
        "result_event_count": len(result_events),
    }


def evaluate_blockers(
    sample: dict[str, Any],
    initial_counts: dict[str, int],
    state: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not sample["current"].get("matches_baseline"):
        blockers.append("CURRENT_REVISION_CHANGED")
    if sample["systemd"].get("active") != "active":
        blockers.append("SYSTEMD_INACTIVE")
    for service, container in sample["containers"].items():
        restart_count = container.get("restart_count")
        if restart_count is not None and restart_count > initial_counts.get(service, restart_count):
            blockers.append(f"{service.upper()}_RESTART_COUNT_INCREASED")
    for service in ["postgres", "redis", "api", "worker", "scheduler", "web"]:
        if sample["containers"].get(service, {}).get("health") not in {"healthy", None}:
            key = f"{service}_unhealthy_count"
            state[key] = int(state.get(key, 0)) + 1
            if state[key] >= 2:
                blockers.append(f"{service.upper()}_UNHEALTHY_CONSECUTIVE")
        else:
            state[f"{service}_unhealthy_count"] = 0
    heartbeat_age = sample["scheduler_heartbeat_age_seconds"]
    if heartbeat_age is None or heartbeat_age > 180:
        blockers.append("SCHEDULER_HEARTBEAT_STALE")
    ready_ok = bool(sample["api"]["ready"].get("ok"))
    state["ready_fail_count"] = 0 if ready_ok else int(state.get("ready_fail_count", 0)) + 1
    if state["ready_fail_count"] >= 2:
        blockers.append("API_READY_FAILED_CONSECUTIVE")
    remaining = sample["quota"].get("remaining_quota")
    if remaining is not None and int(remaining) < 1500:
        blockers.append("QUOTA_BELOW_RESERVE")
    if sample["listeners"].get("public_business_ports"):
        blockers.append("PUBLIC_BUSINESS_PORT_DETECTED")
    gate = sample.get("gate", {})
    if gate.get("GATE_4_NATIONAL_1X2") not in {None, "PROVISIONAL_FORWARD_HOLDOUT_PENDING"}:
        blockers.append("GATE4_UNEXPECTED_STATE")
    if gate.get("STAGE_9") not in {None, "BLOCKED"}:
        blockers.append("STAGE9_UNEXPECTED_STATE")
    return sorted(set(blockers))


def summarize(
    runtime: Path,
    started_at: datetime,
    expected_end: datetime,
    completed: bool,
    baseline_revision: str,
    fixture_id: str,
    scheduled_kickoff_utc: str,
    expected_alembic_head: str,
    selection_json: Path,
    selection_sha256: str,
) -> dict[str, Any]:
    observations = runtime / "observations.jsonl"
    samples: list[dict[str, Any]] = []
    if observations.exists():
        for line in observations.read_text(encoding="utf-8").splitlines():
            if line.strip():
                samples.append(json.loads(line))
    blockers = sorted({blocker for sample in samples for blocker in sample.get("blockers", [])})
    first_ts = samples[0]["timestamp_utc"] if samples else None
    last_ts = samples[-1]["timestamp_utc"] if samples else None
    duration = 0
    if first_ts and last_ts:
        duration = int(
            (
                datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                - datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            ).total_seconds()
        )
    latest = samples[-1] if samples else {}
    summary = {
        "baseline_revision": baseline_revision,
        "fixture_id": fixture_id,
        "scheduled_kickoff_utc": scheduled_kickoff_utc,
        "expected_alembic_head": expected_alembic_head,
        "selection_json_path": str(selection_json),
        "selection_sha256": selection_sha256,
        "started_at_utc": iso(started_at),
        "expected_end_utc": iso(expected_end),
        "completed_at_utc": iso(utc_now()) if completed else None,
        "completed": completed,
        "sample_count": len(samples),
        "duration_seconds": duration,
        "blockers": blockers,
        "latest_current_revision": (latest.get("current") or {}).get("revision"),
        "latest_systemd": latest.get("systemd"),
        "latest_container_health": {
            service: {
                "status": state.get("status"),
                "health": state.get("health"),
                "restart_count": state.get("restart_count"),
            }
            for service, state in (latest.get("containers") or {}).items()
        },
        "latest_quota": latest.get("quota"),
        "latest_forward": latest.get("forward"),
        "latest_gate": latest.get("gate"),
        "latest_listener_policy": latest.get("listeners"),
    }
    write_json(runtime / "summary.json", summary)
    return summary


def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def resolve_baseline_revision(current: Path, configured: str | None) -> str:
    if configured:
        return configured
    revision = current_revision(current, "").get("revision")
    if not revision:
        raise RuntimeError("Unable to resolve current deployment revision")
    return str(revision)


def run_observer(
    runtime: Path,
    current: Path,
    interval: int,
    duration: int,
    once: bool,
    baseline_revision: str,
    fixture_id: str,
    scheduled_kickoff_utc: str,
    expected_alembic_head: str,
    selection_json: Path,
    global_lock_path: Path,
) -> int:
    runtime.mkdir(parents=True, exist_ok=True)
    global_lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = global_lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("OBSERVATION_ALREADY_RUNNING", file=sys.stderr)
        return 2
    lock_handle.seek(0)
    lock_handle.truncate()
    lock_handle.write(f"{os.getpid()}\n")
    lock_handle.flush()
    pid_path = runtime / "observer.pid"
    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            existing_pid = 0
        if existing_pid != os.getpid() and process_is_running(existing_pid):
            print("OBSERVATION_ALREADY_RUNNING", file=sys.stderr)
            return 2
    selection = validate_selection(
        selection_json,
        fixture_id=fixture_id,
        scheduled_kickoff_utc=scheduled_kickoff_utc,
    )
    selection_hash = sha256_file(selection_json)
    kickoff = parse_utc(scheduled_kickoff_utc, "scheduled_kickoff_utc")
    if kickoff <= utc_now():
        raise ValueError("scheduled kickoff has already occurred")
    resolved_baseline = resolve_baseline_revision(current, baseline_revision)
    revision = current_revision(current, resolved_baseline)
    if not revision.get("matches_baseline"):
        raise ValueError("current revision does not match baseline")
    alembic = alembic_head_status(current, expected_alembic_head)
    if not alembic["matches_expected"]:
        raise ValueError("Alembic head does not match expected head")
    started_at = utc_now()
    expected_end = started_at + timedelta(seconds=duration)
    write_json(
        runtime / "start.json",
        {
            "status": "IN_PROGRESS",
            "fixture_id": fixture_id,
            "runtime_dir": str(runtime),
            "scheduled_kickoff_utc": scheduled_kickoff_utc,
            "baseline_revision": resolved_baseline,
            "expected_alembic_head": expected_alembic_head,
            "alembic": alembic,
            "selection_json_path": str(selection_json),
            "selection_sha256": selection_hash,
            "selection_source": selection.get("source"),
            "global_lock_path": str(global_lock_path),
            "lock_holder_pid": os.getpid(),
            "observer_id": f"stage7i-{fixture_id}-{os.getpid()}",
            "started_at_utc": iso(started_at),
            "observer_started_at_utc": iso(started_at),
            "expected_end_utc": iso(expected_end),
            "interval_seconds": interval,
            "duration_seconds": duration,
            "pid": os.getpid(),
            "candidate": False,
            "formal_recommendation": False,
            "gate5_eligible": False,
            "evidence_classification": "FORWARD_OBSERVATION",
            "initial_sample": {
                "fixture_id": fixture_id,
                "captured_at_utc": iso(started_at),
                "candidate": False,
                "formal_recommendation": False,
                "actual_kickoff_source": "ACTUAL_KICKOFF_SOURCE_UNAVAILABLE",
            },
        },
    )
    (runtime / "observer.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    state: dict[str, Any] = {}
    completed = False
    try:
        while True:
            sample = collect_sample(
                runtime,
                current,
                state,
                resolved_baseline,
                fixture_id,
                scheduled_kickoff_utc,
            )
            append_jsonl(runtime / "observations.jsonl", sample)
            append_jsonl(
                runtime / "observer.log",
                {
                    "timestamp_utc": sample["timestamp_utc"],
                    "sample_index": sum(
                        1
                        for _ in (runtime / "observations.jsonl").open(
                            encoding="utf-8"
                        )
                    ),
                    "blockers": sample["blockers"],
                },
            )
            if once:
                break
            if utc_now() >= expected_end:
                completed = True
                break
            time.sleep(interval)
    finally:
        summary = summarize(
            runtime,
            started_at,
            expected_end,
            completed,
            resolved_baseline,
            fixture_id,
            scheduled_kickoff_utc,
            expected_alembic_head,
            selection_json,
            selection_hash,
        )
        if completed:
            completed_content = json.dumps(summary, sort_keys=True) + "\n"
            (runtime / "COMPLETED").write_text(
                completed_content,
                encoding="utf-8",
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Observe W2 Stage7I staging runtime stability.")
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--current-dir", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--interval-seconds", type=int, default=SAMPLE_INTERVAL_SECONDS)
    parser.add_argument("--duration-seconds", type=int, default=OBSERVATION_SECONDS)
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--scheduled-kickoff-utc", required=True)
    parser.add_argument("--baseline-revision", required=True)
    parser.add_argument("--expected-alembic-head", required=True)
    parser.add_argument("--selection-json", type=Path, required=True)
    parser.add_argument("--global-lock-path", type=Path, default=DEFAULT_GLOBAL_LOCK)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    return run_observer(
        args.runtime_dir,
        args.current_dir,
        args.interval_seconds,
        args.duration_seconds,
        args.once,
        args.baseline_revision,
        args.fixture_id,
        args.scheduled_kickoff_utc,
        args.expected_alembic_head,
        args.selection_json,
        args.global_lock_path,
    )


if __name__ == "__main__":
    raise SystemExit(main())
