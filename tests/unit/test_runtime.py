from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from apps.scheduler import main as scheduler_main
from apps.scheduler.main import (
    due_checkpoint_refresh_batch,
    forward_outcome_ledger_tick,
    future_fixture_refresh_competition_ids,
    future_fixture_refresh_tick,
    heartbeat,
    market_timeline_refresh_tick,
    xg_history_backfill_tick,
)
from apps.worker.celery_app import (
    celery_app,
    forward_outcome_ledger,
    future_fixture_refresh,
    market_timeline_refresh,
    ping,
    result_materialize,
    xg_history_backfill,
)

from w2.competitions.seed import set_competition_enabled
from w2.config import Settings
from w2.infrastructure.cache import redis_status
from w2.infrastructure.database import create_engine
from w2.ingestion.checkpoint_refresh import postmatch_result_checkpoint_plan


@contextmanager
def db_enabled_competitions(*competition_ids: str):  # type: ignore[no-untyped-def]
    engine = create_engine()
    for competition_id in competition_ids:
        set_competition_enabled(
            engine,
            competition_id=competition_id,
            enabled=True,
            updated_by="runtime-test",
        )
    try:
        yield
    finally:
        for competition_id in competition_ids:
            set_competition_enabled(
                engine,
                competition_id=competition_id,
                enabled=False,
                updated_by="runtime-test-cleanup",
            )


def test_celery_ping_task_has_no_business_side_effect() -> None:
    assert ping.run() == "pong"


def test_scheduler_heartbeat_does_not_call_external_api() -> None:
    assert heartbeat() == "w2 scheduler heartbeat"


def test_postmatch_result_checkpoint_is_single_bounded_status_fixture_refresh() -> None:
    kickoff = datetime(2026, 8, 3, 17, tzinfo=UTC)
    plan = postmatch_result_checkpoint_plan(
        fixture_id="api_football:1494237",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=kickoff,
        now=kickoff.replace(hour=21),
    )

    assert plan.status == "DUE"
    assert plan.checkpoint == "POSTMATCH_RESULT"
    assert plan.scheduled_at == kickoff.replace(hour=20)
    assert plan.endpoints == ("status", "fixtures")


def test_scheduler_future_refresh_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"
    assert xg_history_backfill_tick()["status"] == "DISABLED"
    assert market_timeline_refresh_tick()["status"] == "DISABLED"
    assert forward_outcome_ledger_tick()["status"] == "DISABLED"


def test_scheduler_future_refresh_intersects_runtime_allowlist(monkeypatch) -> None:
    class Entry:
        def __init__(self, competition_id: str) -> None:
            self.competition_id = competition_id
            self.enabled = True
            self.refresh_switches = {"fixtures": True}

    class Registry:
        def entries(self) -> dict[str, Entry]:
            return {
                competition_id: Entry(competition_id)
                for competition_id in ("allsvenskan", "eliteserien", "world_cup_2026")
            }

    monkeypatch.setenv(
        "W2_FUTURE_REFRESH_COMPETITION_ALLOWLIST",
        "allsvenskan,eliteserien",
    )
    monkeypatch.setattr("w2.competitions.registry.CompetitionRegistry", Registry)

    assert future_fixture_refresh_competition_ids() == ("allsvenskan", "eliteserien")


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
    assert result["provider_refresh_min_interval_policy"] == ("REPLACED_BY_PER_FIXTURE_CHECKPOINTS")
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


def test_scheduler_future_refresh_accepts_staging_competition_list(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sent: list[dict[str, object]] = []

    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now, **kwargs: {
            "status": "READY",
            "generated_plan_count": 1,
            "due_checkpoint_count": 1,
            "selected_checkpoint_count": 1,
            "projected_calls": 1,
            "all_due_projected_calls": 1,
            "tick_hard_cap": 30,
            "checkpoints": [
                {
                    "fixture_id": "fixture-1",
                    "checkpoint": "OPEN",
                    "kickoff_utc": "2026-07-08T12:00:00Z",
                    "due_at": "2026-07-08T10:00:00Z",
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
            {"allowed": True, "status": "ACQUIRED", "backend": "test"},
        )(),
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )

    with db_enabled_competitions(
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    ):
        result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert result["queued_count"] == 5
    assert len(sent) == 5
    assert {item["kwargs"]["competition_id"] for item in sent} == {
        "world_cup_2026",
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    }


def test_scheduler_future_refresh_seeds_staging_league_without_local_fixtures(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now, **kwargs: {
            "status": "NO_CHECKPOINT_DUE",
            "fixture_payload_count": 0,
            "generated_plan_count": 0,
            "due_checkpoint_count": 0,
            "selected_checkpoint_count": 0,
            "projected_calls": 0,
            "all_due_projected_calls": 0,
            "tick_hard_cap": 30,
            "checkpoints": [],
        },
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
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )
    monkeypatch.setattr(
        scheduler_main,
        "future_fixture_refresh_competition_ids",
        lambda: ("brasileirao_serie_a",),
    )

    with db_enabled_competitions("brasileirao_serie_a"):
        result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert result["competition_id"] == "brasileirao_serie_a"
    assert result["provider_refresh_min_interval_policy"] == ("INITIAL_SEED_WHEN_NO_LOCAL_FIXTURES")
    assert sent == [
        {
            "name": "w2.future_fixture_refresh",
            "kwargs": {
                "competition_id": "brasileirao_serie_a",
                "task_key": result["task_key"],
                "queued_at_utc": result["queued_at_utc"],
            },
            "task_id": result["task_id"],
        }
    ]


def test_scheduler_future_refresh_does_not_seed_when_local_fixtures_exist(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now, **kwargs: {
            "status": "NO_CHECKPOINT_DUE",
            "fixture_payload_count": 6,
            "generated_plan_count": 0,
            "due_checkpoint_count": 0,
            "selected_checkpoint_count": 0,
            "projected_calls": 0,
            "all_due_projected_calls": 0,
            "tick_hard_cap": 30,
            "checkpoints": [],
        },
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )
    monkeypatch.setattr(
        scheduler_main,
        "future_fixture_refresh_competition_ids",
        lambda: ("brasileirao_serie_a",),
    )

    with db_enabled_competitions("brasileirao_serie_a"):
        result = future_fixture_refresh_tick()

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["competition_id"] == "brasileirao_serie_a"
    assert result["provider_calls"] == 0
    assert sent == []


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
    assert sent[0]["kwargs"]["capture_forward_ledger"] is False


def test_scheduler_market_timeline_is_not_blocked_by_provider_master_switch(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_MARKET_TIMELINE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "false")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = market_timeline_refresh_tick()

    assert result["status"] == "QUEUED"
    assert sent[0]["name"] == "w2.market_timeline_refresh"


def test_scheduler_market_timeline_can_chain_forward_ledger_without_running_provider(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_MARKET_TIMELINE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_FORWARD_OUTCOME_LEDGER_AFTER_MARKET_TIMELINE", "true")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = market_timeline_refresh_tick()

    assert result["status"] == "QUEUED"
    assert result["capture_forward_ledger"] is True
    assert sent[0]["name"] == "w2.market_timeline_refresh"
    assert sent[0]["kwargs"]["capture_forward_ledger"] is True


def test_scheduler_forward_outcome_ledger_dispatches_without_provider_calls(monkeypatch) -> None:
    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FORWARD_OUTCOME_LEDGER_ENABLED", "true")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)

    result = forward_outcome_ledger_tick()

    assert result["status"] == "QUEUED"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert str(result["task_id"]).startswith("forward-outcome-ledger:")
    assert sent[0]["name"] == "w2.forward_outcome_ledger"
    assert sent[0]["kwargs"]["window"] == "next36"


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
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "false")
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


def test_worker_market_timeline_can_capture_forward_ledger(monkeypatch) -> None:
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
    monkeypatch.setattr(
        "apps.worker.celery_app._run_forward_outcome_ledger",
        lambda **kwargs: {
            "status": "PASS",
            "provider_calls": 0,
            "db_writes": 0,
            "record_count": 2,
            "written": 2,
        },
    )

    result = market_timeline_refresh.run(
        queued_at_utc="2026-06-29T12:00:00Z",
        max_fixtures=2,
        capture_forward_ledger=True,
    )

    assert result["status"] == "PASS"
    assert result["forward_outcome_ledger"]["record_count"] == 2
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False
    assert result["beats_market"] is False


def test_worker_forward_outcome_ledger_task_reports_safety_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.worker.celery_app._run_forward_outcome_ledger",
        lambda **kwargs: {
            "status": "PASS",
            "provider_calls": 0,
            "db_writes": 0,
            "lock_capture_write": False,
            "settlement_write": False,
            "record_count": 1,
            "written": 1,
        },
    )

    result = forward_outcome_ledger.run(queued_at_utc="2026-06-29T12:00:00Z")

    assert result["status"] == "PASS"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert result["lock_capture_write"] is False
    assert result["settlement_write"] is False
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False


def test_worker_result_materialize_task_reports_safety_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        "apps.worker.celery_app._run_result_materialize",
        lambda **kwargs: {
            "status": "PASS",
            "provider_calls": 0,
            "db_writes": 1,
            "materialized_result_count": 1,
            "scoring_projection_status": "PASS",
            "scoring_projection_db_writes": 4,
        },
    )

    result = result_materialize.run(
        queued_at_utc="2026-06-29T12:00:00Z",
        fixture_ids=["fixture-1"],
    )

    assert result["status"] == "PASS"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 1
    assert result["scoring_projection_status"] == "PASS"
    assert result["scoring_projection_db_writes"] == 4
    assert result["lock_capture_write"] is False
    assert result["settlement_write"] is False
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False


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


def test_worker_future_refresh_uses_allowlisted_live_client(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Audit:
        task_id = "task"
        key = "key"
        status = "COMPLETED"
        result: dict[str, object] = {}

    def fake_run_future_refresh_task(**kwargs: object) -> Audit:
        captured.update(kwargs)
        return Audit()

    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv(
        "W2_PROVIDER_ENDPOINT_ALLOWLIST",
        "status,fixtures,odds,lineups",
    )
    monkeypatch.setattr(
        "apps.worker.celery_app.run_future_refresh_task",
        fake_run_future_refresh_task,
    )

    result = future_fixture_refresh.run(competition_id="allsvenskan")

    client: Any = captured["client"]
    assert type(client).__name__ == "ApiFootballClient"
    assert client.allow_live is True
    assert client.allowed_live_endpoints == frozenset({"status", "fixtures", "odds", "lineups"})
    assert result["status"] == "COMPLETED"


def test_scheduler_checkpoint_batch_has_no_due_without_pending_plan(monkeypatch) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)

    class FakeRepository:
        def upsert_checkpoint_plan(self, plan: object) -> str:
            return "plan"

        def due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            raise AssertionError("must not read global due rows without generated plans")

        def claim_due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            raise AssertionError("must not claim rows without generated plans")

    monkeypatch.setattr(scheduler_main, "future_refresh_fixture_payloads", lambda **kwargs: [])
    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        FakeRepository,
    )

    result = due_checkpoint_refresh_batch(now)

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["projected_calls"] == 0


def test_scheduler_checkpoint_batch_ignores_due_rows_outside_current_fixture_set(
    monkeypatch,
) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    kickoff = "2026-06-25T19:00:00Z"
    fixtures = [
        {
            "fixture": {
                "id": 2001,
                "date": kickoff,
                "status": {"short": "NS", "elapsed": None},
            },
            "league": {"id": 71, "season": 2026},
            "teams": {
                "home": {"id": 1, "name": "Home"},
                "away": {"id": 2, "name": "Away"},
            },
        }
    ]

    claimed_plan_ids: set[str] | None = None

    class FakeRepository:
        def upsert_checkpoint_plan(self, plan: object) -> str:
            return "plan"

        def claim_due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            nonlocal claimed_plan_ids
            claimed_plan_ids = kwargs.get("plan_ids")  # type: ignore[assignment]
            return [
                {
                    "id": "checkpoint:9999:open",
                    "fixture_id": "9999",
                    "checkpoint": "OPEN",
                    "kickoff_utc": "2026-06-25T19:00:00Z",
                    "due_at": "2026-06-25T12:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                    "claim_token": "token",
                    "claim_expires_at": "2026-06-25T12:15:00Z",
                }
            ]

        def release_checkpoint_claim(self, **kwargs: object) -> bool:
            return True

    monkeypatch.setattr(
        scheduler_main,
        "future_refresh_fixture_payloads",
        lambda **kwargs: fixtures,
    )
    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        FakeRepository,
    )

    with db_enabled_competitions("brasileirao_serie_a"):
        result = due_checkpoint_refresh_batch(now, provider_league_id="71")

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["generated_plan_count"] > 0
    assert result["due_checkpoint_count"] == 0
    assert result["selected_checkpoint_count"] == 0
    assert claimed_plan_ids
    assert "checkpoint:9999:open" not in claimed_plan_ids


def test_worker_future_refresh_task_is_registered() -> None:
    assert future_fixture_refresh.name == "w2.future_fixture_refresh"
    assert market_timeline_refresh.name == "w2.market_timeline_refresh"
    assert forward_outcome_ledger.name == "w2.forward_outcome_ledger"
    assert result_materialize.name == "w2.result_materialize"


def test_redis_status_handles_unavailable_connection() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")
    assert redis_status(settings) == "unavailable"
