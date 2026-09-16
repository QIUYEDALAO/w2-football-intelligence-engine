from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from apps.scheduler.main import (
    future_fixture_refresh_contract_ready,
    future_fixture_refresh_tick,
)
from apps.worker.celery_app import celery_app
from sqlalchemy.orm import Session

from w2.competitions.seed import set_competition_enabled
from w2.infrastructure.database import create_engine
from w2.infrastructure.persistence.league_models import LeagueSeasonModel
from w2.refresh.matchday_schedule import MatchdayRefreshPolicy, build_matchday_refresh_plan

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_shared_competition_environment_stamp() -> Iterator[None]:
    """Put the shared competition database's environment stamp back.

    Tests here set ``W2_ENVIRONMENT=staging`` and then reach the shared database.
    conftest's registry adapter re-stamps every league season row to whatever
    environment is current when an engine is created, so the rows are left saying
    "staging" -- ``monkeypatch`` restores the variable at teardown but cannot
    restore the rows. Any later test that reads the registry then fails with
    ``COMPETITION_DB_ENVIRONMENT_MISMATCH:db=staging:runtime=test``, and which
    test that is depends purely on shard composition: adding an unrelated file to
    tests/ moves the failure somewhere new.
    """
    yield
    environment = os.environ.get("W2_ENVIRONMENT", "test").strip().lower()
    engine = create_engine()
    with Session(engine) as session:
        for row in session.query(LeagueSeasonModel).all():
            payload = dict(row.payload or {})
            if payload.get("environment") != environment:
                payload["environment"] = environment
                row.payload = payload
        session.commit()
CONTROLLED_OVERRIDE = ROOT / "infra/compose/controlled-future-refresh.override.yml"
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
        assert scheduler["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == (
            "status,fixtures,odds,lineups,statistics"
        )
        assert scheduler["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
        assert scheduler["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
        assert scheduler["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
        assert scheduler["W2_FIXTURE_DISCOVERY_ENABLED"] == (
            "${W2_FIXTURE_DISCOVERY_ENABLED:-false}"
        )
        assert "W2_STAGING_ENABLED_COMPETITIONS" not in scheduler
        assert scheduler["W2_XG_BACKFILL_ENABLED"] == "false"
        assert "W2_MARKET_TIMELINE_REFRESH_ENABLED" not in scheduler
        assert "W2_MARKET_TIMELINE_WINDOW" not in scheduler
        assert "W2_MARKET_TIMELINE_MAX_FIXTURES" not in scheduler
        assert scheduler["W2_FORWARD_OUTCOME_LEDGER_ENABLED"] == (
            "${W2_FORWARD_OUTCOME_LEDGER_ENABLED:-true}"
        )
        assert "W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE" not in scheduler
        assert scheduler["W2_FORWARD_OUTCOME_LEDGER_WINDOW"] == (
            "${W2_FORWARD_OUTCOME_LEDGER_WINDOW:-next7}"
        )
        api = env_for(path, "api")
        assert api["W2_PROVIDER_CALLS_DISABLED"] == "true"
        assert api["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
        assert api["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
        assert api["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
        assert "W2_STAGING_ENABLED_COMPETITIONS" not in api
        for service in ("worker",):
            env = env_for(path, service)
            assert env["W2_PROVIDER_CALLS_DISABLED"] == "true"
            assert env["W2_PROVIDER_SCHEDULER_ENABLED"] == "false"
            assert env["W2_PROVIDER_REQUEST_LEDGER_ENABLED"] == "true"
            assert env["W2_PROVIDER_REFRESH_MIN_INTERVAL_SECONDS"] == "900"
            assert env["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == (
                "status,fixtures,odds,lineups,statistics"
            )
            assert env["W2_PROVIDER_REFRESH_TICK_HARD_CAP"] == "30"
            assert env["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
            assert env["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
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
        ROOT / "infra/compose/compose.staging.yml": None,
        ROOT / "infra/compose/staging-lite.override.yml": "./config",
    }
    assert (ROOT / "config/competitions/world_cup_2026.v1.json").is_file()
    for path in COMPOSE_PATHS:
        for service in ("api", "worker", "scheduler"):
            mounts = [volume for volume in volumes_for(path, service) if ":/app/config:" in volume]
            expected = expected_sources[path]
            assert mounts == ([] if expected is None else [f"{expected}:/app/config:ro"])


def test_staging_compose_enables_only_shadow_candidate() -> None:
    for path in COMPOSE_PATHS:
        scheduler = env_for(path, "scheduler")
        assert scheduler["W2_DEEPSEEK_ENABLED"] == "false"
        assert scheduler["W2_RECOMMENDATION_ENABLED"] == "false"
        assert scheduler["W2_CANDIDATE_ENABLED"] == "true"
        assert scheduler["W2_PRODUCTION_RELEASE"] == "false"
        assert scheduler["W2_EXTERNAL_ALERTING"] == "false"


def test_controlled_override_selects_one_collection_task_and_discovery_mode() -> None:
    payload = load_compose(CONTROLLED_OVERRIDE)
    worker = payload["services"]["worker"]["environment"]
    scheduler = payload["services"]["scheduler"]["environment"]

    assert "W2_FIXTURE_DISCOVERY_ENABLED" not in worker
    assert scheduler["W2_FIXTURE_DISCOVERY_ENABLED"] == (
        "${W2_FIXTURE_DISCOVERY_ENABLED:-false}"
    )
    assert scheduler["W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS"] == "7"
    assert scheduler["W2_FUTURE_FIXTURE_REFRESH_ENABLED"] == "true"
    assert scheduler["W2_POSTMATCH_ONLY_ENABLED"] == (
        "${W2_POSTMATCH_ONLY_ENABLED:-false}"
    )
    assert worker["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == (
        "${W2_PROVIDER_ENDPOINT_ALLOWLIST:-status,fixtures,odds,lineups,statistics}"
    )
    assert scheduler["W2_PROVIDER_ENDPOINT_ALLOWLIST"] == (
        "${W2_PROVIDER_ENDPOINT_ALLOWLIST:-status,fixtures,odds,lineups,statistics}"
    )
    assert worker["W2_PROVIDER_HTTP_MAX_ATTEMPTS"] == "1"
    assert scheduler["W2_PROVIDER_HTTP_MAX_ATTEMPTS"] == "1"
    assert worker["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
    assert scheduler["W2_PROVIDER_DAILY_HARD_CAP"] == "7500"
    assert worker["W2_POSTMATCH_RESULT_DAILY_HARD_CAP"] == "200"
    assert scheduler["W2_POSTMATCH_RESULT_DAILY_HARD_CAP"] == "200"
    assert worker["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
    assert scheduler["W2_PROVIDER_DAILY_UNALLOCATED_BUFFER"] == "0"
    assert worker["W2_PROVIDER_DAILY_RESERVE"] == "1500"
    assert scheduler["W2_PROVIDER_DAILY_RESERVE"] == "1500"
    assert worker["W2_PROVIDER_OBSERVED_DAILY_LIMIT"] == "7500"
    assert scheduler["W2_PROVIDER_OBSERVED_DAILY_LIMIT"] == "7500"
    assert worker["W2_PROVIDER_PREFLIGHT_MIN_REMAINING"] == "1500"
    assert scheduler["W2_PROVIDER_PREFLIGHT_MIN_REMAINING"] == "1500"
    assert worker["W2_CANDIDATE_ENABLED"] == "true"
    assert worker["W2_FORMAL_RECOMMENDATION_ENABLED"] == "false"
    assert worker["W2_PRODUCTION_RELEASE"] == "false"


def test_world_cup_legacy_policy_does_not_restore_league_whitelist() -> None:
    import json

    policy = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(encoding="utf-8")
    )
    assert any(item["competition_id"] == "world_cup_2026" for item in policy["competitions"])
    from w2.competitions.league_whitelist_scope import load_league_whitelist_scope

    assert "world_cup_2026" not in load_league_whitelist_scope().all_whitelist


def test_exact_13_share_seven_day_open_and_t72_t48_collection_policy() -> None:
    import json

    from w2.competitions.league_whitelist_scope import load_league_whitelist_scope

    scope = set(load_league_whitelist_scope().all_whitelist)
    future = json.loads(
        (ROOT / "config/policies/future_fixture_refresh.v1.json").read_text(
            encoding="utf-8"
        )
    )
    matchday = json.loads(
        (ROOT / "config/policies/matchday_intake.v2.json").read_text(encoding="utf-8")
    )
    future_by_id = {item["competition_id"]: item for item in future["competitions"]}
    matchday_by_id = {item["competition_id"]: item for item in matchday["competitions"]}

    # 原假设：all_whitelist 恰好 13 个联赛、且都共享同一 collection policy。放宽原因：
    # LEAGUE-01R 新增 14 个 seed-only 联赛进入 all_whitelist，但它们没有 policy 条目
    # （enabled=false）。本测试的真实保护点是「有 collection policy 的 whitelist 联赛
    # 共享七天开放 + T72/T48」——故 scope 收窄为「all_whitelist ∩ future/matchday policy」，
    # 而非整个 all_whitelist。放宽后仍能测到：有 policy 的联赛集合非空、每个联赛的
    # feature_enrichment 与 T168/T72/T48 checkpoint 契约仍被逐项校验。
    policy_scope = set(future_by_id) & set(matchday_by_id)
    scope = scope & policy_scope
    assert scope
    for competition_id in scope:
        assert future_by_id[competition_id]["feature_enrichment_enabled"] is True
        assert "statistics" in future_by_id[competition_id]["feature_enrichment_endpoints"]
        checkpoints = {item["name"]: item for item in matchday_by_id[competition_id]["checkpoints"]}
        assert checkpoints["T168_OPEN_ODDS"] == {
            "name": "T168_OPEN_ODDS",
            "offset_seconds_before_kickoff": 604800,
            "endpoints": ["odds"],
            "grace_seconds": 604800,
            "enabled": True,
        }
        assert checkpoints["T72_ODDS"]["offset_seconds_before_kickoff"] == 259200
        assert checkpoints["T48_ODDS"]["offset_seconds_before_kickoff"] == 172800


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
                    "competition_id": "allsvenskan",
                    "season": "2026",
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
        "w2.competitions.registry.CompetitionRegistry",
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
