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
POLICY = ROOT / "config/policies/future_fixture_refresh.v1.json"
SCHEDULER = ROOT / "apps/scheduler/main.py"
FORBIDDEN_TRUE_FLAGS = {
    "W2_DEEPSEEK_ENABLED",
    "W2_RECOMMENDATION_ENABLED",
    "W2_CANDIDATE_ENABLED",
    "W2_PRODUCTION_RELEASE",
    "W2_EXTERNAL_ALERTING",
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
            elif current_section == "healthcheck":
                services[current_service].setdefault("healthcheck", {})
            continue
        if current_section == "environment" and line.startswith("      ") and ":" in line:
            key, value = line.strip().split(":", 1)
            services[current_service].setdefault("environment", {})[key] = parse_scalar(value)
        elif current_section == "ports" and line.startswith("      - "):
            port = parse_scalar(line.split("-", 1)[1])
            services[current_service].setdefault("ports", []).append(port)
        elif current_section == "healthcheck" and line.strip().startswith("test:"):
            _, value = line.strip().split(":", 1)
            services[current_service].setdefault("healthcheck", {})["test"] = ast.literal_eval(
                value.strip()
            )
    return {"services": services}


def service_env(compose: dict[str, Any], service: str) -> dict[str, Any]:
    services = compose.get("services")
    if not isinstance(services, dict):
        fail("compose services missing")
    definition = services.get(service)
    if not isinstance(definition, dict):
        fail(f"{service} service missing")
    env = definition.get("environment")
    if not isinstance(env, dict):
        fail(f"{service} environment missing")
    return env


def service_healthcheck(compose: dict[str, Any], service: str) -> list[Any]:
    services = compose.get("services")
    if not isinstance(services, dict):
        fail("compose services missing")
    definition = services.get(service)
    if not isinstance(definition, dict):
        fail(f"{service} service missing")
    healthcheck = definition.get("healthcheck")
    if not isinstance(healthcheck, dict):
        fail(f"{service} healthcheck missing")
    test = healthcheck.get("test")
    if not isinstance(test, list):
        fail(f"{service} healthcheck test must be list")
    return test


def assert_ports_not_public(compose: dict[str, Any], path: Path) -> None:
    for service, definition in compose.get("services", {}).items():
        for port in definition.get("ports", []) or []:
            value = str(port)
            if value.startswith(("0.0.0.0:", ":::")):
                fail(f"{path}: {service} exposes public port")


def assert_compose(path: Path) -> None:
    compose = load_yaml(path)
    scheduler_env = service_env(compose, "scheduler")
    if scheduler_env.get("W2_FUTURE_FIXTURE_REFRESH_ENABLED") != "true":
        fail(f"{path}: scheduler future refresh enable flag missing")
    if scheduler_env.get("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID") != "world_cup_2026":
        fail(f"{path}: scheduler future refresh competition mismatch")
    for service in ("api", "web", "worker"):
        env = service_env(compose, service)
        if "W2_FUTURE_FIXTURE_REFRESH_ENABLED" in env:
            fail(f"{path}: {service} must not enable scheduler future refresh")
    for flag in FORBIDDEN_TRUE_FLAGS:
        if str(scheduler_env.get(flag)).lower() != "false":
            fail(f"{path}: {flag} must stay false")
    health = " ".join(str(item) for item in service_healthcheck(compose, "scheduler"))
    if "future_fixture_refresh_contract_ready" not in health:
        fail(f"{path}: scheduler healthcheck missing enablement contract")
    if "future_fixture_refresh_tick" in health or "send_task" in health:
        fail(f"{path}: scheduler healthcheck must not dispatch")
    assert_ports_not_public(compose, path)


def assert_policy() -> None:
    import json

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    competitions = policy.get("competitions")
    if not isinstance(competitions, list):
        fail("future refresh policy competitions missing")
    match = next(
        (item for item in competitions if item.get("competition_id") == "world_cup_2026"),
        None,
    )
    if not isinstance(match, dict):
        fail("world_cup_2026 policy missing")
    if match.get("enabled") is not True:
        fail("world_cup_2026 policy must be enabled")
    if match.get("season") != "2026":
        fail("world_cup_2026 policy season mismatch")


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
