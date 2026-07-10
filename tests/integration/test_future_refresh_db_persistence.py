from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

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
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


class FakeApiFootballClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

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
                        "league": {"id": 71, "name": "Serie A", "round": "Regular Season"},
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
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv("W2_STAGING_ENABLED_COMPETITIONS", "brasileirao_serie_a")
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
        competition_id="brasileirao_serie_a",
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
        assert session.scalar(select(func.count()).select_from(FutureMarketObservationModel)) == 1
        assert session.scalar(select(func.count()).select_from(FutureRefreshTaskAuditModel)) == 2
        assert session.scalar(select(func.count()).select_from(FutureRefreshRunAuditModel)) == 1
        assert set(session.scalars(select(RawPayloadModel.endpoint)).all()) == {
            "fixtures",
            "odds",
            "status",
        }
        observation = session.scalar(select(FutureMarketObservationModel))
        assert observation is not None
        assert observation.candidate is False
        assert observation.formal_recommendation is False


def test_db_persistence_allows_retry_after_blocked_task_key(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    key = deterministic_task_key(
        competition_id="brasileirao_serie_a",
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
    ]


def test_api_repository_reads_future_refresh_projection_from_db(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setattr(api_repository, "RUNTIME", tmp_path / "api-runtime")
    key = deterministic_task_key(
        competition_id="brasileirao_serie_a",
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

    assert repository.upsert_checkpoint_plans([row]) == 1
    assert repository.upsert_checkpoint_plans([row]) == 1
    assert [item["id"] for item in repository.due_checkpoint_plans(now=NOW)] == [
        "1489404:T24"
    ]
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
            session.scalar(select(func.count()).select_from(FutureRefreshCheckpointPlanModel))
            == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(FutureRefreshCheckpointAuditModel))
            == 1
        )


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
