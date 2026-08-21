from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from apps.scheduler import main as scheduler_main
from apps.scheduler.main import (
    due_checkpoint_refresh_batch,
    fixture_discovery_tick,
    forward_outcome_ledger_tick,
    future_fixture_refresh_competition_ids,
    future_fixture_refresh_tick,
    heartbeat,
    xg_history_backfill_tick,
)
from apps.worker.celery_app import (
    _refresh_model_forecast_analysis_cards,
    celery_app,
    forward_outcome_ledger,
    future_fixture_refresh,
    ping,
    result_materialize,
    xg_history_backfill,
)

import w2.competitions.league_whitelist_scope  # noqa: F401
from w2.competitions.seed import set_competition_enabled
from w2.config import Settings
from w2.infrastructure.cache import redis_status
from w2.infrastructure.database import create_engine
from w2.ingestion.checkpoint_refresh import postmatch_result_checkpoint_plan
from w2.matchday.intake_v2 import stable_hash


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


def test_non_sqlite_database_engine_is_reused_per_process() -> None:
    settings = Settings(database_url="postgresql+psycopg://user:pass@localhost/test")

    assert create_engine(settings) is create_engine(settings)


def test_scheduler_heartbeat_does_not_call_external_api() -> None:
    assert heartbeat() == "w2 scheduler heartbeat"


def test_candidate_delivery_loop_does_not_wait_for_main_scheduler_work(monkeypatch) -> None:
    calls = []

    class StopLoop(Exception):
        pass

    monkeypatch.setattr(
        scheduler_main,
        "candidate_notification_delivery_tick",
        lambda: calls.append("tick") or {"status": "IDLE"},
    )
    monkeypatch.setattr(
        scheduler_main.time,
        "sleep",
        lambda _seconds: (_ for _ in ()).throw(StopLoop),
    )

    with pytest.raises(StopLoop):
        scheduler_main.candidate_notification_delivery_loop()

    assert calls == ["tick"]


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

    missed = postmatch_result_checkpoint_plan(
        fixture_id="api_football:1494238",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=kickoff,
        now=kickoff + timedelta(hours=37),
    )
    assert missed.status == "MISSED"
    assert missed.blockers == ("RESULT_WINDOW_MISSED",)

    boundary = postmatch_result_checkpoint_plan(
        fixture_id="api_football:1494239",
        competition_id="allsvenskan",
        season="2026",
        kickoff_utc=kickoff,
        now=kickoff + timedelta(hours=36),
    )
    assert boundary.status == "DUE"
    assert boundary.window_end == kickoff + timedelta(hours=36)


def test_scheduler_future_refresh_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", raising=False)
    assert future_fixture_refresh_tick()["status"] == "DISABLED"
    assert xg_history_backfill_tick()["status"] == "DISABLED"
    assert forward_outcome_ledger_tick()["status"] == "DISABLED"
    assert fixture_discovery_tick()["status"] == "DISABLED"


def test_checkpoint_dispatch_and_plan_generation_have_independent_cadence(monkeypatch) -> None:
    monkeypatch.setenv("W2_CHECKPOINT_REFRESH_POLL_SECONDS", "45")
    monkeypatch.setenv("W2_CHECKPOINT_PLAN_GENERATION_SECONDS", "3600")

    assert scheduler_main.checkpoint_poll_seconds() == 45
    assert scheduler_main.checkpoint_plan_generation_seconds() == 3600


def test_fixture_discovery_enqueues_the_canonical_refresh_task(
    monkeypatch,
) -> None:
    sent: list[dict[str, object]] = []
    now = datetime(2026, 8, 8, 5, tzinfo=UTC)
    monkeypatch.setenv("W2_FIXTURE_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_FIXTURE_DISCOVERY_MAX_OFFSET_DAYS", "1")
    monkeypatch.setattr(
        scheduler_main,
        "datetime",
        type(
            "FrozenDatetime",
            (),
            {"now": staticmethod(lambda tz=None: now)},
        ),
    )
    monkeypatch.setattr(
        scheduler_main,
        "provider_task_key_gate",
        lambda **kwargs: type(
            "Gate",
            (),
            {"allowed": True, "status": "ACQUIRED", "backend": "redis"},
        )(),
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )
    monkeypatch.setattr(
        scheduler_main,
        "matchday_checkpoint_competition_ids",
        lambda: tuple(f"league-{index}" for index in range(13)),
    )

    result = fixture_discovery_tick()

    assert result["status"] == "QUEUED"
    assert str(result["task_key"]).startswith("fixture-discovery:")
    assert result["provider_calls"] == 0
    assert sent[0]["name"] == "w2.future_fixture_refresh"
    assert sent[0]["kwargs"]["task_key"] == result["task_key"]
    assert sent[0]["kwargs"]["discovery_date"] == result["discovery_date"]
    assert result["discovery_date"] in {"2026-08-08", "2026-08-09"}


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
    monkeypatch.setattr(
        "w2.competitions.league_whitelist_scope.load_league_whitelist_scope",
        lambda registry: type(
            "Scope", (), {"all_whitelist": ("allsvenskan", "eliteserien")}
        )(),
    )

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
        "future_fixture_refresh_competition_ids",
        lambda: ("allsvenskan",),
    )
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
                    "competition_id": "allsvenskan",
                    "season": "2026",
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
    assert str(result["task_key"]).startswith("checkpoint-refresh:allsvenskan:2026:")
    assert result["provider_refresh_min_interval_policy"] == "PERSISTED_PLAN_EDF"
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
    released: list[dict[str, object]] = []

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "future_fixture_refresh_competition_ids",
        lambda: ("allsvenskan",),
    )
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
                    "competition_id": "allsvenskan",
                    "season": "2026",
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
    monkeypatch.setattr(
        scheduler_main,
        "release_checkpoint_batch_claims",
        lambda checkpoints, **kwargs: released.append(
            {"checkpoints": checkpoints, **kwargs}
        ),
    )

    result = future_fixture_refresh_tick()

    assert result["status"] == "DUPLICATE_TASK_KEY_SUPPRESSED"
    assert result["provider_calls"] == 0
    assert sent == []
    assert released[0]["restore_attempt"] is True


def test_scheduler_enqueue_failure_keeps_attempt_for_ambiguous_delivery(monkeypatch) -> None:
    released: list[dict[str, object]] = []
    checkpoint = {
        "competition_id": "allsvenskan",
        "season": "2026",
        "fixture_id": "1489404",
        "checkpoint": "T24",
        "endpoints": ["odds"],
        "source": "scheduled",
    }
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "future_fixture_refresh_competition_ids",
        lambda: ("allsvenskan",),
    )
    monkeypatch.setattr(
        scheduler_main,
        "due_checkpoint_refresh_batch",
        lambda now, **kwargs: {"status": "READY", "checkpoints": [checkpoint]},
    )
    monkeypatch.setattr(
        scheduler_main,
        "provider_task_key_gate",
        lambda **kwargs: type(
            "Gate", (), {"allowed": True, "status": "ACQUIRED", "backend": "test"}
        )(),
    )
    monkeypatch.setattr(
        scheduler_main,
        "release_checkpoint_batch_claims",
        lambda checkpoints, **kwargs: released.append(
            {"checkpoints": checkpoints, **kwargs}
        ),
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("broker uncertain")),
    )

    with pytest.raises(RuntimeError, match="broker uncertain"):
        future_fixture_refresh_tick()

    assert released == [
        {"checkpoints": [checkpoint], "reason": "CHECKPOINT_ENQUEUE_FAILED"}
    ]


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
        "future_fixture_refresh_competition_ids",
        lambda: ("world_cup_2026",),
    )
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
                    "competition_id": "world_cup_2026",
                    "season": "2026",
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


def test_checkpoint_task_key_changes_for_a_new_claim_attempt() -> None:
    checkpoint = {
        "fixture_id": "api_football:1494248",
        "checkpoint": "POSTMATCH_RESULT",
        "claim_token": "claim-1",
    }
    first = scheduler_main.checkpoint_task_key(
        competition_id="allsvenskan",
        season="2026",
        checkpoints=[checkpoint],
    )
    repeated = scheduler_main.checkpoint_task_key(
        competition_id="allsvenskan",
        season="2026",
        checkpoints=[checkpoint],
    )
    second = scheduler_main.checkpoint_task_key(
        competition_id="allsvenskan",
        season="2026",
        checkpoints=[{**checkpoint, "claim_token": "claim-2"}],
    )

    assert first == repeated
    assert first != second


def test_scheduler_prioritizes_due_capture_competitions_globally(monkeypatch) -> None:
    class Repository:
        def due_checkpoint_competition_ids(self, **kwargs: object) -> list[str]:
            assert kwargs["competition_ids"] == (
                "brasileirao_serie_a",
                "allsvenskan",
            )
            return ["allsvenskan", "brasileirao_serie_a"]

    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        Repository,
    )

    assert scheduler_main.prioritized_future_fixture_refresh_competition_ids(
        now=datetime(2026, 8, 16, tzinfo=UTC),
        competition_ids=("brasileirao_serie_a", "allsvenskan"),
    ) == ("allsvenskan", "brasileirao_serie_a")


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
            "generated_plan_count": 0,
            "due_checkpoint_count": 4,
            "selected_checkpoint_count": 4,
            "projected_calls": 4,
            "all_due_projected_calls": 4,
            "tick_hard_cap": 30,
            "checkpoints": [
                {
                    "competition_id": competition_id,
                    "season": "2026",
                    "fixture_id": f"fixture-{index}",
                    "checkpoint": "T15_ODDS",
                    "kickoff_utc": "2026-07-08T12:15:00Z",
                    "due_at": "2026-07-08T12:00:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                }
                for index, competition_id in enumerate(
                    (
                        "brasileirao_serie_a",
                        "chinese_super_league",
                        "allsvenskan",
                        "eliteserien",
                    ),
                    start=1,
                )
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

    result = future_fixture_refresh_tick()

    assert result["status"] == "QUEUED"
    assert result["queued_count"] == 4
    assert len(sent) == 4
    assert {item["kwargs"]["competition_id"] for item in sent} == {
        "brasileirao_serie_a",
        "chinese_super_league",
        "allsvenskan",
        "eliteserien",
    }


def test_scheduler_dispatcher_does_not_seed_provider_refresh_without_due_plans(
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

    result = future_fixture_refresh_tick()

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["provider_refresh_min_interval_policy"] == "PERSISTED_PLAN_EDF"
    assert sent == []


def test_scheduler_uses_idle_prematch_tick_for_postmatch_result(monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    requested_modes: list[str] = []

    def due_batch(now: datetime, **kwargs: object) -> dict[str, object]:
        mode = str(kwargs["refresh_mode"])
        requested_modes.append(mode)
        checkpoints = (
            [
                {
                    "competition_id": "la_liga",
                    "season": "2026",
                    "fixture_id": "api_football:1570351",
                    "checkpoint": "POSTMATCH_RESULT",
                    "endpoints": ["fixtures"],
                    "source": "scheduled",
                }
            ]
            if mode == "POSTMATCH"
            else []
        )
        return {
            "status": "READY" if checkpoints else "NO_CHECKPOINT_DUE",
            "checkpoints": checkpoints,
            "refresh_mode": "POSTMATCH_RESULT" if checkpoints else "PREMATCH",
        }

    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.delenv("W2_POSTMATCH_ONLY_ENABLED", raising=False)
    monkeypatch.setattr(scheduler_main, "due_checkpoint_refresh_batch", due_batch)
    monkeypatch.setattr(
        scheduler_main,
        "provider_task_key_gate",
        lambda **kwargs: type(
            "Gate", (), {"allowed": True, "status": "ACQUIRED", "backend": "test"}
        )(),
    )
    monkeypatch.setattr(
        celery_app,
        "send_task",
        lambda name, **kwargs: sent.append({"name": name, **kwargs}),
    )

    result = future_fixture_refresh_tick()

    assert requested_modes == ["PREMATCH", "POSTMATCH"]
    assert result["status"] == "QUEUED"
    assert result["refresh_mode"] == "POSTMATCH_RESULT"
    assert sent[0]["kwargs"]["refresh_checkpoints"][0]["checkpoint"] == "POSTMATCH_RESULT"


def test_scheduler_postmatch_only_never_seeds_prematch_refresh(monkeypatch) -> None:
    sent: list[dict[str, object]] = []
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_GIT_SHA", "a" * 40)
    monkeypatch.setenv("W2_FUTURE_FIXTURE_REFRESH_ENABLED", "true")
    monkeypatch.setenv("W2_PROVIDER_SCHEDULER_ENABLED", "true")
    monkeypatch.setenv("W2_POSTMATCH_ONLY_ENABLED", "true")
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
    monkeypatch.setattr(celery_app, "send_task", lambda name, **kwargs: sent.append({}))
    monkeypatch.setattr(
        scheduler_main,
        "future_fixture_refresh_competition_ids",
        lambda: ("brasileirao_serie_a",),
    )

    result = future_fixture_refresh_tick()

    assert result["status"] == "NO_POSTMATCH_RESULT_DUE"
    assert result["provider_calls"] == 0
    assert sent == []


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

    result = future_fixture_refresh_tick()

    assert result["status"] == "NO_CHECKPOINT_DUE"
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
    monkeypatch.setattr(
        scheduler_main,
        "matchday_checkpoint_competition_ids",
        lambda: tuple(f"league-{index}" for index in range(13)),
    )

    result = xg_history_backfill_tick()

    assert result["status"] == "QUEUED"
    assert len(result["task_ids"]) == 13
    assert sent[0]["name"] == "w2.xg_history_backfill"
    assert sent[0]["kwargs"]["queued_at_utc"] == result["queued_at_utc"]
    assert sent[0]["kwargs"]["competition_id"] == "league-0"


def test_scheduler_forward_outcome_ledger_dispatches_without_provider_calls(monkeypatch) -> None:
    from w2.tracking.outcome_ledger_runtime import DispatchDecision

    sent: list[dict[str, object]] = []

    def fake_send_task(name: str, **kwargs: object) -> None:
        sent.append({"name": name, **kwargs})

    monkeypatch.setenv("W2_FORWARD_OUTCOME_LEDGER_ENABLED", "true")
    monkeypatch.setenv("W2_CANDIDATE_ENABLED", "true")
    monkeypatch.setattr(celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(
        "w2.tracking.outcome_ledger_runtime.OutcomeLedgerRuntimeRepository.prepare_dispatch",
        lambda _self, **kwargs: DispatchDecision(
            status="QUEUED",
            task_id=str(kwargs["task_id"]),
            reason=None,
            consecutive_deferrals=0,
            pending_settlement_count=0,
        ),
    )

    result = forward_outcome_ledger_tick()

    assert result["status"] == "QUEUED"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert result["candidate"] is True
    assert result["formal_recommendation"] is False
    assert str(result["task_id"]).startswith("forward-outcome-ledger:")
    assert sent[0]["name"] == "w2.forward_outcome_ledger"
    assert sent[0]["kwargs"]["window"] == "next7"


def test_scheduler_defers_outcome_ledger_without_enqueuing(monkeypatch) -> None:
    from w2.tracking.outcome_ledger_runtime import DispatchDecision

    sent: list[dict[str, object]] = []
    monkeypatch.setenv("W2_FORWARD_OUTCOME_LEDGER_ENABLED", "true")
    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: sent.append(kwargs))
    monkeypatch.setattr(
        "w2.tracking.outcome_ledger_runtime.OutcomeLedgerRuntimeRepository.prepare_dispatch",
        lambda _self, **_kwargs: DispatchDecision(
            status="DEFERRED_FOR_PREMATCH_CHECKPOINT",
            task_id=None,
            reason="UNFINISHED_PREMATCH_DUE",
            consecutive_deferrals=1,
            pending_settlement_count=2,
        ),
    )

    result = forward_outcome_ledger_tick()

    assert result["status"] == "DEFERRED_FOR_PREMATCH_CHECKPOINT"
    assert result["consecutive_deferrals"] == 1
    assert result["pending_settlement_count"] == 2
    assert sent == []


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
        lambda **_kwargs: FakeResult(),
    )

    result = xg_history_backfill.run(
        queued_at_utc="2026-06-26T12:00:00Z",
        competition_id="allsvenskan",
    )

    assert result["status"] == "COMPLETED"
    assert result["result"]["candidate"] is False
    assert result["result"]["formal_recommendation"] is False
    assert result["candidate"] is False
    assert result["formal_recommendation"] is False


def test_worker_forward_outcome_ledger_task_reports_safety_flags(monkeypatch) -> None:
    completed: list[dict[str, object]] = []
    monkeypatch.setattr(
        "w2.tracking.outcome_ledger_runtime.OutcomeLedgerRuntimeRepository.mark_running",
        lambda _self, **_kwargs: True,
    )
    monkeypatch.setattr(
        "w2.tracking.outcome_ledger_runtime.OutcomeLedgerRuntimeRepository.mark_succeeded",
        lambda _self, **kwargs: completed.append(kwargs),
    )
    monkeypatch.setattr(
        "apps.worker.celery_app._run_forward_outcome_ledger",
        lambda **kwargs: {
            "status": "PASS",
            "candidate": True,
            "provider_calls": 0,
            "db_writes": 0,
            "lock_capture_write": False,
            "settlement_write": False,
            "record_count": 1,
            "written": 1,
            "source_cursor": {"analysis_created_at": "2026-06-29T12:00:00Z"},
            "pending_settlement_count": 0,
        },
    )

    result = forward_outcome_ledger.run(queued_at_utc="2026-06-29T12:00:00Z")

    assert result["status"] == "PASS"
    assert result["provider_calls"] == 0
    assert result["db_writes"] == 0
    assert result["lock_capture_write"] is False
    assert result["settlement_write"] is False
    assert result["candidate"] is True
    assert result["formal_recommendation"] is False
    assert completed[0]["source_cursor"] == {
        "analysis_created_at": "2026-06-29T12:00:00Z"
    }


def test_model_forecast_projection_refresh_targets_only_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []

    def materialize(value: list[Any]) -> list[str]:
        events.extend(value)
        return [event.fixture_id for event in value]

    class XgReadyRepository:
        def xg_ready_fixture_ids(self, _cards: list[Any]) -> tuple[str, ...]:
            return ("blocked", "missing")

    monkeypatch.setattr(
        "apps.worker.celery_app._materialize_shadow_projection_events",
        materialize,
    )
    monkeypatch.setattr(
        "w2.tracking.model_forecast_ledger.ModelForecastLedgerRepository",
        XgReadyRepository,
    )
    evaluated_at = datetime(2026, 8, 17, 6, 0, tzinfo=UTC)

    result = _refresh_model_forecast_analysis_cards(
        {
            "all": [
                {"fixture_id": "ready", "simulation": {"status": "READY"}},
                {"fixture_id": "blocked", "simulation": {"status": "UNAVAILABLE"}},
                {"fixture_id": "missing"},
            ]
        },
        evaluated_at=evaluated_at,
    )

    assert result == {
        "status": "PASS",
        "provider_calls": 0,
        "db_writes": 2,
        "scanned_fixture_count": 3,
        "xg_ready_fixture_count": 2,
        "targeted_fixture_count": 2,
        "materialized_fixture_count": 2,
    }
    assert [(event.fixture_id, event.event_type) for event in events] == [
        ("blocked", "XG_CHANGED"),
        ("missing", "XG_CHANGED"),
    ]


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


def test_worker_provider_master_switch_blocks_direct_tasks(monkeypatch) -> None:
    monkeypatch.delenv("W2_PROVIDER_SCHEDULER_ENABLED", raising=False)
    monkeypatch.setattr(
        "apps.worker.celery_app.run_xg_history_backfill",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not run provider task")),
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


def test_scheduler_checkpoint_batch_queries_persisted_due_plans_directly(monkeypatch) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    claims: list[dict[str, object]] = []

    class FakeRepository:
        def claim_due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            claims.append(kwargs)
            return []

    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        FakeRepository,
    )

    result = due_checkpoint_refresh_batch(now)

    assert result["status"] == "NO_CHECKPOINT_DUE"
    assert result["projected_calls"] == 0
    assert len(claims) == 1
    assert "plan_ids" not in claims[0]


def test_scheduler_postmatch_only_filters_prematch_plans(monkeypatch) -> None:
    now = datetime(2026, 8, 16, 11, tzinfo=UTC)
    kickoff = datetime(2026, 8, 16, 12, tzinfo=UTC)
    checkpoints: list[str] = []

    class FakeRepository:
        def upsert_checkpoint_plan(self, plan: Any) -> str:
            checkpoints.append(plan.checkpoint)
            return stable_hash(plan.natural_identity)

    monkeypatch.setenv("W2_POSTMATCH_ONLY_ENABLED", "true")
    monkeypatch.setattr(
        scheduler_main,
        "future_refresh_fixture_payloads",
        lambda **kwargs: [
            {
                "fixture": {"id": 1494241, "date": kickoff.isoformat()},
                "league": {"id": 113, "season": 2026},
            }
        ],
    )
    monkeypatch.setattr("w2.matchday.repository.MatchdayRuntimeRepository", FakeRepository)

    result = scheduler_main.generate_checkpoint_plans(now, provider_league_id="113")

    assert result["status"] == "PLANS_GENERATED"
    assert result["generated_plan_count"] == 1
    assert checkpoints == ["POSTMATCH_RESULT"]


def test_checkpoint_plan_generation_applies_live_horizon_to_legacy_reader(
    monkeypatch,
) -> None:
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    captured: dict[str, object] = {}

    class FakeRepository:
        def upsert_checkpoint_plan(self, _plan: Any) -> str:
            raise AssertionError("no fixtures means no plans")

    def fixture_payloads(**kwargs: object) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(scheduler_main, "future_refresh_fixture_payloads", fixture_payloads)
    monkeypatch.setattr("w2.matchday.repository.MatchdayRuntimeRepository", FakeRepository)

    result = scheduler_main.generate_checkpoint_plans(now, provider_league_id="113")

    assert result["generated_plan_count"] == 0
    assert captured["provider_league_id"] == "113"
    assert captured["kickoff_from"] == now - timedelta(hours=36)
    assert captured["kickoff_to"] > now


def test_future_refresh_fixture_payloads_filters_legacy_reader_by_kickoff(
    monkeypatch,
) -> None:
    now = datetime(2026, 8, 21, 12, tzinfo=UTC)
    captured: dict[str, object] = {}

    class FakeRepository:
        def fixture_payloads(self, **kwargs: object) -> list[dict[str, Any]]:
            captured.update(kwargs)
            return [
                {
                    "fixture": {
                        "id": 1,
                        "date": (now - timedelta(hours=36, seconds=1)).isoformat(),
                    }
                },
                {"fixture": {"id": 2, "date": (now - timedelta(hours=36)).isoformat()}},
                {"fixture": {"id": 3, "date": (now - timedelta(hours=35)).isoformat()}},
                {"fixture": {"id": 4, "date": (now + timedelta(hours=2)).isoformat()}},
                {"fixture": {"id": 5, "date": (now + timedelta(hours=336)).isoformat()}},
                {
                    "fixture": {
                        "id": 6,
                        "date": (now + timedelta(hours=336, seconds=1)).isoformat(),
                    }
                },
            ]

    monkeypatch.setattr(
        "w2.ingestion.future_refresh_repository.FutureRefreshDbRepository",
        FakeRepository,
    )

    rows = scheduler_main.future_refresh_fixture_payloads(
        provider_league_id="113",
        kickoff_from=now - timedelta(hours=36),
        kickoff_to=now + timedelta(hours=336),
    )

    assert captured == {"provider_league_id": "113"}
    assert [row["fixture"]["id"] for row in rows] == [2, 3, 4, 5]


def test_scheduler_checkpoint_batch_claims_persisted_rows_without_fixture_rebuild(
    monkeypatch,
) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    claim_kwargs: dict[str, object] = {}

    class FakeRepository:
        def claim_due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            claim_kwargs.update(kwargs)
            return [
                {
                    "id": "checkpoint:9999:t15",
                    "competition_id": "brasileirao_serie_a",
                    "season": "2026",
                    "fixture_id": "api_football:9999",
                    "checkpoint": "T15_ODDS",
                    "kickoff_utc": "2026-06-25T19:00:00Z",
                    "due_at": "2026-06-25T12:00:00Z",
                    "window_start": "2026-06-25T12:00:00Z",
                    "window_end": "2026-06-25T12:15:00Z",
                    "endpoints": ["odds"],
                    "source": "scheduled",
                    "policy_version": "candidate-eval.v1",
                    "claim_token": "token",
                    "claim_expires_at": "2026-06-25T12:15:00Z",
                }
            ]

        def release_checkpoint_claim(self, **kwargs: object) -> bool:
            return True

    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        FakeRepository,
    )

    result = due_checkpoint_refresh_batch(now)

    assert result["status"] == "READY"
    assert result["generated_plan_count"] == 0
    assert result["due_checkpoint_count"] == 1
    assert result["selected_checkpoint_count"] == 1
    assert result["checkpoints"][0]["fixture_id"] == "api_football:9999"
    assert "plan_ids" not in claim_kwargs


def test_scheduler_hard_cap_restores_unselected_claim_attempt(monkeypatch) -> None:
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    released: list[dict[str, object]] = []

    class FakeRepository:
        def claim_due_checkpoint_plans(self, **kwargs: object) -> list[dict[str, Any]]:
            return [
                {
                    "id": f"plan-{fixture_id}",
                    "competition_id": "brasileirao_serie_a",
                    "season": "2026",
                    "fixture_id": f"api_football:{fixture_id}",
                    "checkpoint": "T15_ODDS",
                    "kickoff_utc": now + timedelta(minutes=15),
                    "due_at": now,
                    "window_start": now,
                    "window_end": now + timedelta(minutes=15),
                    "endpoints": ["odds"],
                    "source": "matchday_intake.v2",
                    "policy_version": "candidate-eval.v1",
                    "claim_token": f"token:{fixture_id}",
                    "claim_expires_at": now + timedelta(minutes=15),
                }
                for fixture_id in (2001, 2002)
            ]

        def release_checkpoint_claim(self, **kwargs: object) -> bool:
            released.append(kwargs)
            return True

    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")
    monkeypatch.setattr(
        scheduler_main,
        "provider_refresh_tick_hard_cap",
        lambda: 1,
    )
    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository",
        FakeRepository,
    )

    result = due_checkpoint_refresh_batch(now)

    assert result["due_checkpoint_count"] == 2
    assert result["selected_checkpoint_count"] == 1
    assert result["checkpoints"][0]["window_start"] is not None
    assert result["checkpoints"][0]["window_end"] is not None
    assert len(released) == 1
    assert released[0]["restore_attempt"] is True


def test_worker_future_refresh_task_is_registered() -> None:
    assert future_fixture_refresh.name == "w2.future_fixture_refresh"
    assert "w2.market_timeline_refresh" not in celery_app.tasks
    assert forward_outcome_ledger.name == "w2.forward_outcome_ledger"
    assert result_materialize.name == "w2.result_materialize"


def test_redis_status_handles_unavailable_connection() -> None:
    settings = Settings(redis_url="redis://127.0.0.1:1/0")
    assert redis_status(settings) == "unavailable"
