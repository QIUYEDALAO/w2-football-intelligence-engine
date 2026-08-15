from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from apps.worker.celery_app import _materialize_outcome_results
from scripts.requeue_unlinked_t168_provider_empty import requeue_unlinked_t168_provider_empty
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import Session

import w2.prematch.analysis_calculator as api_repository
from w2.api.repository import ReadModelRepository as DashboardReadModelRepository
from w2.competitions.seed import (
    apply_collection_policy_update,
    seed_competition_runtime_authority,
)
from w2.config import get_settings
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.future_refresh_models import (
    FutureRefreshCheckpointAuditModel,
    FutureRefreshRunAuditModel,
    FutureRefreshTaskAuditModel,
    RawPayloadModel,
)
from w2.infrastructure.persistence.ingestion_models import (
    ProviderRequestLogModel,
    QuotaUsageModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayEndpointCaptureModel,
    MatchdayEndpointCapturePlanModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import ResultModel, StructuredLineupSnapshotModel
from w2.ingestion.checkpoint_refresh import postmatch_result_checkpoint_plan
from w2.ingestion.future_refresh import deterministic_task_key, run_future_refresh_task
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
)
from w2.matchday.intake_v2 import CheckpointPlan
from w2.matchday.repository import MatchdayRuntimeRepository
from w2.prematch.analysis_calculator import ReadModelRepository, ReadModelService
from w2.prematch.read_model_projection import (
    ProjectionSourceEvent,
    ScopedAnalysisRepository,
    materialize_projection_events,
)
from w2.providers.api_football import LiveApiFootballResponse

NOW = datetime(2026, 6, 23, 10, 0, tzinfo=UTC)


def materialize_projection_events_for_test(events: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(event.fixture_id) for event in events))


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

            def team_lineup(team_id: int, offset: int) -> dict[str, Any]:
                return {
                    "team": {"id": team_id, "name": f"Team {team_id}"},
                    "formation": "4-3-3",
                    "startXI": [
                        {
                            "player": {
                                "id": offset + index,
                                "name": f"Player {offset + index}",
                                "number": index + 1,
                                "pos": "G" if index == 0 else "M",
                                "grid": f"{index // 4 + 1}:{index % 4 + 1}",
                            }
                        }
                        for index in range(11)
                    ],
                    "substitutes": [],
                }

            return {
                "response": [
                    team_lineup(10, 100),
                    team_lineup(20, 200),
                ]
            }
        if endpoint == "injuries":
            return {"response": []}
        raise AssertionError(endpoint)


class FinishedFixtureClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "fixtures":
            return {
                "response": [
                    {
                        "fixture": {
                            "id": 1489404,
                            "date": (NOW - timedelta(hours=4)).isoformat(),
                            "status": {"short": "FT"},
                        },
                        "league": {"id": 1, "name": "World Cup", "round": "Group K"},
                        "teams": {
                            "home": {"id": 10, "name": "Team A"},
                            "away": {"id": 20, "name": "Team B"},
                        },
                        "goals": {"home": 2, "away": 1},
                        "score": {"fulltime": {"home": 2, "away": 1}},
                    }
                ]
            }
        return super().payload(endpoint, params)


class SchemaDriftLineupsClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        return {"response": {}} if endpoint == "lineups" else super().payload(endpoint, params)


class EmptyOddsClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        return {"response": []} if endpoint == "odds" else super().payload(endpoint, params)


class FirstFixtureErrorsOddsClient(FakeApiFootballClient):
    def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
        if endpoint == "odds" and params.get("fixture") == "1489404":
            return {"errors": {"plan": "restricted"}, "response": []}
        return super().payload(endpoint, params)


class RetryOddsClient(FakeApiFootballClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        if endpoint == "odds" and not self.calls:
            self.calls.append((endpoint, params))
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=429,
                elapsed_ms=7,
                payload={},
                headers={},
                captured_at=NOW - timedelta(seconds=1),
            )
        return super().request_live(endpoint, params)


class RetryEveryOddsClient(FakeApiFootballClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        fixture = params.get("fixture", "")
        if endpoint == "odds" and sum(call == (endpoint, params) for call in self.calls) == 0:
            self.calls.append((endpoint, params))
            return LiveApiFootballResponse(
                endpoint=endpoint,
                params=params,
                status_code=429,
                elapsed_ms=7,
                payload={},
                headers={},
                captured_at=NOW - timedelta(seconds=1),
            )
        assert fixture
        return super().request_live(endpoint, params)


class Http500OddsClient(FakeApiFootballClient):
    def request_live(self, endpoint: str, params: dict[str, str]) -> LiveApiFootballResponse:
        self.calls.append((endpoint, params))
        return LiveApiFootballResponse(
            endpoint=endpoint,
            params=params,
            status_code=500,
            elapsed_ms=7,
            payload={"errors": {"server": "failure"}},
            headers={"x-ratelimit-requests-remaining": "7000"},
            captured_at=NOW,
        )


def configure_sqlite_db(
    monkeypatch: Any,
    tmp_path: Path,
    *,
    collection_policy: bool = False,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'future-refresh.db'}"
    monkeypatch.setenv("W2_ENVIRONMENT", "test")
    monkeypatch.setenv("W2_DATABASE_URL", database_url)
    monkeypatch.setenv("W2_FUTURE_REFRESH_PERSISTENCE", "db")
    get_settings.cache_clear()
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    if collection_policy:
        seed_competition_runtime_authority(engine, environment="test", now=NOW)
        apply_collection_policy_update(engine, updated_by="checkpoint-test", now=NOW)


def seed_odds_checkpoint(
    fixture_id: str,
    *,
    with_identity: bool,
    endpoints: tuple[str, ...] = ("odds",),
    checkpoint: str = "T168_OPEN_ODDS",
) -> None:
    repository = MatchdayRuntimeRepository()
    payload = FakeApiFootballClient().payload("fixtures", {})["response"][0]
    payload["fixture"]["id"] = int(fixture_id)
    payload["league"] = {"id": 113, "name": "Allsvenskan", "round": "Regular Season"}
    kickoff = NOW + timedelta(hours=7)
    payload["fixture"]["date"] = kickoff.isoformat()
    if with_identity:
        repository.upsert_fixture_identities_with_business_changes(
            [
                {
                    "fixture_id": f"api_football:{fixture_id}",
                    "provider": "api_football",
                    "provider_fixture_id": fixture_id,
                    "competition_id": "allsvenskan",
                    "provider_league_id": "113",
                    "season": "2026",
                    "kickoff_utc": kickoff,
                    "fixture_status": "NS",
                    "home_provider_team_id": "10",
                    "away_provider_team_id": "20",
                    "home_w2_team_id": None,
                    "away_w2_team_id": None,
                    "team_identity_status": "REVIEW_REQUIRED",
                    "raw_payload_sha256": "a" * 64,
                    "endpoint_capture_id": None,
                    "captured_at": NOW,
                    "identity_hash": "b" * 64,
                    "payload": payload,
                }
            ]
        )
    repository.upsert_checkpoint_plan(
        CheckpointPlan(
            fixture_id=f"api_football:{fixture_id}",
            competition_id="allsvenskan",
            season="2026",
            checkpoint=checkpoint,
            kickoff_utc=kickoff,
            scheduled_at=NOW,
            window_start=NOW - timedelta(minutes=1),
            window_end=NOW + timedelta(hours=1),
            endpoints=endpoints,
            status="DUE",
            blockers=(),
        )
    )


def claimed_odds_checkpoint(*, with_identity: bool) -> dict[str, Any]:
    seed_odds_checkpoint("1489404", with_identity=with_identity)
    repository = MatchdayRuntimeRepository()
    claimed = repository.claim_due_checkpoint_plans(now=NOW, worker_id="direct-test")
    assert len(claimed) == 1
    return claimed[0]


def run_direct_checkpoint(
    tmp_path: Path,
    client: FakeApiFootballClient,
    *checkpoints: dict[str, Any],
) -> Any:
    return run_future_refresh_task(
        task_id="direct-checkpoint",
        key="direct:checkpoint",
        queued_at=NOW,
        competition_id="allsvenskan",
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        checkpoint_fixture_ids=tuple(str(item["fixture_id"]) for item in checkpoints),
        refresh_checkpoints=checkpoints,
        materialize_public_artifacts=materialize_projection_events_for_test,
    )


def test_discovery_mode_uses_the_canonical_refresh_writer_only(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)

    class DiscoveryClient(FakeApiFootballClient):
        def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
            payload = super().payload(endpoint, params)
            if endpoint == "fixtures":
                payload["response"][0]["league"] = {
                    "id": 113,
                    "name": "Allsvenskan",
                    "season": 2026,
                }
            return payload

    client = DiscoveryClient()
    audit = run_future_refresh_task(
        task_id="fixture-discovery",
        key="fixture-discovery:2026-06-23:2026-06-23",
        queued_at=NOW,
        competition_id="allsvenskan",
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        discovery_date="2026-06-23",
    )

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        identity = session.get(MatchdayFixtureIdentityModel, "api_football:1489404")
        canonical_team_count = session.scalar(
            select(func.count()).select_from(CanonicalTeamModel)
        )
        crosswalk_count = session.scalar(
            select(func.count()).select_from(ProviderTeamIdentityCrosswalkModel)
        )
        observation_count = session.scalar(
            select(func.count()).select_from(MatchdayMarketObservationModel)
        )

    assert client.calls == [("fixtures", {"date": "2026-06-23"})]
    assert audit.status == "COMPLETED"
    assert audit.result["discovery_date"] == "2026-06-23"
    assert audit.result["market_snapshot_count"] == 0
    assert identity is not None
    assert identity.competition_id == "allsvenskan"
    assert identity.team_identity_status == "PROVIDER_PRIMARY_READY"
    assert identity.home_w2_team_id == "w2:team:api_football:10"
    assert identity.away_w2_team_id == "w2:team:api_football:20"
    assert canonical_team_count == 2
    assert crosswalk_count == 2
    assert audit.result["identity_pool_expansions"] == [
        {
            "event": "TEAM_IDENTITY_POOL_EXPANDED",
            "competition_id": "allsvenskan",
            "provider_league_id": "113",
            "season": "2026",
            "canonical_team_count": 2,
            "provider_crosswalk_count": 2,
            "fixture_identity_ready_count": 1,
        }
    ]
    assert observation_count == 0


def test_checkpoint_missing_persisted_fixture_fails_without_provider_call(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    checkpoint = claimed_odds_checkpoint(with_identity=False)
    client = FakeApiFootballClient()

    audit = run_direct_checkpoint(tmp_path, client, checkpoint)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        checkpoint_audit = session.scalar(select(FutureRefreshCheckpointAuditModel))

    assert client.calls == []
    assert plan is not None and plan.status == "FAILED"
    assert checkpoint_audit is not None and checkpoint_audit.calls_used == 0
    assert audit.status == "BLOCKED"


def test_checkpoint_daily_cap_preflight_restores_unattempted_claim(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "1")
    monkeypatch.setenv("W2_PROVIDER_DAILY_RESERVE", "0")
    checkpoint = claimed_odds_checkpoint(with_identity=True)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            ProviderRequestLogModel(
                provider="api_football",
                endpoint="odds",
                request_hash="f" * 64,
                live=True,
                status_code=200,
                requested_at=NOW,
                completed_at=NOW,
            )
        )
        session.commit()
    client = FakeApiFootballClient()

    run_direct_checkpoint(tmp_path, client, checkpoint)

    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        audit = session.scalar(select(FutureRefreshCheckpointAuditModel))
    assert client.calls == []
    assert plan is not None and plan.status == "DUE"
    assert plan.attempt_count == 0
    assert plan.claim_token is None
    assert audit is not None and (audit.status, audit.calls_used) == ("RETRY_PENDING", 0)


def test_postmatch_result_cap_restores_unattempted_claim(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setenv("W2_POSTMATCH_RESULT_DAILY_HARD_CAP", "2")
    repository = MatchdayRuntimeRepository()
    repository.upsert_checkpoint_plan(
        postmatch_result_checkpoint_plan(
            fixture_id="api_football:1489404",
            competition_id="world_cup_2026",
            season="2026",
            kickoff_utc=NOW - timedelta(hours=4),
            now=NOW,
        )
    )
    checkpoint = repository.claim_due_checkpoint_plans(
        now=NOW,
        worker_id="postmatch-cap-test",
    )[0]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            FutureRefreshTaskAuditModel(
                task_id="earlier-postmatch-task",
                key="earlier-postmatch-key",
                owner="test",
                queued_at=NOW,
                started_at=NOW,
                finished_at=NOW,
                status="COMPLETED",
                result={
                    "request_count": 2,
                    "refresh_checkpoints": [{"checkpoint": "POSTMATCH_RESULT"}],
                },
            )
        )
        session.commit()
    client = FakeApiFootballClient()

    run_future_refresh_task(
        task_id="postmatch-cap-task",
        key="postmatch-cap:world_cup_2026:1489404",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        checkpoint_fixture_ids=("api_football:1489404",),
        refresh_checkpoints=(checkpoint,),
    )

    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        audit = session.scalar(select(FutureRefreshCheckpointAuditModel))
    assert client.calls == []
    assert plan is not None and plan.status == "DUE"
    assert plan.attempt_count == 0
    assert plan.claim_token is None
    assert "RESULT_QUOTA_EXHAUSTED" in plan.blockers
    assert audit is not None and (audit.status, audit.calls_used) == ("RETRY_PENDING", 0)
    assert audit.details["result_collection_state"] == "RESULT_QUOTA_EXHAUSTED"


@pytest.mark.parametrize(
    ("client", "checkpoint_name", "endpoints", "expected_status", "expected_lineups"),
    [
        (FakeApiFootballClient(), "T45_LINEUPS_RETRY", ("lineups",), "CAPTURED", 2),
        (
            FakeApiFootballClient(),
            "T60_ODDS_LINEUPS",
            ("odds", "lineups"),
            "CAPTURED",
            2,
        ),
        (SchemaDriftLineupsClient(), "T45_LINEUPS_RETRY", ("lineups",), "FAILED", 0),
    ],
)
def test_checkpoint_direct_endpoints_are_exact_and_fail_closed(
    tmp_path: Path,
    monkeypatch: Any,
    client: FakeApiFootballClient,
    checkpoint_name: str,
    endpoints: tuple[str, ...],
    expected_status: str,
    expected_lineups: int,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    seed_odds_checkpoint(
        "1489404",
        with_identity=True,
        endpoints=endpoints,
        checkpoint=checkpoint_name,
    )
    checkpoint = MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="endpoint-matrix"
    )[0]

    run_direct_checkpoint(tmp_path, client, checkpoint)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        captures = list(session.scalars(select(MatchdayEndpointCaptureModel)))
        links = session.scalar(select(func.count()).select_from(MatchdayEndpointCapturePlanModel))
        lineup_count = session.scalar(
            select(func.count()).select_from(StructuredLineupSnapshotModel)
        )
    assert [endpoint for endpoint, _params in client.calls] == list(endpoints)
    assert plan is not None and plan.status == expected_status
    assert len(captures) == len(endpoints)
    assert links == len(endpoints)
    assert {row.checkpoint for row in captures} == {checkpoint_name}
    assert lineup_count == expected_lineups


@pytest.mark.parametrize(
    ("client_type", "second_status", "second_audit", "expected_calls"),
    [
        (FirstFixtureErrorsOddsClient, "CAPTURED", "COMPLETED", 2),
        (Http500OddsClient, "DUE", "RETRY_PENDING", 1),
    ],
)
def test_checkpoint_batch_isolates_failure_and_releases_unattempted(
    tmp_path: Path,
    monkeypatch: Any,
    client_type: type[FakeApiFootballClient],
    second_status: str,
    second_audit: str,
    expected_calls: int,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")
    seed_odds_checkpoint("1489404", with_identity=True)
    seed_odds_checkpoint("1489405", with_identity=True)
    checkpoints = MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="batch-direct-test"
    )
    client = client_type()
    run_direct_checkpoint(tmp_path, client, *checkpoints)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        plans = {
            row.fixture_id: row
            for row in session.scalars(select(MatchdayCheckpointPlanModel))
        }
        audits = {
            row.fixture_id: row.status
            for row in session.scalars(select(FutureRefreshCheckpointAuditModel))
        }

    assert [params["fixture"] for _, params in client.calls] == [
        "1489404",
        "1489405",
    ][:expected_calls]
    assert plans["api_football:1489404"].status == "FAILED"
    assert plans["api_football:1489405"].status == second_status
    assert audits == {
        "api_football:1489404": "FAILED",
        "api_football:1489405": second_audit,
    }
    if second_status == "DUE":
        assert plans["api_football:1489405"].claim_token is None
        assert plans["api_football:1489405"].attempt_count == 0
        assert "CHECKPOINT_BATCH_NOT_ATTEMPTED" in plans["api_football:1489405"].blockers


def test_shared_checkpoint_request_marks_every_claim_as_attempted(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "1")
    seed_odds_checkpoint("1489404", with_identity=True, checkpoint="T72_OPEN_ODDS")
    seed_odds_checkpoint("1489404", with_identity=True, checkpoint="T48_OPEN_ODDS")
    checkpoints = MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="shared-request"
    )

    run_direct_checkpoint(tmp_path, Http500OddsClient(), *checkpoints)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        plans = list(session.scalars(select(MatchdayCheckpointPlanModel)))
    assert len(plans) == 2
    assert {plan.attempt_count for plan in plans} == {1}
    assert {plan.status for plan in plans} == {"FAILED"}


def test_checkpoint_retry_uses_final_capture(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "2")
    checkpoint = claimed_odds_checkpoint(with_identity=True)
    client = RetryOddsClient()

    audit = run_direct_checkpoint(tmp_path, client, checkpoint)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        captures = list(
            session.scalars(
                select(MatchdayEndpointCaptureModel).order_by(
                    MatchdayEndpointCaptureModel.attempt
                )
            )
        )
        checkpoint_audit = session.scalar(select(FutureRefreshCheckpointAuditModel))

    assert plan is not None and plan.status == "CAPTURED"
    assert [(row.attempt, row.capture_status, row.error_code) for row in captures] == [
        (1, "FAILED", "PROVIDER_HTTP_ERROR"),
        (2, "CAPTURED", None),
    ]
    assert checkpoint_audit is not None and checkpoint_audit.calls_used == 2
    assert audit.status == "COMPLETED"


def test_requeued_checkpoint_attempt_two_links_provider_empty_capture(
    tmp_path: Path, monkeypatch: Any
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    seed_odds_checkpoint("1489404", with_identity=True)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with engine.begin() as connection:
        connection.execute(
            update(MatchdayCheckpointPlanModel).values(status="PROVIDER_EMPTY", attempt_count=1)
        )
    dry_run = requeue_unlinked_t168_provider_empty(engine, now=NOW)
    requeue_unlinked_t168_provider_empty(
        engine,
        now=NOW,
        apply=True,
        expected_count=1,
        expected_plan_ids_sha256=dry_run.plan_ids_sha256,
    )
    checkpoint = MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="attempt-two"
    )[0]

    run_direct_checkpoint(tmp_path, EmptyOddsClient(), checkpoint)

    with Session(engine) as session:
        plan = session.scalar(select(MatchdayCheckpointPlanModel))
        capture = session.scalar(select(MatchdayEndpointCaptureModel))
        links = session.scalar(select(func.count()).select_from(MatchdayEndpointCapturePlanModel))
    assert plan is not None and (plan.status, plan.attempt_count) == ("PROVIDER_EMPTY", 2)
    assert capture is not None and capture.capture_status == "PROVIDER_EMPTY"
    assert links == 1


def test_checkpoint_batch_budget_covers_each_planned_retry(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    monkeypatch.setenv("W2_PROVIDER_HTTP_MAX_ATTEMPTS", "2")
    for fixture_id in map(str, range(1489404, 1489419)):
        seed_odds_checkpoint(fixture_id, with_identity=True)
    checkpoints = MatchdayRuntimeRepository().claim_due_checkpoint_plans(
        now=NOW, worker_id="retry-budget"
    )
    client = RetryEveryOddsClient()

    audit = run_direct_checkpoint(tmp_path, client, *checkpoints)

    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        statuses = set(session.scalars(select(MatchdayCheckpointPlanModel.status)))
    assert audit.status == "COMPLETED"
    assert len(client.calls) == 30
    assert statuses == {"CAPTURED"}


@pytest.mark.parametrize(
    "mutation",
    [
        {"checkpoint": "POSTMATCH_RESULT", "endpoints": ["status", "fixtures"]},
        {"endpoints": ["lineups"]},
    ],
)
def test_checkpoint_claim_payload_is_canonical_before_provider_call(
    tmp_path: Path,
    monkeypatch: Any,
    mutation: dict[str, Any],
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path, collection_policy=True)
    checkpoint = {**claimed_odds_checkpoint(with_identity=True), **mutation}
    client = FakeApiFootballClient()

    audit = run_direct_checkpoint(tmp_path, client, checkpoint)

    assert audit.result["blockers"] == ["CHECKPOINT_CLAIM_PAYLOAD_MISMATCH"]
    assert client.calls == []


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
            materialize_public_artifacts=materialize_projection_events_for_test,
        )
        second = run_future_refresh_task(
            task_id="task-2",
            key=key,
            queued_at=NOW,
            runtime_root=runtime_root,
            client=client,
            now=NOW,
            persistence="db",
            materialize_public_artifacts=materialize_projection_events_for_test,
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
    assert (
        DashboardReadModelRepository().market_collection_status_for_fixtures(["1489404"], now=NOW)[
            "1489404"
        ]["odds_status"]
        == "READY"
    )


def test_postmatch_checkpoint_fetches_once_and_materializes_real_result(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    monkeypatch.setenv("W2_PROVIDER_DAILY_HARD_CAP", "0")
    monkeypatch.setenv("W2_PROVIDER_ENDPOINT_ALLOWLIST", "status,fixtures,odds,lineups")
    kickoff = NOW - timedelta(hours=4)
    repository = MatchdayRuntimeRepository()
    plan = postmatch_result_checkpoint_plan(
        fixture_id="api_football:1489404",
        competition_id="world_cup_2026",
        season="2026",
        kickoff_utc=kickoff,
        now=NOW,
    )
    repository.upsert_checkpoint_plan(plan)
    checkpoints = repository.claim_due_checkpoint_plans(now=NOW, worker_id="postmatch-test")
    assert len(checkpoints) == 1
    client = FinishedFixtureClient()

    audit = run_future_refresh_task(
        task_id="postmatch-result-task",
        key="postmatch-result:world_cup_2026:1489404",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        checkpoint_fixture_ids=("api_football:1489404",),
        refresh_checkpoints=(checkpoints[0],),
        materialize_public_artifacts=materialize_projection_events_for_test,
        materialize_results=_materialize_outcome_results,
    )

    assert audit.status == "COMPLETED"
    assert [endpoint for endpoint, _params in client.calls] == ["status", "fixtures"]
    assert client.calls[1][1] == {"id": "1489404"}
    assert audit.result["materialized_fixture_ids"] == ["api_football:1489404"]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        result = session.scalar(select(ResultModel))
        checkpoint = session.scalar(select(MatchdayCheckpointPlanModel))
        checkpoint_audit = session.scalar(select(FutureRefreshCheckpointAuditModel))
        assert result is not None
        assert (result.home_goals, result.away_goals, result.result_status) == (2, 1, "FT")
        assert checkpoint is not None
        assert checkpoint.status == "CAPTURED"
        assert checkpoint_audit is not None and checkpoint_audit.status == "COMPLETED"


def test_c9_fake_provider_emits_exact_required_event_set(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    observed_event_types: list[str] = []

    def materialize(events: list[Any]) -> list[str]:
        observed_event_types.extend(str(event.event_type) for event in events)
        return list(dict.fromkeys(str(event.fixture_id) for event in events))

    client = FakeApiFootballClient()
    audit = run_future_refresh_task(
        task_id="task-c9-event-set",
        key="checkpoint-refresh:test:c9-event-set",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=client,
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materialize,
    )

    assert audit.status == "COMPLETED"
    assert audit.result["request_count"] == 4
    assert audit.result["fixture_count"] > 0
    assert set(observed_event_types) == {
        "FIXTURE_CHANGED",
        "LINEUP_CHANGED",
        "ODDS_CHANGED",
    }
    assert audit.result["candidate"] is False
    assert audit.result["formal_recommendation"] is False
    assert [endpoint for endpoint, _params in client.calls] == [
        "status",
        "fixtures",
        "odds",
        "lineups",
    ]


def test_c9_fake_provider_materializes_real_shadow_projection(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    class PredeployClient(FakeApiFootballClient):
        def payload(self, endpoint: str, params: dict[str, str]) -> dict[str, Any]:
            if endpoint != "odds":
                return super().payload(endpoint, params)
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
                                        "id": 4,
                                        "name": "Asian Handicap",
                                        "values": [
                                            {"value": "Home -0.5", "odd": "1.91"},
                                            {"value": "Away +0.5", "odd": "1.93"},
                                        ],
                                    },
                                    {
                                        "id": 5,
                                        "name": "Goals Over/Under",
                                        "values": [
                                            {"value": "Over 2.5", "odd": "2.01"},
                                            {"value": "Under 2.5", "odd": "1.82"},
                                        ],
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }

    configure_sqlite_db(monkeypatch, tmp_path)
    audit = run_future_refresh_task(
        task_id="task-c9-shadow",
        key="checkpoint-refresh:test:c9-shadow",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=PredeployClient(),
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materialize_projection_events_for_test,
    )
    assert audit.status == "COMPLETED"
    repository = ReadModelRepository()

    def calculate(
        scoped_repository: ScopedAnalysisRepository,
        fixture_id: str,
        evaluated_at: datetime,
    ) -> dict[str, Any] | None:
        return ReadModelService(repository=scoped_repository).public_analysis_card_bounded(
            fixture_id,
            evaluation_time=evaluated_at,
            use_frozen_canary=False,
        )

    fixture_id = "1489404"
    event = ProjectionSourceEvent.create(
        fixture_id=fixture_id,
        event_type="ODDS_CHANGED",
        event_id=f"c9-shadow:{fixture_id}",
        event_at=NOW,
        payload={"fixture_id": fixture_id, "source": "c9-contract"},
    )

    assert materialize_projection_events(
        [event],
        repository=repository,
        calculate_analysis_card=calculate,
    ) == [fixture_id]


def test_lineup_materialization_failure_is_stable_and_preserves_raw_lineage(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)

    def reject_lineup(self: Any, **_kwargs: Any) -> int:
        raise FutureRefreshPersistenceError("STARTING_XI_INCOMPLETE")

    monkeypatch.setattr(FutureRefreshDbRepository, "save_lineup_snapshots", reject_lineup)
    audit = run_future_refresh_task(
        task_id="task-lineup-fail",
        key="checkpoint-refresh:test:lineup-fail",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materialize_projection_events_for_test,
    )

    assert audit.status == "BLOCKED"
    assert audit.result["blockers"] == ["LINEUP_MATERIALIZATION_FAILED:STARTING_XI_INCOMPLETE"]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(RawPayloadModel)
                .where(RawPayloadModel.endpoint == "lineups")
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(MatchdayEndpointCaptureModel)
                .where(MatchdayEndpointCaptureModel.endpoint == "lineups")
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(StructuredLineupSnapshotModel)) == 0


def test_fixture_identity_failure_blocks_lineup_materialization_with_stable_reason(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)

    def reject_identity(self: Any, _rows: list[dict[str, Any]]) -> tuple[int, list[str]]:
        raise RuntimeError("injected identity failure")

    monkeypatch.setattr(
        "w2.matchday.repository.MatchdayRuntimeRepository."
        "upsert_fixture_identities_with_business_changes",
        reject_identity,
    )
    audit = run_future_refresh_task(
        task_id="task-fixture-identity-fail",
        key="checkpoint-refresh:test:fixture-identity-fail",
        queued_at=NOW,
        runtime_root=tmp_path / "runtime",
        client=FakeApiFootballClient(),
        now=NOW,
        persistence="db",
        materialize_public_artifacts=materialize_projection_events_for_test,
    )

    assert audit.status == "BLOCKED"
    assert audit.result["blockers"] == ["FIXTURE_IDENTITY_PERSISTENCE_FAILED:RuntimeError"]
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(StructuredLineupSnapshotModel)) == 0


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
        materialize_public_artifacts=materialize_projection_events_for_test,
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
        materialize_public_artifacts=materialize_projection_events_for_test,
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
        materialize_public_artifacts=materialize_projection_events_for_test,
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


def test_fixture_scoped_market_refresh_status_never_reports_past_tick(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="past-plan",
                fixture_id="api_football:fixture",
                competition_id="allsvenskan",
                season="2026",
                policy_version="test-policy",
                checkpoint="T60",
                kickoff_utc=NOW + timedelta(hours=1),
                scheduled_at=NOW - timedelta(minutes=1),
                window_start=NOW - timedelta(minutes=2),
                window_end=NOW + timedelta(minutes=3),
                endpoints=["odds"],
                status="DUE",
                blockers=[],
                plan_hash="a" * 64,
            )
        )
        session.commit()

    assert FutureRefreshDbRepository().market_refresh_status_for_fixtures(
        ["fixture"], now=NOW
    ) == {
        "odds_last_confirmed_at": None,
        "next_refresh_tick": None,
    }


def test_fixture_scoped_market_refresh_status_reads_canonical_matchday_plan(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    scheduled_at = NOW + timedelta(minutes=30)
    with Session(engine) as session:
        session.add_all(
            [
                MatchdayCheckpointPlanModel(
                    plan_id="canonical-plan",
                    fixture_id="api_football:fixture",
                    competition_id="world_cup_2026",
                    season="2026",
                    policy_version="test-policy",
                    checkpoint="T30",
                    kickoff_utc=NOW + timedelta(hours=1),
                    scheduled_at=scheduled_at,
                    window_start=scheduled_at,
                    window_end=scheduled_at + timedelta(minutes=5),
                    endpoints=["odds"],
                    status="PLANNED",
                    blockers=[],
                    plan_hash="a" * 64,
                ),
                MatchdayCheckpointPlanModel(
                    plan_id="past-odds-plan",
                    fixture_id="api_football:fixture",
                    competition_id="world_cup_2026",
                    season="2026",
                    policy_version="test-policy",
                    checkpoint="T48",
                    kickoff_utc=NOW + timedelta(hours=1),
                    scheduled_at=NOW - timedelta(minutes=30),
                    window_start=NOW - timedelta(minutes=30),
                    window_end=NOW - timedelta(minutes=25),
                    endpoints=["odds"],
                    status="DUE",
                    blockers=[],
                    plan_hash="b" * 64,
                ),
            ]
        )
        session.commit()

    assert FutureRefreshDbRepository().market_refresh_status_for_fixtures(["fixture"], now=NOW)[
        "next_refresh_tick"
    ] == scheduled_at.isoformat().replace("+00:00", "Z")
    assert DashboardReadModelRepository().market_collection_status_for_fixtures(
        ["fixture"], now=NOW
    )["fixture"] == {
        "odds_status": "WINDOW_DUE",
        "last_refresh_hint": None,
        "market_collection": {
            "latest_snapshot_at": None,
            "latest_snapshot_checkpoint": None,
            "target_checkpoint": "T48",
            "scheduled_at": (NOW - timedelta(minutes=30)).isoformat().replace(
                "+00:00", "Z"
            ),
            "window_end_at": (NOW - timedelta(minutes=25)).isoformat().replace(
                "+00:00", "Z"
            ),
            "overdue": True,
            "public_semantics": {"scope": "MATCH", "cause": "AWAITING_COLLECTION"},
        },
    }
    assert FutureRefreshDbRepository().next_market_refresh_by_fixture(
        ["fixture", "api_football:fixture"], now=NOW
    ) == {
        "fixture": scheduled_at.isoformat().replace("+00:00", "Z"),
        "api_football:fixture": scheduled_at.isoformat().replace("+00:00", "Z"),
    }


@pytest.mark.parametrize(
    ("scheduled_delta", "window_end_delta", "cause", "status", "overdue"),
    [
        (timedelta(minutes=10), timedelta(minutes=15), "NOT_YET_DUE", "WAITING_WINDOW", False),
        (timedelta(minutes=-2), timedelta(minutes=3), "AWAITING_COLLECTION", "WINDOW_DUE", False),
        (timedelta(minutes=-10), timedelta(minutes=-5), "AWAITING_COLLECTION", "WINDOW_DUE", True),
    ],
)
def test_market_collection_uses_plan_window_not_fixed_snapshot_age(
    tmp_path: Path,
    monkeypatch: Any,
    scheduled_delta: timedelta,
    window_end_delta: timedelta,
    cause: str,
    status: str,
    overdue: bool,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    scheduled_at = NOW + scheduled_delta
    window_end = NOW + window_end_delta
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="window-plan",
                fixture_id="api_football:fixture",
                competition_id="allsvenskan",
                season="2026",
                policy_version="test-policy",
                checkpoint="T24_OPEN_ODDS",
                kickoff_utc=NOW + timedelta(days=1),
                scheduled_at=scheduled_at,
                window_start=scheduled_at,
                window_end=window_end,
                endpoints=["odds"],
                status="DUE" if scheduled_at <= NOW else "PLANNED",
                blockers=[],
                plan_hash="d" * 64,
            )
        )
        session.commit()

    payload = DashboardReadModelRepository().market_collection_status_for_fixtures(
        ["fixture"], now=NOW
    )["fixture"]

    assert payload["odds_status"] == status
    assert payload["market_collection"] == {
        "latest_snapshot_at": None,
        "latest_snapshot_checkpoint": None,
        "target_checkpoint": "T24_OPEN_ODDS",
        "scheduled_at": scheduled_at.isoformat().replace("+00:00", "Z"),
        "window_end_at": window_end.isoformat().replace("+00:00", "Z"),
        "overdue": overdue,
        "public_semantics": {"scope": "MATCH", "cause": cause},
    }


def test_satisfied_collection_window_exposes_snapshot_checkpoint_and_next_plan(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    captured_at = NOW - timedelta(minutes=4)
    next_scheduled_at = NOW + timedelta(hours=12)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add_all(
            [
                MatchdayCheckpointPlanModel(
                    plan_id="satisfied-plan",
                    fixture_id="api_football:fixture",
                    competition_id="allsvenskan",
                    season="2026",
                    policy_version="test-policy",
                    checkpoint="T24_OPEN_ODDS",
                    kickoff_utc=NOW + timedelta(days=1),
                    scheduled_at=NOW - timedelta(minutes=5),
                    window_start=NOW - timedelta(minutes=5),
                    window_end=NOW + timedelta(minutes=5),
                    endpoints=["odds"],
                    status="CAPTURED",
                    blockers=[],
                    plan_hash="e" * 64,
                ),
                MatchdayCheckpointPlanModel(
                    plan_id="next-plan",
                    fixture_id="api_football:fixture",
                    competition_id="allsvenskan",
                    season="2026",
                    policy_version="test-policy",
                    checkpoint="T12_OPEN_ODDS",
                    kickoff_utc=NOW + timedelta(days=1),
                    scheduled_at=next_scheduled_at,
                    window_start=next_scheduled_at,
                    window_end=next_scheduled_at + timedelta(minutes=10),
                    endpoints=["odds"],
                    status="PLANNED",
                    blockers=[],
                    plan_hash="f" * 64,
                ),
                MatchdayEndpointCaptureModel(
                    capture_id="satisfied-capture",
                    fixture_id="api_football:fixture",
                    competition_id="allsvenskan",
                    checkpoint="T24_OPEN_ODDS",
                    endpoint="odds",
                    sanitized_params={"fixture": "fixture"},
                    params_hash="1" * 64,
                    request_task_key="test",
                    attempt=1,
                    requested_at=captured_at,
                    provider_captured_at=captured_at,
                    status_code=200,
                    elapsed_ms=1,
                    response_count=1,
                    quota_values={},
                    raw_payload_sha256="2" * 64,
                    provider_event_time=None,
                    capture_status="CAPTURED",
                    error_code=None,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                MatchdayEndpointCapturePlanModel(
                    link_hash="3" * 64,
                    capture_id="satisfied-capture",
                    plan_id="satisfied-plan",
                    endpoint="odds",
                    link_status="LINKED",
                    linked_at=captured_at,
                ),
                MatchdayMarketObservationModel(
                    observation_id="4" * 64,
                    fixture_id="api_football:fixture",
                    provider_fixture_id="fixture",
                    competition_id="allsvenskan",
                    provider="api_football",
                    bookmaker_id="1",
                    bookmaker_name="Bookmaker",
                    capture_id="satisfied-capture",
                    provider_bet_id="4",
                    raw_market_label="Asian Handicap",
                    canonical_market="ASIAN_HANDICAP",
                    canonical_selection="HOME",
                    provider_selection="Home",
                    line="-0.25",
                    decimal_odds="1.95",
                    suspended=False,
                    live=False,
                    provider_updated_at=captured_at.isoformat(),
                    captured_at=captured_at,
                    ingested_at=captured_at,
                    raw_payload_sha256="2" * 64,
                    source_revision="test",
                ),
            ]
        )
        session.commit()

    payload = DashboardReadModelRepository().market_collection_status_for_fixtures(
        ["fixture"], now=NOW
    )["fixture"]

    assert payload["odds_status"] == "READY"
    assert payload["market_collection"] == {
        "latest_snapshot_at": captured_at.isoformat().replace("+00:00", "Z"),
        "latest_snapshot_checkpoint": "T24_OPEN_ODDS",
        "target_checkpoint": "T12_OPEN_ODDS",
        "scheduled_at": next_scheduled_at.isoformat().replace("+00:00", "Z"),
        "window_end_at": (next_scheduled_at + timedelta(minutes=10))
        .isoformat()
        .replace("+00:00", "Z"),
        "overdue": False,
        "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
    }


def test_lineups_only_checkpoint_is_separate_from_market_collection(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    scheduled_at = NOW + timedelta(minutes=10)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="lineups-only-plan",
                fixture_id="api_football:fixture",
                competition_id="world_cup_2026",
                season="2026",
                policy_version="test-policy",
                checkpoint="T45_LINEUPS_RETRY",
                kickoff_utc=NOW + timedelta(hours=1),
                scheduled_at=scheduled_at,
                window_start=scheduled_at,
                window_end=scheduled_at + timedelta(minutes=5),
                endpoints=["lineups"],
                status="PLANNED",
                blockers=[],
                plan_hash="c" * 64,
            )
        )
        session.commit()

    assert DashboardReadModelRepository().market_collection_status_for_fixtures(
        ["fixture"], now=NOW
    )["fixture"] == {
        "odds_status": "NOT_SCHEDULED",
        "last_refresh_hint": None,
        "market_collection": {
            "latest_snapshot_at": None,
            "latest_snapshot_checkpoint": None,
            "target_checkpoint": None,
            "scheduled_at": None,
            "window_end_at": None,
            "overdue": False,
            "public_semantics": {"scope": "MATCH", "cause": None},
        },
        "lineup_collection": {
            "target_checkpoint": "T45_LINEUPS_RETRY",
            "scheduled_at": scheduled_at.isoformat().replace("+00:00", "Z"),
            "window_end_at": (scheduled_at + timedelta(minutes=5))
            .isoformat()
            .replace("+00:00", "Z"),
            "overdue": False,
            "public_semantics": {"scope": "MATCH", "cause": "NOT_YET_DUE"},
        },
    }


@pytest.mark.parametrize(
    ("response_count", "expected_status"),
    [(0, "PROVIDER_EMPTY"), (2, "MARKET_UNAVAILABLE")],
)
def test_market_collection_status_distinguishes_empty_provider_from_unmapped_market(
    tmp_path: Path,
    monkeypatch: Any,
    response_count: int,
    expected_status: str,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        session.add(
            MatchdayEndpointCaptureModel(
                capture_id="capture",
                fixture_id="api_football:fixture",
                competition_id="world_cup_2026",
                checkpoint="T60",
                endpoint="odds",
                sanitized_params={"fixture": "fixture"},
                params_hash="a" * 64,
                request_task_key="test",
                attempt=1,
                requested_at=NOW,
                provider_captured_at=NOW,
                status_code=200,
                elapsed_ms=1,
                response_count=response_count,
                quota_values={},
                raw_payload_sha256="b" * 64,
                provider_event_time=None,
                capture_status="CAPTURED",
                error_code=None,
            )
        )
        session.commit()

    assert DashboardReadModelRepository().market_collection_status_for_fixtures(
        ["fixture"], now=NOW
    )["fixture"] == {
        "odds_status": expected_status,
        "last_refresh_hint": NOW.isoformat().replace("+00:00", "Z"),
        "market_collection": {
            "latest_snapshot_at": None,
            "latest_snapshot_checkpoint": None,
            "target_checkpoint": None,
            "scheduled_at": None,
            "window_end_at": None,
            "overdue": False,
            "public_semantics": {"scope": "MATCH", "cause": None},
        },
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
        materialize_public_artifacts=materialize_projection_events_for_test,
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
        materialize_public_artifacts=materialize_projection_events_for_test,
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


def test_checkpoint_audit_retains_evidence_without_retired_plan_authority(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    audit_id = repository.write_checkpoint_audit(
        fixture_id="1489404",
        checkpoint="T24",
        as_of=NOW,
        calls_used=1,
        status="COMPLETED",
        details={"contract": "w2.checkpoint_refresh.v1"},
    )

    assert audit_id >= 1
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        assert (
            session.scalar(select(func.count()).select_from(FutureRefreshCheckpointAuditModel)) == 1
        )


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


def test_raw_payload_inserted_at_is_first_insert_authority(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    repository = FutureRefreshDbRepository()
    sha256 = "f" * 64
    repository.save_raw_payload(
        sha256=sha256,
        endpoint="odds",
        captured_at=NOW,
        payload={"response": []},
    )
    engine = create_engine(get_settings().database_url.get_secret_value())
    with Session(engine) as session:
        first = session.get(RawPayloadModel, sha256)
        assert first is not None
        first_inserted_at = first.inserted_at
        assert first_inserted_at is not None

    repository.save_raw_payload(
        sha256=sha256,
        endpoint="odds",
        captured_at=NOW + timedelta(minutes=1),
        payload={"response": []},
    )
    with Session(engine) as session:
        replay = session.get(RawPayloadModel, sha256)
        assert replay is not None
        assert replay.inserted_at == first_inserted_at
        assert session.scalar(select(func.count()).select_from(RawPayloadModel)) == 1


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

    before_restart = FutureRefreshDbRepository().request_count_since(since)
    after_restart = FutureRefreshDbRepository().request_count_since(since)

    assert before_restart >= 120
    assert after_restart == before_restart


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


def test_request_count_since_prefers_provider_quota_over_local_request_logs(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    since = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        for index in range(80):
            requested_at = since + timedelta(seconds=index)
            session.add(
                ProviderRequestLogModel(
                    provider="api_football",
                    endpoint="status" if index < 40 else "fixtures",
                    request_hash=f"{index:064x}",
                    live=True,
                    status_code=200,
                    requested_at=requested_at,
                    completed_at=requested_at,
                )
            )
        session.add(
            QuotaUsageModel(
                provider="api_football",
                endpoint="odds",
                used=10,
                limit=100,
                window_start=since,
                window_end=since + timedelta(days=1),
            )
        )
        session.commit()

    repository = FutureRefreshDbRepository()
    assert repository.request_count_since(since) == 10
    assert repository.request_count_since(since, include_quota_usage=False) == 80


def test_provider_quota_snapshot_uses_strictest_persisted_remaining(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    configure_sqlite_db(monkeypatch, tmp_path)
    engine = create_engine(get_settings().database_url.get_secret_value())
    since = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
    with Session(engine) as session:
        session.add_all(
            [
                QuotaUsageModel(
                    provider="api_football",
                    endpoint="status",
                    used=5,
                    limit=100,
                    window_start=since,
                    window_end=since + timedelta(days=1),
                ),
                QuotaUsageModel(
                    provider="api_football",
                    endpoint="odds",
                    used=7,
                    limit=100,
                    window_start=since,
                    window_end=since + timedelta(days=1),
                ),
            ]
        )
        session.commit()

    assert FutureRefreshDbRepository().provider_quota_snapshot(since) == {
        "daily_limit": 100,
        "used": 7,
        "remaining": 93,
    }
