#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised when system Python lacks PyYAML.
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILES = [
    ROOT / "infra/compose/compose.staging.yml",
    ROOT / "infra/compose/staging-lite.override.yml",
]
EXPECTED_RUNTIME_MOUNT_SOURCES = {
    ROOT / "infra/compose/compose.staging.yml": "../../runtime",
    ROOT / "infra/compose/staging-lite.override.yml": "./runtime",
}
POLICY_MOUNT_TARGET = "/app/config/policies"
CONFIG_MOUNT_TARGET = "/app/config"
RUNTIME_MOUNT_TARGET = "/app/runtime"
MARKET_TIMELINE_MOUNT_TARGET = "/app/market_timeline_snapshots"
EXPECTED_CONFIG_MOUNT_SOURCES = {
    ROOT / "infra/compose/compose.staging.yml": "../../config",
    ROOT / "infra/compose/staging-lite.override.yml": "./config",
}
EXPECTED_MARKET_TIMELINE_MOUNT_SOURCES = {
    ROOT / "infra/compose/compose.staging.yml": "../../runtime/market_timeline_snapshots",
    ROOT / "infra/compose/staging-lite.override.yml": "./runtime/market_timeline_snapshots",
}
POLICY = ROOT / "config/policies/future_fixture_refresh.v1.json"
SCHEDULER = ROOT / "apps/scheduler/main.py"
FORBIDDEN_TRUE_FLAGS = {
    "W2_DEEPSEEK_ENABLED",
    "W2_RECOMMENDATION_ENABLED",
    "W2_CANDIDATE_ENABLED",
    "W2_PRODUCTION_RELEASE",
    "W2_EXTERNAL_ALERTING",
}
ALLOWED_PUBLIC_PORTS = {
    (ROOT / "infra/compose/compose.staging.yml", "web", "127.0.0.1:18080:8080"),
}


def fail(message: str) -> None:
    print(f"future_refresh_staging_contract FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_scalar(value: str) -> str:
    parsed = value.strip()
    if parsed.startswith('"') and parsed.endswith('"'):
        return parsed[1:-1]
    return parsed


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text)
    return load_compose_subset(text)


def load_compose_subset(text: str) -> dict[str, Any]:
    services: dict[str, dict[str, Any]] = {}
    current_service: str | None = None
    current_section: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            current_service = line.strip()[:-1]
            services.setdefault(current_service, {})
            current_section = None
            continue
        if current_service is None:
            continue
        if line.startswith("    ") and not line.startswith("      ") and line.strip().endswith(":"):
            current_section = line.strip()[:-1]
            if current_section == "environment":
                services[current_service].setdefault("environment", {})
            elif current_section == "ports":
                services[current_service].setdefault("ports", [])
            elif current_section == "volumes":
                services[current_service].setdefault("volumes", [])
            elif current_section == "healthcheck":
                services[current_service].setdefault("healthcheck", {})
            continue
        if current_section == "environment" and line.startswith("      ") and ":" in line:
            key, value = line.strip().split(":", 1)
            services[current_service].setdefault("environment", {})[key] = parse_scalar(value)
        elif current_section == "ports" and line.startswith("      - "):
            port = parse_scalar(line.split("-", 1)[1])
            services[current_service].setdefault("ports", []).append(port)
        elif current_section == "volumes" and line.startswith("      - "):
            volume = parse_scalar(line.split("-", 1)[1])
            services[current_service].setdefault("volumes", []).append(volume)
        elif current_section == "healthcheck" and line.strip().startswith("test:"):
            _, value = line.strip().split(":", 1)
            services[current_service].setdefault("healthcheck", {})["test"] = ast.literal_eval(
                value.strip()
            )
    return {"services": services}


def service_definition(compose: dict[str, Any], service: str) -> dict[str, Any]:
    services = compose.get("services")
    if not isinstance(services, dict):
        fail("compose services missing")
    definition = services.get(service)
    if not isinstance(definition, dict):
        fail(f"{service} service missing")
    return definition


def service_env(compose: dict[str, Any], service: str) -> dict[str, Any]:
    definition = service_definition(compose, service)
    env = definition.get("environment")
    if not isinstance(env, dict):
        fail(f"{service} environment missing")
    return env


def service_healthcheck(compose: dict[str, Any], service: str) -> list[Any]:
    definition = service_definition(compose, service)
    healthcheck = definition.get("healthcheck")
    if not isinstance(healthcheck, dict):
        fail(f"{service} healthcheck missing")
    test = healthcheck.get("test")
    if not isinstance(test, list):
        fail(f"{service} healthcheck test must be list")
    return test


def service_volumes(compose: dict[str, Any], service: str) -> list[Any]:
    definition = service_definition(compose, service)
    volumes = definition.get("volumes", [])
    if not isinstance(volumes, list):
        fail(f"{service} volumes missing")
    return volumes


def split_volume(volume: Any) -> tuple[str, str, str | None]:
    if isinstance(volume, str):
        parts = volume.split(":")
        if len(parts) < 2:
            fail(f"invalid volume mount: {volume}")
        mode = parts[2] if len(parts) > 2 else None
        return parts[0], parts[1], mode
    if isinstance(volume, dict):
        source = str(volume.get("source") or volume.get("src") or "")
        target = str(volume.get("target") or volume.get("dst") or volume.get("destination") or "")
        read_only = volume.get("read_only")
        mode = "ro" if read_only is True else str(volume.get("mode") or "")
        return source, target, mode or None
    fail(f"unsupported volume mount shape: {volume!r}")


def assert_no_runtime_policy_mount(path: Path, compose: dict[str, Any]) -> None:
    for service in ("api", "web", "worker", "scheduler"):
        mounts = [
            split_volume(volume)
            for volume in service_volumes(compose, service)
            if split_volume(volume)[1] == POLICY_MOUNT_TARGET
        ]
        if mounts:
            fail(f"{path}: {service} must not mount install-seed policy as runtime authority")


def assert_config_mount(path: Path, compose: dict[str, Any]) -> None:
    expected_source = EXPECTED_CONFIG_MOUNT_SOURCES[path]
    for service in ("api", "worker", "scheduler"):
        matches = [
            split_volume(volume)
            for volume in service_volumes(compose, service)
            if split_volume(volume)[1] == CONFIG_MOUNT_TARGET
        ]
        if len(matches) != 1:
            fail(f"{path}: {service} must have exactly one full config mount")
        source, target, mode = matches[0]
        if source != expected_source:
            fail(f"{path}: {service} config mount source mismatch")
        if target != CONFIG_MOUNT_TARGET:
            fail(f"{path}: {service} config mount target mismatch")
        if mode != "ro":
            fail(f"{path}: {service} config mount must be read-only")
    if not (ROOT / "config/competitions/national_leagues/allsvenskan.v1.json").is_file():
        fail("allsvenskan competition registry config missing")


def assert_runtime_mount(path: Path, compose: dict[str, Any]) -> None:
    expected_source = EXPECTED_RUNTIME_MOUNT_SOURCES[path]
    expected_market_timeline_source = EXPECTED_MARKET_TIMELINE_MOUNT_SOURCES[path]
    for service in ("api", "worker", "scheduler"):
        matches = [
            split_volume(volume)
            for volume in service_volumes(compose, service)
            if split_volume(volume)[1] == RUNTIME_MOUNT_TARGET
        ]
        if len(matches) != 1:
            fail(f"{path}: {service} must have exactly one runtime mount")
        source, target, mode = matches[0]
        if source != expected_source:
            fail(f"{path}: {service} runtime mount source mismatch")
        if target != RUNTIME_MOUNT_TARGET:
            fail(f"{path}: {service} runtime mount target mismatch")
        timeline_matches = [
            split_volume(volume)
            for volume in service_volumes(compose, service)
            if split_volume(volume)[1] == MARKET_TIMELINE_MOUNT_TARGET
        ]
        if len(timeline_matches) != 1:
            fail(f"{path}: {service} must have exactly one market timeline mount")
        timeline_source, timeline_target, _ = timeline_matches[0]
        if timeline_source != expected_market_timeline_source:
            fail(f"{path}: {service} market timeline mount source mismatch")
        if timeline_target != MARKET_TIMELINE_MOUNT_TARGET:
            fail(f"{path}: {service} market timeline mount target mismatch")


def assert_worker_runtime_healthcheck(path: Path, compose: dict[str, Any]) -> None:
    health = " ".join(str(item) for item in service_healthcheck(compose, "worker"))
    if "os.path.isdir('/app/runtime')" not in health:
        fail(f"{path}: worker healthcheck must verify runtime directory")
    if "os.access('/app/runtime', os.W_OK)" in health:
        fail(f"{path}: worker healthcheck must not require runtime writability")
    if any(token in health for token in ("open(", "write(", "touch", "mkdir", "remove", "unlink")):
        fail(f"{path}: worker runtime healthcheck must be side-effect free")


def assert_public_ports_allowlisted(compose: dict[str, Any], path: Path) -> None:
    for service, definition in compose.get("services", {}).items():
        for port in definition.get("ports", []) or []:
            value = str(port)
            if value.startswith(("0.0.0.0:", ":::")) and (
                path,
                str(service),
                value,
            ) not in ALLOWED_PUBLIC_PORTS:
                fail(f"{path}: {service} exposes public port")


def assert_compose(path: Path) -> None:
    compose = load_yaml(path)
    assert_config_mount(path, compose)
    assert_no_runtime_policy_mount(path, compose)
    assert_runtime_mount(path, compose)
    assert_worker_runtime_healthcheck(path, compose)
    scheduler_env = service_env(compose, "scheduler")
    if scheduler_env.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED") != "false":
        fail(f"{path}: scheduler future refresh must default disabled")
    for removed in (
        "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID",
        "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_IDS",
        "W2_STAGING_ENABLED_COMPETITIONS",
    ):
        if removed in scheduler_env:
            fail(f"{path}: scheduler removed DB-owned switch remains: {removed}")
    if scheduler_env.get("W2_PROVIDER_CALLS_DISABLED") != "true":
        fail(f"{path}: scheduler provider calls must default disabled")
    if scheduler_env.get("W2_PROVIDER_SCHEDULER_ENABLED") != "false":
        fail(f"{path}: scheduler provider scheduler must default disabled")
    if scheduler_env.get("W2_MARKET_TIMELINE_REFRESH_ENABLED") != "true":
        fail(f"{path}: scheduler market timeline refresh enable flag missing")
    if scheduler_env.get("W2_MARKET_TIMELINE_MAX_FIXTURES") != "10":
        fail(f"{path}: scheduler market timeline max fixtures must be 10")
    if scheduler_env.get("W2_MARKET_TIMELINE_RUNTIME_ROOT") != MARKET_TIMELINE_MOUNT_TARGET:
        fail(f"{path}: scheduler market timeline runtime root mismatch")
    safe_defaults = {
        "W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS": "900",
        "W2_PROVIDER_ENDPOINT_ALLOWLIST": "status,fixtures,odds,lineups",
        "W2_PROVIDER_REFRESH_TICK_HARD_CAP": "30",
    }
    for flag, expected in safe_defaults.items():
        if scheduler_env.get(flag) != expected:
            fail(f"{path}: scheduler {flag} mismatch")
    for service in ("api", "web", "worker"):
        env = service_env(compose, service)
        if "W2_FUTURE_FIXTURE_REFRESH_ENABLED" in env:
            fail(f"{path}: {service} must not enable scheduler future refresh")
        if service == "api":
            if env.get("W2_PROVIDER_CALLS_DISABLED") != "true":
                fail(f"{path}: api provider calls must stay disabled")
            if env.get("W2_PROVIDER_SCHEDULER_ENABLED") != "false":
                fail(f"{path}: api provider scheduler must stay disabled")
            if "W2_STAGING_ENABLED_COMPETITIONS" in env:
                fail(f"{path}: api staging competition override remains")
        if service == "worker":
            if env.get("W2_PROVIDER_CALLS_DISABLED") != "true":
                fail(f"{path}: worker provider calls must default disabled")
            if env.get("W2_PROVIDER_SCHEDULER_ENABLED") != "false":
                fail(f"{path}: worker provider scheduler must default disabled")
            if "W2_STAGING_ENABLED_COMPETITIONS" in env:
                fail(f"{path}: worker staging competition override remains")
        if service in {"api", "worker"} and env.get("W2_MARKET_TIMELINE_RUNTIME_ROOT") != (
            MARKET_TIMELINE_MOUNT_TARGET
        ):
            fail(f"{path}: {service} market timeline runtime root mismatch")
        if service in {"api", "worker"}:
            for flag, expected in safe_defaults.items():
                if env.get(flag) != expected:
                    fail(f"{path}: {service} {flag} mismatch")
            if str(env.get("W2_XG_BACKFILL_ENABLED")).lower() != "false":
                fail(f"{path}: {service} W2_XG_BACKFILL_ENABLED must stay false")
    for flag in FORBIDDEN_TRUE_FLAGS:
        if str(scheduler_env.get(flag)).lower() != "false":
            fail(f"{path}: {flag} must stay false")
    health = " ".join(str(item) for item in service_healthcheck(compose, "scheduler"))
    if "future_fixture_refresh_contract_ready" not in health:
        fail(f"{path}: scheduler healthcheck missing enablement contract")
    if "future_fixture_refresh_tick" in health or "send_task" in health:
        fail(f"{path}: scheduler healthcheck must not dispatch")
    assert_public_ports_allowlisted(compose, path)


def assert_policy() -> None:
    import json

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    competitions = policy.get("competitions")
    if not isinstance(competitions, list):
        fail("future refresh policy competitions missing")
    # Legacy tournament policy remains for historical replay compatibility;
    # the league whitelist and staging default exclude it.
    expected_staging = {
        "brasileirao_serie_a": ("71", "2026"),
        "chinese_super_league": ("169", "2026"),
        "allsvenskan": ("113", "2026"),
        "eliteserien": ("103", "2026"),
    }
    for competition_id, (league_id, season) in expected_staging.items():
        item = next(
            (row for row in competitions if row.get("competition_id") == competition_id),
            None,
        )
        if not isinstance(item, dict):
            fail(f"{competition_id} policy missing")
        if item.get("provider_league_id") != league_id:
            fail(f"{competition_id} provider league mismatch")
        if item.get("season") != season:
            fail(f"{competition_id} season mismatch")
        if item.get("enabled") is not True:
            fail(f"{competition_id} policy must be enabled behind staging registry override")
        if item.get("request_budget") != 10:
            fail(f"{competition_id} request_budget must stay at 10 for lite staging seed")
        if item.get("daily_hard_cap") != 120:
            fail(f"{competition_id} daily_hard_cap must stay at 120 for R2.3")
        if item.get("daily_reserve") != 0:
            fail(f"{competition_id} daily_reserve must stay at 0 for R2.3 lite seed")
        if competition_id == "allsvenskan":
            if item.get("feature_enrichment_enabled") is not True:
                fail("allsvenskan lineup enrichment must stay enabled")
            if item.get("feature_enrichment_endpoints") != ["lineups"]:
                fail("allsvenskan enrichment must be lineups-only")
            if item.get("feature_enrichment_request_budget") != 3:
                fail("allsvenskan lineup enrichment budget must stay at 3")
        else:
            if item.get("feature_enrichment_enabled") is not False:
                fail(f"{competition_id} feature enrichment must stay disabled for lite seed")
            if item.get("feature_enrichment_endpoints") != []:
                fail(f"{competition_id} feature enrichment endpoints must stay empty")
            if item.get("feature_enrichment_request_budget") != 0:
                fail(f"{competition_id} feature enrichment budget must stay at 0")
        if item.get("max_odds_requests") != 8:
            fail(f"{competition_id} max_odds_requests must stay at 8 for R2.3")


def assert_scheduler_default_fail_closed() -> None:
    tree = ast.parse(SCHEDULER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "future_fixture_refresh_enabled":
            source = ast.get_source_segment(SCHEDULER.read_text(encoding="utf-8"), node) or ""
            if '"false"' not in source and "'false'" not in source:
                fail("scheduler future refresh default must remain false")
            return
    fail("future_fixture_refresh_enabled missing")


def main() -> int:
    for path in COMPOSE_FILES:
        assert_compose(path)
    assert_policy()
    assert_scheduler_default_fail_closed()
    print("future_refresh_staging_contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
