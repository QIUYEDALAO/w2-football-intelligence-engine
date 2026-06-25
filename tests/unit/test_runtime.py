from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from apps.scheduler import main as scheduler_main
from apps.scheduler.main import (
    fixture_refresh_gradient_interval_seconds,
    future_fixture_refresh_tick,
    heartbeat,
)
from apps.worker.celery_app import celery_app, future_fixture_refresh, ping

from w2.config import Settings
from w2.infrastructure.cache import redis_status


def test_celery_ping_task_has_no_business_side_effect() -> None:
    assert ping.run() == "pong"


def test_scheduler_heartbeat_does_not_call_external_api() -> None:
    assert heartbeat() == "w2 scheduler heartbeat"


def test_scheduler_future_refresh_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"


def test_scheduler_future_refresh_dispatches_worker_task_without_running_provider(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert str(result["task_key"]).startswith("future-refresh:world_cup_2026:2026:")
    assert sent[0]["name"] == "w2.future_fixture_refresh"
    assert sent[0]["kwargs"]["task_key"] == result["task_key"]


def test_scheduler_refresh_interval_uses_roadmap_frequency_gradient(monkeypatch) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)

    def fixture_payloads(seconds_until_kickoff: int) -> list[dict[str, Any]]:
        return [
            {
                "fixture": {
                    "date": (now + timedelta(seconds=seconds_until_kickoff)).isoformat(),
                    "status": {"short": "NS"},
                }
            }
        ]

    for seconds_until_kickoff, expected_interval in [
        (72 * 60 * 60, 3600),
        (24 * 60 * 60, 1800),
        (6 * 60 * 60, 900),
        (2 * 60 * 60, 300),
        (30 * 60, 120),
        (5 * 60, 60),
    ]:
        monkeypatch.setattr(
            scheduler_main,
            "future_refresh_fixture_payloads",
            lambda seconds_until_kickoff=seconds_until_kickoff: fixture_payloads(
                seconds_until_kickoff
            ),
        )
        assert fixture_refresh_gradient_interval_seconds(now=now) == expected_interval


def test_scheduler_refresh_interval_ignores_started_and_finished_fixtures(
    monkeypatch,
) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)

    monkeypatch.setattr(
        scheduler_main,
        "future_refresh_fixture_payloads",
        lambda: [
            {
                "fixture": {
                    "date": (now - timedelta(minutes=5)).isoformat(),
                    "status": {"short": "NS"},
                }
            },
            {
                "fixture": {
                    "date": (now + timedelta(minutes=5)).isoformat(),
                    "status": {"short": "1H"},
                }
            },
        ],
    )

    assert (
        fixture_refresh_gradient_interval_seconds(
            now=now,
            default_interval_seconds=900,
        )
        == 3600
    )


def test_scheduler_refresh_interval_falls_back_when_db_unavailable(monkeypatch) -> None:
    def unavailable_repository() -> list[dict[str, Any]]:
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        scheduler_main,
        "future_refresh_fixture_payloads",
        unavailable_repository,
    )

    assert (
        fixture_refresh_gradient_interval_seconds(
            now=datetime(2026, 6, 25, 12, tzinfo=UTC),
            default_interval_seconds=777,
        )
        == 777
    )


def test_worker_future_refresh_task_is_registered() -> None:
    assert future_fixture_refresh.name == "w2.future_fixture_refresh"


def test_redis_status_handles_unavailable_connection() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")
    assert redis_status(settings) == "unavailable"
