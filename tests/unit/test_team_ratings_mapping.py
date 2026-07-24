from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from w2.features.framework import FeatureContext
from w2.prematch import analysis_calculator as api_repository
from w2.prematch.analysis_calculator import ReadModelService

ROOT = Path(__file__).resolve().parents[2]
RATINGS_PATH = ROOT / "config/team_ratings/world_cup_2026.v1.json"
TEAM_IDS_PATH = ROOT / "config/team_values/world_cup_2026.team_ids.csv"


def _payload() -> dict[str, Any]:
    return json.loads(RATINGS_PATH.read_text(encoding="utf-8"))


def test_world_cup_real_elo_mapping_covers_all_known_team_ids() -> None:
    payload = _payload()
    items = payload["items"]
    mapped_ids = {str(item["team_id"]) for item in items}
    with TEAM_IDS_PATH.open(newline="", encoding="utf-8") as handle:
        expected_ids = {row["team_id"] for row in csv.DictReader(handle)}

    assert len(items) == 48
    assert mapped_ids == expected_ids


def test_world_cup_real_elo_mapping_has_reviewed_static_source_metadata() -> None:
    payload = _payload()

    assert payload["source_system"] == "world_football_elo"
    assert payload["source_url"] == "https://www.eloratings.net/World.tsv"
    assert "no market/xg/score-derived ratings" in payload["source_policy"]
    assert payload["observed_at"] == "2026-07-01T22:50:30Z"
    assert payload["reviewed_by"] == "liudehua"
    assert (ROOT / payload["raw_snapshot_path"]).exists()

    for item in payload["items"]:
        assert item["source_system"] == "world_football_elo"
        assert item["source_url"] == "https://www.eloratings.net/World.tsv"
        assert item["observed_at"] == payload["observed_at"]
        assert item["reviewed_by"] == "liudehua"
        assert item["confidence"] >= 0.9
        assert isinstance(item["elo"], int)
        assert 300 <= item["elo"] <= 2300


def test_team_ratings_do_not_fallback_to_world_cup_for_other_competition(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    target = tmp_path / "config/team_ratings/world_cup_2026.v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(RATINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(api_repository, "ROOT", tmp_path)
    service = ReadModelService(repository=cast(Any, object()))
    context = FeatureContext(
        fixture_id="fixture-1",
        competition_id="allsvenskan",
        home_team_id="1",
        away_team_id="2",
        kickoff_at=datetime(2026, 7, 10, 18, tzinfo=UTC),
        as_of=datetime(2026, 7, 1, tzinfo=UTC),
    )

    home, away = service._team_ratings_from_static_mapping(
        context=context,
        home_team_id="1",
        away_team_id="2",
        history_home_ratings=[],
        history_away_ratings=[],
    )

    assert home == []
    assert away == []
