from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.ingestion.future_refresh import FutureRefreshError, load_refresh_policy
from w2.strategy.score_card import build_score_card


def test_only_world_cup_2026_is_enabled_in_competition_registry() -> None:
    registry = CompetitionRegistry()

    assert registry.enabled_ids() == {"world_cup_2026"}
    world_cup = registry.require_enabled("world_cup_2026")
    assert world_cup.season == "2026"
    assert (
        world_cup.coverage_profile.xg
        == "API_FOOTBALL_FIXTURES_STATISTICS_AVAILABLE_CONTROLLED_LIVE"
    )
    assert world_cup.provider_mapping["api_football_league_id"] == "1"
    assert world_cup.provider_mapping["api_football_season"] == "2026"

    disabled = [entry for entry in registry.entries().values() if not entry.enabled]
    assert disabled
    assert all(
        entry.coverage_profile.bookmaker_depth == "NOT_AUDITED_STAGE14_REQUIRED"
        for entry in disabled
    )


def test_future_refresh_policy_rejects_non_whitelisted_competition(tmp_path: Path) -> None:
    policy = {
        "competitions": [
            {
                "competition_id": "summer_low_quality",
                "provider": "api_football",
                "provider_league_id": "999",
                "season": "2026",
                "horizon_days": 14,
                "scheduler_interval_seconds": 900,
                "quota_reserve": 1500,
                "request_budget": 40,
                "max_fixture_candidates": 20,
                "max_odds_requests": 10,
                "market_freshness_seconds": 3600,
                "enabled": True,
            }
        ]
    }
    path = tmp_path / "future_fixture_refresh.v1.json"
    path.write_text(json.dumps(policy), encoding="utf-8")

    with pytest.raises(FutureRefreshError, match="COMPETITION_NOT_REGISTERED"):
        load_refresh_policy(competition_id="summer_low_quality", policy_path=path)


def test_score_card_non_whitelisted_competition_defaults_to_skip() -> None:
    card = build_score_card(
        score_matrix={"1-0": 0.4, "0-1": 0.1},
        decision="MAIN",
        primary_direction="HOME",
        competition_id="summer_low_quality",
    )

    assert card.decision == "SKIP"
    assert card.scenarios == []
    assert card.candidate is False
    assert card.formal_recommendation is False


def test_registry_rejects_missing_coverage_profile(tmp_path: Path) -> None:
    root = tmp_path / "competitions"
    root.mkdir()
    (root / "bad.json").write_text(
        json.dumps({"competition_id": "bad", "season": "2026", "enabled": False}),
        encoding="utf-8",
    )

    with pytest.raises(CompetitionRegistryError, match="COVERAGE_PROFILE_MISSING"):
        CompetitionRegistry(root).entries()


def test_future_refresh_world_cup_policy_remains_enabled() -> None:
    policy = load_refresh_policy(competition_id="world_cup_2026")

    assert policy.competition_id == "world_cup_2026"
    assert policy.enabled is True


def test_registry_uses_static_config_not_runtime_time() -> None:
    assert datetime(2026, 6, 25, tzinfo=UTC).tzinfo is UTC
    assert CompetitionRegistry().is_enabled("world_cup_2026") is True
