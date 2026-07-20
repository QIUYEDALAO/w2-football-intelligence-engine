from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from w2.competitions.registry import CoverageProfile
from w2.features.framework import FeatureContext
from w2.features.team_factors import TeamMatchHistory, recent_ah_cover_factor
from w2.historical.formal_ah import (
    audit_formal_ah_sources,
    build_canonical_ah_facts,
    decimal_line,
)
from w2.lineups.value_identity import (
    approved_crosswalk_for_team,
    build_team_crosswalk,
    materialize_team_value_asof,
)

AS_OF = datetime(2026, 7, 20, tzinfo=UTC)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _registry(path: Path, *, local_path: str, **overrides: object) -> Path:
    payload = {
        "sources": [
            {
                "source_id": "src-1",
                "provider": "local-approved",
                "local_path": local_path,
                "schema_version": "test.v1",
                "license_status": "APPROVED",
                "retention_permitted": True,
                "internal_backtest_permitted": True,
                **overrides,
            }
        ]
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
    assert first["facts"][0]["home_settlement"] == "WIN"
    assert first["facts"][0]["away_settlement"] == "LOSS"


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


def test_missing_crosswalk_and_conflicting_crosswalk() -> None:
    approved = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "tm-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
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


def test_team_value_asof_uses_source_valuation_date_and_rejects_future(tmp_path: Path) -> None:
    crosswalk = build_team_crosswalk(
        {
            "api_football_team_id": "1",
            "transfermarkt_club_id": "club-1",
            "competition_id": "allsvenskan",
            "valid_from": "2024-01-01T00:00:00Z",
            "source_sha256": "a" * 64,
            "review_status": "APPROVED",
            "reviewed_by": "reviewer",
            "reviewed_at": "2024-01-02T00:00:00Z",
        }
    )
    _write_csv(
        tmp_path / "game_lineups.csv",
        [
            {
                "transfermarkt_player_id": "p1",
                "club_id": "club-1",
                "date": "2024-05-01T00:00:00Z",
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
        source_root=tmp_path,
    )
    rebuilt = materialize_team_value_asof(
        fixture={
            "team_external_id": "1",
            "competition_id": "allsvenskan",
            "as_of": "2024-05-02T00:00:00Z",
        },
        crosswalks=[crosswalk],
        source_root=tmp_path,
    )

    assert artifact["status"] == "READY"
    assert artifact["squad_value_eur"] == "100"
    assert artifact["future_valuation_exclusions"] == 1
    assert artifact["artifact_hash"] == rebuilt["artifact_hash"]


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
        source_group="team_fixture_history",
        proxy_of=proxy_of,
        collection_status="READY",
        ah_fact_id=fact_id,
        ah_fact_hash=f"{fact_id}-hash",
        quote_identity_hash=f"{fact_id}-quote",
        result_identity_hash=f"{fact_id}-result",
        settlement_outcome=settlement,
    )
