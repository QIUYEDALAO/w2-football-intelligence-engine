from __future__ import annotations

import pytest

import w2.operations.leagues as leagues
from w2.operations.leagues import (
    MarketStatus,
    audit_league,
    load_profiles,
    run_top_five_audit,
)


def premier_league_fixture_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seasons = {
        "2024": [f"10{team:02d}" for team in range(1, 21)],
        "2025": [f"10{team:02d}" for team in range(4, 24)],
    }
    fixture_id = 1
    for season, teams in seasons.items():
        for index in range(20):
            home = teams[index]
            away = teams[(index + 1) % len(teams)]
            rows.append(
                {
                    "fixture": {
                        "id": fixture_id,
                        "date": f"{season}-08-{(index % 28) + 1:02d}T15:00:00+00:00",
                        "venue": {"name": f"Test Stadium {index}"},
                    },
                    "league": {
                        "id": "39",
                        "country": "England",
                        "season": season,
                        "round": f"Regular Season - {index + 1}",
                    },
                    "teams": {
                        "home": {"id": home, "name": f"Team {home}"},
                        "away": {"id": away, "name": f"Team {away}"},
                    },
                    "goals": {"home": index % 4, "away": (index + 1) % 3},
                }
            )
            fixture_id += 1
    return rows


@pytest.fixture()
def top_five_fixture_rows(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    rows = premier_league_fixture_rows()
    monkeypatch.setattr(leagues, "_fixture_items", lambda: rows)
    return rows


def test_top_five_profiles_schema() -> None:
    profiles = load_profiles()
    assert len(profiles) == 5
    assert {profile.competition_id for profile in profiles} == {
        "premier_league",
        "la_liga",
        "bundesliga",
        "serie_a",
        "ligue_1",
    }
    assert all(profile.expected_team_count in {18, 20} for profile in profiles)
    assert all("ONE_X_TWO" in profile.market_scope for profile in profiles)


def test_dynamic_team_loading_and_season_identification(
    top_five_fixture_rows: list[dict[str, object]],
) -> None:
    assert top_five_fixture_rows
    audit = run_top_five_audit()
    premier = audit["coverage"]["premier_league"]
    assert premier["fixture_result_count"] > 0
    assert premier["team_count"] >= 20
    assert sorted(premier["seasons"])[-1] == "2025"
    assert premier["result_dataset_not_market_dataset"] is True


def test_rollover_manual_review_and_no_guessing(
    top_five_fixture_rows: list[dict[str, object]],
) -> None:
    assert top_five_fixture_rows
    audit = run_top_five_audit()
    rollover = audit["rollover"]["premier_league"]
    assert rollover["status"] == "MANUAL_REVIEW_REQUIRED"
    assert "PROMOTION_RELEGATION_NOT_CONFIRMED_OFFLINE" in rollover["unresolved_mappings"]
    assert rollover["next_season"] == "2026"


def test_market_coverage_semantics_and_model_scope_isolation(
    top_five_fixture_rows: list[dict[str, object]],
) -> None:
    assert top_five_fixture_rows
    audit = run_top_five_audit()
    readiness = audit["readiness"]["premier_league"]
    market = readiness["audit"]["market_state"]
    assert market["RESULTS_READY"] == "READY"
    assert market["MARKET_AH_READY"] in {MarketStatus.PARTIAL.value, MarketStatus.MISSING.value}
    policy = readiness["model_scope_policy"]
    assert policy["national_to_club_parameter_reuse"] == "FORBIDDEN"
    assert policy["final_parameter_sharing_between_leagues"] == "FORBIDDEN"
    assert readiness["checklist"]["strategy_validation"] == "BLOCKED_GATE4"


def test_fresh_audit_without_runtime_data_stays_missing() -> None:
    premier = next(
        profile for profile in load_profiles() if profile.competition_id == "premier_league"
    )
    audit = audit_league(premier, [])

    assert audit["market_state"]["RESULTS_READY"] == "MISSING"
