from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from w2.competitions.registry import CompetitionRegistry
from w2.features import market_factors
from w2.features.engine import FeatureInputs, build_feature_set, load_importance_config
from w2.features.framework import FeatureContext, FeatureStatus
from w2.features.live_factors import (
    lineup_injury_factor,
    parse_api_football_availability,
    parse_api_football_xg,
    true_xg_factor,
)
from w2.features.market_factors import (
    BookmakerQuote,
    bookmaker_divergence_factor,
    market_movement_factor,
)
from w2.features.team_factors import (
    TeamMatchHistory,
    TeamRatingSnapshot,
    TeamValueSnapshot,
    h2h_factor,
    recent_ah_cover_factor,
    rest_fitness_factor,
    squad_value_factor,
    strength_form_factor,
)
from w2.markets.movement import MarketSnapshot

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=UTC)
KICKOFF = datetime(2026, 6, 22, 18, 0, tzinfo=UTC)


def context() -> FeatureContext:
    return FeatureContext(
        fixture_id="fx-1",
        competition_id="world_cup_2026",
        home_team_id="10",
        away_team_id="20",
        kickoff_at=KICKOFF,
        as_of=NOW,
        stage_id="group",
    )


def coverage():
    return CompetitionRegistry().require_enabled("world_cup_2026").coverage_profile


def test_market_movement_contribution_is_explainable_and_as_of_safe() -> None:
    snapshots = [
        MarketSnapshot(
            fixture_id="fx-1",
            market="ONE_X_TWO",
            selection="Home",
            price=Decimal("2.10"),
            captured_at=NOW - timedelta(hours=3),
            snapshot_semantics="CAPTURED_AT",
        ),
        MarketSnapshot(
            fixture_id="fx-1",
            market="ONE_X_TWO",
            selection="Home",
            price=Decimal("1.95"),
            captured_at=NOW - timedelta(hours=1),
            snapshot_semantics="CAPTURED_AT",
        ),
    ]

    item = market_movement_factor(context=context(), profile=coverage(), snapshots=snapshots)

    assert item.status == FeatureStatus.READY
    assert item.score is not None
    assert item.inputs["velocity"] is not None
    assert item.candidate is False
    assert item.formal_recommendation is False


def test_market_movement_blocks_future_rows() -> None:
    item = market_movement_factor(
        context=context(),
        profile=coverage(),
        snapshots=[
            MarketSnapshot(
                fixture_id="fx-1",
                market="ONE_X_TWO",
                selection="Home",
                price=Decimal("1.90"),
                captured_at=NOW + timedelta(minutes=1),
                snapshot_semantics="CAPTURED_AT",
            )
        ],
    )

    assert item.status == FeatureStatus.LEAKAGE_BLOCKED
    assert item.reason.startswith("AS_OF_LEAKAGE")


def test_bookmaker_divergence_uses_consensus_and_sharp_soft_gap() -> None:
    quotes = [
        BookmakerQuote(
            bookmaker="Pinnacle",
            market="ONE_X_TWO",
            selection="Home",
            decimal_odds=Decimal("1.92"),
            captured_at=NOW,
            provider_updated_at=NOW,
        ),
        BookmakerQuote(
            bookmaker="SoftBook",
            market="ONE_X_TWO",
            selection="Home",
            decimal_odds=Decimal("2.04"),
            captured_at=NOW,
            provider_updated_at=NOW,
        ),
    ]

    item = bookmaker_divergence_factor(context=context(), profile=coverage(), quotes=quotes)

    assert item.status in {FeatureStatus.READY, FeatureStatus.DEGRADED}
    assert item.inputs["effective_bookmakers"] == 2
    assert item.inputs["sharp_soft_gap"] == -0.1200000000000001


def test_bookmaker_divergence_degrades_when_consensus_cannot_be_built(monkeypatch) -> None:
    def fail_build(*object_args: object, **object_kwargs: object) -> object:
        raise IndexError("empty weighted median")

    monkeypatch.setattr(market_factors.MarketConsensusBuilder, "build", fail_build)
    quotes = [
        BookmakerQuote(
            bookmaker="Pinnacle",
            market="ONE_X_TWO",
            selection="Home",
            decimal_odds=Decimal("1.92"),
            captured_at=NOW,
            provider_updated_at=NOW,
        ),
        BookmakerQuote(
            bookmaker="SoftBook",
            market="ONE_X_TWO",
            selection="Home",
            decimal_odds=Decimal("2.04"),
            captured_at=NOW,
            provider_updated_at=NOW,
        ),
    ]

    item = bookmaker_divergence_factor(context=context(), profile=coverage(), quotes=quotes)

    assert item.status == FeatureStatus.INSUFFICIENT_DATA
    assert item.reason == "CONSENSUS_UNAVAILABLE"


def test_team_factors_degrade_or_compute_without_inventing_missing_data() -> None:
    home_history = [
        TeamMatchHistory(
            team_id="10",
            opponent_id="30",
            kickoff_at=NOW - timedelta(days=6),
            goals_for=2,
            goals_against=1,
            ah_result="COVER",
            ah_fact_id="canonical-ah:home",
            ah_fact_hash="a" * 64,
            quote_identity_hash="b" * 64,
            result_identity_hash="c" * 64,
            settlement_outcome="WIN",
            source="canonical_historical_ah_fact",
            collection_status="CANONICAL_AH_FACT",
        )
    ]
    away_history = [
        TeamMatchHistory(
            team_id="20",
            opponent_id="40",
            kickoff_at=NOW - timedelta(days=3),
            goals_for=1,
            goals_against=1,
            ah_result="NO_COVER",
            ah_fact_id="canonical-ah:away",
            ah_fact_hash="d" * 64,
            quote_identity_hash="e" * 64,
            result_identity_hash="f" * 64,
            settlement_outcome="LOSS",
            source="canonical_historical_ah_fact",
            collection_status="CANONICAL_AH_FACT",
        )
    ]

    rest = rest_fitness_factor(
        context=context(),
        home_history=home_history,
        away_history=away_history,
    )
    cover = recent_ah_cover_factor(
        context=context(),
        profile=coverage(),
        home_history=home_history,
        away_history=away_history,
    )
    h2h = h2h_factor(context=context(), profile=coverage(), meetings=[])

    assert rest.status == FeatureStatus.READY
    assert cover.status == FeatureStatus.READY
    assert cover.weight < 0.10
    assert h2h.status == FeatureStatus.UNAVAILABLE
    assert h2h.reason == "NO_H2H_HISTORY"
    assert h2h.collection_status == "NO_H2H_HISTORY"


def test_strength_and_squad_value_use_latest_as_of_not_future() -> None:
    home_ratings = [
        TeamRatingSnapshot(
            team_id="10",
            observed_at=NOW - timedelta(days=1),
            elo=1700,
            attack_strength=0.5,
            defence_strength=0.2,
            form_index=0.4,
        )
    ]
    away_ratings = [
        TeamRatingSnapshot(
            team_id="20",
            observed_at=NOW - timedelta(days=1),
            elo=1600,
            attack_strength=0.2,
            defence_strength=0.4,
            form_index=0.1,
        )
    ]
    home_values = [
        TeamValueSnapshot(
            team_id="10",
            observed_at=NOW + timedelta(days=2),
            squad_value_eur=900_000_000,
            source_system="transfermarkt_dataset",
            confidence=0.9,
        ),
        TeamValueSnapshot(
            team_id="10",
            observed_at=NOW - timedelta(days=2),
            squad_value_eur=700_000_000,
            source_system="transfermarkt_dataset",
            confidence=0.9,
        ),
    ]
    away_values = [
        TeamValueSnapshot(
            team_id="20",
            observed_at=NOW - timedelta(days=2),
            squad_value_eur=500_000_000,
            source_system="transfermarkt_dataset",
            confidence=0.9,
        )
    ]

    strength = strength_form_factor(
        context=context(),
        home_ratings=home_ratings,
        away_ratings=away_ratings,
    )
    value = squad_value_factor(
        context=context(),
        profile=coverage(),
        home_values=home_values,
        away_values=away_values,
    )

    assert strength.status == FeatureStatus.READY
    assert value.status == FeatureStatus.READY
    assert value.inputs["home_value_eur"] == 700_000_000


def test_importance_is_config_driven_and_feature_set_keeps_disclaimer() -> None:
    importance = load_importance_config("world_cup_2026")
    feature_set = build_feature_set(context=context(), inputs=FeatureInputs())

    assert importance.score_for_stage("group") == 0.72
    assert feature_set.disclaimer == "分析参考，非保证盈利"
    assert feature_set.candidate is False
    assert feature_set.formal_recommendation is False


def test_live_xg_and_lineup_injury_features_parse_fake_payloads() -> None:
    xg_rows = parse_api_football_xg(
        captured_at=NOW,
        payload={
            "response": [
                {
                    "team": {"id": 10},
                    "statistics": [{"type": "expected_goals", "value": "1.8"}],
                },
                {
                    "team": {"id": 20},
                    "statistics": [{"type": "expected_goals", "value": "0.9"}],
                },
            ]
        },
    )
    availability = parse_api_football_availability(
        captured_at=NOW,
        lineups_payload={
            "response": [
                {"team": {"id": 10}, "startXI": [{} for _ in range(11)], "substitutes": []},
                {"team": {"id": 20}, "startXI": [{} for _ in range(11)], "substitutes": [{}]},
            ]
        },
        injuries_payload={
            "response": [
                {
                    "team": {"id": 20},
                    "player": {"position": "Goalkeeper"},
                    "reason": "Suspended",
                }
            ]
        },
    )

    xg = true_xg_factor(
        context=context(),
        profile=coverage(),
        home_xg=[row for row in xg_rows if row.team_id == "10"],
        away_xg=[row for row in xg_rows if row.team_id == "20"],
    )
    lineups = lineup_injury_factor(
        context=context(),
        profile=coverage(),
        home_availability=[row for row in availability if row.team_id == "10"],
        away_availability=[row for row in availability if row.team_id == "20"],
    )

    assert xg.status == FeatureStatus.READY
    assert xg.inputs["home_xg_net"] == 0.9
    assert lineups.status == FeatureStatus.READY
    assert lineups.inputs["away_availability_risk"] > lineups.inputs["home_availability_risk"]


def test_disabled_competition_degrades_by_whitelist() -> None:
    disabled = FeatureContext(
        fixture_id="fx-2",
        competition_id="premier_league",
        home_team_id="10",
        away_team_id="20",
        kickoff_at=KICKOFF,
        as_of=NOW,
    )

    feature_set = build_feature_set(context=disabled, inputs=FeatureInputs())

    assert feature_set.status == FeatureStatus.NOT_WHITELISTED
    assert feature_set.contributions[0].reason == "COMPETITION_NOT_ENABLED"
