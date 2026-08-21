from __future__ import annotations

import inspect
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from w2.api import repository as api_repository
from w2.dashboard.date_window import football_day_window
from w2.dashboard.day_view import build_dashboard_day_view
from w2.dashboard.workspace import build_dashboard_intelligence_workspace
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.api_models import ReadModelCheckpointModel
from w2.infrastructure.persistence.market_projection_view import (
    PROJECTION_VIEW_NAME,
    current_market_projection,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayCheckpointPlanModel,
    MatchdayFixtureIdentityModel,
    MatchdayMarketObservationModel,
)
from w2.infrastructure.persistence.models import ResultModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository
from w2.prematch import analysis_calculator as calculation_repository

AUTHORITY_TABLE = "matchday_market_observations"
LEGACY_TABLE = "future_market_observation"
AUTHORITY_METHOD = "future_market_observations_for_fixtures"
FORBIDDEN_API_ODDS_SOURCES = (
    "stage7e/market_snapshots.json",
    "W2_MARKET_TIMELINE_RUNTIME_ROOT",
    "staging_seed_dashboard",
)


def _engine() -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _seed_authority(engine: Any) -> None:
    captured_at = datetime(2026, 7, 23, 1, 2, 3, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MatchdayMarketObservationModel(
                observation_id="authority-quote-1",
                fixture_id="api_football:123",
                provider_fixture_id="123",
                competition_id="world_cup_2026",
                provider="api_football",
                bookmaker_id="bookmaker-7",
                bookmaker_name="Bookmaker Seven",
                capture_id="capture-1",
                provider_bet_id="4",
                raw_market_label="Asian Handicap",
                canonical_market="ASIAN_HANDICAP",
                canonical_selection="HOME",
                provider_selection="Home -0.5",
                line="-0.5",
                decimal_odds="1.91",
                suspended=False,
                live=False,
                provider_updated_at="2026-07-23T01:01:00Z",
                captured_at=captured_at,
                ingested_at=captured_at,
                raw_payload_sha256="a" * 64,
                source_revision="authority-revision",
            )
        )
        session.commit()


def _identity(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["fixture_id"],
        row["bookmaker_id"],
        row["bookmaker_name"],
        row["canonical_market"],
        row["selection"],
        row["line"],
        row["decimal_odds"],
        row["captured_at"],
        row["observation_id"],
    )


def test_matchday_observation_is_the_only_database_read_authority() -> None:
    engine = _engine()
    _seed_authority(engine)
    repository = FutureRefreshDbRepository(engine=engine)

    rows = repository.latest_market_observations_for_fixtures(["123"])

    assert len(rows) == 1
    assert _identity(rows[0]) == (
        "123",
        "bookmaker-7",
        "Bookmaker Seven",
        "ASIAN_HANDICAP",
        "HOME",
        "-0.5",
        "1.91",
        "2026-07-23T01:02:03Z",
        "authority-quote-1",
    )
    assert repository.latest_market_observations_for_fixtures(["999"]) == []
    assert repository.market_snapshots() == [
        {
            "fixture_id": "123",
            "captured_at": "2026-07-23T01:02:03Z",
            "captured_at_utc": "2026-07-23T01:02:03Z",
            "snapshot_semantics": "CAPTURED_AT",
            "bookmaker_count": 1,
            "quality": "READY",
            "source": AUTHORITY_TABLE,
            "market_coverage": {"ASIAN_HANDICAP": True},
            "candidate": False,
            "formal_recommendation": False,
        }
    ]
    assert (
        repository.market_refresh_status_for_fixtures(
            ["123"],
            now=datetime(2026, 7, 23, 1, 3, tzinfo=UTC),
        )["odds_last_confirmed_at"]
        == "2026-07-23T01:02:03Z"
    )


def test_api_refresh_status_reads_canonical_scheduler_plan(
    monkeypatch: Any,
) -> None:
    engine = _engine()
    now = datetime(2026, 8, 3, 1, 20, tzinfo=UTC)
    scheduled_at = now + timedelta(hours=3)
    with Session(engine) as session:
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="api-canonical-plan",
                fixture_id="api_football:123",
                competition_id="brasileirao_serie_a",
                season="2026",
                policy_version="test-policy",
                checkpoint="T12",
                kickoff_utc=now + timedelta(hours=12),
                scheduled_at=scheduled_at,
                window_start=scheduled_at,
                window_end=scheduled_at + timedelta(minutes=5),
                endpoints=["odds"],
                status="PLANNED",
                blockers=[],
                plan_hash="b" * 64,
            )
        )
        session.commit()
    monkeypatch.setattr(api_repository, "create_engine", lambda: engine)

    status = api_repository.ReadModelRepository().market_refresh_status_for_fixtures(
        ["123"],
        now=now,
    )

    assert status["next_refresh_tick"] == "2026-08-03T04:20:00Z"


def test_api_dashboard_metadata_supports_more_than_64_fixtures(monkeypatch: Any) -> None:
    engine = _engine()
    now = datetime(2026, 8, 3, 1, 20, tzinfo=UTC)
    fixture_id = "api_football:1064"
    scheduled_at = now + timedelta(hours=3)
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=fixture_id,
                provider="api_football",
                provider_fixture_id="1064",
                competition_id="allsvenskan",
                provider_league_id="113",
                season="2026",
                kickoff_utc=now + timedelta(hours=12),
                fixture_status="NS",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id="api_football:1",
                away_w2_team_id="api_football:2",
                team_identity_status="PROVIDER_PRIMARY_READY",
                raw_payload_sha256="a" * 64,
                captured_at=now,
                identity_hash="b" * 64,
                payload={},
            )
        )
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="api-plan-over-64",
                fixture_id=fixture_id,
                competition_id="allsvenskan",
                season="2026",
                policy_version="test-policy",
                checkpoint="T12",
                kickoff_utc=now + timedelta(hours=12),
                scheduled_at=scheduled_at,
                window_start=scheduled_at,
                window_end=scheduled_at + timedelta(minutes=5),
                endpoints=["odds"],
                status="PLANNED",
                blockers=[],
                plan_hash="c" * 64,
            )
        )
        session.commit()
    monkeypatch.setattr(api_repository, "create_engine", lambda: engine)
    fixture_ids = [str(1000 + index) for index in range(65)]
    repository = api_repository.ReadModelRepository()

    assert repository.canonical_competitions_for_fixtures(fixture_ids)["1064"] == "allsvenskan"
    assert (
        repository.market_refresh_status_for_fixtures(fixture_ids, now=now)["next_refresh_tick"]
        == "2026-08-03T04:20:00Z"
    )


def test_api_dashboard_uses_current_fixture_status_from_identity(monkeypatch: Any) -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 3, 14, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="api_football:1493049",
                provider="api_football",
                provider_fixture_id="1493049",
                competition_id="liga_profesional_argentina",
                provider_league_id="128",
                season="2026",
                kickoff_utc=datetime(2026, 8, 10, 22, tzinfo=UTC),
                fixture_status="FT",
                home_provider_team_id="1",
                away_provider_team_id="2",
                home_w2_team_id=None,
                away_w2_team_id=None,
                team_identity_status="REVIEW_REQUIRED",
                raw_payload_sha256="a" * 64,
                captured_at=now,
                identity_hash="b" * 64,
                payload={},
            )
        )
        session.commit()
    monkeypatch.setattr(api_repository, "create_engine", lambda: engine)

    statuses = api_repository.ReadModelRepository().fixture_statuses_for_fixtures(
        ["1493049"]
    )

    assert statuses == {
        "1493049": "FT",
        "api_football:1493049": "FT",
    }


def test_api_dashboard_projects_finished_status_over_stale_analysis_card() -> None:
    class Repository:
        @staticmethod
        def release_counts() -> dict[str, int]:
            return {
                "read_model_fixture_count": 1,
                "matchday_card_count": 1,
                "future_fixture_count": 1,
                "result_event_count": 0,
            }

        @staticmethod
        def dashboard_latest_fixtures() -> list[dict[str, Any]]:
            return [
                {
                    "fixture_id": "1493049",
                    "competition_id": "liga_profesional_argentina",
                    "kickoff_utc": "2026-08-10T22:00:00Z",
                    "status": "UPCOMING",
                }
            ]

        @staticmethod
        def fixture_statuses_for_fixtures(_fixture_ids: list[str]) -> dict[str, str]:
            return {"1493049": "FT"}

        @staticmethod
        def public_team_labels_for_fixtures(
            _fixture_ids: list[str],
        ) -> dict[str, dict[str, dict[str, Any]]]:
            return {
                "1493049": {
                    "home": {
                        "display_name": "天狼星",
                        "state": "CHINESE_LABEL_READY",
                        "canonical_team_id": "w2:team:api_football:370",
                        "provider_team_id": "370",
                        "raw_provider_name": "Sirius",
                    },
                    "away": {
                        "display_name": "布洛马波卡纳",
                        "state": "CHINESE_LABEL_READY",
                        "canonical_team_id": "w2:team:api_football:371",
                        "provider_team_id": "371",
                        "raw_provider_name": "IF Brommapojkarna",
                    },
                }
            }

        @staticmethod
        def analysis_card_projection(_fixture_id: str) -> dict[str, Any]:
            return {
                "fixture_id": "1493049",
                "competition_id": "liga_profesional_argentina",
                "decision_tier": "NOT_READY",
                "data_status": "BLOCKED",
                "lifecycle_status": "DRAFT",
                "lineup_requirement": "ADVISORY",
                "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
                "decision_contract": {
                    "decision_tier": "NOT_READY",
                    "data_status": "BLOCKED",
                    "lifecycle_status": "DRAFT",
                    "outcome_tracked": False,
                    "lock_eligible": False,
                    "recommendation_id": None,
                    "pick": None,
                    "non_pick": {
                        "reason_code": "NOT_READY",
                        "reason_human": "身份待确认",
                        "action": "WAIT",
                        "next_eval_at": None,
                    },
                    "lineup_requirement": "ADVISORY",
                    "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
                },
            }

    payload = api_repository.ReadModelService(
        repository=Repository(),  # type: ignore[arg-type]
    ).dashboard(target_date="2026-08-10", window="today")

    assert payload["all"][0]["status"] == "FINISHED"
    assert payload["all"][0]["home_team_label"]["display_name"] == "天狼星"
    assert payload["all"][0]["away_team_label"]["display_name"] == "布洛马波卡纳"
    assert payload["finished"][0]["fixture_id"] == "1493049"
    assert payload["upcoming"] == []
    day_view = build_dashboard_day_view(payload, environment="staging")
    workspace = build_dashboard_intelligence_workspace(day_view, replay={})
    assert workspace["matches"][0]["home_team_label"]["display_name"] == "天狼星"
    assert workspace["matches"][0]["away_team_label"]["display_name"] == "布洛马波卡纳"


def test_sc19_date_strip_reads_persisted_inventory_without_business_writes(
    monkeypatch: Any,
) -> None:
    engine = _engine()
    now = datetime(2026, 8, 11, 1, 0, tzinfo=UTC)
    fixture_id = "api_football:1494239"
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id=fixture_id,
                provider="api_football",
                provider_fixture_id="1494239",
                competition_id="allsvenskan",
                provider_league_id="113",
                season="2026",
                kickoff_utc=datetime(2026, 8, 10, 17, 0, tzinfo=UTC),
                fixture_status="FT",
                home_provider_team_id="370",
                away_provider_team_id="371",
                home_w2_team_id="w2:team:api_football:370",
                away_w2_team_id="w2:team:api_football:371",
                team_identity_status="PROVIDER_PRIMARY_READY",
                raw_payload_sha256="a" * 64,
                captured_at=now,
                identity_hash="b" * 64,
                payload={},
            )
        )
        for provider, competition_id, suffix in (
            ("other_provider", "allsvenskan", "other-provider"),
            ("api_football", "rogue_league", "rogue-league"),
        ):
            session.add(
                MatchdayFixtureIdentityModel(
                    fixture_id=f"{provider}:{suffix}",
                    provider=provider,
                    provider_fixture_id=suffix,
                    competition_id=competition_id,
                    provider_league_id="outside-scope",
                    season="2026",
                    kickoff_utc=datetime(2026, 8, 10, 18, 0, tzinfo=UTC),
                    fixture_status="NS",
                    home_provider_team_id="outside-home",
                    away_provider_team_id="outside-away",
                    home_w2_team_id=None,
                    away_w2_team_id=None,
                    team_identity_status="REVIEW_REQUIRED",
                    raw_payload_sha256=suffix.ljust(64, "a")[:64],
                    captured_at=now,
                    identity_hash=suffix.ljust(64, "b")[:64],
                    payload={},
                )
            )
        session.add(
            MatchdayCheckpointPlanModel(
                plan_id="sc19-plan",
                fixture_id=fixture_id,
                competition_id="allsvenskan",
                season="2026",
                policy_version="existing-policy",
                checkpoint="T12",
                kickoff_utc=datetime(2026, 8, 10, 17, 0, tzinfo=UTC),
                scheduled_at=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
                window_start=datetime(2026, 8, 10, 5, 0, tzinfo=UTC),
                window_end=datetime(2026, 8, 10, 5, 5, tzinfo=UTC),
                endpoints=["odds"],
                status="DUE",
                test_only=False,
                blockers=[],
                plan_hash="c" * 64,
            )
        )
        session.commit()
    monkeypatch.setattr(api_repository, "create_engine", lambda: engine)
    monkeypatch.setattr(
        api_repository.ReadModelRepository,
        "_dashboard_competition_ids",
        lambda _self: ("allsvenskan",),
    )
    writes: list[str] = []

    def record_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "MERGE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    strip = api_repository.ReadModelRepository().persisted_date_strip(
        date(2026, 8, 10),
        now=now,
    )

    assert strip[7]["fixture_count"] == 1
    assert strip[7]["finished_fixture_count"] == 1
    assert strip[7]["market_collection_window_status"] == (
        "MARKET_COLLECTION_DUE_EVIDENCE_NOT_READY"
    )
    assert writes == []


def test_dashboard_window_read_batches_before_projection(monkeypatch: Any) -> None:
    engine = _engine()
    target_start = datetime(2026, 8, 14, 4, tzinfo=UTC)
    target_end = datetime(2026, 8, 15, 4, tzinfo=UTC)
    with Session(engine) as session:
        for index in range(72):
            provider_fixture_id = (
                ("9999", "1000", "1001")[index]
                if index < 3
                else str(2000 + index)
            )
            kickoff = (
                target_start + timedelta(hours=index + 1)
                if index < 3
                else target_end + timedelta(days=1, minutes=index)
            )
            session.add(
                MatchdayFixtureIdentityModel(
                    fixture_id=f"api_football:{provider_fixture_id}",
                    provider="api_football",
                    provider_fixture_id=provider_fixture_id,
                    competition_id="allsvenskan",
                    provider_league_id="113",
                    season="2026",
                    kickoff_utc=kickoff,
                    fixture_status="NS",
                    home_provider_team_id=f"home-{index}",
                    away_provider_team_id=f"away-{index}",
                    home_w2_team_id=None,
                    away_w2_team_id=None,
                    team_identity_status="REVIEW_REQUIRED",
                    raw_payload_sha256=f"{index:064x}",
                    captured_at=target_start,
                    identity_hash=f"{index + 100:064x}",
                    payload={
                        "home_team_name": f"Home {index}",
                        "away_team_name": f"Away {index}",
                    },
                )
            )
            if index != 0:
                session.add(
                    ReadModelCheckpointModel(
                        checkpoint_key=(
                            f"{api_repository.ANALYSIS_CARD_SHADOW_PREFIX}"
                            f"{provider_fixture_id}"
                        ),
                        source_hash=f"{index + 200:064x}",
                        created_at=target_start,
                        payload={"kickoff_utc": kickoff.isoformat()},
                    )
                )
        for provider, competition_id, suffix in (
            ("other_provider", "allsvenskan", "other-provider"),
            ("api_football", "rogue_league", "rogue-league"),
        ):
            session.add(
                MatchdayFixtureIdentityModel(
                    fixture_id=f"{provider}:{suffix}",
                    provider=provider,
                    provider_fixture_id=suffix,
                    competition_id=competition_id,
                    provider_league_id="outside-scope",
                    season="2026",
                    kickoff_utc=target_start + timedelta(minutes=30),
                    fixture_status="NS",
                    home_provider_team_id="outside-home",
                    away_provider_team_id="outside-away",
                    home_w2_team_id=None,
                    away_w2_team_id=None,
                    team_identity_status="REVIEW_REQUIRED",
                    raw_payload_sha256=suffix.ljust(64, "c")[:64],
                    captured_at=target_start,
                    identity_hash=suffix.ljust(64, "d")[:64],
                    payload={},
                )
            )
        session.commit()

    repository = api_repository.ReadModelRepository(engine=engine)
    monkeypatch.setattr(repository, "_dashboard_competition_ids", lambda: ("allsvenskan",))
    projected: list[str] = []

    def project(
        row: api_repository.Checkpoint,
        fixture_id: str,
    ) -> dict[str, Any]:
        projected.append(fixture_id)
        return {
            "fixture_id": fixture_id,
            "competition_id": "allsvenskan",
            "kickoff_utc": row.payload["kickoff_utc"],
            "status": "NS",
            "home_team_name": f"Home {fixture_id}",
            "away_team_name": f"Away {fixture_id}",
        }

    monkeypatch.setattr(repository, "_analysis_card_from_checkpoint", project)
    statements: list[str] = []

    def record_select(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_select)
    fixtures = repository.dashboard_fixtures_for_window(
        start=target_start,
        end=target_end,
        limit=2,
    )

    assert [row["fixture_id"] for row in fixtures] == ["9999", "1000"]
    assert fixtures[0]["_analysis_card_projection"] is None
    assert projected == ["1000"]
    assert len(statements) == 1
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_dashboard_repository_reuses_one_lazy_engine(monkeypatch: Any) -> None:
    engine = _engine()
    engine_calls = 0

    def engine_factory() -> Any:
        nonlocal engine_calls
        engine_calls += 1
        return engine

    monkeypatch.setattr(api_repository, "create_engine", engine_factory)
    repository = api_repository.ReadModelRepository()

    assert repository.analysis_checkpoint_count() == 0
    assert repository.analysis_checkpoint_count() == 0
    assert engine_calls == 1


def test_dashboard_identity_without_analysis_checkpoint_fails_closed(
    monkeypatch: Any,
) -> None:
    engine = _engine()
    kickoff = datetime(2026, 8, 14, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MatchdayFixtureIdentityModel(
                fixture_id="api_football:missing-analysis",
                provider="api_football",
                provider_fixture_id="missing-analysis",
                competition_id="allsvenskan",
                provider_league_id="113",
                season="2026",
                kickoff_utc=kickoff,
                fixture_status="NS",
                home_provider_team_id="home-missing",
                away_provider_team_id="away-missing",
                home_w2_team_id=None,
                away_w2_team_id=None,
                team_identity_status="REVIEW_REQUIRED",
                raw_payload_sha256="c" * 64,
                captured_at=kickoff,
                identity_hash="d" * 64,
                payload={
                    "home_team_name": "Known Home",
                    "away_team_name": "Known Away",
                },
            )
        )
        session.commit()

    repository = api_repository.ReadModelRepository(engine=engine)
    monkeypatch.setattr(repository, "_dashboard_competition_ids", lambda: ("allsvenskan",))
    payload = api_repository.ReadModelService(
        repository=repository
    ).dashboard(target_date="2026-08-14", window="today", include_debug=True)

    assert [row["fixture_id"] for row in payload["all"]] == ["missing-analysis"]
    assert payload["all"][0]["projection_health"] == {
        "status": "SYSTEM_DEGRADED",
        "reason_code": "ANALYSIS_PROJECTION_NOT_READY",
    }
    assert payload["all"][0]["kickoff_utc"] == "2026-08-14T12:00:00Z"
    assert payload["debug"]["analysis_projection_count"] == 0


def test_dashboard_outcome_read_is_one_fixture_scoped_select() -> None:
    engine = _engine()
    with Session(engine) as session:
        session.add(
            ResultModel(
                id="result-1493049",
                fixture_id="api_football:1493049",
                home_goals=0,
                away_goals=2,
                result_status="FT",
                confirmed_at=datetime(2026, 8, 10, 23, tzinfo=UTC),
                source_payload_sha256="a" * 64,
                source_capture_id="capture-result-1493049",
                result_hash="b" * 64,
            )
        )
        session.commit()
    statements: list[str] = []

    def record_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    repository = api_repository.ReadModelRepository(engine=engine)

    outcomes = repository.dashboard_outcomes_for_fixtures(["1493049", "missing"])

    assert outcomes == [
        {"fixture_id": "1493049", "result_status": "FT", "score": "0-2"}
    ]
    assert len(statements) == 1
    assert statements[0].lstrip().upper().startswith("SELECT")


def test_release_counts_aggregates_without_materializing_analysis_cards(
    monkeypatch: Any,
) -> None:
    engine = _engine()
    with Session(engine) as session:
        for fixture_id, status in (("1", "NS"), ("2", "FT"), ("3", None)):
            session.add(
                ReadModelCheckpointModel(
                    checkpoint_key=(f"{api_repository.ANALYSIS_CARD_SHADOW_PREFIX}{fixture_id}"),
                    source_hash=fixture_id * 64,
                    created_at=datetime(2026, 8, 20, tzinfo=UTC),
                    payload={"analysis_card": {"status": status}},
                )
            )
        session.commit()

    repository = api_repository.ReadModelRepository(engine=engine)
    monkeypatch.setattr(
        repository,
        "dashboard_latest_fixtures",
        lambda: (_ for _ in ()).throw(AssertionError("analysis cards materialized")),
    )

    assert repository.release_counts() == {
        "read_model_fixture_count": 3,
        "matchday_card_count": 3,
        "future_fixture_count": 3,
        "result_event_count": 1,
    }


def test_dashboard_service_consumes_batched_projection_without_per_fixture_reads() -> None:
    class Repository:
        window: tuple[datetime | None, datetime | None] | None = None
        fixture_ids: tuple[str, ...] | None = None

        def dashboard_fixtures_for_window(
            self,
            *,
            start: datetime | None,
            end: datetime | None,
            limit: int,
            fixture_ids: tuple[str, ...] | None = None,
        ) -> list[dict[str, Any]]:
            self.window = (start, end)
            self.fixture_ids = fixture_ids
            assert limit == (
                len(fixture_ids) if fixture_ids else api_repository.MAX_PUBLIC_FIXTURES
            )
            return [
                {
                    "fixture_id": "1493049",
                    "competition_id": "liga_profesional_argentina",
                    "kickoff_utc": "2026-08-10T22:00:00Z",
                    "status": "FT",
                    "_analysis_card_projection": {
                        "fixture_id": "1493049",
                        "competition_id": "liga_profesional_argentina",
                        "kickoff_utc": "2026-08-10T22:00:00Z",
                        "decision_tier": "NOT_READY",
                        "data_status": "BLOCKED",
                        "lifecycle_status": "DRAFT",
                        "lineup_requirement": "ADVISORY",
                        "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
                        "decision_contract": {
                            "decision_tier": "NOT_READY",
                            "data_status": "BLOCKED",
                            "lifecycle_status": "DRAFT",
                            "outcome_tracked": False,
                            "lock_eligible": False,
                            "recommendation_id": None,
                            "pick": None,
                            "non_pick": {
                                "reason_code": "NOT_READY",
                                "reason_human": "等待证据",
                                "action": "WAIT",
                                "next_eval_at": None,
                            },
                            "lineup_requirement": "ADVISORY",
                            "risk_reason_codes": ["LINEUP_UNOBSERVABLE"],
                        },
                    },
                    "_public_team_labels": {
                        "home": {"display_name": "班菲尔德"},
                        "away": {"display_name": "贝尔格拉诺"},
                    },
                }
            ]

        @staticmethod
        def analysis_checkpoint_count() -> int:
            return 72

        @staticmethod
        def dashboard_latest_fixtures() -> list[dict[str, Any]]:
            raise AssertionError("full checkpoint scan must not run")

        @staticmethod
        def analysis_card_projection(_fixture_id: str) -> dict[str, Any]:
            raise AssertionError("per-fixture checkpoint read must not run")

    repository = Repository()
    payload = api_repository.ReadModelService(
        repository=repository,  # type: ignore[arg-type]
    ).dashboard(target_date="2026-08-10", window="today", include_debug=True)

    assert repository.window == football_day_window(date(2026, 8, 10))
    assert [row["fixture_id"] for row in payload["all"]] == ["1493049"]
    assert payload["all"][0]["status"] == "FINISHED"
    assert payload["all"][0]["home_team_label"]["display_name"] == "班菲尔德"
    assert payload["debug"]["fixture_checkpoint_count"] == 72
    assert "_analysis_card_projection" not in payload["all"][0]
    assert "_public_team_labels" not in payload["all"][0]

    targeted = api_repository.ReadModelService(
        repository=repository,  # type: ignore[arg-type]
    ).dashboard_cards_for_fixtures(
        ["1493049"],
        generated_at=payload["generated_at"],
    )

    assert repository.fixture_ids == ("1493049",)
    assert targeted == payload["all"]


def test_api_dashboard_card_keeps_historical_v3_identity_immutable() -> None:
    class Repository:
        @staticmethod
        def analysis_card_projection(_fixture_id: str) -> dict[str, Any]:
            return {
                "fixture_id": "123",
                "competition_id": "71",
                "decision_tier": "NOT_READY",
                "recommendation_decision_v3": {
                    "competition_id": "71",
                    "outcome": "NOT_READY",
                },
            }

    card = api_repository.ReadModelService(
        repository=Repository(),  # type: ignore[arg-type]
    )._project_dashboard_card(
        {
            "fixture_id": "123",
            "competition_id": "71",
            "kickoff_utc": "2026-08-10T00:00:00Z",
            "status": "NS",
        },
        canonical_competition_id="brasileirao_serie_a",
    )

    assert card["competition_id"] == "brasileirao_serie_a"
    assert card["recommendation_decision_v3"]["competition_id"] == "71"
    assert card["recommendation_decision_v3_role"] == "HISTORY_ONLY"


def test_fixture_scoped_timeline_reads_history_not_current_projection() -> None:
    engine = _engine()
    _seed_authority(engine)
    opening_at = datetime(2026, 7, 22, 20, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            MatchdayMarketObservationModel(
                observation_id="authority-opening-1",
                fixture_id="api_football:123",
                provider_fixture_id="123",
                competition_id="world_cup_2026",
                provider="api_football",
                bookmaker_id="bookmaker-7",
                bookmaker_name="Bookmaker Seven",
                capture_id="capture-opening",
                provider_bet_id="4",
                raw_market_label="Asian Handicap",
                canonical_market="ASIAN_HANDICAP",
                canonical_selection="HOME",
                provider_selection="Home -0.5",
                line="-0.5",
                decimal_odds="2.05",
                suspended=False,
                live=False,
                provider_updated_at="2026-07-22T19:59:00Z",
                captured_at=opening_at,
                ingested_at=opening_at,
                raw_payload_sha256="b" * 64,
                source_revision="opening-revision",
            )
        )
        session.commit()

    repository = FutureRefreshDbRepository(engine=engine)
    current = repository.latest_market_observations_for_fixtures(["123"])
    timeline = repository.market_observation_timeline_for_fixtures(["123"])

    assert [row["observation_id"] for row in current] == ["authority-quote-1"]
    assert [row["observation_id"] for row in timeline] == [
        "authority-opening-1",
        "authority-quote-1",
    ]
    assert timeline[0]["provider"] == timeline[1]["provider"] == "api_football"
    assert timeline[0]["bookmaker_id"] == timeline[1]["bookmaker_id"] == "bookmaker-7"
    assert timeline[0]["raw_payload_sha256"] == "b" * 64
    assert timeline[0]["source_revision"] == "opening-revision"


def test_twenty_reads_preserve_identity_and_issue_zero_writes() -> None:
    engine = _engine()
    _seed_authority(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    writes: list[str] = []

    def record_statement(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "MERGE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(MatchdayMarketObservationModel))

    results = [repository.latest_market_observations_for_fixtures(["123"]) for _ in range(20)]

    with Session(engine) as session:
        after = session.scalar(select(func.count()).select_from(MatchdayMarketObservationModel))
    assert before == after == 1
    assert writes == []
    assert len(results) == 20
    expected = _identity(results[0][0])
    assert all(_identity(batch[0]) == expected for batch in results)


def test_runtime_market_snapshot_cannot_fill_database_result(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    runtime_snapshot = tmp_path / "stage7e" / "market_snapshots.json"
    runtime_snapshot.parent.mkdir(parents=True)
    runtime_snapshot.write_text(
        json.dumps([{"fixture_id": "poison", "source": "runtime"}]),
        encoding="utf-8",
    )

    class DbRepository:
        def market_snapshots(self) -> list[dict[str, Any]]:
            return [{"fixture_id": "database", "source": AUTHORITY_TABLE}]

    monkeypatch.setattr(calculation_repository, "RUNTIME", tmp_path)
    monkeypatch.setattr(
        calculation_repository,
        "future_refresh_db_repository",
        lambda: DbRepository(),
    )

    assert calculation_repository.ReadModelRepository().market_snapshots() == [
        {"fixture_id": "database", "source": AUTHORITY_TABLE}
    ]


def test_api_odds_reads_use_projection_only_and_no_runtime_or_seed() -> None:
    source = Path("src/w2/api/repository.py").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_API_ODDS_SOURCES:
        assert forbidden not in source
    assert "read_model_checkpoint" in source
    assert "FutureRefreshDbRepository" not in source
    assert "future_refresh_db_repository" not in source
    assert "_fixture_observations_bounded" not in source
    assert "_attach_last_known_odds" not in source
    for method in (
        api_repository.ReadModelService.odds_timeline,
        api_repository.ReadModelService.market_probabilities,
    ):
        method_source = inspect.getsource(method)
        assert "public_analysis_card_bounded" in method_source
    assert not hasattr(api_repository.ReadModelRepository, "staging_seed_dashboard")


def test_empty_database_returns_empty_odds_without_file_fill(monkeypatch: Any) -> None:
    monkeypatch.setattr(calculation_repository, "future_refresh_db_repository", lambda: None)
    repository = calculation_repository.ReadModelRepository()

    assert repository.market_snapshots() == []
    assert repository.future_market_observations_for_fixtures(["123"]) == []


def test_legacy_odds_table_is_fully_removed() -> None:
    """ARCH-P1-02: one odds history table, no legacy twin left to drift from it."""
    assert LEGACY_TABLE not in Base.metadata.tables

    # The canonical read method is named `future_market_observations_...`, so the
    # table name is only a hit when it is not followed by the plural "s".
    legacy_reference = re.compile(rf"{LEGACY_TABLE}(?!s)")
    # Deployment scripts and CI query the database directly, so they belong in
    # the guard: a stale `select ... from future_market_observation` there fails
    # only at deploy time, not at import time.
    scanned_roots = (Path("src/w2"), Path("apps"), Path("scripts"), Path("infra"))
    scanned_suffixes = {".py", ".sh", ".sql", ".yml", ".yaml"}
    # Asserting the table is gone necessarily names it; that is the opposite of
    # using it, so those lines are not offenders.
    absence_assertion = re.compile(r"information_schema|still exists")
    offenders = sorted(
        f"{path}:{number}"
        for root in scanned_roots
        if root.exists()
        for path in root.rglob("*")
        if path.is_file() and path.suffix in scanned_suffixes
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1
        )
        if legacy_reference.search(line) and not absence_assertion.search(line)
    )
    assert offenders == []


def test_current_market_projection_is_a_view_over_the_canonical_history() -> None:
    """ARCH-P1-02: the only current projection is derived, never a second table."""
    engine = _engine()
    _seed_authority(engine)
    inspector = sa_inspect(engine)

    assert PROJECTION_VIEW_NAME in inspector.get_view_names()
    assert PROJECTION_VIEW_NAME not in inspector.get_table_names()
    assert PROJECTION_VIEW_NAME not in Base.metadata.tables

    with Session(engine) as session:
        rows = list(session.execute(select(current_market_projection)).mappings())
    assert [row["observation_id"] for row in rows] == ["authority-quote-1"]
    assert rows[0]["projection_fixture_id"] == "123"


def test_bounded_projection_read_has_a_total_deterministic_order() -> None:
    """ARCH-P1-02 option A: rows differing only by line must not sort arbitrarily."""
    engine = _engine()
    captured_at = datetime(2026, 7, 23, 1, 2, 3, tzinfo=UTC)
    with Session(engine) as session:
        for index, line in enumerate(["-1.5", "-0.5", "0.5", "-0.25"]):
            session.add(
                MatchdayMarketObservationModel(
                    observation_id=f"quote-{index}",
                    fixture_id="api_football:123",
                    provider_fixture_id="123",
                    competition_id="eliteserien",
                    provider="api_football",
                    bookmaker_id="bookmaker-7",
                    bookmaker_name="Bookmaker Seven",
                    capture_id="capture-1",
                    provider_bet_id="4",
                    raw_market_label="Asian Handicap",
                    canonical_market="ASIAN_HANDICAP",
                    canonical_selection="HOME",
                    provider_selection="Home",
                    line=line,
                    decimal_odds="1.91",
                    suspended=False,
                    live=False,
                    provider_updated_at="2026-07-23T01:01:00Z",
                    captured_at=captured_at,
                    ingested_at=captured_at,
                    raw_payload_sha256="a" * 64,
                    source_revision="authority-revision",
                )
            )
        session.commit()

    repository = FutureRefreshDbRepository(engine=engine)
    reads = [repository.latest_market_observations_for_fixtures(["123"]) for _ in range(5)]

    # Same input, same order, every time - the previous sort stopped at the
    # selection and left these four rows in an arbitrary order.
    assert [row["line"] for row in reads[0]] == ["-0.25", "-0.5", "-1.5", "0.5"]
    assert all(read == reads[0] for read in reads)


def test_projection_keeps_two_providers_that_reuse_the_same_numeric_ids() -> None:
    """ARCH-P1-02: fixture and bookmaker ids are unique per provider, not globally.

    Two providers reusing the same numeric ids must stay two quotes; partitioning
    on the bare provider fixture id would drop one of them.
    """
    engine = _engine()
    captured_at = datetime(2026, 7, 23, 1, 2, 3, tzinfo=UTC)
    with Session(engine) as session:
        for provider, odds in (("api_football", "1.91"), ("other_provider", "2.05")):
            session.add(
                MatchdayMarketObservationModel(
                    observation_id=f"{provider}-quote",
                    fixture_id=f"{provider}:123",
                    provider_fixture_id="123",
                    competition_id="eliteserien",
                    provider=provider,
                    bookmaker_id="7",
                    bookmaker_name="Bookmaker Seven",
                    capture_id="capture-1",
                    provider_bet_id="4",
                    raw_market_label="Asian Handicap",
                    canonical_market="ASIAN_HANDICAP",
                    canonical_selection="HOME",
                    provider_selection="Home -0.5",
                    line="-0.5",
                    decimal_odds=odds,
                    suspended=False,
                    live=False,
                    provider_updated_at="2026-07-23T01:01:00Z",
                    captured_at=captured_at,
                    ingested_at=captured_at,
                    raw_payload_sha256="a" * 64,
                    source_revision="authority-revision",
                )
            )
        session.commit()

    with Session(engine) as session:
        rows = list(session.execute(select(current_market_projection)).mappings())

    assert sorted(row["provider"] for row in rows) == ["api_football", "other_provider"]
    assert sorted(row["decimal_odds"] for row in rows) == ["1.91", "2.05"]

    # The bounded read resolves a bare fixture id inside the api_football
    # namespace by its existing caller contract, so it returns that provider's
    # quote only - it must never pick up the other provider's row by numeric
    # collision.
    repository = FutureRefreshDbRepository(engine=engine)
    bounded = repository.latest_market_observations_for_fixtures(["123"])
    assert [row["provider"] for row in bounded] == ["api_football"]
    assert [row["decimal_odds"] for row in bounded] == ["1.91"]
