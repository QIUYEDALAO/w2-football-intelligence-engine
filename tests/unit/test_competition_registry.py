from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from w2.competitions.registry import CompetitionRegistry, CompetitionRegistryError
from w2.competitions.seed import seed_competition_runtime_authority
from w2.infrastructure.database import Base
from w2.infrastructure.persistence.league_models import LeagueProfileModel
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


def test_future_refresh_policy_rejects_non_whitelisted_competition() -> None:
    with pytest.raises(FutureRefreshError, match="COMPETITION_NOT_REGISTERED"):
        load_refresh_policy(competition_id="summer_low_quality")


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


def test_registry_rejects_missing_coverage_profile() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    seed_competition_runtime_authority(engine)
    with Session(engine) as session:
        profile = session.query(LeagueProfileModel).filter_by(competition_id="world_cup_2026").one()
        profile.payload = dict(profile.payload) | {"coverage_profile": {}}
        session.commit()

    with pytest.raises(CompetitionRegistryError, match="COVERAGE_PROFILE_MISSING"):
        CompetitionRegistry(engine).entries()


def test_future_refresh_world_cup_policy_remains_enabled() -> None:
    policy = load_refresh_policy(competition_id="world_cup_2026")

    assert policy.competition_id == "world_cup_2026"
    assert policy.enabled is True


def test_registry_uses_static_config_not_runtime_time() -> None:
    assert datetime(2026, 6, 25, tzinfo=UTC).tzinfo is UTC
    assert CompetitionRegistry().is_enabled("world_cup_2026") is True


def test_removed_staging_env_override_cannot_enable_competitions(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "staging")
    monkeypatch.setenv(
        "W2_STAGING_ENABLED_COMPETITIONS",
        "brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien",
    )

    registry = CompetitionRegistry()

    assert registry.enabled_ids() == {"world_cup_2026"}


def test_staging_enabled_competitions_do_not_apply_to_production(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("W2_ENVIRONMENT", "production")
    monkeypatch.setenv(
        "W2_STAGING_ENABLED_COMPETITIONS",
        "brasileirao_serie_a,chinese_super_league,allsvenskan,eliteserien",
    )

    registry = CompetitionRegistry()

    assert registry.enabled_ids() == {"world_cup_2026"}
