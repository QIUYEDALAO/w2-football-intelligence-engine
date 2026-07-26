from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from w2.infrastructure.database import Base
from w2.infrastructure.persistence.factor_model_models import (
    CanonicalTeamModel,
    ProviderTeamIdentityCrosswalkModel,
)
from w2.infrastructure.persistence.future_refresh_models import RawPayloadModel
from w2.infrastructure.persistence.models import (
    PlayerIdentityMappingModel,
    StructuredLineupPlayerModel,
    StructuredLineupSnapshotModel,
    TeamLineupBaselineModel,
    TransfermarktPlayerReferenceModel,
)
from w2.ingestion.future_refresh_repository import (
    FutureRefreshDbRepository,
    FutureRefreshPersistenceError,
    approved_player_identity_manifest_rows,
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


def test_arch_p1_03b_review_manifest_recomputes_approved_package_hash() -> None:
    path = Path(
        "docs/operations/architecture_convergence/"
        "W2_ARCH_P1_03B_REVIEW_PACKAGE_MANIFEST_V1.json"
    )
    payload = path.read_bytes()
    assert (
        hashlib.sha256(payload).hexdigest()
        == "916fb7aed46d0c69cae6aff0107ad4e67e12aa55fe6be5fa32b17b7aa0d4b9ea"
    )
    rows = approved_player_identity_manifest_rows(json.loads(payload))
    assert len(rows) == 66
    assert len(
        {
            (row["api_football_player_id"], row["team_external_id"])
            for row in rows
        }
    ) == 66


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
                            "wrong-club"
                            if player_id == wrong_club_player_id
                            else f"club-{team_id}"
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


def test_m2b_materializes_only_full_name_authority_chain_candidates() -> None:
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

    with Session(engine) as session:
        mappings = list(
            session.scalars(
                select(PlayerIdentityMappingModel).order_by(
                    PlayerIdentityMappingModel.api_football_player_id
                )
            )
        )
    assert len(mappings) == 22
    assert all(mapping.mapping_status == "CANDIDATE" for mapping in mappings)
    assert all(mapping.evidence["authority_chain_complete"] for mapping in mappings)
    assert all(
        mapping.evidence["reason"] == "UNIQUE_AUTHORITY_TEAM_FULL_NAME_POSITION"
        for mapping in mappings
    )
    assert all(mapping.valid_from == kickoff.replace(tzinfo=None) for mapping in mappings)
    with Session(engine) as session:
        mapping = session.get(PlayerIdentityMappingModel, mappings[0].id)
        assert mapping is not None
        mapping.evidence = {
            **mapping.evidence,
            "prior_preview": {
                "mapping_status": "CANDIDATE",
                "evidence": {"reason": "UNTRACKED_PREVIEW"},
            },
        }
        session.commit()
    audit = repository.player_identity_candidate_audit(
        fixture_ids=["fixture-authority"],
        as_of=captured_at,
    )
    assert len(audit) == 22
    assert {
        row["generator"] for row in audit
    } == {"FutureRefreshDbRepository.materialize_player_identity_mappings"}
    assert {row["candidate_reason"] for row in audit} == {
        "UNIQUE_AUTHORITY_TEAM_FULL_NAME_POSITION"
    }


def test_m2b_rejects_missing_full_name_and_wrong_club() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(
        repository,
        engine,
        missing_squad_player_id="100",
        wrong_club_player_id="101",
    )
    captured_at = kickoff.replace(hour=17)

    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=captured_at,
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )

    matrix = repository.player_identity_fixture_matrix(
        fixture_ids=["fixture-authority"],
        as_of=captured_at,
    )
    assert matrix == [
        {
            "fixture_id": "fixture-authority",
            "starters": 22,
            "unique_candidates": 20,
            "missing": 2,
            "conflicts": 0,
            "missing_player_ids": ["100", "101"],
        }
    ]


def test_human_review_package_can_resolve_an_explicit_missing_mapping() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(
        repository,
        engine,
        missing_squad_player_id="100",
    )
    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=kickoff.replace(hour=17),
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )
    review = {
        "review_package_sha256": "p" * 64,
        "api_football_player_id": "100",
        "team_external_id": "10",
        "transfermarkt_player_id": "tm-100",
        "fixture_id": "fixture-authority",
        "issues": ["PROVIDER_FULL_NAME_NULL"],
    }
    with pytest.raises(FutureRefreshPersistenceError):
        repository.approve_player_identity_mapping(
            api_football_player_id="100",
            team_external_id="10",
            canonical_player_id="w2:player:transfermarkt:tm-100",
            transfermarkt_player_id="tm-100",
            reviewed_by="operator:reviewer",
            reviewed_at=kickoff,
            source_artifact_hash="x" * 64,
            review_exception=review,
        )

    identity_hash = repository.approve_player_identity_mapping(
        api_football_player_id="100",
        team_external_id="10",
        canonical_player_id="w2:player:transfermarkt:tm-100",
        transfermarkt_player_id="tm-100",
        reviewed_by="operator:reviewer",
        reviewed_at=kickoff,
        source_artifact_hash="p" * 64,
        approval_artifact_hash="a" * 64,
        review_exception=review,
    )

    with Session(engine) as session:
        mapping = session.scalar(
            select(PlayerIdentityMappingModel).where(
                PlayerIdentityMappingModel.api_football_player_id == "100"
            )
        )
    assert mapping is not None
    assert mapping.mapping_status == "REVIEWED"
    assert mapping.identity_hash == identity_hash
    assert mapping.evidence["review_exception"] == review
    assert mapping.evidence["approval_artifact_sha256"] == "a" * 64


def test_m2b_uses_explicit_player_profile_name_when_squad_name_is_abbreviated() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FutureRefreshDbRepository(engine=engine)
    kickoff = _install_player_identity_sources(
        repository,
        engine,
        missing_squad_player_id="100",
    )
    with Session(engine) as session:
        reference = session.scalar(
            select(TransfermarktPlayerReferenceModel).where(
                TransfermarktPlayerReferenceModel.transfermarkt_player_id == "tm-100"
            )
        )
        assert reference is not None
        reference.player_name = "Player 100"
        reference.normalized_name = "player100"
        session.commit()
    captured_at = kickoff.replace(hour=17)
    repository.save_lineup_snapshots(
        fixture_id="fixture-authority",
        captured_at=captured_at,
        raw_sha256="l" * 64,
        payload={"response": [_team(10, 100), _team(20, 200)]},
        materialize_baselines=False,
    )
    profile_at = captured_at.replace(minute=5)
    repository.save_raw_payload(
        sha256="p" * 64,
        endpoint="players",
        captured_at=profile_at,
        payload={
            "parameters": {"id": "100", "season": "2026"},
            "response": [
                {
                    "player": {
                        "id": 100,
                        "name": "P. 100",
                        "firstname": "Karl Player",
                        "lastname": "100",
                    },
                    "statistics": [{"team": {"id": 10, "name": "Team 10"}}],
                }
            ],
        },
    )

    repository.materialize_player_identity_mappings(
        fixture_id="fixture-authority",
        as_of=profile_at,
    )

    matrix = repository.player_identity_fixture_matrix(
        fixture_ids=["fixture-authority"],
        as_of=profile_at,
    )
    assert matrix[0]["unique_candidates"] == 22
    with Session(engine) as session:
        mapping = session.scalar(
            select(PlayerIdentityMappingModel).where(
                PlayerIdentityMappingModel.api_football_player_id == "100"
            )
        )
    assert mapping is not None
    assert mapping.evidence["provider_full_name"] == "Karl Player 100"
    assert mapping.evidence["provider_full_name_endpoint"] == "players"
    assert mapping.evidence["name_match_mode"] == "PROVIDER_FULL_NAME_SUBSEQUENCE"


def test_player_profile_name_can_use_separate_current_squad_team_evidence() -> None:
    captured_at = datetime(2026, 7, 19, tzinfo=UTC)
    evidence = FutureRefreshDbRepository._provider_player_evidence(
        [
            RawPayloadModel(
                sha256="s" * 64,
                endpoint="squads",
                captured_at=captured_at,
                storage_uri="db://raw_payload/squad",
                payload={
                    "parameters": {"team": "10"},
                    "response": [
                        {
                            "team": {"id": 10},
                            "players": [{"id": 100, "name": "P. One"}],
                        }
                    ],
                },
            ),
            RawPayloadModel(
                sha256="p" * 64,
                endpoint="player_profiles",
                captured_at=captured_at,
                storage_uri="db://raw_payload/profile",
                payload={
                    "response": [
                        {
                            "player": {
                                "id": 100,
                                "firstname": "Player",
                                "lastname": "One",
                            },
                        }
                    ]
                },
            ),
        ],
        team_external_id="10",
        api_football_player_id="100",
    )

    assert evidence["full_name"] == "Player One"
    assert evidence["endpoint"] == "player_profiles"


def test_player_identity_join_evidence_is_read_only_and_deterministic() -> None:
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
    approved_rows = []
    for team_id, offset in (("10", 100), ("20", 200)):
        for index in range(11):
            player_id = str(offset + index)
            with Session(engine) as session:
                mapping = session.scalar(
                    select(PlayerIdentityMappingModel).where(
                        PlayerIdentityMappingModel.api_football_player_id == player_id,
                        PlayerIdentityMappingModel.team_external_id == team_id,
                    )
                )
            assert mapping is not None
            approved_rows.append(
                {
                    "api_football_player_id": player_id,
                    "team_external_id": team_id,
                    "fixture_id": "fixture-authority",
                    "canonical_player_id": f"w2:player:transfermarkt:tm-{player_id}",
                    "transfermarkt_player_id": f"tm-{player_id}",
                    "canonical_team_id": mapping.evidence["canonical_team_id"],
                    "transfermarkt_club_id": mapping.evidence[
                        "transfermarkt_club_id"
                    ],
                    "source_hashes": mapping.evidence["source_artifact_hashes"],
                }
            )
            repository.approve_player_identity_mapping(
                api_football_player_id=player_id,
                team_external_id=team_id,
                canonical_player_id=f"w2:player:transfermarkt:tm-{player_id}",
                transfermarkt_player_id=f"tm-{player_id}",
                reviewed_by="real-technical-reviewer",
                reviewed_at=captured_at,
                source_artifact_hash="r" * 64,
                approval_artifact_hash="a" * 64,
            )

    reconciliation_runs = [
        repository.player_identity_review_reconciliation(
            approved_rows=approved_rows,
            review_package_sha256="r" * 64,
            approval_artifact_sha256="a" * 64,
            reviewed_by="real-technical-reviewer",
        )
        for _ in range(2)
    ]
    assert reconciliation_runs[0] == reconciliation_runs[1]
    assert reconciliation_runs[0]["status"] == "PASS"
    assert reconciliation_runs[0]["expected_rows"] == 22
    assert reconciliation_runs[0]["actual_reviewed_rows"] == 22
    assert reconciliation_runs[0]["exact_rows"] == 22

    runs = [
        repository.player_identity_join_evidence(
            fixture_id="fixture-authority",
            as_of=kickoff,
            approved_rows=approved_rows,
            review_package_sha256="r" * 64,
            approval_artifact_sha256="a" * 64,
            reviewed_by="real-technical-reviewer",
        )
        for _ in range(3)
    ]

    assert [run["status"] for run in runs] == ["PASS", "PASS", "PASS"]
    assert len({run["business_hash"] for run in runs}) == 1
    assert runs[0]["rows"] == runs[1]["rows"] == runs[2]["rows"]
    assert runs[0]["provider_calls"] == 0
    assert runs[0]["db_writes"] == 0
    assert runs[0]["metrics"] == {
        "CONFIRMED_SNAPSHOTS": 2,
        "CONFIRMED_STARTERS": 22,
        "UNIQUE_PROVIDER_PLAYERS": 22,
        "UNIQUE_CANONICAL_PLAYERS": 22,
        "REVIEWED_MAPPINGS": 22,
        "REVIEW_PROVENANCE_VALID": 22,
        "PACKAGE_HASH_VALID": 22,
        "APPROVAL_HASH_VALID": 22,
        "SOURCE_HASHES_VALID": 22,
        "TEAM_CONSISTENT": 22,
        "VALID_AT_KICKOFF": 22,
        "MISSING": 0,
        "AMBIGUOUS": 0,
        "CONFLICT": 0,
        "DUPLICATE_CANONICAL": 0,
        "INVALID_AT_KICKOFF": 0,
    }
