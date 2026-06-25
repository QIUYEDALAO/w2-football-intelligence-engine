from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts/check_compose_staging_ports.py"
STAGING_COMPOSE = ROOT / "infra/compose/compose.staging.yml"


def load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("compose_staging_ports", CHECKER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_compose() -> dict[str, Any]:
    return yaml.safe_load(STAGING_COMPOSE.read_text(encoding="utf-8"))


def test_staging_web_public_binding_is_allowlisted() -> None:
    checker = load_checker()
    compose = load_compose()

    assert checker.service_ports(compose, "web") == ["0.0.0.0:80:8080"]
    checker.assert_no_public_ports(checker.service_ports(compose, "web"), "web")


def test_staging_api_public_binding_is_rejected() -> None:
    checker = load_checker()

    with pytest.raises(SystemExit):
        checker.assert_no_public_ports(["0.0.0.0:18000:8000"], "api")
