from __future__ import annotations

import json
from pathlib import Path

import pytest

from w2.dashboard.l1_view import build_boss_dashboard_l1
from w2.dashboard.team_localization import (
    DEFAULT_REGISTRY_PATH,
    TeamLocalizationRegistry,
    TeamLocalizationRegistryError,
    clear_team_localization_registry_cache,
    localize_team_name,
)


def test_registry_covers_all_cached_2026_whitelist_teams() -> None:
    payload = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    rows = payload["teams"]

    assert len(rows) == 308
    assert {row["competition_id"] for row in rows} == {
        "world_cup_2026",
        "premier_league",
        "ligue_1",
        "brasileirao_serie_a",
        "bundesliga",
        "eredivisie",
        "primeira_liga",
        "eliteserien",
        "allsvenskan",
        "argentina_primera",
        "serie_a",
        "la_liga",
        "chinese_super_league",
        "mls",
    }


def test_localize_prefers_competition_scoped_team_id() -> None:
    localized = localize_team_name(
        competition_id="world_cup_2026",
        provider_team_id="2",
        provider_name="Unexpected Provider Spelling",
        missing_name_fallback="主队",
    )

    assert localized.display_name == "法国"
    assert localized.name_zh == "法国"
    assert localized.provider_name == "Unexpected Provider Spelling"
    assert localized.status == "MATCHED_BY_ID"


def test_localize_supports_provider_league_id_and_club_alias() -> None:
    localized = localize_team_name(
        competition_id="169",
        provider_team_id=None,
        provider_name="Shandong Luneng",
        missing_name_fallback="主队",
    )

    assert localized.display_name == "山东泰山"
    assert localized.provider_name == "Shandong Luneng"
    assert localized.status == "MATCHED_BY_ALIAS"


def test_localize_unknown_team_falls_back_to_provider_name() -> None:
    localized = localize_team_name(
        competition_id="premier_league",
        provider_team_id="999999",
        provider_name="New Provider Club",
        missing_name_fallback="主队",
    )

    assert localized.display_name == "New Provider Club"
    assert localized.name_zh is None
    assert localized.status == "FALLBACK_PROVIDER_NAME"


def test_registry_rejects_conflicting_aliases(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "competition_aliases": {},
                "teams": [
                    {
                        "competition_id": "league",
                        "provider_team_id": "1",
                        "provider_name": "Same Club",
                        "name_zh": "甲队",
                    },
                    {
                        "competition_id": "league",
                        "provider_team_id": "2",
                        "provider_name": "Other Club",
                        "name_zh": "乙队",
                        "aliases": ["Same Club"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TeamLocalizationRegistryError, match="conflicting"):
        TeamLocalizationRegistry.load(path)


def test_explicit_registry_path_works_outside_source_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "installed-wheel-registry.json"
    path.write_text(
        json.dumps(
            {
                "competition_aliases": {},
                "teams": [
                    {
                        "competition_id": "league",
                        "provider_team_id": "7",
                        "provider_name": "Provider Club",
                        "name_zh": "测试俱乐部",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("W2_TEAM_LOCALIZATION_REGISTRY_PATH", str(path))
    clear_team_localization_registry_cache()
    try:
        localized = localize_team_name(
            competition_id="league",
            provider_team_id="7",
            provider_name="Provider Club",
            missing_name_fallback="主队",
        )
        assert localized.display_name == "测试俱乐部"
    finally:
        clear_team_localization_registry_cache()


def test_l1_view_uses_localized_display_names_without_leaking_status() -> None:
    l1 = build_boss_dashboard_l1(
        {
            "environment": "staging",
            "football_day": "2026-07-10",
            "generated_at": "2026-07-10T00:00:00Z",
            "counts": {"lock_eligible": 0},
            "cards": [
                {
                    "fixture_id": "fixture-localized",
                    "kickoff_utc": "2026-07-10T12:00:00Z",
                    "home_team_name": "France",
                    "away_team_name": "Morocco",
                    "home_team_display_name": "法国",
                    "away_team_display_name": "摩洛哥",
                    "home_team_localization_status": "MATCHED_BY_ID",
                    "away_team_localization_status": "MATCHED_BY_ID",
                    "decision_tier": "WATCH",
                    "data_status": "PARTIAL",
                    "lock_eligible": False,
                    "non_pick": {"reason_code": "LINEUPS_PENDING"},
                }
            ],
        }
    )

    assert l1["cards"][0]["match"] == "法国 vs 摩洛哥"
    assert "MATCHED_BY_ID" not in json.dumps(l1, ensure_ascii=False)
