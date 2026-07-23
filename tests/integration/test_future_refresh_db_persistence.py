from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

import w2.api.repository as api_repository
from w2.api.repository import ReadModelRepository, ReadModelService
from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import (
    FutureMarketObservationModel,
    FutureRefreshCheckpointAuditModel,
    FutureRefreshCheckpointPlanModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayEndpointCaptureModel,
    MatchdayMarketObservationModel,
)
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


def observation_row(observation_id: str) -> dict[str, Any]:
    return {
        "observation_id": observation_id,
        "fixture_id": "fixture",
        "provider": "test",
        "bookmaker_id": "book",
        "bookmaker_name": "Book",
        "provider_bet_id": "1",
        "raw_market_label": "Over/Under",
        "canonical_market": "TOTALS",
        "selection": "Over",
        "line": "2.5",
        "decimal_odds": "1.91",
        "suspended": False,
        "live": False,
        "provider_last_update": NOW.isoformat(),
        "captured_at": NOW.isoformat(),
        "ingested_at": NOW.isoformat(),
        "raw_payload_sha256": "a" * 64,
        "source_revision": "test",
    }


class FakeApiFootballClient:
    def __init__(self, *, requested_at: datetime | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.requested_at = requested_at

    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=200,
            elapsed_ms=7,
            payload=self.payload(endpoint, params),
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=NOW,
            requested_at=self.requested_at,
        )

    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "status":
            return {"response": {"requests": {"remaining": 7000}}}
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": "2026-06-23T17:00:00+00:00",
                            "status": {"short": "NS"},
                            "venue": {"name": "DB Test Venue"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                    }
                ]
            }
        if endpoint == "odds":
            return {
                "response": [
                    {
                        "fixture": {"id": int(params["fixture"])},
                        "bookmakers": [
                            {
                                "id": 1,
                                "name": "Book A",
                                "bets": [
                                    {
                                        "id": 1,
                                        "name": "Match Winner",
                                        "values": [{"value": "Home", "odd": "1.80"}],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        if endpoint == "statistics":
            return {
                "response": [
                    {
                        "team": {"id": 10},
                        "statistics": [{"type": "expected_goals", "value": "1.4"}],
                    },
                    {
                        "team": {"id": 20},
                        "statistics": [{"type": "expected_goals", "value": "0.7"}],
                    },
                ]
            }
        if endpoint == "lineups":
            return {
                "response": [
                    {"team": {"id": 10}, "startXI": [{} for _ in range(11)], "substitutes": []},
                    {"team": {"id": 20}, "startXI": [{} for _ in range(11)], "substitutes": [{}]},
                ]
            }
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


def configure_sqlite_db(monkeypatch: Any, tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'future-refresh.db'}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)


def test_db_persistence_completes_with_read_only_runtime_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    runtime_root.chmod(0o500)
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    client = FakeApiFootballClient()

    try:
        first = run_future_refresh_task(
            task_id="task-1",
            key=key,
            queued_at=NOW,
            runtime_root=runtime_root,
            client=client,
            now=NOW,
            persistence="db",
        )
        second = run_future_refresh_task(
            task_id="task-2",
            key=key,
            queued_at=NOW,
            runtime_root=runtime_root,
            client=client,
            now=NOW,
            persistence="db",
        )
    finally:
        runtime_root.chmod(0o700)

    assert first.status == "COMPLETED"
    assert second.status == "ALREADY_RUNNING"
    assert first.result["candidate"] is False
    assert first.result["formal_recommendation"] is False
    assert not any(runtime_root.iterdir())

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(FutureMarketObservationModel)) == 0
        assert session.scalar(select(func.count()).select_from(MatchdayMarketObservationModel)) == 1
        assert session.scalar(select(func.count()).select_from(FutureRefreshTaskAuditModel)) == 2
        assert session.scalar(select(func.count()).select_from(FutureRefreshRunAuditModel)) == 1
        assert set(session.scalars(select(RawPayloadModel.endpoint)).all()) == {
            "fixtures",
            "odds",
            "lineups",
            "status",
        }
        observation = session.scalar(select(MatchdayMarketObservationModel))
        assert observation is not None
        assert observation.live is False


def test_raw_payload_failure_blocks_db_runtime_processing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setattr(
        FutureRefreshDbRepository,
        "save_raw_payload",
        lambda self, **kwargs: (_ for _ in ()).throw(RuntimeError("raw failed")),
    )
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )

    audit = run_future_refresh_task(
        task_id="task-raw-fail",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="db",
    )

    assert audit.status == "BLOCKED"
    assert "RAW_PAYLOAD_WRITE_FAILED:RuntimeError" in audit.result["blockers"]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawPayloadModel)) == 0
        assert session.scalar(select(func.count()).select_from(MatchdayEndpointCaptureModel)) == 0
        assert session.scalar(select(func.count()).select_from(MatchdayMarketObservationModel)) == 0


def test_endpoint_capture_failure_blocks_normalization(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)

    def reject_capture(self: Any, capture: dict[str, Any]) -> str:
        raise RuntimeError("capture failed")

    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository.insert_endpoint_capture",
        reject_capture,
    )
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )

    audit = run_future_refresh_task(
        task_id="task-capture-fail",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="db",
    )

    assert audit.status == "BLOCKED"
    assert any(
        str(item).startswith("ENDPOINT_CAPTURE_WRITE_FAILED:") for item in audit.result["blockers"]
    )
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawPayloadModel)) == 1
        assert session.scalar(select(func.count()).select_from(MatchdayEndpointCaptureModel)) == 0
        assert session.scalar(select(func.count()).select_from(MatchdayMarketObservationModel)) == 0


def test_endpoint_capture_preserves_request_start_time(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    requested_at = NOW - timedelta(seconds=3)
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )

    audit = run_future_refresh_task(
        task_id="task-requested-at",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(requested_at=requested_at),
        now=NOW,
        persistence="db",
    )

    assert audit.status == "COMPLETED"
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        capture = session.scalar(
            select(MatchdayEndpointCaptureModel).where(
                MatchdayEndpointCaptureModel.endpoint == "status",
            )
        )
        assert capture is not None
        assert capture.requested_at == requested_at.replace(tzinfo=None)
        assert capture.provider_captured_at == NOW.replace(tzinfo=None)


def test_observation_batch_validation_failure_writes_no_partial_rows(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    invalid = observation_row("invalid")
    invalid.pop("decimal_odds")

    with pytest.raises(FutureRefreshPersistenceError, match="OBSERVATION_WRITE_FAILED"):
        repository.append_observations([observation_row("valid"), invalid])

    with Session(repository.engine) as session:
        count = session.scalar(select(func.count()).select_from(FutureMarketObservationModel))
    assert count == 0


def test_legacy_future_observations_remain_append_only_but_are_not_production_reads(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    first = observation_row("capture-one")
    confirmed = {
        **observation_row("capture-two"),
        "captured_at": (NOW + timedelta(minutes=45)).isoformat(),
        "ingested_at": (NOW + timedelta(minutes=45)).isoformat(),
    }

    assert repository.append_observations([first]) == 1
    assert repository.append_observations([first]) == 0
    assert repository.append_observations([confirmed]) == 1

    latest = repository.latest_market_observations_for_fixtures(["fixture"])
    assert latest == []
    with Session(repository.engine) as session:
        rows = list(
            session.scalars(
                select(FutureMarketObservationModel).order_by(
                    FutureMarketObservationModel.captured_at
                )
            )
        )
    assert [row.observation_id for row in rows] == ["capture-one", "capture-two"]


def test_legacy_future_observation_does_not_report_production_confirmation(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    observation = {
        **observation_row("confirmed"),
        "captured_at": (NOW + timedelta(minutes=5)).isoformat(),
    }
    plan = {
        "id": "fixture:T15",
        "fixture_id": "fixture",
        "checkpoint": "T15",
        "kickoff_utc": NOW + timedelta(hours=1),
        "due_at": NOW + timedelta(minutes=45),
        "endpoints": ["odds"],
        "source": "scheduled",
        "status": "PENDING",
    }
    assert repository.append_observations([observation]) == 1
    assert repository.upsert_checkpoint_plans([plan]) == 0

    assert repository.market_refresh_status_for_fixtures(["fixture"], now=NOW) == {
        "odds_last_confirmed_at": None,
        "next_refresh_tick": None,
    }
    assert repository.next_market_refresh_by_fixture(["fixture"], now=NOW) == {}
    assert repository.market_refresh_status_for_fixtures([]) == {
        "odds_last_confirmed_at": None,
        "next_refresh_tick": None,
    }


def test_fixture_scoped_market_refresh_status_never_reports_past_tick(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    plan = {
        "id": "fixture:T60",
        "fixture_id": "fixture",
        "checkpoint": "T60",
        "kickoff_utc": NOW + timedelta(hours=1),
        "due_at": NOW - timedelta(minutes=1),
        "endpoints": ["odds"],
        "source": "scheduled",
        "status": "PENDING",
    }
    assert repository.upsert_checkpoint_plans([plan]) == 0

    assert repository.market_refresh_status_for_fixtures(["fixture"], now=NOW) == {
        "odds_last_confirmed_at": None,
        "next_refresh_tick": None,
    }


def test_db_persistence_allows_retry_after_blocked_task_key(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            FutureRefreshTaskAuditModel(
                task_id="blocked-task",
                key=key,
                owner="owner-a",
                queued_at=NOW,
                started_at=NOW,
                finished_at=NOW,
                status="BLOCKED",
                result={
                    "blockers": ["PROVIDER_RESERVE_PROTECTED"],
                    "candidate": False,
                    "formal_recommendation": False,
                },
            )
        )
        session.commit()
    client = FakeApiFootballClient()

    audit = run_future_refresh_task(
        task_id="retry-task",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
    )

    assert audit.status == "COMPLETED"
    assert [endpoint for endpoint, _ in client.calls] == [
        "status",
        "fixtures",
        "odds",
        "lineups",
    ]


def test_api_repository_reads_future_refresh_projection_from_db(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setattr(api_repository, "RUNTIME", tmp_path / "api-runtime")
    key = deterministic_task_key(
        competition_id="world_cup_2026",
        season="2026",
        now=NOW,
        interval_seconds=900,
    )
    audit = run_future_refresh_task(
        task_id="task-api",
        key=key,
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="db",
    )

    repository = ReadModelRepository()
    fixtures = repository.fixture_payloads()
    observations = repository.future_market_observations()
    snapshots = repository.market_snapshots()
    provider = ReadModelService(repository=repository).provider_status()

    assert audit.status == "COMPLETED"
    assert [str(item["fixture"]["id"]) for item in fixtures] == ["1489404"]
    assert len(observations) == 1
    assert observations[0]["candidate"] is False
    assert observations[0]["formal_recommendation"] is False
    assert snapshots[0]["fixture_id"] == "1489404"
    assert snapshots[0]["source"] == "matchday_market_observations"
    assert provider["remaining_quota"] == 7000
    assert provider["blockers"] == []


def test_checkpoint_plan_is_idempotent_and_audited(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    due_at = NOW - timedelta(minutes=1)
    row = {
        "id": "1489404:T24",
        "fixture_id": "1489404",
        "checkpoint": "T24",
        "kickoff_utc": NOW + timedelta(hours=24),
        "due_at": due_at,
        "endpoints": ["odds"],
        "source": "scheduled",
        "status": "PENDING",
    }

    assert repository.upsert_checkpoint_plans([row]) == 0
    assert repository.upsert_checkpoint_plans([row]) == 0
    assert repository.due_checkpoint_plans(now=NOW) == []
    audit_id = repository.write_checkpoint_audit(
        fixture_id="1489404",
        checkpoint="T24",
        as_of=NOW,
        calls_used=1,
        status="COMPLETED",
        details={"contract": "w2.checkpoint_refresh.v1"},
    )

    assert audit_id >= 1
    assert repository.due_checkpoint_plans(now=NOW) == []
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(FutureRefreshCheckpointPlanModel)) == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(FutureRefreshCheckpointAuditModel)) == 1
        )


def test_fixture_scoped_reader_ignores_legacy_future_observation_population(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    common = {
        "provider": "api_football",
        "bookmaker_id": "book",
        "bookmaker_name": "Book",
        "provider_bet_id": "bet",
        "raw_market_label": "Goals Over/Under",
        "canonical_market": "TOTALS",
        "selection": "Over",
        "line": "2.5",
        "decimal_odds": "1.91",
        "suspended": False,
        "live": False,
        "provider_last_update": "2026-07-18T00:00:00Z",
        "captured_at": NOW,
        "ingested_at": NOW,
        "raw_payload_sha256": "a" * 64,
        "source_revision": "test",
        "candidate": False,
        "formal_recommendation": False,
    }
    unrelated = [
        {
            **common,
            "observation_id": f"unrelated-{index}",
            "fixture_id": f"unrelated-{index}",
        }
        for index in range(10_000)
    ]
    target = [
        {
            **common,
            "observation_id": "target-old",
            "fixture_id": "target",
            "captured_at": NOW - timedelta(minutes=1),
        },
        {
            **common,
            "observation_id": "target-latest",
            "fixture_id": "target",
        },
    ]
    with Session(engine) as session:
        session.execute(FutureMarketObservationModel.__table__.insert(), unrelated + target)
        session.commit()

    rows = FutureRefreshDbRepository(engine=engine).latest_market_observations_for_fixtures(
        ["target"]
    )

    assert rows == []


def test_fixture_scoped_reader_does_not_use_legacy_future_market_ladder(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    rows: list[dict[str, Any]] = []
    for market, label, sides in (
        ("ASIAN_HANDICAP", "Asian Handicap", ("Home", "Away")),
        ("TOTALS", "Goals Over/Under", ("Over", "Under")),
    ):
        for bookmaker_index in range(8):
            for line_index in range(20):
                line = (line_index + 1) / 4
                for side_index, side in enumerate(sides):
                    signed_line = -line if market == "ASIAN_HANDICAP" and side == "Away" else line
                    rows.append(
                        {
                            **observation_row(
                                f"{market}-{bookmaker_index}-{line_index}-{side_index}"
                            ),
                            "fixture_id": "target",
                            "bookmaker_id": f"book-{bookmaker_index}",
                            "bookmaker_name": f"Book {bookmaker_index}",
                            "raw_market_label": label,
                            "canonical_market": market,
                            "selection": f"{side} {signed_line:+g}",
                            "line": str(signed_line),
                            "decimal_odds": str(1.88 + (line_index % 3) * 0.01),
                            "provider_last_update": NOW,
                            "captured_at": NOW,
                            "ingested_at": NOW,
                        }
                    )
    for index in range(400):
        rows.append(
            {
                **observation_row(f"other-market-{index}"),
                "fixture_id": "target",
                "bookmaker_id": f"other-{index}",
                "raw_market_label": "Goals Over/Under First Half",
                "canonical_market": "TOTALS",
                "provider_last_update": NOW,
                "captured_at": NOW,
                "ingested_at": NOW,
            }
        )
    with Session(engine) as session:
        session.execute(FutureMarketObservationModel.__table__.insert(), rows)
        session.commit()

    scoped = FutureRefreshDbRepository(engine=engine).latest_market_observations_for_fixtures(
        ["target"]
    )

    assert scoped == []


def test_scoped_raw_payload_and_xg_readers_enforce_fixed_limits(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    for index in range(40):
        fixture_id = "target" if index == 39 else f"unrelated-{index}"
        repository.save_raw_payload(
            sha256=f"{index:064x}",
            endpoint="lineups",
            captured_at=NOW + timedelta(seconds=index),
            payload={"parameters": {"fixture": fixture_id}, "response": []},
        )
    matches = []
    for team_id in ("home", "away", "unrelated"):
        for index in range(25):
            matches.append(
                {
                    "id": f"{team_id}-{index}",
                    "fixture_id": f"fixture-{team_id}-{index}",
                    "team_id": team_id,
                    "opponent_team_id": "opponent",
                    "kickoff_at": NOW - timedelta(days=index + 1),
                    "captured_at": NOW,
                    "xg_for": 1.0,
                    "xg_against": 1.0,
                    "goals_for": 1,
                    "goals_against": 1,
                    "raw_payload_sha256": "a" * 64,
                    "source_system": "test",
                }
            )
    repository.upsert_team_xg_matches(matches)

    raw = repository.raw_payloads_for_scope(
        "lineups",
        fixture_id="target",
        limit=32,
    )
    xg = repository.team_xg_matches_for_teams(
        ["home", "away"],
        before=NOW + timedelta(days=1),
        limit_per_team=20,
    )

    assert [row["payload"]["parameters"]["fixture"] for row in raw] == ["target"]
    assert len(xg) == 40
    assert {row["team_id"] for row in xg} == {"home", "away"}


def test_scoped_xg_snapshot_reader_uses_latest_pre_fixture_team_state(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    snapshots = []
    for team_id in ("home", "away", "unrelated"):
        for index in range(3):
            snapshots.append(
                {
                    "snapshot_id": f"{team_id}-{index}",
                    "team_id": team_id,
                    "as_of_fixture_id": f"previous-{team_id}-{index}",
                    "as_of_time": NOW - timedelta(days=3 - index),
                    "match_count": 6 + index,
                    "rolling_xg_for": 1.1 + index / 10,
                    "rolling_xg_against": 0.9,
                    "rolling_goals_for": 1.0,
                    "rolling_goals_against": 1.0,
                    "regression_index": 0.1,
                    "source_system": "test",
                }
            )
    repository.upsert_team_xg_rolling_snapshots(snapshots)

    selected = repository.team_xg_rolling_snapshots_for_teams(
        ["home", "away"],
        before=NOW,
    )

    assert [(row["team_id"], row["match_count"]) for row in selected] == [
        ("away", 8),
        ("home", 8),
    ]
    assert {row["as_of_fixture_id"] for row in selected} == {
        "previous-away-2",
        "previous-home-2",
    }


def test_request_count_since_includes_provider_request_logs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    since = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        for index in range(120):
            requested_at = since + timedelta(seconds=index)
            session.add(
                ProviderRequestLogModel(
                    provider="api_football",
                    endpoint="odds",
                    request_hash=f"{index:064x}",
                    live=True,
                    status_code=200,
                    requested_at=requested_at,
                    completed_at=requested_at,
                )
            )
        session.commit()

    assert FutureRefreshDbRepository().request_count_since(since) >= 120


def test_request_count_since_includes_quota_usage(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    since = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        session.add(
            QuotaUsageModel(
                provider="api_football",
                endpoint="odds",
                used=7000,
                limit=7500,
                window_start=since,
                window_end=since + timedelta(days=1),
            )
        )
        session.commit()

    assert FutureRefreshDbRepository().request_count_since(since) >= 7000
