from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.model_forecast_models import ModelForecastCaptureModel
from w2.infrastructure.persistence.models import ResultModel
from w2.infrastructure.persistence.outcome_ledger_models import OutcomeLedgerRunStateModel
from w2.matchday.intake_v2 import stable_hash
from w2.tracking.outcome_ledger_runtime import OutcomeLedgerRuntimeRepository

NOW = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)


def _repository() -> OutcomeLedgerRuntimeRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    MatchdayCheckpointPlanModel.__table__.create(engine)
    RawPayloadModel.__table__.create(engine)
    MatchdayEndpointCaptureModel.__table__.create(engine)
    MatchdayFixtureIdentityModel.__table__.create(engine)
    ReadModelCheckpointModel.__table__.create(engine)
    ResultModel.__table__.create(engine)
    OutcomeLedgerRunStateModel.__table__.create(engine)
    ModelForecastCaptureModel.__table__.create(engine)
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


def test_terminal_raw_fixture_payload_without_endpoint_capture_is_consumed_once() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add_all(
            [
                MatchdayFixtureIdentityModel(
                    fixture_id="api_football:5",
                    provider="api_football",
                    provider_fixture_id="5",
                    competition_id="la_liga",
                    provider_league_id="140",
                    season="2026",
                    kickoff_utc=NOW - timedelta(hours=3),
                    fixture_status="NS",
                    home_provider_team_id="1",
                    away_provider_team_id="2",
                    team_identity_status="RESOLVED",
                    raw_payload_sha256=stable_hash("raw-5-old"),
                    captured_at=NOW - timedelta(hours=6),
                    identity_hash=stable_hash("identity-5"),
                    payload={},
                ),
                RawPayloadModel(
                    sha256=stable_hash("raw-5-terminal"),
                    endpoint="fixtures",
                    captured_at=NOW,
                    storage_uri="db://raw_payload/raw-5-terminal",
                    payload={
                        "response": [
                            {
                                "fixture": {"id": 5, "status": {"short": "FT"}},
                                "score": {"fulltime": {"home": 1, "away": 0}},
                            },
                            {
                                "fixture": {"id": 999, "status": {"short": "FT"}},
                                "score": {"fulltime": {"home": 2, "away": 2}},
                            },
                        ]
                    },
                ),
            ]
        )
        session.commit()

    first = repository.incremental_work(now=NOW)
    repository.prepare_dispatch(
        now=NOW,
        task_id="task-raw-1",
        pending_settlement_count=0,
    )
    assert repository.mark_running(task_id="task-raw-1", now=NOW)
    repository.mark_succeeded(
        task_id="task-raw-1",
        now=NOW,
        source_cursor=first.source_cursor,
        pending_settlement_count=0,
    )
    second = repository.incremental_work(now=NOW)

    assert first.result_fixture_ids == ("api_football:5",)
    assert first.source_cursor["raw_fixture_payload_sha256"] == stable_hash(
        "raw-5-terminal"
    )
    assert second.result_fixture_ids == ()


def _fixture_identity(
    provider_fixture_id: str, *, kickoff: datetime
) -> MatchdayFixtureIdentityModel:
    return MatchdayFixtureIdentityModel(
        fixture_id=f"api_football:{provider_fixture_id}",
        provider="api_football",
        provider_fixture_id=provider_fixture_id,
        competition_id="la_liga",
        provider_league_id="140",
        season="2026",
        kickoff_utc=kickoff,
        fixture_status="NS",
        home_provider_team_id="1",
        away_provider_team_id="2",
        team_identity_status="RESOLVED",
        raw_payload_sha256=stable_hash(f"raw-{provider_fixture_id}"),
        captured_at=NOW,
        identity_hash=stable_hash(f"identity-{provider_fixture_id}"),
        payload={},
    )


def _shadow_card(
    provider_fixture_id: str, *, source_hash: str | None = None
) -> ReadModelCheckpointModel:
    return ReadModelCheckpointModel(
        checkpoint_key=f"analysis-card:shadow:v1:{provider_fixture_id}",
        source_hash=source_hash or stable_hash(f"source-{provider_fixture_id}"),
        created_at=NOW,
        payload={"analysis_card": {"fixture_id": provider_fixture_id}},
    )


def _capture_row(
    provider_fixture_id: str,
    *,
    fixture_id: str | None = None,
    captured_at: datetime | None = None,
) -> ModelForecastCaptureModel:
    captured = captured_at or NOW
    return ModelForecastCaptureModel(
        capture_identity_hash=f"cap-{provider_fixture_id}",
        fixture_id=fixture_id if fixture_id is not None else provider_fixture_id,
        competition_id="la_liga",
        kickoff_utc=NOW + timedelta(hours=2),
        captured_at=captured,
        lead_time_seconds=7200,
        lead_time_bucket="T-2h",
        model_family="EXACT_DC_POISSON",
        model_version="v1",
        capture_policy="FIRST_ELIGIBLE_FREEZE_IMMUTABLE",
        horizon_id="NONE",
        model_input_manifest_hash="h" * 64,
        four_field_xg_identity_hash="h" * 64,
        score_matrix_hash="h" * 64,
        payload={},
        payload_sha256="h" * 64,
        inserted_at=captured,
    )


def _advance_cursor(repository: OutcomeLedgerRuntimeRepository) -> None:
    """Persist the current source_cursor so a second pass sees unchanged cards."""
    work = repository.incremental_work(now=NOW)
    repository.prepare_dispatch(
        now=NOW,
        task_id="task-retry",
        pending_settlement_count=0,
    )
    assert repository.mark_running(task_id="task-retry", now=NOW)
    repository.mark_succeeded(
        task_id="task-retry",
        now=NOW,
        source_cursor=work.source_cursor,
        pending_settlement_count=0,
    )


def test_capture_retry_excludes_already_captured_fixtures() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(_fixture_identity("1570001", kickoff=NOW + timedelta(hours=2)))
        session.add(_shadow_card("1570001", source_hash=stable_hash("source-1")))
        session.add(_capture_row("1570001"))  # 不带前缀
        session.add(_fixture_identity("1570002", kickoff=NOW + timedelta(hours=3)))
        session.add(_shadow_card("1570002", source_hash=stable_hash("source-2")))
        session.add(_capture_row("1570002", fixture_id="api_football:1570002"))  # 带前缀
        session.commit()

    _advance_cursor(repository)
    work = repository.incremental_work(now=NOW)

    # 卡未变（cursor 已记录）且已捕获 → 不进入重试
    assert work.analysis_fixture_ids == ()
    assert work.capture_retry_fixture_ids == ()


def test_unchanged_uncaptured_card_enters_retry() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(_fixture_identity("1570001", kickoff=NOW + timedelta(hours=2)))
        session.add(_shadow_card("1570001"))
        session.commit()

    first = repository.incremental_work(now=NOW)
    # 第一次：卡变化进入 analysis，去重后不进 retry
    assert first.analysis_fixture_ids == ("1570001",)
    assert first.capture_retry_fixture_ids == ()

    repository.prepare_dispatch(now=NOW, task_id="t1", pending_settlement_count=0)
    assert repository.mark_running(task_id="t1", now=NOW)
    repository.mark_succeeded(
        task_id="t1",
        now=NOW,
        source_cursor=first.source_cursor,
        pending_settlement_count=0,
    )
    second = repository.incremental_work(now=NOW)

    # 第二次：卡未变、无 capture → 进入 retry，不再进 analysis
    assert second.analysis_fixture_ids == ()
    assert second.capture_retry_fixture_ids == ("1570001",)


def test_changed_card_does_not_duplicate_in_retry() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(_fixture_identity("1570001", kickoff=NOW + timedelta(hours=2)))
        session.add(_shadow_card("1570001"))
        session.commit()

    work = repository.incremental_work(now=NOW)

    # 卡变化走原路径；同一 fixture 不重复出现在 retry
    assert work.analysis_fixture_ids == ("1570001",)
    assert "1570001" not in work.capture_retry_fixture_ids


def test_capture_retry_capped_at_200() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        for index in range(205):
            provider_id = f"1571{index:03d}"
            session.add(
                _fixture_identity(
                    provider_id,
                    kickoff=NOW + timedelta(days=1, minutes=index),
                )
            )
            session.add(_shadow_card(provider_id))
        session.commit()

    _advance_cursor(repository)
    work = repository.incremental_work(now=NOW)

    # 205 个未捕获的未变卡（均在 7 天窗口内）→ retry 上限 200
    assert len(work.capture_retry_fixture_ids) == 200


def test_capture_retry_excludes_past_kickoff() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(_fixture_identity("1570001", kickoff=NOW - timedelta(hours=1)))
        session.add(_shadow_card("1570001"))
        session.commit()

    work = repository.incremental_work(now=NOW)

    # kickoff 已过 → 不进 retry（也不进 analysis 窗口）
    assert work.analysis_fixture_ids == ()
    assert work.capture_retry_fixture_ids == ()


def test_capture_retry_does_not_alter_source_cursor() -> None:
    repository = _repository()
    with Session(repository.engine) as session:
        session.add(_fixture_identity("1570001", kickoff=NOW + timedelta(hours=2)))
        session.add(_shadow_card("1570001"))
        session.commit()

    _advance_cursor(repository)
    work = repository.incremental_work(now=NOW)

    # retry 名单每次重查，不写入游标；游标字段与改动前一致
    assert work.capture_retry_fixture_ids == ("1570001",)
    assert "capture_retry" not in work.source_cursor
    assert "capture_retry_fixture_ids" not in work.source_cursor
    assert "analysis_sources" in work.source_cursor
