from __future__ import annotations

import csv
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from w2.competitions.registry import CoverageProfile
from w2.data_assets.registry import build_football_data_registry
from w2.features.framework import FeatureContext
from w2.features.team_factors import TeamMatchHistory, recent_ah_cover_factor
from w2.historical.fah_repository import FahDataFoundationRepository
from w2.historical.formal_ah import (
    audit_formal_ah_sources,
    build_canonical_ah_facts,
    decimal_line,
)
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.models import (
    CanonicalHistoricalAhFactModel,
    PlayerIdentityCrosswalkModel,
    RegisteredRosterSnapshotModel,
    TeamIdentityCrosswalkModel,
    TeamValueAsOfArtifactModel,
)
from w2.lineups.value_identity import (
    PlayerIdentityCrosswalkV1,
    TeamIdentityCrosswalkV1,
    approved_crosswalk_for_team,
    build_player_crosswalk,
    build_team_crosswalk,
    materialize_team_value_asof,
)

AS_OF = datetime(2026, 7, 20, tzinfo=UTC)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _registry(path: Path, *, local_path: str, **overrides: object) -> Path:
    payload = {
        "schema_version": "w2.formal_ah_source_registry.v1",
        "sources": [
            {
                "source_id": "src-1",
                "provider": "local-approved",
                "local_path": local_path,
                "schema_version": "test.v1",
                "license_status": "APPROVED",
                "retention_permitted": True,
                "internal_backtest_permitted": True,
                "snapshot_semantics": "CAPTURED_AT",
                "canonical_bookmaker_policy": {"type": "SINGLE_BOOK_SOURCE"},
                **overrides,
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _ah_rows() -> list[dict[str, object]]:
    base = {
        "provider_fixture_id": "fx-1",
        "competition_id": "allsvenskan",
        "season": "2024",
        "kickoff_utc": "2024-05-01T19:00:00Z",
        "home_team_provider_id": "home-1",
        "away_team_provider_id": "away-1",
        "provider": "local-approved",
        "bookmaker_id": "book-1",
        "bookmaker_name": "Book 1",
        "captured_at": "2024-05-01T18:20:00Z",
        "market": "ASIAN_HANDICAP",
        "decimal_odds": "1.91",
        "live": "false",
        "suspended": "false",
        "result_status": "FT",
        "final_home_goals_90": "2",
        "final_away_goals_90": "1",
        "result_source_sha256": "r" * 64,
    }
    return [
        {**base, "observation_id": "home-obs", "side": "HOME", "line": "-0.25"},
        {**base, "observation_id": "away-obs", "side": "AWAY", "line": "0.25"},
    ]


def test_source_license_and_captured_at_gate(tmp_path: Path) -> None:
    _write_csv(tmp_path / "approved.csv", _ah_rows())
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    report = audit_formal_ah_sources(source_root=tmp_path, registry_path=registry)

    assert report["approved_source_count"] == 1
    assert report["sources"][0]["source_status"] == "APPROVED_CAPTURED_AT"


def test_missing_registry_metadata_does_not_approve_file(tmp_path: Path) -> None:
    _write_csv(tmp_path / "approved.csv", _ah_rows())

    report = audit_formal_ah_sources(source_root=tmp_path, registry_path=None)

    assert report["status"] == "SOURCE_NOT_AVAILABLE"
    assert report["approved_source_count"] == 0


def test_registry_rejects_duplicate_source_id(tmp_path: Path) -> None:
    registry = {
        "sources": [
            {"source_id": "dup", "provider": "p"},
            {"source_id": "dup", "provider": "p"},
        ]
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry), encoding="utf-8")

    try:
        audit_formal_ah_sources(source_root=tmp_path, registry_path=path)
    except ValueError as exc:
        assert "DUPLICATE_SOURCE_ID:dup" in str(exc)
    else:
        raise AssertionError("duplicate source_id must fail closed")


def test_source_path_must_stay_under_source_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.csv"
    _write_csv(outside, _ah_rows())
    registry = _registry(tmp_path / "registry.json", local_path="../outside.csv")

    report = audit_formal_ah_sources(source_root=tmp_path, registry_path=registry)

    assert report["approved_source_count"] == 0
    assert "BLOCKED_SOURCE_OUTSIDE_ROOT" in report["blocked_reasons"]


def test_csv_gz_source_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "approved.csv.gz"
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_ah_rows()[0]))
        writer.writeheader()
        writer.writerows(_ah_rows())
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv.gz")

    report = audit_formal_ah_sources(source_root=tmp_path, registry_path=registry)

    assert report["approved_source_count"] == 1


def test_closing_only_and_aggregate_sources_are_excluded(tmp_path: Path) -> None:
    _write_csv(tmp_path / "closing.csv", [{**row, "captured_at": ""} for row in _ah_rows()])
    registry = _registry(
        tmp_path / "registry.json",
        local_path="closing.csv",
        snapshot_semantics="CLOSING",
    )

    report = audit_formal_ah_sources(source_root=tmp_path, registry_path=registry)

    assert report["approved_source_count"] == 0
    assert "DIAGNOSTIC_CLOSING_ONLY" in report["blocked_reasons"]


def test_canonical_fact_uses_latest_t30_pair_and_is_deterministic(tmp_path: Path) -> None:
    _write_csv(tmp_path / "approved.csv", _ah_rows())
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    first = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)
    second = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert first["audit"]["canonical_fact_count"] == 1
    assert first["facts"][0]["fact_hash"] == second["facts"][0]["fact_hash"]
    assert first["facts"][0]["canonical_key"]
    assert first["facts"][0]["fact_id"] == f"canonical-ah:{first['facts'][0]['canonical_key']}"
    assert first["facts"][0]["home_settlement"] == "WIN"
    assert first["facts"][0]["away_settlement"] == "LOSS"


def test_canonical_fact_applies_ordered_bookmaker_policy(tmp_path: Path) -> None:
    rows = _ah_rows()
    second_book = [
        {
            **row,
            "bookmaker_id": "book-2",
            "bookmaker_name": "Book 2",
            "observation_id": f"{row['side']}-obs-book-2",
            "captured_at": "2024-05-01T18:10:00Z",
        }
        for row in rows
    ]
    _write_csv(tmp_path / "approved.csv", rows + second_book)
    registry = _registry(
        tmp_path / "registry.json",
        local_path="approved.csv",
        canonical_bookmaker_policy={
            "type": "ORDERED_BOOKMAKER_PRIORITY",
            "bookmaker_ids": ["book-2", "book-1"],
        },
    )

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 1
    assert result["facts"][0]["bookmaker_id"] == "book-2"


def test_preflight_accepts_independent_result_row(tmp_path: Path) -> None:
    quote_rows = [
        {
            key: value
            for key, value in row.items()
            if key
            not in {
                "result_status",
                "final_home_goals_90",
                "final_away_goals_90",
                "result_source_sha256",
            }
        }
        for row in _ah_rows()
    ]
    result_row = {
        "provider_fixture_id": "fx-1",
        "result_status": "FT",
        "final_home_goals_90": "2",
        "final_away_goals_90": "1",
        "result_source_sha256": "r" * 64,
        "result_reference_id": "result-1",
    }
    _write_csv(tmp_path / "approved.csv", quote_rows + [result_row])
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 1


def test_provider_mismatch_rejects_source(tmp_path: Path) -> None:
    rows = [{**row, "provider": "other-provider"} for row in _ah_rows()]
    _write_csv(tmp_path / "approved.csv", rows)
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 0
    assert result["audit"]["exclusions"]["REGISTRY_PROVIDER_MISMATCH"] == 1


def test_missing_canonical_identity_rejects_fact(tmp_path: Path) -> None:
    rows = [{**row, "home_team_provider_id": ""} for row in _ah_rows()]
    _write_csv(tmp_path / "approved.csv", rows)
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 0
    assert result["audit"]["exclusions"]["MISSING_REQUIRED_CANONICAL_IDENTITY"] == 1


def test_fact_hash_changes_when_odds_change(tmp_path: Path) -> None:
    rows = _ah_rows()
    _write_csv(tmp_path / "first.csv", rows)
    _write_csv(
        tmp_path / "second.csv",
        [{**row, "decimal_odds": "1.92"} if row["side"] == "HOME" else row for row in rows],
    )
    first = build_canonical_ah_facts(
        source_root=tmp_path,
        registry_path=_registry(tmp_path / "first-registry.json", local_path="first.csv"),
    )
    second = build_canonical_ah_facts(
        source_root=tmp_path,
        registry_path=_registry(tmp_path / "second-registry.json", local_path="second.csv"),
    )

    assert first["facts"][0]["fact_hash"] != second["facts"][0]["fact_hash"]


def test_result_identity_conflict_is_isolated(tmp_path: Path) -> None:
    rows = _ah_rows() + [{**_ah_rows()[0], "market": "RESULT", "final_home_goals_90": "3"}]
    _write_csv(tmp_path / "approved.csv", rows)
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 0
    assert result["audit"]["result_conflicts"] == 1


def test_post_kickoff_quote_rejected(tmp_path: Path) -> None:
    rows = [{**row, "captured_at": "2024-05-01T18:45:01Z"} for row in _ah_rows()]
    _write_csv(tmp_path / "approved.csv", rows)
    registry = _registry(tmp_path / "registry.json", local_path="approved.csv")

    result = build_canonical_ah_facts(source_root=tmp_path, registry_path=registry)

    assert result["audit"]["canonical_fact_count"] == 0
    assert result["audit"]["post_kickoff_quote_exclusions"] == 1


def test_quarter_line_validation() -> None:
    assert decimal_line("-0.75") is not None
    assert decimal_line("0.3") is None


def test_f5_uses_canonical_facts_and_excludes_push_denominator() -> None:
    context = FeatureContext(
        fixture_id="future",
        competition_id="allsvenskan",
        home_team_id="home",
        away_team_id="away",
        kickoff_at=datetime(2026, 7, 21, tzinfo=UTC),
        as_of=AS_OF,
    )
    profile = CoverageProfile(
        xg="API_FOOTBALL_STATISTICS",
        lineups_injuries="API_FOOTBALL_LINEUPS",
        squad_value="TRANSFERMARKT_REVIEWED_STATIC_MAPPING",
        bookmaker_depth="API_FOOTBALL_ODDS",
        h2h="API_FOOTBALL_FIXTURES",
        settled_ah="INTERNAL_SETTLEMENT",
    )
    home = [
        _history("h1", "WIN"),
        _history("h2", "PUSH"),
        _history("future", "WIN", kickoff=datetime(2026, 7, 21, tzinfo=UTC)),
        _history("proxy", "WIN", proxy_of="xg"),
    ]
    away = [_history("a1", "LOSS")]

    factor = recent_ah_cover_factor(
        context=context,
        profile=profile,
        home_history=home,
        away_history=away,
    )

    assert factor.status.value == "READY"
    assert factor.inputs["home_decisive_count"] == 1
    assert factor.inputs["home_push_count"] == 1
    assert factor.inputs["away_decisive_count"] == 1


def test_f5_rejects_conflicting_fact_id_hash_identity() -> None:
    context = FeatureContext(
        fixture_id="future",
        competition_id="allsvenskan",
        home_team_id="home",
        away_team_id="away",
        kickoff_at=datetime(2026, 7, 21, tzinfo=UTC),
        as_of=AS_OF,
    )
    profile = CoverageProfile(
        xg="API_FOOTBALL_STATISTICS",
        lineups_injuries="API_FOOTBALL_LINEUPS",
        squad_value="TRANSFERMARKT_REVIEWED_STATIC_MAPPING",
        bookmaker_depth="API_FOOTBALL_ODDS",
        h2h="API_FOOTBALL_FIXTURES",
        settled_ah="INTERNAL_SETTLEMENT",
    )
    first = _history("same-fact", "WIN")
    conflicting = TeamMatchHistory(
        **{
            **first.__dict__,
            "ah_fact_hash": "different-hash",
        }
    )

    factor = recent_ah_cover_factor(
        context=context,
        profile=profile,
        home_history=[first, conflicting],
        away_history=[_history("a1", "LOSS")],
    )

    assert factor.status.value == "INSUFFICIENT_DATA"


def test_f5_rejects_raw_payload_provenance_spoof() -> None:
    context = FeatureContext(
        fixture_id="future",
        competition_id="allsvenskan",
        home_team_id="home",
        away_team_id="away",
        kickoff_at=datetime(2026, 7, 21, tzinfo=UTC),
        as_of=AS_OF,
    )
    profile = CoverageProfile(
        xg="API_FOOTBALL_STATISTICS",
        lineups_injuries="API_FOOTBALL_LINEUPS",
        squad_value="TRANSFERMARKT_REVIEWED_STATIC_MAPPING",
        bookmaker_depth="API_FOOTBALL_ODDS",
        h2h="API_FOOTBALL_FIXTURES",
        settled_ah="INTERNAL_SETTLEMENT",
    )
    spoof = TeamMatchHistory(
        **{
            **_history("spoof", "WIN").__dict__,
            "source_group": "raw_provider_fixture",
        }
    )

    factor = recent_ah_cover_factor(
        context=context,
        profile=profile,
        home_history=[spoof],
        away_history=[_history("a1", "LOSS")],
    )

    assert factor.status.value == "INSUFFICIENT_DATA"
    assert factor.reason == "MISSING_AH_EVIDENCE"


def test_missing_crosswalk_and_conflicting_crosswalk() -> None:
    approved = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "tm-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
            "evidence": {"source": "manual-review"},
            "source_refs": ["manual-review"],
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        }
    )
    found, status = approved_crosswalk_for_team(
        [approved],
        api_football_team_id="2",
        competition_id="allsvenskan",
        as_of=AS_OF,
    )
    assert found is None
    assert status == "MISSING"
    conflict, status = approved_crosswalk_for_team(
        [approved, approved],
        api_football_team_id="1",
        competition_id="allsvenskan",
        as_of=AS_OF,
    )
    assert conflict is None
    assert status == "CONFLICT"


def test_player_crosswalk_requires_reviewed_evidence_and_approved_team_crosswalk() -> None:
    pending = build_player_crosswalk(
        {
            "api_football_player_id": "p-api",
            "api_football_team_id": "1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "b" * 64,
            "evidence": {"name_match": "exact", "position_match": "forward"},
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        },
        team_crosswalks=[],
    )

    team = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "club-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
            "evidence": {"source": "manual-review"},
            "source_refs": ["manual-review"],
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        }
    )
    approved = build_player_crosswalk(
        {
            "api_football_player_id": "p-api",
            "transfermarkt_player_id": "tm-p",
            "api_football_team_id": "1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "b" * 64,
            "evidence": {"source": "manual-review"},
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        },
        team_crosswalks=[team],
    )

    assert pending.review_status == "REVIEW_REQUIRED"
    assert approved.review_status == "APPROVED"
    assert approved.transfermarkt_club_id == "club-1"


def _approved_player_crosswalk() -> tuple[TeamIdentityCrosswalkV1, PlayerIdentityCrosswalkV1]:
    team = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "club-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
            "evidence": {"source": "manual-review"},
            "source_refs": ["manual-review"],
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        }
    )
    player = build_player_crosswalk(
        {
            "api_football_player_id": "api-p1",
            "transfermarkt_player_id": "p1",
            "api_football_team_id": "1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "b" * 64,
            "evidence": {"source": "manual-review"},
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        },
        team_crosswalks=[team],
    )
    return team, player


def test_team_value_asof_uses_source_valuation_date_and_rejects_future(tmp_path: Path) -> None:
    crosswalk, player_crosswalk = _approved_player_crosswalk()
    _write_csv(
        tmp_path / "registered_roster_snapshots.csv",
        [
            {
                "transfermarkt_player_id": "p1",
                "club_id": "club-1",
                "roster_snapshot_id": "club-1-2024-05-01",
                "snapshot_date": "2024-05-01T00:00:00Z",
                "observed_at": "2024-05-01T00:00:00Z",
                "identity_hash": "p1hash",
            }
        ],
    )
    _write_csv(
        tmp_path / "player_valuations.csv",
        [
            {
                "transfermarkt_player_id": "p1",
                "observed_at": "2024-04-01T00:00:00Z",
                "market_value_eur": "100",
            },
            {
                "transfermarkt_player_id": "p1",
                "observed_at": "2024-06-01T00:00:00Z",
                "market_value_eur": "999",
            },
        ],
    )

    artifact = materialize_team_value_asof(
        fixture={
            "team_external_id": "1",
            "competition_id": "allsvenskan",
            "as_of": "2024-05-02T00:00:00Z",
        },
        crosswalks=[crosswalk],
        player_crosswalks=[player_crosswalk],
        source_root=tmp_path,
    )
    rebuilt = materialize_team_value_asof(
        fixture={
            "team_external_id": "1",
            "competition_id": "allsvenskan",
            "as_of": "2024-05-02T00:00:00Z",
        },
        crosswalks=[crosswalk],
        player_crosswalks=[player_crosswalk],
        source_root=tmp_path,
    )

    assert artifact["status"] == "READY"
    assert artifact["squad_value_eur"] == "100"
    assert artifact["roster_source_hash"]
    assert artifact["membership_source_hashes"] == [artifact["roster_source_hash"]]
    assert artifact["future_valuation_exclusions"] == 1
    assert artifact["artifact_hash"] == rebuilt["artifact_hash"]


def test_team_value_asof_rejects_same_day_valuation_conflict(tmp_path: Path) -> None:
    crosswalk, player_crosswalk = _approved_player_crosswalk()
    _write_csv(
        tmp_path / "registered_roster_snapshots.csv",
        [
            {
                "transfermarkt_player_id": "p1",
                "club_id": "club-1",
                "roster_snapshot_id": "club-1-2024-05-01",
                "snapshot_date": "2024-05-01T00:00:00Z",
                "observed_at": "2024-05-01T00:00:00Z",
            }
        ],
    )
    _write_csv(
        tmp_path / "player_valuations.csv",
        [
            {
                "transfermarkt_player_id": "p1",
                "observed_at": "2024-04-01T00:00:00Z",
                "market_value_eur": "100",
            },
            {
                "transfermarkt_player_id": "p1",
                "observed_at": "2024-04-01T12:00:00Z",
                "market_value_eur": "101",
            },
        ],
    )

    artifact = materialize_team_value_asof(
        fixture={
            "team_external_id": "1",
            "competition_id": "allsvenskan",
            "as_of": "2024-05-02T00:00:00Z",
        },
        crosswalks=[crosswalk],
        player_crosswalks=[player_crosswalk],
        source_root=tmp_path,
    )

    assert artifact["status"] == "INCOMPLETE"
    assert artifact["squad_value_eur"] is None
    assert "VALUATION_CONFLICT" in artifact["blockers"]


def test_fah_repository_writes_idempotently_and_rolls_back_conflicts() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    row = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "club-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
            "evidence": {"source": "manual-review"},
            "source_refs": ["manual-review"],
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        }
    ).as_dict()

    first = repository.write_team_crosswalks([row])
    second = repository.write_team_crosswalks([row])
    conflict = repository.write_team_crosswalks([{**row, "transfermarkt_club_id": "club-2"}])

    with Session(engine) as session:
        count = len(session.scalars(select(TeamIdentityCrosswalkModel)).all())

    assert first.inserted == 1
    assert second.skipped_identical == 1
    assert conflict.rolled_back is True
    assert count == 1


def test_fah_repository_can_query_team_value_by_team_and_asof() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    artifact = {
        "team_external_id": "1",
        "transfermarkt_club_id": "club-1",
        "competition_id": "allsvenskan",
        "as_of": "2024-05-02T00:00:00Z",
        "status": "READY",
        "artifact_hash": "c" * 64,
    }

    summary = repository.write_team_value_artifacts([artifact])

    with Session(engine) as session:
        found = session.scalars(
            select(TeamValueAsOfArtifactModel).where(
                TeamValueAsOfArtifactModel.team_external_id == "1"
            )
        ).one()

    assert summary.inserted == 1
    assert found.artifact_hash == "c" * 64


def test_fah_repository_import_and_query_authorities() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    source_root = _source_root_for_repo_test()
    fact = build_canonical_ah_facts(
        source_root=source_root,
        registry_path=source_root / "registry.json",
    )["facts"][0]
    team, player = _approved_player_crosswalk()
    roster = {
        "roster_snapshot_id": "club-1-2024-05-01",
        "transfermarkt_club_id": "club-1",
        "transfermarkt_player_id": "p1",
        "snapshot_date": "2024-05-01T00:00:00Z",
        "source_sha256": "c" * 64,
        "snapshot_status": "COMPLETE",
    }

    source_summary = repository.import_source_snapshots(
        [
            {
                "source_id": "src-1",
                "provider": "local-approved",
                "schema_version": "test.v1",
                "snapshot_semantics": "CAPTURED_AT",
                "canonical_bookmaker_policy": {"type": "SINGLE_BOOK_SOURCE"},
                "object_uri": "approved.csv",
                "sha256": fact["source_sha256"],
                "license_status": "APPROVED",
                "row_count": 2,
            }
        ]
    )
    assert source_summary.inserted == 1
    assert repository.import_canonical_ah_facts([fact]).inserted == 1
    assert repository.import_team_crosswalks([team.as_dict()]).inserted == 1
    assert repository.import_player_crosswalks([player.as_dict()]).inserted == 1
    assert repository.import_registered_roster_snapshots([roster]).inserted == 1

    facts = repository.historical_ah_facts_for_teams(
        team_ids=["home-1"],
        competition_id="allsvenskan",
        as_of=datetime(2024, 6, 1, tzinfo=UTC),
    )
    assert facts[0]["canonical_key"] == fact["canonical_key"]
    assert (
        repository.team_crosswalk_at(
            api_football_team_id="1",
            competition_id="allsvenskan",
            as_of=AS_OF,
        )["crosswalk_hash"]
        == team.crosswalk_hash
    )
    assert (
        len(
            repository.player_crosswalks_for_roster(
                api_football_team_id="1",
                competition_id="allsvenskan",
                as_of=AS_OF,
            )
        )
        == 1
    )
    assert len(repository.registered_roster_at(transfermarkt_club_id="club-1", as_of=AS_OF)) == 1

    with Session(engine) as session:
        assert len(session.scalars(select(CanonicalHistoricalAhFactModel)).all()) == 1
        assert len(session.scalars(select(PlayerIdentityCrosswalkModel)).all()) == 1
        assert len(session.scalars(select(RegisteredRosterSnapshotModel)).all()) == 1


def test_f5_runtime_query_requires_approved_mapping_and_returns_canonical_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    source_root = _source_root_for_repo_test()
    fact = build_canonical_ah_facts(
        source_root=source_root,
        registry_path=source_root / "registry.json",
    )["facts"][0]
    team, _player = _approved_player_crosswalk()
    repository.import_source_snapshots(
        [
            {
                "source_id": "src-1",
                "provider": "local-approved",
                "schema_version": "test.v1",
                "snapshot_semantics": "CAPTURED_AT",
                "canonical_bookmaker_policy": {"type": "SINGLE_BOOK_SOURCE"},
                "object_uri": "approved.csv",
                "sha256": fact["source_sha256"],
                "license_status": "APPROVED",
                "row_count": 2,
            }
        ]
    )
    repository.import_canonical_ah_facts([fact])
    assert (
        repository.canonical_f5_team_history(
            team_ids=["home-1"],
            competition_id="allsvenskan",
            before=datetime(2024, 6, 1, tzinfo=UTC),
        )["status"]
        == "W2_RUNTIME_F5_NOT_READY"
    )

    repository.import_team_crosswalks([{**team.as_dict(), "api_football_team_id": "home-1"}])
    partial = repository.canonical_f5_team_history(
        team_ids=["home-1"],
        competition_id="allsvenskan",
        before=datetime(2024, 6, 1, tzinfo=UTC),
    )
    assert partial["status"] == "W2_RUNTIME_F5_NOT_READY"

    repository.import_football_data_team_crosswalks(
        [
            {
                "schema_version": "FootballDataTeamCrosswalkV1",
                "football_data_source_identity": "home-1",
                "football_data_team_name": "Home",
                "league": "allsvenskan",
                "competition_id": "allsvenskan",
                "season_coverage": ["2024"],
                "w2_team_id": "club-1",
                "api_football_team_ids": ["home-1"],
                "valid_from": "2024-01-01T00:00:00Z",
                "valid_to": None,
                "evidence": {"basis": "unit"},
                "source_hashes": [fact["source_sha256"]],
                "candidate_generation_method": "manual_unit",
                "review_status": "APPROVED",
                "reviewed_by": "unit",
                "reviewed_at": "2024-01-02T00:00:00Z",
            }
        ]
    )
    result = repository.canonical_f5_team_history(
        team_ids=["home-1"],
        competition_id="allsvenskan",
        before=datetime(2024, 6, 1, tzinfo=UTC),
    )

    assert result["status"] == "W2_RUNTIME_F5_READY"
    assert result["rows"][0]["canonical_key"] == fact["canonical_key"]


def test_f8_authority_keeps_static_or_unreviewed_values_out_of_formal() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    repository.write_team_value_artifacts(
        [
            {
                "team_external_id": "1",
                "transfermarkt_club_id": "club-1",
                "competition_id": "allsvenskan",
                "as_of": "2024-05-02T00:00:00Z",
                "status": "READY",
                "review_status": "REVIEW_REQUIRED",
                "artifact_hash": "d" * 64,
            }
        ]
    )

    result = repository.f8_authority_at(
        team_external_id="1",
        competition_id="allsvenskan",
        as_of=datetime(2024, 6, 1, tzinfo=UTC),
    )

    assert result["authority"] == "TeamValueAsOfArtifactModel"
    assert result["status"] == "INCOMPLETE"
    assert result["formal_eligible"] is False
    assert "TEAM_CROSSWALK_REVIEW_REQUIRED" in result["blockers"]


def test_f8_authority_ready_requires_complete_reviewed_artifact() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = FahDataFoundationRepository(engine)
    repository.write_team_value_artifacts(
        [
            {
                "team_external_id": "1",
                "transfermarkt_club_id": "club-1",
                "competition_id": "allsvenskan",
                "as_of": "2024-05-02T00:00:00Z",
                "status": "READY",
                "review_status": "APPROVED",
                "artifact_hash": "e" * 64,
                "hash_verified": True,
                "conflict_count": 0,
                "missing_mapping_count": 0,
                "missing_valuation_count": 0,
                "player_count": 2,
                "uniquely_mapped_count": 2,
                "valued_count": 2,
                "roster_snapshot_status": "COMPLETE",
                "valuation_observed_at": "2024-05-01T00:00:00Z",
                "blockers": [],
            }
        ]
    )

    result = repository.f8_authority_at(
        team_external_id="1",
        competition_id="allsvenskan",
        as_of=datetime(2024, 6, 1, tzinfo=UTC),
    )

    assert result["status"] == "READY"
    assert result["formal_eligible"] is False
    assert result["blockers"] == ["FORMAL_CAPABILITY_DISABLED"]


def test_data_asset_registry_uses_aliases_and_backup_missing_is_external_blocker(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "football-data"
    _write_csv(data_root / "sample.csv", [{"A": 1, "B": 2}])

    registry = build_football_data_registry(
        data_root=data_root, now=datetime(2026, 7, 20, tzinfo=UTC)
    )
    payload = registry.as_dict()
    text = json.dumps(payload, sort_keys=True)

    assert payload["private_storage_location_alias"] == "$W2_FOOTBALL_DATA_ROOT"
    assert str(data_root) not in text
    assert "BACKUP_LOCATION_REQUIRED" in payload["blockers"]


def test_data_asset_registry_hashes_all_allowed_file_types_and_restores_manifest(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "football-data"
    backup_root = tmp_path / "W2_BACKUP"
    backup_root.mkdir()
    for suffix in (".zip", ".gz", ".csv", ".json", ".jsonl", ".txt", ".html", ".xlsx", ".xls"):
        path = data_root / f"sample{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"payload-{suffix}".encode())
    (data_root / "ignored.bin").write_bytes(b"not part of manifest")

    registry = build_football_data_registry(
        data_root=data_root,
        backup_root=backup_root,
        now=datetime(2026, 7, 20, tzinfo=UTC),
    )
    payload = registry.as_dict()

    assert sorted(payload["source_file_hashes"]) == [
        "sample.csv",
        "sample.gz",
        "sample.html",
        "sample.json",
        "sample.jsonl",
        "sample.txt",
        "sample.xls",
        "sample.xlsx",
        "sample.zip",
    ]
    assert payload["restore_test_status"] == "RESTORE_DRILL_PASS"
    assert payload["backup_location"].startswith("$W2_DESKTOP_BACKUP_ROOT/football-data-co-uk/")
    assert payload["backup_classification"] == "OWNER_APPROVED_SAME_DEVICE_DESKTOP_BACKUP"
    assert payload["durability_status"] == "NOT_DURABLE_AGAINST_DEVICE_FAILURE"


def _source_root_for_repo_test() -> Path:
    import tempfile

    root = Path(tempfile.mkdtemp())
    _write_csv(root / "approved.csv", _ah_rows())
    _registry(root / "registry.json", local_path="approved.csv")
    return root


def _history(
    fact_id: str,
    settlement: str,
    *,
    kickoff: datetime = datetime(2024, 5, 1, tzinfo=UTC),
    proxy_of: str | None = None,
) -> TeamMatchHistory:
    return TeamMatchHistory(
        team_id="team",
        opponent_id="opp",
        kickoff_at=kickoff,
        goals_for=1,
        goals_against=0,
        ah_result="legacy-string-ignored",
        source="canonical_historical_ah_fact",
        source_group="canonical_historical_ah_fact",
        proxy_of=proxy_of,
        collection_status="CANONICAL_AH_FACT",
        ah_fact_id=fact_id,
        ah_fact_hash=f"{fact_id}-hash",
        quote_identity_hash=f"{fact_id}-quote",
        result_identity_hash=f"{fact_id}-result",
        settlement_outcome=settlement,
    )
