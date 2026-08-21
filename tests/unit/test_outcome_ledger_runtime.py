from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerRunStateModel
from w2.matchday.intake_v2 import stable_hash
from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)


def _repository() -> OutcomeLedgerRuntimeRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    MatchdayCheckpointPlanModel.__table__.create(engine)
    MatchdayEndpointCaptureModel.__table__.create(engine)
    MatchdayFixtureIdentityModel.__table__.create(engine)
    ReadModelCheckpointModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
    OutcomeLedgerRunStateModel.__table__.create(engine)
    return OutcomeLedgerRuntimeRepository(engine)


def _due_plan(repository: OutcomeLedgerRuntimeRepository) -> None:
    with Session(repository.engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="fixture:T15_ODDS",
                fixture_id="api_football:1",
                competition_id="la_liga",
                season="2026",
                policy_version="candidate-eval.v1",
                checkpoint="T15_ODDS",
                kickoff_utc=NOW + timedelta(minutes=15),
                scheduled_at=NOW,
                window_start=NOW,
                window_end=NOW + timedelta(minutes=15),
                endpoints=["odds"],
                status="DUE",
                attempt_count=0,
                test_only=False,
                blockers=[],
                plan_hash=stable_hash("plan"),
            )
        )
        session.commit()


def test_three_deferrals_are_bounded_and_fourth_tick_forces_execution(monkeypatch) -> None:
    repository = _repository()
    _due_plan(repository)
    monkeypatch.setenv("W2_OUTCOME_LEDGER_MAX_CONSECUTIVE_DEFERRALS", "3")
    monkeypatch.setenv("W2_OUTCOME_LEDGER_MAX_DEFER_SECONDS", "1800")

    decisions = [
        repository.prepare_dispatch(
            now=NOW + timedelta(minutes=10 * index),
            task_id=f"task-{index}",
            pending_settlement_count=2,
        )
        for index in range(4)
    ]

    assert [item.status for item in decisions] == [
        "DEFERRED_FOR_PREMATCH_CHECKPOINT",
        "DEFERRED_FOR_PREMATCH_CHECKPOINT",
        "DEFERRED_FOR_PREMATCH_CHECKPOINT",
        "QUEUED",
    ]
    assert decisions[-1].forced is True
    assert decisions[-1].reason == "UNFINISHED_PREMATCH_DUE"


def test_active_task_is_not_enqueued_twice() -> None:
    repository = _repository()
    first = repository.prepare_dispatch(
        now=NOW,
        task_id="task-1",
        pending_settlement_count=0,
    )
    second = repository.prepare_dispatch(
        now=NOW + timedelta(minutes=1),
        task_id="task-2",
        pending_settlement_count=0,
    )

    assert first.status == "QUEUED"
    assert second.status == "ACTIVE_OR_RESERVED"
    assert second.task_id == "task-1"


def test_success_resets_deferrals_and_exposes_healthy_state() -> None:
    repository = _repository()
    decision = repository.prepare_dispatch(
        now=NOW,
        task_id="task-1",
        pending_settlement_count=0,
    )
    assert decision.status == "QUEUED"
    assert repository.mark_running(task_id="task-1", now=NOW + timedelta(seconds=1))
    repository.mark_succeeded(
        task_id="task-1",
        now=NOW + timedelta(seconds=2),
        source_cursor={"analysis_created_at": "2026-08-22T08:00:00Z"},
        pending_settlement_count=0,
    )

    health = repository.health(now=NOW + timedelta(minutes=10))

    assert health["status"] == "READY"
    assert health["run_status"] == "SUCCEEDED"
    assert health["consecutive_deferrals"] == 0
    assert health["seconds_since_last_success"] == 598


def test_settlement_backlog_is_visible_as_degraded() -> None:
    repository = _repository()
    repository.prepare_dispatch(
        now=NOW,
        task_id="task-1",
        pending_settlement_count=1,
    )
    assert repository.mark_running(task_id="task-1", now=NOW)
    repository.mark_succeeded(
        task_id="task-1",
        now=NOW,
        source_cursor={},
        pending_settlement_count=1,
    )

    health = repository.health(now=NOW + timedelta(minutes=1))

    assert health["status"] == "DEGRADED"
    assert health["pending_settlement_count"] == 1
    assert "OUTCOME_LEDGER_SETTLEMENT_BACKLOG" in health["reason_codes"]


def test_incremental_cursor_reads_each_changed_card_once() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="api_football:1570351",
                provider="api_football",
                provider_fixture_id="1570351",
                competition_id="la_liga",
                provider_league_id="140",
                season="2026",
                kickoff_utc=NOW + timedelta(hours=2),
                fixture_status="NS",
                home_provider_team_id="1",
                away_provider_team_id="2",
                team_identity_status="RESOLVED",
                raw_payload_sha256=stable_hash("raw"),
                captured_at=NOW,
                identity_hash=stable_hash("identity"),
                payload={},
            )
        )
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key="analysis-card:shadow:v1:1570351",
                source_hash=stable_hash("source"),
                created_at=NOW,
                payload={"analysis_card": {"fixture_id": "1570351"}},
            )
        )
        session.commit()
    first = repository.incremental_work(now=NOW)
    repository.prepare_dispatch(
        now=NOW,
        task_id="task-1",
        pending_settlement_count=0,
    )
    assert repository.mark_running(task_id="task-1", now=NOW)
    repository.mark_succeeded(
        task_id="task-1",
        now=NOW,
        source_cursor=first.source_cursor,
        pending_settlement_count=0,
    )
    second = repository.incremental_work(now=NOW)

    assert first.analysis_fixture_ids == ("1570351",)
    assert second.analysis_fixture_ids == ()


def test_card_is_processed_when_it_first_enters_next7_window() -> None:
    repository = _repository()
    kickoff = NOW + timedelta(days=8)
    with Session(repository.engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="api_football:2",
                provider="api_football",
                provider_fixture_id="2",
                competition_id="la_liga",
                provider_league_id="140",
                season="2026",
                kickoff_utc=kickoff,
                fixture_status="NS",
                home_provider_team_id="1",
                away_provider_team_id="2",
                team_identity_status="RESOLVED",
                raw_payload_sha256=stable_hash("raw-2"),
                captured_at=NOW,
                identity_hash=stable_hash("identity-2"),
                payload={},
            )
        )
        session.add(
            ReadModelCheckpointModel(
                checkpoint_key="analysis-card:shadow:v1:2",
                source_hash=stable_hash("source-2"),
                created_at=NOW,
                payload={"analysis_card": {"fixture_id": "2"}},
            )
        )
        session.commit()
    outside = repository.incremental_work(now=NOW)
    inside = repository.incremental_work(now=NOW + timedelta(days=2))

    assert outside.analysis_fixture_ids == ()
    assert inside.analysis_fixture_ids == ("2",)


def test_fixture_capture_and_result_are_consumed_once() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id="capture-1",
                fixture_id="api_football:3",
                competition_id="la_liga",
                checkpoint="POSTMATCH_RESULT",
                endpoint="fixtures",
                sanitized_params={"id": "3"},
                params_hash=stable_hash("params-3"),
                request_task_key="task-3",
                attempt=1,
                requested_at=NOW,
                provider_captured_at=NOW,
                status_code=200,
                elapsed_ms=1,
                response_count=1,
                quota_values={},
                raw_payload_sha256=stable_hash("capture-3"),
                capture_status="CAPTURED",
            )
        )
        session.add(
            ResultModel(
                fixture_id="api_football:4",
                home_goals=1,
                away_goals=0,
                result_status="FT",
                confirmed_at=NOW,
                source_payload_sha256=stable_hash("result-payload-4"),
                result_hash=stable_hash("result-4"),
            )
        )
        session.commit()

    first = repository.incremental_work(now=NOW)
    repository.prepare_dispatch(
        now=NOW,
        task_id="task-1",
        pending_settlement_count=0,
    )
    assert repository.mark_running(task_id="task-1", now=NOW)
    repository.mark_succeeded(
        task_id="task-1",
        now=NOW,
        source_cursor=first.source_cursor,
        pending_settlement_count=0,
    )
    second = repository.incremental_work(now=NOW)

    assert first.result_fixture_ids == ("api_football:3", "api_football:4")
    assert second.result_fixture_ids == ()
