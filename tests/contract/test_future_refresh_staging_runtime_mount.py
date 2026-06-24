from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
STANDALONE = ROOT / "infra/compose/compose.staging.yml"
LITE = ROOT / "infra/compose/staging-lite.override.yml"
CHECKER = ROOT / "scripts/check_w2_future_refresh_staging_contract.py"


def load_compose(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_checker() -> Any:
    spec = importlib.util.spec_from_file_location("future_refresh_staging_contract", CHECKER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def volume_source(compose: dict[str, Any], service: str, target: str) -> str:
    for volume in compose["services"][service]["volumes"]:
        source, destination, *_ = str(volume).split(":")
        if destination == target:
            return source
    raise AssertionError(f"{service} missing {target} mount")


def volume_mode(compose: dict[str, Any], service: str, target: str) -> str | None:
    for volume in compose["services"][service]["volumes"]:
        parts = str(volume).split(":")
        if parts[1] == target:
            return parts[2] if len(parts) > 2 else None
    raise AssertionError(f"{service} missing {target} mount")


def test_standalone_runtime_mount_resolves_to_release_root_runtime() -> None:
    compose = load_compose(STANDALONE)
    for service in ("api", "worker", "scheduler"):
        assert volume_source(compose, service, "/app/runtime") == "../../runtime"
        assert volume_mode(compose, service, "/app/runtime") != "ro"


def test_staging_lite_runtime_mount_remains_root_relative() -> None:
    compose = load_compose(LITE)
    for service in ("api", "worker", "scheduler"):
        assert volume_source(compose, service, "/app/runtime") == "./runtime"
        assert volume_mode(compose, service, "/app/runtime") != "ro"


def test_api_worker_scheduler_share_one_runtime_mount_per_compose() -> None:
    for path in (STANDALONE, LITE):
        compose = load_compose(path)
        sources = {
            volume_source(compose, service, "/app/runtime")
            for service in ("api", "worker", "scheduler")
        }
        assert len(sources) == 1


def test_worker_runtime_healthcheck_is_writable_and_side_effect_free() -> None:
    for path in (STANDALONE, LITE):
        compose = load_compose(path)
        healthcheck = " ".join(
            str(item) for item in compose["services"]["worker"]["healthcheck"]["test"]
        )
        assert "os.path.isdir('/app/runtime')" in healthcheck
        assert "os.access('/app/runtime', os.W_OK)" in healthcheck
        assert "open(" not in healthcheck
        assert "write(" not in healthcheck
        assert "mkdir" not in healthcheck
        assert "touch" not in healthcheck
        assert "remove" not in healthcheck
        assert "unlink" not in healthcheck


def test_checker_rejects_standalone_runtime_inside_compose_directory() -> None:
    checker = load_checker()
    compose = load_compose(STANDALONE)
    volumes = compose["services"]["worker"]["volumes"]
    compose["services"]["worker"]["volumes"] = [
        "./runtime:/app/runtime" if str(volume).endswith(":/app/runtime") else volume
        for volume in volumes
    ]
    with pytest.raises(SystemExit):
        checker.assert_runtime_mount(STANDALONE, compose)


def test_no_root_or_permission_workaround_for_worker() -> None:
    compose = load_compose(STANDALONE)
    worker = compose["services"]["worker"]
    assert worker.get("user") not in ("root", "0")
    assert worker.get("privileged") is not True
    assert "0777" not in STANDALONE.read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile.worker").read_text(encoding="utf-8")
    assert "USER w2" in dockerfile
