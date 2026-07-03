from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from apps.scheduler.main import (
    future_fixture_refresh_contract_ready,
    future_fixture_refresh_tick,
)
from apps.worker.celery_app import celery_app

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATHS = [
    ROOT / "infra/compose/compose.staging.yml",
    ROOT / "infra/compose/staging-lite.override.yml",
]


def load_compose(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def env_for(path: Path, service: str) -> dict[str, Any]:
    return load_compose(path)["services"][service]["environment"]


def volumes_for(path: Path, service: str) -> list[str]:
    return [str(volume) for volume in load_compose(path)["services"][service].get("volumes", [])]


def test_staging_compose_enables_scheduler_future_refresh_only() -> None:
    for path in COMPOSE_PATHS:
        scheduler = env_for(path, "scheduler")
        assert scheduler["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "true"
        assert scheduler["W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID"] == "world_cup_2026"
        assert scheduler["W2_PROVIDER_CALLS_DISABLED"] == "true"
        assert scheduler["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
        assert scheduler["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
        assert scheduler["W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS"] == "900"
        assert scheduler["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == "status,fixtures,odds,lineups"
        assert scheduler["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
        assert scheduler["W2_XG_BACKFILL_ENABLED"] == "false"
        for service in ("api", "worker"):
            env = env_for(path, service)
            assert env["W2_PROVIDER_CALLS_DISABLED"] == "true"
            assert env["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
            assert env["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
            assert env["W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS"] == "900"
            assert env["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == "status,fixtures,odds,lineups"
            assert env["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
            assert env["W2_XG_BACKFILL_ENABLED"] == "false"
        for service in ("api", "web", "worker"):
            assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in env_for(path, service)


def test_staging_compose_mounts_versioned_policy_for_worker_and_scheduler_only() -> None:
    expected_sources = {
        ROOT / "infra/compose/compose.staging.yml": "../../config/policies",
        ROOT / "infra/compose/staging-lite.override.yml": "./config/policies",
    }
    for path in COMPOSE_PATHS:
        for service in ("worker", "scheduler"):
            mounts = [
                volume
                for volume in volumes_for(path, service)
                if ":/app/config/policies:" in volume
            ]
            assert mounts == [f"{expected_sources[path]}:/app/config/policies:ro"]
        for service in ("api", "web"):
            assert not [
                volume
                for volume in volumes_for(path, service)
                if ":/app/config/policies:" in volume
            ]


def test_staging_compose_mounts_full_config_for_runtime_services() -> None:
    expected_sources = {
        ROOT / "infra/compose/compose.staging.yml": "../../config",
        ROOT / "infra/compose/staging-lite.override.yml": "./config",
    }
    assert (ROOT / "config/competitions/world_cup_2026.v1.json").is_file()
    for path in COMPOSE_PATHS:
        for service in ("api", "worker", "scheduler"):
            mounts = [
                volume
                for volume in volumes_for(path, service)
                if ":/app/config:" in volume
            ]
            assert mounts == [f"{expected_sources[path]}:/app/config:ro"]


def test_staging_compose_keeps_production_and_recommendation_flags_off() -> None:
    for path in COMPOSE_PATHS:
        scheduler = env_for(path, "scheduler")
        assert scheduler["W2_DEEPSEEK_ENABLED"] == "false"
        assert scheduler["W2_RECOMMENDATION_ENABLED"] == "false"
        assert scheduler["W2_CANDIDATE_ENABLED"] == "false"
        assert scheduler["W2_PRODUCTION_RELEASE"] == "false"
        assert scheduler["W2_EXTERNAL_ALERTING"] == "false"


def test_future_refresh_policy_matches_staging_competition() -> None:
    import json

    policy = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(encoding="utf-8")
    )
    world_cup = next(
        item for item in policy["competitions"] if item["competition_id"] == "world_cup_2026"
    )
    assert world_cup["enabled"] is True
    assert world_cup["season"] == "2026"


def test_scheduler_tick_stays_disabled_without_env_flag(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"


def test_scheduler_tick_queues_without_running_provider(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []

    def fake_send_task(name: str, **kwargs: Any) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        "apps.scheduler.main.provider_task_key_gate",
        lambda **kwargs: type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )(),
    )
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert result["competition_id"] == "world_cup_2026"
    assert sent[0]["name"] == "w2.future_fixture_refresh"


def test_health_contract_has_no_dispatch_or_runtime_side_effect(monkeypatch) -> None:
    def forbidden_send_task(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("health contract must not dispatch")

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    monkeypatch.setattr(celery_app, "send_task", forbidden_send_task)
    runtime_path = ROOT / "runtime/future_refresh"
    before_exists = runtime_path.exists()

    assert future_fixture_refresh_contract_ready()
    assert runtime_path.exists() is before_exists


def test_health_contract_fails_closed_when_policy_is_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID", "world_cup_2026")
    monkeypatch.chdir(tmp_path)

    assert not future_fixture_refresh_contract_ready()


def test_scheduler_healthcheck_contains_enablement_contract() -> None:
    for path in COMPOSE_PATHS:
        healthcheck = load_compose(path)["services"]["scheduler"]["healthcheck"]["test"]
        text = " ".join(str(item) for item in healthcheck)
        assert "future_fixture_refresh_contract_ready" in text
        assert "future_fixture_refresh_tick" not in text
        assert "send_task" not in text
