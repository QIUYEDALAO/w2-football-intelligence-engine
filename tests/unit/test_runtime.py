from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from apps.scheduler import main as scheduler_main
from apps.scheduler.main import (
    due_checkpoint_refresh_batch,
    future_fixture_refresh_tick,
    heartbeat,
    market_timeline_refresh_tick,
    xg_history_backfill_tick,
)
from apps.worker.celery_app import (
    celery_app,
    future_fixture_refresh,
    market_timeline_refresh,
    ping,
    xg_history_backfill,
)

from w2.config import Settings
from w2.infrastructure.cache import redis_status


def test_celery_ping_task_has_no_business_side_effect() -> None:
    assert ping.run() == "pong"


def test_scheduler_heartbeat_does_not_call_external_api() -> None:
    assert heartbeat() == "w2 scheduler heartbeat"


def test_scheduler_future_refresh_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"
    assert xg_history_backfill_tick()["status"] == "DISABLED"
    assert market_timeline_refresh_tick()["status"] == "DISABLED"


def test_scheduler_future_refresh_dispatches_checkpoint_worker_task_without_running_provider(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now: {
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
                    "kickoff_utc": "2026-06-26T12:00:00Z",
                    "due_at": "2026-06-25T12:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
            ],
        },
    )
    monkeypatch.setattr(
        scheduler_main,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {"now": staticmethod(lambda tz=None: now), "fromisoformat": datetime.fromisoformat},
        ),
    )
    monkeypatch.setattr(
        scheduler_main,
        "provider_task_key_gate",
        lambda **kwargs: type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )(),
    )
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert str(result["task_key"]).startswith("checkpoint-refresh:world_cup_2026:2026:")
    assert result["provider_refresh_min_interval_policy"] == (
        "REPLACED_BY_PER_FIXTURE_CHECKPOINTS"
    )
    assert sent[0]["name"] == "w2.future_fixture_refresh"
    assert sent[0]["kwargs"]["task_key"] == result["task_key"]
    assert sent[0]["kwargs"]["checkpoint_fixture_ids"] == ["1489404"]
    assert sent[0]["kwargs"]["refresh_checkpoints"] == result["checkpoints"]


def test_scheduler_provider_master_switch_blocks_refresh_enqueue(monkeypatch) -> None:
    sent: list[dict[str, object]] = []

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.delenv("W2_PROVIDER_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: sent.append({}))

    result = future_fixture_refresh_tick()

    assert result["status"] == "SKIPPED_PROVIDER_SCHEDULER_DISABLED"
    assert result["provider_calls"] == 0
    assert sent == []


def test_scheduler_suppresses_duplicate_future_refresh_task_key(monkeypatch) -> None:
    sent: list[dict[str, object]] = []

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now: {
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
                    "kickoff_utc": "2026-06-26T12:00:00Z",
                    "due_at": "2026-06-25T12:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
            ],
        },
    )
    monkeypatch.setattr(
        scheduler_main,
        "provider_task_key_gate",
        lambda **kwargs: type(
            "Gate",
            (),
            {
                "allowed": False,
                "status": "DUPLICATE_TASK_KEY_SUPPRESSED",
                "backend": "redis",
            },
        )(),
    )
    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: sent.append({}))

    result = future_fixture_refresh_tick()

    assert result["status"] == "DUPLICATE_TASK_KEY_SUPPRESSED"
    assert result["provider_calls"] == 0
    assert sent == []


def test_scheduler_future_refresh_uses_checkpoint_task_key_and_dedup(
    monkeypatch,
) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    sent: list[dict[str, object]] = []
    acquired: set[str] = set()

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    def fake_gate(**kwargs: object) -> object:
        task_key = str(kwargs["task_key"])
        if task_key in acquired:
            return type(
                "Gate",
                (),
                {
                    "allowed": False,
                    "status": "DUPLICATE_TASK_KEY_SUPPRESSED",
                    "backend": "test",
                },
            )()
        acquired.add(task_key)
        return type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )()

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now: {
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
                    "checkpoint": "OPEN",
                    "kickoff_utc": "2026-06-25T17:00:00Z",
                    "due_at": "2026-06-25T12:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
            ],
        },
    )
    monkeypatch.setattr(
        scheduler_main,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {
                "now": staticmethod(lambda tz=None: now),
                "fromisoformat": datetime.fromisoformat,
            },
        ),
    )
    monkeypatch.setattr(scheduler_main, "provider_task_key_gate", fake_gate)
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    first = future_fixture_refresh_tick()
    second = future_fixture_refresh_tick()

    assert second["status"] == "DUPLICATE_TASK_KEY_SUPPRESSED"
    assert first["projected_calls"] == 3
    assert len(sent) == 1


def test_scheduler_xg_backfill_dispatches_worker_task_without_running_provider(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_XG_BACKFILL_ENABLED", "true")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = xg_history_backfill_tick()

    assert result["status"] == "QUEUED"
    assert str(result["task_id"]).startswith("xg-history-backfill:")
    assert sent[0]["name"] == "w2.xg_history_backfill"
    assert sent[0]["kwargs"]["queued_at_utc"] == result["queued_at_utc"]


def test_scheduler_market_timeline_dispatches_worker_task_without_running_provider(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_MARKET_TIMELINE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_MARKET_TIMELINE_MAX_FIXTURES", "7")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = market_timeline_refresh_tick()

    assert result["status"] == "QUEUED"
    assert str(result["task_id"]).startswith("market-timeline-refresh:")
    assert result["max_fixtures"] == 7
    assert sent[0]["name"] == "w2.market_timeline_refresh"
    assert sent[0]["kwargs"]["checkpoint"] == "auto"
    assert sent[0]["kwargs"]["max_fixtures"] == 7


def test_worker_xg_backfill_task_reports_false_flags(monkeypatch) -> None:
    class FakeResult:
        def as_dict(self) -> dict[str, object]:
            return {
                "team_count": 2,
                "candidate": False,
                "formal_recommendation": False,
            }

    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        "apps.worker.celery_app.run_xg_history_backfill",
        lambda: FakeResult(),
    )

    result = xg_history_backfill.run(queued_at_utc="2026-06-26T12:00:00Z")

    assert result["status"] == "COMPLETED"
    assert result["result"]["candidate"] is False
    assert result["result"]["formal_recommendation"] is False
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False


def test_worker_market_timeline_task_reports_false_flags(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        "apps.worker.celery_app.run_market_timeline_refresh",
        lambda **kwargs: {
            "status": "PASS",
            "written": 1,
            "candidate": False,
            "formal_recommendation": False,
            "beats_market": False,
        },
    )

    result = market_timeline_refresh.run(
        queued_at_utc="2026-06-29T12:00:00Z",
        max_fixtures=2,
    )

    assert result["status"] == "PASS"
    assert result["result"]["written"] == 1
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False
    assert result["beats_market"] is False


def test_worker_market_timeline_task_reports_blocked_without_promotion(monkeypatch) -> None:
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        "apps.worker.celery_app.run_market_timeline_refresh",
        lambda **kwargs: {
            "status": "BLOCKED",
            "blockers": ["BACKFILL_QUOTA_GUARD"],
            "written": 0,
            "provider_calls": 0,
            "results": [],
        },
    )

    result = market_timeline_refresh.run(
        queued_at_utc="2026-06-29T12:00:00Z",
        max_fixtures=2,
    )

    assert result["status"] == "BLOCKED"
    assert result["result"]["written"] == 0
    assert result["result"]["provider_calls"] == 0
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False
    assert result["beats_market"] is False


def test_worker_provider_master_switch_blocks_direct_tasks(monkeypatch) -> None:
    monkeypatch.delenv("W2_PROVIDER_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(
        "apps.worker.celery_app.run_xg_history_backfill",
        lambda: (_ for _ in ()).throw(AssertionError("must not run provider task")),
    )

    result = xg_history_backfill.run(queued_at_utc="2026-06-26T12:00:00Z")

    assert result["status"] == "SKIPPED_PROVIDER_SCHEDULER_DISABLED"
    assert result["result"]["provider_calls"] == 0


def test_scheduler_checkpoint_batch_has_no_due_without_pending_plan(monkeypatch) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)

    class FakeRepository:
        def upsert_checkpoint_plans(self, plans: list[dict[str, Any]]) -> int:
            return len(plans)

        def due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr(scheduler_main, "future_refresh_fixture_payloads", lambda: [])
    monkeypatch.setattr(
        "w2.ingestion.future_refresh_repository.FutureRefreshDbRepository",
        FakeRepository,
    )

    result = due_checkpoint_refresh_batch(now)

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["projected_calls"] == 0


def test_worker_future_refresh_task_is_registered() -> None:
    assert future_fixture_refresh.name == "w2.future_fixture_refresh"
    assert market_timeline_refresh.name == "w2.market_timeline_refresh"


def test_redis_status_handles_unavailable_connection() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")
    assert redis_status(settings) == "unavailable"
