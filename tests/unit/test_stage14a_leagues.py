from __future__ import annotations

from w2.operations.leagues import (
    MarketStatus,
    load_profiles,
    run_top_five_audit,
)


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


def test_dynamic_team_loading_and_season_identification() -> None:
    audit = run_top_five_audit()
    premier = audit["coverage"]["premier_league"]
    assert premier["fixture_result_count"] > 0
    assert premier["team_count"] >= 20
    assert sorted(premier["seasons"])[-1] == "2025"
    assert premier["result_dataset_not_market_dataset"] is True


def test_rollover_manual_review_and_no_guessing() -> None:
    audit = run_top_five_audit()
    rollover = audit["rollover"]["premier_league"]
    assert rollover["status"] == "MANUAL_REVIEW_REQUIRED"
    assert "PROMOTION_RELEGATION_NOT_CONFIRMED_OFFLINE" in rollover["unresolved_mappings"]
    assert rollover["next_season"] == "2026"


def test_market_coverage_semantics_and_model_scope_isolation() -> None:
    audit = run_top_five_audit()
    readiness = audit["readiness"]["premier_league"]
    market = readiness["audit"]["market_state"]
    assert market["RESULTS_READY"] == "READY"
    assert market["MARKET_AH_READY"] in {MarketStatus.PARTIAL.value, MarketStatus.MISSING.value}
    policy = readiness["model_scope_policy"]
    assert policy["national_to_club_parameter_reuse"] == "FORBIDDEN"
    assert policy["final_parameter_sharing_between_leagues"] == "FORBIDDEN"
    assert readiness["checklist"]["strategy_validation"] == "BLOCKED_GATE4"
