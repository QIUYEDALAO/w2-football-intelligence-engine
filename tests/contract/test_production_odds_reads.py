from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from w2.api import repository as api_repository
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.future_refresh_models import FutureMarketObservationModel
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
from w2.ingestion.future_refresh_repository import FutureRefreshDbRepository

AUTHORITY_TABLE = "matchday_market_observations"
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


def _seed_authority_and_legacy(engine: Any) -> None:
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
        session.add_all(
            [
                FutureMarketObservationModel(
                    observation_id="legacy-conflict",
                    fixture_id="123",
                    provider="api_football",
                    bookmaker_id="legacy-bookmaker",
                    bookmaker_name="Legacy Bookmaker",
                    provider_bet_id="4",
                    raw_market_label="Asian Handicap",
                    canonical_market="ASIAN_HANDICAP",
                    selection="HOME",
                    line="-9.5",
                    decimal_odds="9.99",
                    suspended=False,
                    live=False,
                    provider_last_update="2026-07-23T01:01:00Z",
                    captured_at=captured_at,
                    ingested_at=captured_at,
                    raw_payload_sha256="b" * 64,
                    source_revision="legacy-revision",
                    candidate=False,
                    formal_recommendation=False,
                ),
                FutureMarketObservationModel(
                    observation_id="legacy-only",
                    fixture_id="999",
                    provider="api_football",
                    bookmaker_id="legacy-bookmaker",
                    bookmaker_name="Legacy Bookmaker",
                    provider_bet_id="4",
                    raw_market_label="Asian Handicap",
                    canonical_market="ASIAN_HANDICAP",
                    selection="HOME",
                    line="-1.0",
                    decimal_odds="1.88",
                    suspended=False,
                    live=False,
                    provider_last_update="2026-07-23T01:01:00Z",
                    captured_at=captured_at,
                    ingested_at=captured_at,
                    raw_payload_sha256="c" * 64,
                    source_revision="legacy-only-revision",
                    candidate=False,
                    formal_recommendation=False,
                ),
            ]
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
    _seed_authority_and_legacy(engine)
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


def test_twenty_reads_preserve_identity_and_issue_zero_writes() -> None:
    engine = _engine()
    _seed_authority_and_legacy(engine)
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

    monkeypatch.setattr(api_repository, "RUNTIME", tmp_path)
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: DbRepository())

    assert api_repository.ReadModelRepository().market_snapshots() == [
        {"fixture_id": "database", "source": AUTHORITY_TABLE}
    ]


def test_api_odds_reads_use_one_scoped_entry_and_no_runtime_or_seed() -> None:
    source = Path("src/w2/api/repository.py").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_API_ODDS_SOURCES:
        assert forbidden not in source
    assert AUTHORITY_METHOD in inspect.getsource(
        api_repository.ReadModelService._fixture_observations_bounded
    )
    assert AUTHORITY_METHOD in inspect.getsource(
        api_repository.ReadModelService._attach_last_known_odds
    )
    assert AUTHORITY_METHOD in inspect.getsource(
        api_repository.ReadModelService.public_analysis_card_bounded
    )
    assert "public_analysis_card_bounded" in inspect.getsource(
        api_repository.ReadModelService._dashboard_card_from_matchday
    )
    for method in (
        api_repository.ReadModelService.odds_timeline,
        api_repository.ReadModelService.market_probabilities,
    ):
        method_source = inspect.getsource(method)
        assert "_fixture_observations_bounded" in method_source
        assert "dashboard_fixture" not in method_source
    assert not hasattr(api_repository.ReadModelRepository, "staging_seed_dashboard")


def test_empty_database_returns_empty_odds_without_file_fill(monkeypatch: Any) -> None:
    monkeypatch.setattr(api_repository, "future_refresh_db_repository", lambda: None)
    repository = api_repository.ReadModelRepository()

    assert repository.market_snapshots() == []
    assert repository.future_market_observations_for_fixtures(["123"]) == []
