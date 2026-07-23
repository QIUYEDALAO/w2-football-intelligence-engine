from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from apps.scheduler.main import (
    future_fixture_refresh_contract_ready,
    future_fixture_refresh_tick,
)
from apps.worker.celery_app import celery_app

from w2.competitions.seed import set_competition_enabled
from w2.infrastructure.database import create_engine
from w2.refresh.matchday_schedule import MatchdayRefreshPolicy, build_matchday_refresh_plan

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


def test_staging_compose_defaults_future_refresh_and_provider_calls_disabled() -> None:
    for path in COMPOSE_PATHS:
        scheduler = env_for(path, "scheduler")
        assert scheduler["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "false"
        assert "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_ID" not in scheduler
        assert "W2_FUTURE_FIXTURE_REFRESH_COMPETITION_IDS" not in scheduler
        assert scheduler["W2_PROVIDER_CALLS_DISABLED"] == "true"
        assert scheduler["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
        assert scheduler["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
        assert scheduler["W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS"] == "900"
        assert scheduler["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == "status,fixtures,odds,lineups"
        assert scheduler["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
        assert scheduler["W2_PROVIDER_DAILY_HARD_CAP"] == "120"
        assert "W2_STAGING_ENABLED_COMPETITIONS" not in scheduler
        assert scheduler["W2_XG_BACKFILL_ENABLED"] == "false"
        assert scheduler["W2_MARKET_TIMELINE_REFRESH_ENABLED"] == "true"
        assert scheduler["W2_MARKET_TIMELINE_WINDOW"] == "future"
        assert scheduler["W2_FORWARD_OUTCOME_LEDGER_ENABLED"] == (
            "${W2_FORWARD_OUTCOME_LEDGER_ENABLED:-true}"
        )
        assert scheduler["W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE"] == (
            "${W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE:-true}"
        )
        assert scheduler["W2_FORWARD_OUTCOME_LEDGER_WINDOW"] == (
            "${W2_FORWARD_OUTCOME_LEDGER_WINDOW:-future}"
        )
        api = env_for(path, "api")
        assert api["W2_PROVIDER_CALLS_DISABLED"] == "true"
        assert api["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
        assert api["W2_PROVIDER_DAILY_HARD_CAP"] == "120"
        assert "W2_STAGING_ENABLED_COMPETITIONS" not in api
        for service in ("worker",):
            env = env_for(path, service)
            assert env["W2_PROVIDER_CALLS_DISABLED"] == "true"
            assert env["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
            assert env["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
            assert env["W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS"] == "900"
            assert env["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == "status,fixtures,odds,lineups"
            assert env["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
            assert env["W2_PROVIDER_DAILY_HARD_CAP"] == "120"
            assert "W2_STAGING_ENABLED_COMPETITIONS" not in env
            assert env["W2_XG_BACKFILL_ENABLED"] == "false"
        for service in ("api", "web", "worker"):
            assert "W2_FUTURE_FIXTURE_REFRESH_ENABLED" not in env_for(path, service)


def test_staging_compose_does_not_mount_install_seed_policy_as_runtime_authority() -> None:
    for path in COMPOSE_PATHS:
        for service in ("api", "web", "worker", "scheduler"):
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
            mounts = [volume for volume in volumes_for(path, service) if ":/app/config:" in volume]
            assert mounts == [f"{expected_sources[path]}:/app/config:ro"]


def test_staging_compose_keeps_production_and_recommendation_flags_off() -> None:
    for path in COMPOSE_PATHS:
        scheduler = env_for(path, "scheduler")
        assert scheduler["W2_DEEPSEEK_ENABLED"] == "false"
        assert scheduler["W2_RECOMMENDATION_ENABLED"] == "false"
        assert scheduler["W2_CANDIDATE_ENABLED"] == "false"
        assert scheduler["W2_PRODUCTION_RELEASE"] == "false"
        assert scheduler["W2_EXTERNAL_ALERTING"] == "false"


def test_world_cup_legacy_policy_does_not_restore_league_whitelist() -> None:
    import json

    policy = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(encoding="utf-8")
    )
    assert any(item["competition_id"] == "world_cup_2026" for item in policy["competitions"])
    from w2.competitions.league_whitelist_scope import ALL_WHITELIST_COMPETITIONS

    assert "world_cup_2026" not in ALL_WHITELIST_COMPETITIONS


def test_scheduler_tick_stays_disabled_without_env_flag(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"


def test_matchday_refresh_plan_excludes_xg_backfill_by_default() -> None:
    plan = build_matchday_refresh_plan(
        [
            {
                "fixture_id": "fixture-1",
                "competition_id": "allsvenskan",
                "kickoff_utc": "2026-07-05T03:00:00Z",
            }
        ],
        as_of=datetime(2026, 7, 4, 0, 0, tzinfo=UTC),
        policy=MatchdayRefreshPolicy(competition_id="allsvenskan"),
    )

    assert plan
    for tick in plan:
        assert tick.allowed_endpoints == ("status", "fixtures", "odds", "lineups")
        assert "xg" not in tick.allowed_endpoints
        assert "xg_history_backfill" not in tick.task_key


def test_scheduler_tick_queues_without_running_provider(monkeypatch) -> None:
    sent: list[dict[str, Any]] = []

    def fake_send_task(name: str, **kwargs: Any) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        "apps.scheduler.main.due_checkpoint_refresh_batch",
        lambda now, **kwargs: {
            "status": "READY",
            "generated_plan_count": 8,
            "due_checkpoint_count": 1,
            "selected_checkpoint_count": 1,
            "projected_calls": 3,
            "all_due_projected_calls": 3,
            "tick_hard_cap": 30,
            "checkpoints": [
                {
                    "fixture_id": "1489404",
                    "checkpoint": "T24",
                    "kickoff_utc": "2026-06-24T17:00:00Z",
                    "due_at": "2026-06-23T17:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "apps.scheduler.main.provider_task_key_gate",
        lambda **kwargs: type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )(),
    )
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(
        "apps.scheduler.main.future_fixture_refresh_competition_ids",
        lambda: ("allsvenskan",),
    )

    engine = create_engine()
    set_competition_enabled(
        engine,
        competition_id="allsvenskan",
        enabled=True,
        updated_by="contract-test",
    )
    try:
        result = future_fixture_refresh_tick()
    finally:
        set_competition_enabled(
            engine,
            competition_id="allsvenskan",
            enabled=False,
            updated_by="contract-test-cleanup",
        )

    assert result["status"] == "QUEUED"
    assert result["competition_id"] == "allsvenskan"
    assert sent[0]["name"] == "w2.future_fixture_refresh"


def test_health_contract_has_no_dispatch_or_runtime_side_effect(monkeypatch) -> None:
    def forbidden_send_task(*args: Any, **kwargs: Any) -> None:  # pragma: no cover
        raise AssertionError("health contract must not dispatch")

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setattr(celery_app, "send_task", forbidden_send_task)
    runtime_path = ROOT / "runtime/future_refresh"
    before_exists = runtime_path.exists()

    assert future_fixture_refresh_contract_ready()
    assert runtime_path.exists() is before_exists


def test_health_contract_fails_closed_when_database_authority_is_missing(monkeypatch) -> None:
    from w2.competitions.registry import CompetitionRegistryError

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setattr(
        "w2.ingestion.future_refresh.CompetitionRegistry",
        lambda: (_ for _ in ()).throw(CompetitionRegistryError("DB_UNAVAILABLE")),
    )

    assert not future_fixture_refresh_contract_ready()


def test_scheduler_healthcheck_contains_enablement_contract() -> None:
    for path in COMPOSE_PATHS:
        healthcheck = load_compose(path)["services"]["scheduler"]["healthcheck"]["test"]
        text = " ".join(str(item) for item in healthcheck)
        assert "future_fixture_refresh_contract_ready" in text
        assert "future_fixture_refresh_tick" not in text
        assert "send_task" not in text
