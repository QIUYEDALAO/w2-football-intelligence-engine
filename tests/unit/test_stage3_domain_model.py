from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from w2.domain.entities import (
    AuditEvent,
    Bookmaker,
    Competition,
    DataProvenance,
    FeatureSnapshot,
    Fixture,
    Injury,
    Lineup,
    Market,
    ModelRun,
    OddsObservation,
    Player,
    Prediction,
    ProviderEntityMapping,
    RawPayloadReference,
    Recommendation,
    RecommendationLock,
    Referee,
    Result,
    Season,
    Settlement,
    Squad,
    Stage,
    Suspension,
    Team,
    TeamRating,
    Venue,
    WeatherObservation,
)
from w2.domain.enums import (
    DataLayer,
    FixtureStatus,
    MarketType,
    RecommendationStatus,
    SettlementOutcome,
)
from w2.domain.odds import (
    canonicalize_selection,
    settle_asian_handicap,
    settle_total_goals,
    split_quarter_line,
)
from w2.schemas.domain import FeatureSnapshotSchema, FixtureSchema, OddsObservationSchema

NOW = datetime(2026, 6, 22, 1, 0, tzinfo=UTC)
DIGEST = "a" * 64


def test_all_core_entities_are_constructible_with_uuid_identity() -> None:
    competition = Competition(name="synthetic competition")
    season = Season(
        competition_id=competition.id,
        name="synthetic season",
        start_date=NOW,
        end_date=NOW,
    )
    stage = Stage(season_id=season.id, name="synthetic stage", order_index=1)
    home = Team(name="synthetic home")
    away = Team(name="synthetic away")
    player = Player(name="synthetic player", birth_date=NOW)
    squad = Squad(team_id=home.id, player_id=player.id, season_id=season.id)
    venue = Venue(name="synthetic venue")
    referee = Referee(name="synthetic referee")
    fixture = Fixture(
        competition_id=competition.id,
        season_id=season.id,
        stage_id=stage.id,
        home_team_id=home.id,
        away_team_id=away.id,
        venue_id=venue.id,
        referee_id=referee.id,
        kickoff_at=NOW,
        status=FixtureStatus.SCHEDULED,
    )
    bookmaker = Bookmaker(name="synthetic bookmaker")
    market = Market(fixture_id=fixture.id, market=MarketType.TOTALS, settlement_rule="total_goals")
    odds = OddsObservation(
        fixture_id=fixture.id,
        bookmaker_id=bookmaker.id,
        market=MarketType.TOTALS,
        selection="over",
        line=Decimal("2.25"),
        decimal_odds=Decimal("1.9000"),
        suspended=False,
        live=False,
        stale=False,
        provider_updated_at=NOW,
        captured_at=NOW,
        raw_label="O 2.25",
        settlement_rule="total_goals",
    )
    raw = RawPayloadReference(
        provider="synthetic",
        object_uri="object://payload",
        sha256=DIGEST,
        captured_at=NOW,
    )
    provenance = DataProvenance(
        entity_type="fixture",
        entity_id=fixture.id,
        layer=DataLayer.NORMALIZED,
        source_ref_id=raw.id,
        event_time=NOW,
        provider_updated_at=NOW,
        ingested_at=NOW,
    )
    lineup = Lineup(fixture_id=fixture.id, team_id=home.id, player_id=player.id, confirmed_at=NOW)
    injury = Injury(player_id=player.id, team_id=home.id, status="synthetic", as_of_time=NOW)
    suspension = Suspension(
        player_id=player.id,
        team_id=home.id,
        status="synthetic",
        as_of_time=NOW,
    )
    weather = WeatherObservation(
        fixture_id=fixture.id,
        observed_at=NOW,
        temperature_c=Decimal("18.5"),
    )
    rating = TeamRating(team_id=home.id, as_of_time=NOW, rating=Decimal("1500.0"))
    features = FeatureSnapshot(
        fixture_id=fixture.id,
        as_of_time=NOW,
        features={"rating_delta": Decimal("1.0")},
    )
    model_run = ModelRun(name="synthetic model run", run_time=NOW)
    prediction = Prediction(
        fixture_id=fixture.id,
        model_run_id=model_run.id,
        as_of_time=NOW,
        probability=Decimal("0.5000"),
    )
    recommendation = Recommendation(
        fixture_id=fixture.id,
        prediction_id=prediction.id,
        status=RecommendationStatus.DRAFT,
        created_at=NOW,
    )
    lock = RecommendationLock(
        recommendation_id=recommendation.id,
        status=RecommendationStatus.LOCKED,
        locked_at=NOW,
        reason="synthetic lock",
    )
    result = Result(fixture_id=fixture.id, home_goals=1, away_goals=1, confirmed_at=NOW)
    settlement = Settlement(
        recommendation_id=recommendation.id,
        result_id=result.id,
        outcome="PUSH",
        settled_at=NOW,
    )
    audit = AuditEvent(
        entity_type="fixture",
        entity_id=fixture.id,
        action="created",
        occurred_at=NOW,
        actor="test",
    )

    constructed = [
        competition,
        season,
        stage,
        home,
        away,
        player,
        squad,
        venue,
        referee,
        fixture,
        bookmaker,
        market,
        odds,
        raw,
        provenance,
        lineup,
        injury,
        suspension,
        weather,
        rating,
        features,
        model_run,
        prediction,
        recommendation,
        lock,
        result,
        settlement,
        audit,
    ]
    assert all(item.id for item in constructed)
    assert odds.canonical_selection == "OVER"


def test_provider_mapping_requires_confidence_and_utc_validity() -> None:
    mapping = ProviderEntityMapping(
        entity_type="team",
        entity_id=uuid4(),
        provider="synthetic",
        external_id="external-1",
        source="provider payload",
        confidence=Decimal("0.90"),
        valid_from=NOW,
    )
    assert mapping.confidence == Decimal("0.90")
    with pytest.raises(ValueError):
        ProviderEntityMapping(
            entity_type="team",
            entity_id=uuid4(),
            provider="synthetic",
            external_id="external-1",
            source="provider payload",
            confidence=Decimal("1.50"),
            valid_from=NOW,
        )


def test_naive_datetime_is_rejected_and_unknown_fields_forbidden() -> None:
    payload = {
        "id": uuid4(),
        "competition_id": uuid4(),
        "season_id": uuid4(),
        "stage_id": uuid4(),
        "home_team_id": uuid4(),
        "away_team_id": uuid4(),
        "kickoff_at": datetime(2026, 6, 22, 1, 0),
        "status": "SCHEDULED",
    }
    with pytest.raises(ValidationError):
        FixtureSchema.model_validate(payload)
    payload["kickoff_at"] = NOW
    payload["unexpected"] = "field"
    with pytest.raises(ValidationError):
        FixtureSchema.model_validate(payload)


def test_decimal_odds_line_ranges_and_canonicalization() -> None:
    with pytest.raises(ValidationError):
        OddsObservationSchema.model_validate(
            {
                "id": uuid4(),
                "fixture_id": uuid4(),
                "bookmaker_id": uuid4(),
                "market": "TOTALS",
                "selection": "over",
                "line": Decimal("2.30"),
                "decimal_odds": Decimal("1.50"),
                "suspended": False,
                "live": False,
                "stale": False,
                "provider_updated_at": NOW,
                "captured_at": NOW,
                "raw_label": "O 2.30",
                "settlement_rule": "total_goals",
            }
        )
    assert canonicalize_selection(MarketType.ONE_X_TWO, "1") == "HOME"
    assert canonicalize_selection(MarketType.ASIAN_HANDICAP, "away") == "AWAY"
    assert canonicalize_selection(MarketType.TOTALS, "u") == "UNDER"
    assert canonicalize_selection(MarketType.BTTS, "yes") == "YES"


def test_quarter_lines_and_settlement_outcomes() -> None:
    assert split_quarter_line(Decimal("2.25")) == (Decimal("2"), Decimal("2.5"))
    assert settle_total_goals(3, "OVER", Decimal("2.25")) == SettlementOutcome.WIN
    assert settle_total_goals(2, "OVER", Decimal("2.25")) == SettlementOutcome.HALF_LOSS
    assert settle_total_goals(2, "UNDER", Decimal("2.25")) == SettlementOutcome.HALF_WIN
    assert settle_total_goals(2, "OVER", Decimal("2.0")) == SettlementOutcome.PUSH
    assert settle_asian_handicap(1, 0, "HOME", Decimal("-0.75")) == SettlementOutcome.HALF_WIN
    assert settle_asian_handicap(1, 0, "AWAY", Decimal("0.75")) == SettlementOutcome.HALF_LOSS


def test_raw_and_lock_objects_are_immutable() -> None:
    raw = RawPayloadReference(
        provider="synthetic",
        object_uri="object://payload",
        sha256=DIGEST,
        captured_at=NOW,
    )
    lock = RecommendationLock(
        recommendation_id=uuid4(),
        status=RecommendationStatus.LOCKED,
        locked_at=NOW,
        reason="synthetic",
    )
    with pytest.raises(FrozenInstanceError):
        raw.object_uri = "object://changed"
    with pytest.raises(FrozenInstanceError):
        lock.reason = "changed"
    with pytest.raises(ValueError):
        RawPayloadReference(
            provider="synthetic",
            object_uri="object://payload",
            sha256=DIGEST,
            captured_at=NOW,
            immutable=False,
        )


def test_feature_snapshot_rejects_result_leakage() -> None:
    with pytest.raises(ValueError):
        FeatureSnapshot(fixture_id=uuid4(), as_of_time=NOW, features={"home_goals": Decimal("1")})
    with pytest.raises(ValidationError):
        FeatureSnapshotSchema.model_validate(
            {
                "id": uuid4(),
                "fixture_id": uuid4(),
                "as_of_time": NOW,
                "features": {"final_score": Decimal("2")},
                "layer": "FEATURE",
            }
        )
