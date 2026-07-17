from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_w2_future_refresh_staging_contract.py"
STAGING_COMPOSE = ROOT / "infra/compose/compose.staging.yml"


def load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("future_refresh_staging_contract", CHECKER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replace_config_mounts(compose: dict[str, Any], source: str) -> dict[str, Any]:
    mutated = dict(compose)
    services = dict(mutated["services"])
    mutated["services"] = services
    for service in ("api", "worker", "scheduler"):
        definition = dict(services[service])
        services[service] = definition
        volumes = []
        for volume in definition.get("volumes", []):
            if isinstance(volume, str) and ":/app/config:" in volume:
                volumes.append(f"{source}:/app/config:ro")
            else:
                volumes.append(volume)
        definition["volumes"] = volumes
    return mutated


def test_predeploy_contract_rejects_infra_compose_config_mount() -> None:
    checker = load_checker()
    compose = checker.load_yaml(STAGING_COMPOSE)
    broken = replace_config_mounts(compose, "./config")

    with pytest.raises(SystemExit):
        checker.assert_config_mount(STAGING_COMPOSE, broken)


def test_predeploy_contract_accepts_release_root_config_mount() -> None:
    checker = load_checker()
    compose = checker.load_yaml(STAGING_COMPOSE)

    checker.assert_config_mount(STAGING_COMPOSE, compose)


def test_predeploy_contract_allows_only_public_staging_web() -> None:
    checker = load_checker()
    compose = checker.load_yaml(STAGING_COMPOSE)

    checker.assert_public_ports_allowlisted(compose, STAGING_COMPOSE)


def test_predeploy_contract_rejects_public_api_port() -> None:
    checker = load_checker()
    compose = checker.load_yaml(STAGING_COMPOSE)
    compose["services"]["api"]["ports"] = ["0.0.0.0:18000:8000"]

    with pytest.raises(SystemExit):
        checker.assert_public_ports_allowlisted(compose, STAGING_COMPOSE)
