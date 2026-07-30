from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.matchday_intake_models import (
    MatchdayFixtureIdentityModel,
)
from w2.infrastructure.persistence.models import (
    PlayerIdentityMappingModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
    TeamLineupBaselineModel,
    TransfermarktPlayerReferenceModel,
)
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
)


def _team(team_id: int, offset: int) -> dict[str, object]:
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


def _install_player_identity_sources(
    repository: FutureRefreshDbRepository,
    engine: object,
    *,
    fixture_id: str = "fixture-authority",
    missing_squad_player_id: str | None = None,
    wrong_club_player_id: str | None = None,
) -> datetime:
    source_at = datetime(2026, 7, 18, tzinfo=UTC)
    kickoff = datetime(2026, 7, 19, 18, tzinfo=UTC)
    with Session(engine) as session:
        for team_id in ("10", "20"):
            w2_team_id = f"w2:team:api_football:{team_id}"
            session.add(
                CanonicalTeamModel(
                    w2_team_id=w2_team_id,
                    display_name=f"Team {team_id}",
                    country="Sweden",
                    active_status="ACTIVE",
                    created_at=source_at,
                    identity_hash=f"canonical-{team_id}",
                    payload={},
                )
            )
            for provider, provider_team_id in (
                ("api_football", team_id),
                ("transfermarkt", f"club-{team_id}"),
            ):
                session.add(
                    ProviderTeamIdentityCrosswalkModel(
                        id=f"{provider}:{provider_team_id}:allsvenskan:2026",
                        provider=provider,
                        provider_team_id=provider_team_id,
                        w2_team_id=w2_team_id,
                        competition_id="allsvenskan",
                        season="2026",
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_to=None,
                        identity_status="PROVIDER_PRIMARY_READY",
                        evidence_hashes=[f"{provider}-source-{team_id}"],
                        identity_hash=f"{provider}-identity-{team_id}",
                        review_status="APPROVED",
                        reviewed_by="fixture-authority-reviewer",
                        reviewed_at=source_at,
                        source_hashes=[f"{provider}-source-{team_id}"],
                        payload={},
                    )
                )
        for team_id, offset in (("10", 100), ("20", 200)):
            for index in range(11):
                player_id = str(offset + index)
                session.add(
                    TransfermarktPlayerReferenceModel(
                        transfermarkt_player_id=f"tm-{player_id}",
                        player_name=f"Player {player_id}",
                        normalized_name=f"player{player_id}",
                        current_club_id=(
                            "wrong-club" if player_id == wrong_club_player_id else f"club-{team_id}"
                        ),
                        current_club_name=f"Team {team_id}",
                        competition_code="SE1",
                        position="Goalkeeper" if index == 0 else "Midfield",
                        sub_position=None,
                        market_value_eur=Decimal("1000000"),
                        source_sha256="t" * 64,
                        observed_at=source_at,
                    )
                )
                session.add(
                    PlayerIdentityMappingModel(
                        api_football_player_id=player_id,
                        canonical_player_id=f"w2:player:transfermarkt:tm-{player_id}",
                        transfermarkt_player_id=f"tm-{player_id}",
                        team_external_id=team_id,
                        player_name=f"Player {player_id}",
                        normalized_name=f"player{player_id}",
                        provider_position="G" if index == 0 else "M",
                        transfermarkt_position="Goalkeeper" if index == 0 else "Midfield",
                        mapping_status="REVIEWED",
                        evidence={
                            "canonical_team_id": f"w2:team:api_football:{team_id}",
                            "review_status": "APPROVED",
                        },
                        identity_hash=f"reviewed-player-{player_id}",
                        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                        valid_to=None,
                        reviewed_at=source_at,
                        reviewed_by="fixture-authority-reviewer",
                    )
                )
        session.commit()
    repository.save_raw_payload(
        sha256="f" * 64,
        endpoint="fixtures",
        captured_at=source_at,
        payload={
            "response": [
                {
                    "fixture": {"id": fixture_id, "date": kickoff.isoformat()},
                    "league": {"id": 113, "season": 2026},
                }
            ]
        },
    )
    for team_id, offset, source_hash in (
        ("10", 100, "1" * 64),
        ("20", 200, "2" * 64),
    ):
        repository.save_raw_payload(
            sha256=source_hash,
            endpoint="squads",
            captured_at=source_at,
            payload={
                "parameters": {"team": team_id},
                "response": [
                    {
                        "team": {"id": int(team_id), "name": f"Team {team_id}"},
                        "players": [
                            {
                                "id": offset + index,
                                "name": f"Player {offset + index}",
                                "position": "Goalkeeper" if index == 0 else "Midfielder",
                            }
                            for index in range(11)
                            if str(offset + index) != missing_squad_player_id
                        ],
                    }
                ],
            },
        )
    return kickoff


def test_lineup_materialization_is_atomic_structured_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    payload = {"response": [_team(10, 100), _team(20, 200)]}
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=captured_at,
            raw_sha256="a" * 64,
            payload=payload,
        )
        == 2
    )
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=captured_at,
            raw_sha256="a" * 64,
            payload=payload,
        )
        == 0
    )
    with Session(engine) as session:
        snapshots = session.scalars(select(StructuredLineupSnapshotModel)).all()
        player_count = session.scalar(select(func.count(StructuredLineupPlayerModel.id)))
    assert len(snapshots) == 2
    assert all(snapshot.confirmed for snapshot in snapshots)
    assert player_count == 22


def test_lineup_business_identity_ignores_repeat_capture_and_changes_with_xi() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    first_at = datetime(2026, 7, 19, tzinfo=UTC)
    payload = {"response": [_team(10, 100), _team(20, 200)]}

    assert repository.confirmed_lineup_business_identity(fixture_id="fixture-1") is None
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=first_at,
            raw_sha256="a" * 64,
            payload=payload,
        )
        == 2
    )
    first_identity = repository.confirmed_lineup_business_identity(fixture_id="fixture-1")
    assert first_identity is not None

    repeat_payload = {"response": [_team(10, 100), _team(20, 200)]}
    repeat_payload["response"][0]["formation"] = "3-4-3"  # type: ignore[index]
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=first_at.replace(hour=1),
            raw_sha256="b" * 64,
            payload=repeat_payload,
        )
        == 2
    )
    assert repository.confirmed_lineup_business_identity(fixture_id="fixture-1") == first_identity

    changed_payload = {"response": [_team(10, 100), _team(20, 200)]}
    changed_payload["response"][1]["startXI"][10]["player"]["id"] = 999  # type: ignore[index]
    assert (
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=first_at.replace(hour=2),
            raw_sha256="c" * 64,
            payload=changed_payload,
        )
        == 2
    )
    assert repository.confirmed_lineup_business_identity(fixture_id="fixture-1") != first_identity


def test_lineup_materialization_rejects_one_team_without_visible_partial_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    try:
        repository.save_lineup_snapshots(
            fixture_id="fixture-1",
            captured_at=datetime(2026, 7, 19, tzinfo=UTC),
            raw_sha256="b" * 64,
            payload={"response": [_team(10, 100)]},
        )
    except Exception as exc:
        assert str(exc) == "LINEUP_TEAMS_INCOMPLETE"
    else:
        raise AssertionError("incomplete two-team lineup must fail closed")
    with Session(engine) as session:
        assert session.scalar(select(func.count(StructuredLineupSnapshotModel.id))) == 0


def test_historical_null_lineup_identity_hash_fails_closed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    with Session(engine) as session:
        for team_id in (10, 20):
            snapshot = StructuredLineupSnapshotModel(
                fixture_id="legacy-fixture",
                team_external_id=str(team_id),
                team_name=f"Team {team_id}",
                formation="4-3-3",
                captured_at=captured_at,
                confirmed=True,
                authoritative_status="COMPLETE",
                raw_sha256="a" * 64,
                lineup_identity_hash=None,
                schema_version="w2.structured_lineup.v1",
            )
            session.add(snapshot)
        session.commit()
    repository = FutureRefreshDbRepository(engine=engine)
    assert repository.lineup_gate_evidence(fixture_id="legacy-fixture", as_of=captured_at)[
        "blockers"
    ] == ["LINEUP_IDENTITY_HASH_MISSING"]


def test_saved_lineup_materializer_is_bounded_provider_free_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    payload = {
        "endpoint": "lineups",
        "parameters": {"fixture": "fixture-saved"},
        "response": [_team(10, 100), _team(20, 200)],
    }
    repository.save_raw_payload(
        sha256="e" * 64,
        endpoint="lineups",
        captured_at=captured_at,
        payload=payload,
    )
    repository.save_raw_payload(
        sha256="f" * 64,
        endpoint="lineups",
        captured_at=captured_at,
        payload={"endpoint": "lineups", "response": [_team(10, 100), _team(20, 200)]},
    )
    assert repository.stored_lineup_materialization_candidates(limit=0) == []
    assert len(repository.stored_lineup_materialization_candidates(limit=10)) == 1
    first = repository.materialize_stored_lineup_payloads(limit=10)
    second = repository.materialize_stored_lineup_payloads(limit=10)
    assert first == {
        "candidate_payload_count": 1,
        "materialized_snapshot_count": 2,
        "skipped_incomplete_count": 0,
        "provider_calls": 0,
    }
    assert second == {
        "candidate_payload_count": 1,
        "materialized_snapshot_count": 0,
        "skipped_incomplete_count": 0,
        "provider_calls": 0,
    }


def test_saved_lineups_materialize_asof_safe_deterministic_team_baselines() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    fixture_payload = {
        "response": [
            {
                "fixture": {"id": "fixture-1", "date": "2026-07-01T18:00:00Z"},
                "league": {"id": 39, "season": 2026},
            },
            {
                "fixture": {"id": "fixture-2", "date": "2026-07-10T18:00:00Z"},
                "league": {"id": 39, "season": 2026},
            },
        ]
    }
    repository.save_raw_payload(
        sha256="1" * 64,
        endpoint="fixtures",
        captured_at=datetime(2026, 6, 30, tzinfo=UTC),
        payload=fixture_payload,
    )
    repository.save_lineup_snapshots(
        fixture_id="fixture-1",
        captured_at=datetime(2026, 7, 1, 17, tzinfo=UTC),
        raw_sha256="2" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )
    repository.save_lineup_snapshots(
        fixture_id="fixture-2",
        captured_at=datetime(2026, 7, 10, 17, tzinfo=UTC),
        raw_sha256="3" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )

    first = repository.materialize_team_lineup_baselines(limit=10)
    second = repository.materialize_team_lineup_baselines(limit=10)

    assert first["materialized_baseline_count"] == 4
    assert second["materialized_baseline_count"] == 0
    with Session(engine) as session:
        baselines = list(
            session.scalars(
                select(TeamLineupBaselineModel).order_by(
                    TeamLineupBaselineModel.as_of_time,
                    TeamLineupBaselineModel.team_external_id,
                )
            )
        )
    assert len(baselines) == 4
    assert [row.match_count for row in baselines] == [0, 0, 1, 1]
    assert baselines[-1].payload["input_fixture_ids"] == ["fixture-1"]
    evidence = repository.lineup_gate_evidence(
        fixture_id="fixture-2",
        as_of=datetime(2026, 7, 10, 17, tzinfo=UTC),
    )
    assert len(evidence["baseline_artifact_hashes"]) == 2
    assert all(item["status"] == "COMPLETE" for item in evidence["lineup_change_features"])


def test_transfermarkt_snapshot_enables_team_scoped_identity_and_value_gate() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    observed_at = datetime(2026, 7, 18, tzinfo=UTC)
    rows = []
    for team_id, offset in ((10, 100), (20, 200)):
        for index in range(11):
            rows.append(
                {
                    "transfermarkt_player_id": f"tm-{offset + index}",
                    "player_name": f"Player {offset + index}",
                    "normalized_name": f"player{offset + index}",
                    "current_club_id": f"club-{team_id}",
                    "current_club_name": f"Team {team_id}",
                    "competition_code": "GB1",
                    "position": "Goalkeeper" if index == 0 else "Midfield",
                    "sub_position": None,
                    "market_value_eur": Decimal("1000000"),
                    "source_sha256": "c" * 64,
                    "observed_at": observed_at,
                }
            )
    import_args = {
        "source_url": "https://example.invalid/players.csv.gz",
        "source_sha256": "c" * 64,
        "observed_at": observed_at,
        "rows": rows,
    }
    assert repository.import_transfermarkt_player_snapshot(**import_args) == 22
    assert repository.import_transfermarkt_player_snapshot(**import_args) == 0
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    repository.save_lineup_snapshots(
        fixture_id="fixture-mapped",
        captured_at=captured_at,
        raw_sha256="d" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
    )
    evidence = repository.lineup_gate_evidence(fixture_id="fixture-mapped", as_of=captured_at)
    assert evidence["status"] == "INCOMPLETE"
    assert evidence["uniquely_mapped_starters"] == 0
    assert evidence["valued_starters"] == 0
    assert "PLAYER_IDENTITY_MAPPING_INCOMPLETE" in evidence["blockers"]


def test_lineup_materialization_projects_reviewed_db_identity_without_mapping_writes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(repository, engine)
    captured_at = kickoff.replace(hour=17)
    with Session(engine) as session:
        before = list(
            session.execute(
                select(
                    PlayerIdentityMappingModel.identity_hash,
                    PlayerIdentityMappingModel.canonical_player_id,
                ).order_by(PlayerIdentityMappingModel.identity_hash)
            )
        )

    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=captured_at,
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )

    with Session(engine) as session:
        after = list(
            session.execute(
                select(
                    PlayerIdentityMappingModel.identity_hash,
                    PlayerIdentityMappingModel.canonical_player_id,
                ).order_by(PlayerIdentityMappingModel.identity_hash)
            )
        )
        players = session.scalars(
            select(StructuredLineupPlayerModel).order_by(
                StructuredLineupPlayerModel.api_football_player_id
            )
        ).all()
    assert before == after
    assert len(players) == 22
    assert all(player.mapping_status == "REVIEWED" for player in players)
    assert all(
        player.canonical_player_id == f"w2:player:transfermarkt:tm-{player.api_football_player_id}"
        for player in players
    )


def test_join_evidence_and_lineup_gate_use_the_materialized_canonical_players() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(repository, engine)
    captured_at = kickoff.replace(hour=17)
    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=captured_at,
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )

    runs = [
        repository.player_identity_join_evidence(
            fixture_id="fixture-authority",
            as_of=kickoff,
        )
        for _ in range(2)
    ]
    assert [run["status"] for run in runs] == ["PASS", "PASS"]
    assert runs[0]["business_hash"] == runs[1]["business_hash"]
    assert runs[0]["provider_calls"] == 0
    assert runs[0]["db_writes"] == 0
    assert runs[0]["metrics"] == {
        "CONFIRMED_SNAPSHOTS": 2,
        "CONFIRMED_STARTERS": 22,
        "UNIQUE_PROVIDER_PLAYERS": 22,
        "UNIQUE_CANONICAL_PLAYERS": 22,
        "REVIEWED_MAPPINGS": 22,
        "MISSING_OR_INVALID": 0,
        "DUPLICATE_CANONICAL": 0,
    }

    lineup = repository.lineup_gate_evidence(
        fixture_id="fixture-authority",
        as_of=kickoff,
    )
    assert lineup["uniquely_mapped_starters"] == 22
    with Session(engine) as session:
        materialized = {
            row.api_football_player_id: row.canonical_player_id
            for row in session.scalars(select(StructuredLineupPlayerModel))
        }
    assert {
        row["api_football_player_id"]: row["canonical_player_id"] for row in runs[0]["rows"]
    } == materialized


def test_identity_valid_at_capture_but_expired_at_kickoff_fails_closed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(repository, engine)
    captured_at = kickoff.replace(hour=17)
    with Session(engine) as session:
        mapping = session.scalar(
            select(PlayerIdentityMappingModel).where(
                PlayerIdentityMappingModel.api_football_player_id == "100"
            )
        )
        assert mapping is not None
        mapping.valid_to = captured_at.replace(minute=30)
        session.commit()

    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=captured_at,
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )

    join = repository.player_identity_join_evidence(
        fixture_id="fixture-authority",
        as_of=kickoff,
    )
    gate = repository.lineup_gate_evidence(
        fixture_id="fixture-authority",
        as_of=kickoff,
    )
    with Session(engine) as session:
        player = session.scalar(
            select(StructuredLineupPlayerModel).where(
                StructuredLineupPlayerModel.api_football_player_id == "100"
            )
        )
    assert player is not None
    assert player.mapping_status == "MISSING"
    assert player.canonical_player_id is None
    assert join["status"] == "INCOMPLETE"
    assert join["metrics"]["MISSING_OR_INVALID"] == 1
    assert gate["uniquely_mapped_starters"] == 21


def _fixture_identity(
    *,
    fixture_id: str,
    provider_fixture_id: str,
    identity_hash: str,
    kickoff: datetime,
    provider: str = "api_football",
    league_id: str = "39",
    season: str = "2026",
) -> MatchdayFixtureIdentityModel:
    return MatchdayFixtureIdentityModel(
        fixture_id=fixture_id,
        provider=provider,
        provider_fixture_id=provider_fixture_id,
        competition_id="premier_league",
        provider_league_id=league_id,
        season=season,
        kickoff_utc=kickoff,
        fixture_status="NS",
        home_provider_team_id="10",
        away_provider_team_id="20",
        home_w2_team_id="w2:team:10",
        away_w2_team_id="w2:team:20",
        team_identity_status="READY",
        raw_payload_sha256=identity_hash,
        endpoint_capture_id=None,
        captured_at=kickoff.replace(hour=0),
        identity_hash=identity_hash,
        payload={},
    )


def _add_lineup(
    session: Session,
    *,
    fixture_id: str,
    team_id: str,
    captured_at: datetime,
    offset: int,
) -> StructuredLineupSnapshotModel:
    snapshot = StructuredLineupSnapshotModel(
        fixture_id=fixture_id,
        team_external_id=team_id,
        team_name=f"Team {team_id}",
        formation="4-3-3",
        captured_at=captured_at,
        confirmed=True,
        authoritative_status="CONFIRMED",
        raw_sha256=f"{fixture_id}:{team_id}",
        lineup_identity_hash=f"lineup:{fixture_id}:{team_id}",
        team_w2_id=f"w2:team:{team_id}",
        source_capture_id=None,
        schema_version="w2.structured_lineup.v1",
    )
    session.add(snapshot)
    session.flush()
    for index in range(11):
        session.add(
            StructuredLineupPlayerModel(
                lineup_snapshot_id=snapshot.id,
                api_football_player_id=str(offset + index),
                player_name=f"Player {offset + index}",
                starter=True,
                shirt_number=index + 1,
                provider_position="M",
                grid=None,
                captain=False,
                identity_mapping_id=None,
                canonical_player_id=None,
                valuation_source_player_id=None,
                mapping_status="MISSING",
            )
        )
    return snapshot


def test_lineup_attribution_rejects_alias_identity_hash_conflict() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    kickoff = datetime(2026, 7, 30, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add_all(
            [
                _fixture_identity(
                    fixture_id="api_football:901",
                    provider_fixture_id="901",
                    identity_hash="a" * 64,
                    kickoff=kickoff,
                ),
                _fixture_identity(
                    fixture_id="901",
                    provider_fixture_id="901",
                    identity_hash="b" * 64,
                    kickoff=kickoff,
                    provider="secondary",
                ),
            ]
        )
        session.commit()

    evidence = FutureRefreshDbRepository(engine=engine).lineup_attribution_evidence_for_fixtures(
        ["901"]
    )["901"]

    assert evidence == {
        "status": "INCOMPLETE",
        "fixture_id": "901",
        "home": None,
        "away": None,
        "blockers": ["FIXTURE_ID_ALIAS_CONFLICT"],
    }


def test_lineup_attribution_isolates_baseline_and_rotation_scope() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    kickoff = datetime(2026, 7, 30, 12, tzinfo=UTC)
    captured_at = kickoff.replace(hour=11)
    with Session(engine) as session:
        session.add(
            _fixture_identity(
                fixture_id="api_football:900",
                provider_fixture_id="900",
                identity_hash="0" * 64,
                kickoff=kickoff,
            )
        )
        _add_lineup(
            session,
            fixture_id="900",
            team_id="10",
            captured_at=captured_at,
            offset=100,
        )
        _add_lineup(
            session,
            fixture_id="900",
            team_id="20",
            captured_at=captured_at,
            offset=200,
        )
        baseline_players = [
            {"player_id": str(100 + index), "starter_weight": 3.0} for index in range(11)
        ]
        for league_id, season, seconds, artifact_hash in (
            ("39", "2026", 300, "correct"),
            ("99", "2026", 120, "wrong-competition"),
            ("39", "2025", 60, "wrong-season"),
        ):
            session.add(
                TeamLineupBaselineModel(
                    team_external_id="10",
                    competition_external_id=league_id,
                    season=season,
                    as_of_time=captured_at - timedelta(seconds=seconds),
                    match_count=6,
                    payload={"players": baseline_players},
                    input_manifest={},
                    artifact_hash=artifact_hash,
                    schema_version="w2.lineup_baseline.v1",
                )
            )
        session.add(
            TeamLineupBaselineModel(
                team_external_id="20",
                competition_external_id="39",
                season="2026",
                as_of_time=captured_at - timedelta(minutes=5),
                match_count=6,
                payload={
                    "players": [
                        {"player_id": str(200 + index), "starter_weight": 3.0}
                        for index in range(11)
                    ]
                },
                input_manifest={},
                artifact_hash="correct-away",
                schema_version="w2.lineup_baseline.v1",
            )
        )
        for index in range(6):
            history_kickoff = kickoff - timedelta(days=12 - index)
            fixture_id = f"history-{index}"
            session.add(
                _fixture_identity(
                    fixture_id=fixture_id,
                    provider_fixture_id=f"8{index}",
                    identity_hash=f"{index + 1}" * 64,
                    kickoff=history_kickoff,
                )
            )
            _add_lineup(
                session,
                fixture_id=fixture_id,
                team_id="10",
                captured_at=history_kickoff - timedelta(hours=1),
                offset=300 + index,
            )
        for league_id, season, suffix in (
            ("99", "2026", "wrong-competition"),
            ("39", "2025", "wrong-season"),
        ):
            history_kickoff = kickoff - timedelta(hours=2)
            session.add(
                _fixture_identity(
                    fixture_id=suffix,
                    provider_fixture_id=suffix,
                    identity_hash=("d" * 64 if league_id == "99" else "e" * 64),
                    kickoff=history_kickoff,
                    league_id=league_id,
                    season=season,
                )
            )
            _add_lineup(
                session,
                fixture_id=suffix,
                team_id="10",
                captured_at=history_kickoff - timedelta(hours=1),
                offset=900,
            )
        session.commit()

    repository = FutureRefreshDbRepository(engine=engine)
    first = repository.lineup_attribution_evidence_for_fixtures(["900"])["900"]
    second = repository.lineup_attribution_evidence_for_fixtures(["900"])["900"]

    assert first["status"] == "READY"
    assert first["home"]["baseline_artifact_hash"] == "correct"
    assert first["home"]["starter_continuity"] == 1.0
    assert first["home"]["rotation_prior"]["input_fixture_ids"] == [
        f"history-{index}" for index in range(6)
    ]
    assert first["input_hash"] == second["input_hash"]

    with Session(engine) as session:
        correct = session.scalar(
            select(TeamLineupBaselineModel).where(
                TeamLineupBaselineModel.artifact_hash == "correct"
            )
        )
        assert correct is not None
        session.delete(correct)
        session.commit()
    without_correct_scope = repository.lineup_attribution_evidence_for_fixtures(["900"])["900"]

    assert without_correct_scope["home"]["baseline_artifact_hash"] is None
    assert "10:LINEUP_BASELINE_INCOMPLETE" in without_correct_scope["blockers"]
