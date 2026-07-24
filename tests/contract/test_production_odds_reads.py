from __future__ import annotations

import inspect
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from w2.api import repository as api_repository
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.market_projection_view import (
    PROJECTION_VIEW_NAME,
    current_market_projection,
)
from w2.infrastructure.persistence.matchday_intake_models import MatchdayMarketObservationModel
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
