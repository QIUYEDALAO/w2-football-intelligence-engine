from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from scripts.check_team_values_mapping import load_mapping, load_team_ids, validate_mapping
from scripts.export_w2_world_cup_team_ids import collect_team_ids, write_csv

from w2.api import repository as api_repository
from w2.api.repository import ReadModelService
from w2.competitions.registry import CoverageProfile
from w2.features.framework import FeatureContext
from w2.features.team_factors import squad_value_factor

AS_OF = datetime(2026, 6, 27, tzinfo=UTC)


def fixture_payload(
    fixture_id: str = "fixture-1",
    *,
    home_id: int | None = 10,
    home_name: str = "Strong",
    away_id: int | None = 20,
    away_name: str = "Weak",
) -> dict[str, Any]:
    home: dict[str, Any] = {"name": home_name}
    away: dict[str, Any] = {"name": away_name}
    if home_id is not None:
        home["id"] = home_id
    if away_id is not None:
        away["id"] = away_id
    return {
        "fixture": {"id": fixture_id, "date": "2026-07-10T18:00:00Z"},
        "league": {"id": 1, "name": "World Cup", "season": 2026},
        "teams": {"home": home, "away": away},
    }


def valid_mapping_payload() -> dict[str, Any]:
    return {
        "version": "world_cup_2026.team_values.v1",
        "source_policy": (
            "real reviewed mappings only; no scraping, no credentials, "
            "no market-derived values"
        ),
        "items": [
            {
                "team_id": "10",
                "team_name": "Strong",
                "squad_value_eur": 900_000_000,
                "currency": "EUR",
                "observed_at": "2026-06-27T00:00:00Z",
                "source_system": "transfermarkt_national_team_page",
                "source_url": "https://www.transfermarkt.com/strong/startseite/verein/10",
                "source_tier": "primary_reviewed",
                "primary_source_review_status": "reviewed_against_primary",
                "confidence": 0.95,
                "reviewed_by": "human:reviewer-a",
                "note": "Manually reviewed team total market value.",
            },
            {
                "team_id": "20",
                "team_name": "Weak",
                "squad_value_eur": 120_000_000,
                "currency": "EUR",
                "observed_at": "2026-06-27T00:00:00Z",
                "source_system": "transfermarkt_national_team_page",
                "source_url": "https://www.transfermarkt.com/weak/startseite/verein/20",
                "source_tier": "primary_reviewed",
                "primary_source_review_status": "reviewed_against_primary",
                "confidence": 0.95,
                "reviewed_by": "human:reviewer-b",
                "note": "Manually reviewed team total market value.",
            },
        ],
    }


def write_mapping(root: Path, payload: dict[str, Any]) -> Path:
    path = root / "config/team_values/world_cup_2026.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_team_ids(path: Path, ids: list[str] | None = None) -> Path:
    ids = ids or ["10", "20", "30"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["team_id", "team_name", "seen_fixture_count", "example_fixture_id"],
        )
        writer.writeheader()
        for team_id in ids:
            writer.writerow(
                {
                    "team_id": team_id,
                    "team_name": f"Team {team_id}",
                    "seen_fixture_count": 1,
                    "example_fixture_id": "fixture-1",
                }
            )
    return path


def feature_context() -> FeatureContext:
    return FeatureContext(
        fixture_id="fixture-1",
        competition_id="world_cup_2026",
        home_team_id="10",
        away_team_id="20",
        kickoff_at=datetime(2026, 7, 10, 18, tzinfo=UTC),
        as_of=AS_OF,
        stage_id="group",
    )


def coverage_profile() -> CoverageProfile:
    return CoverageProfile(
        xg="API_FOOTBALL_STATISTICS",
        lineups_injuries="API_FOOTBALL_LINEUPS",
        squad_value="TRANSFERMARKT_REVIEWED_STATIC_MAPPING",
        bookmaker_depth="API_FOOTBALL_ODDS",
        h2h="API_FOOTBALL_FIXTURES",
        settled_ah="INTERNAL_SETTLEMENT",
    )


def test_export_distinct_team_ids_and_skips_missing_id(tmp_path: Path) -> None:
    teams = collect_team_ids(
        [
            tmp_json(
                tmp_path,
                {
                    "payload": {
                        "response": [
                            fixture_payload("a"),
                            fixture_payload("b"),
                            fixture_payload("c", home_id=None, away_id=30, away_name="Third"),
                        ]
                    }
                },
            )
        ],
        competition_id="world_cup_2026",
    )

    assert sorted(teams) == ["10", "20", "30"]
    assert len(teams["10"].fixture_ids) == 2

    output = tmp_path / "team_ids.csv"
    write_csv(output, teams)
    rows = list(csv.DictReader(output.open(encoding="utf-8")))
    assert {row["team_id"] for row in rows} == {"10", "20", "30"}


def test_export_empty_when_no_api_football_team_ids(tmp_path: Path) -> None:
    teams = collect_team_ids(
        [tmp_json(tmp_path, [{"home_team": "strong", "away_team": "weak"}])],
        competition_id="world_cup_2026",
    )

    assert teams == {}


def test_repository_team_value_mapping_and_asof_guard(monkeypatch: Any, tmp_path: Path) -> None:
    write_mapping(tmp_path, valid_mapping_payload())
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    values = service._team_value_mapping()

    assert sorted(values) == ["10", "20"]
    assert service._team_value_snapshot(values["10"], context=feature_context()) is not None

    future = dict(values["10"])
    future["observed_at"] = "2026-08-01T00:00:00Z"
    assert service._team_value_snapshot(future, context=feature_context()) is None


def test_squad_value_factor_ready_when_both_sides_mapped(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    write_mapping(tmp_path, valid_mapping_payload())
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    context = feature_context()
    home, away = service._team_values_from_static_mapping(
        context=context,
        home_team_id="10",
        away_team_id="20",
    )

    factor = squad_value_factor(
        context=context,
        profile=coverage_profile(),
        home_values=home,
        away_values=away,
    )

    assert factor.status.value == "READY"
    assert factor.source_group == "squad_value"
    assert factor.is_independent_signal is True
    assert factor.collection_status == "READY"
    assert factor.inputs["home_value_eur"] == 900_000_000


def test_squad_value_factor_missing_when_one_side_unmapped(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    payload = valid_mapping_payload()
    payload["items"] = payload["items"][:1]
    write_mapping(tmp_path, payload)
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    context = feature_context()
    home, away = service._team_values_from_static_mapping(
        context=context,
        home_team_id="10",
        away_team_id="20",
    )
    factor = squad_value_factor(
        context=context,
        profile=coverage_profile(),
        home_values=home,
        away_values=away,
    )

    assert factor.status.value == "UNAVAILABLE"
    assert factor.collection_status == "MAPPING_MISSING"
    assert factor.is_independent_signal is False


def test_no_mapping_file_and_empty_items_are_safe(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    assert service._team_value_mapping() == {}

    write_mapping(tmp_path, {**valid_mapping_payload(), "items": []})
    assert service._team_value_mapping() == {}


def test_team_values_do_not_fallback_to_world_cup_for_other_competition(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    write_mapping(tmp_path, valid_mapping_payload())
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    allsvenskan = FeatureContext(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        home_team_id="10",
        away_team_id="20",
        kickoff_at=datetime(2026, 7, 10, 18, tzinfo=UTC),
        as_of=AS_OF,
        stage_id="league",
    )

    home, away = service._team_values_from_static_mapping(
        context=allsvenskan,
        home_team_id="10",
        away_team_id="20",
    )

    assert home == []
    assert away == []


def test_validator_valid_mapping_passes(tmp_path: Path) -> None:
    mapping = valid_mapping_payload()
    summary = validate_mapping(
        mapping,
        known_team_ids={"10", "20", "30"},
        as_of=AS_OF,
    )

    assert summary.ok is True
    assert summary.mapped_teams == 2
    assert summary.unmapped_teams == 1
    assert summary.errors == []
    assert summary.warnings == ["1 teams remain unmapped"]


def test_validator_empty_mapping_passes_with_warning() -> None:
    mapping = {**valid_mapping_payload(), "items": []}
    summary = validate_mapping(mapping, known_team_ids={"10", "20"}, as_of=AS_OF)

    assert summary.ok is True
    assert summary.mapped_teams == 0
    assert summary.unmapped_teams == 2
    assert "F8 will remain MAPPING_MISSING" in summary.warnings[0]


def test_validator_rejects_invalid_mapping_cases() -> None:
    cases = [
        ("duplicate", lambda item: [item, item], "duplicate"),
        ("future", lambda item: [{**item, "observed_at": "2026-08-01T00:00:00Z"}], "after as-of"),
        ("missing_url", lambda item: [{**item, "source_url": ""}], "source_url"),
        ("missing_reviewer", lambda item: [{**item, "reviewed_by": ""}], "reviewed_by"),
        ("unknown_id", lambda item: [{**item, "team_id": "999"}], "not in exported"),
        ("fake", lambda item: [{**item, "note": "fake value"}], "forbidden"),
        ("negative", lambda item: [{**item, "squad_value_eur": -1}], "positive"),
        ("confidence", lambda item: [{**item, "confidence": 1.5}], "confidence"),
        ("missing_source_tier", lambda item: [{**item, "source_tier": ""}], "source_tier"),
        (
            "missing_review_status",
            lambda item: [{**item, "primary_source_review_status": ""}],
            "primary_source_review_status",
        ),
        (
            "secondary_over_cap",
            lambda item: [
                {
                    **item,
                    "source_tier": "secondary_with_primary_reference",
                    "primary_source": "https://www.transfermarkt.com/example",
                    "primary_source_review_status": "pending_primary_review",
                    "confidence": 0.9,
                }
            ],
            "exceeds secondary_with_primary_reference cap",
        ),
    ]
    for _name, mutate, expected in cases:
        item = valid_mapping_payload()["items"][0]
        mapping = {**valid_mapping_payload(), "items": mutate(item)}
        summary = validate_mapping(mapping, known_team_ids={"10", "20"}, as_of=AS_OF)
        assert summary.ok is False
        assert any(expected in error for error in summary.errors), summary.errors


def test_validator_loads_csv_and_mapping(tmp_path: Path) -> None:
    mapping_path = write_mapping(tmp_path, valid_mapping_payload())
    team_ids_path = write_team_ids(tmp_path / "team_ids.csv")

    mapping = load_mapping(mapping_path)
    team_ids = load_team_ids(team_ids_path)

    assert mapping["version"] == "world_cup_2026.team_values.v1"
    assert team_ids == {"10", "20", "30"}


def test_world_cup_team_values_are_marked_secondary_until_primary_review() -> None:
    path = Path("config/team_values/world_cup_2026.v1.json")
    mapping = load_mapping(path)

    assert mapping["primary_review_status"] == "pending_primary_review"
    assert mapping["confidence_policy"]["secondary_with_primary_reference"][
        "max_confidence"
    ] == 0.85
    assert len(mapping["items"]) == 48
    for item in mapping["items"]:
        assert item["source_tier"] == "secondary_with_primary_reference"
        assert item["primary_source_review_status"] == "pending_primary_review"
        assert item["confidence"] == 0.85
        assert item["primary_source"].startswith("https://www.transfermarkt.com/")


def tmp_json(tmp_path: Path, payload: Any) -> Path:
    path = tmp_path / f"payload_{len(list(tmp_path.glob('payload_*.json')))}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
