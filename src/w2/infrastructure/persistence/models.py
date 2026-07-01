from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from w2.infrastructure.database import Base


def uuid_str() -> str:
    return str(uuid4())


class CompetitionModel(Base):
    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(128))

    seasons: Mapped[list[SeasonModel]] = relationship(back_populates="competition")


class SeasonModel(Base):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("competition_id", "name", name="uq_season_competition_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    competition: Mapped[CompetitionModel] = relationship(back_populates="seasons")
    stages: Mapped[list[StageModel]] = relationship(back_populates="season")


class StageModel(Base):
    __tablename__ = "stages"
    __table_args__ = (UniqueConstraint("season_id", "name", name="uq_stage_season_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    season_id: Mapped[str] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    season: Mapped[SeasonModel] = relationship(back_populates="stages")


class TeamModel(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(128))


class PlayerModel(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    birth_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SquadModel(Base):
    __tablename__ = "squads"
    __table_args__ = (
        UniqueConstraint("team_id", "player_id", "season_id", name="uq_squad_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    season_id: Mapped[str] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    shirt_number: Mapped[int | None] = mapped_column(Integer)


class VenueModel(Base):
    __tablename__ = "venues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(128))


class RefereeModel(Base):
    __tablename__ = "referees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(128))


class FixtureModel(Base):
    __tablename__ = "fixtures"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "home_team_id",
            "away_team_id",
            "kickoff_at",
            name="uq_fixture_identity",
        ),
        Index("ix_fixtures_kickoff", "kickoff_at"),
        Index("ix_fixtures_competition_kickoff", "competition_id", "kickoff_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    competition_id: Mapped[str] = mapped_column(ForeignKey("competitions.id"), nullable=False)
    season_id: Mapped[str] = mapped_column(ForeignKey("seasons.id"), nullable=False)
    stage_id: Mapped[str] = mapped_column(ForeignKey("stages.id"), nullable=False)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    venue_id: Mapped[str | None] = mapped_column(ForeignKey("venues.id"))
    referee_id: Mapped[str | None] = mapped_column(ForeignKey("referees.id"))
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    odds_observations: Mapped[list[OddsObservationModel]] = relationship(back_populates="fixture")
    result: Mapped[ResultModel | None] = relationship(back_populates="fixture")


class BookmakerModel(Base):
    __tablename__ = "bookmakers"
    __table_args__ = (UniqueConstraint("name", name="uq_bookmaker_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class MarketModel(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("fixture_id", "market", "settlement_rule", name="uq_market_fixture_rule"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement_rule: Mapped[str] = mapped_column(String(128), nullable=False)


class OddsObservationModel(Base):
    __tablename__ = "odds_observations"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "bookmaker_id",
            "market",
            "canonical_selection",
            "line",
            "provider_updated_at",
            "captured_at",
            name="uq_odds_observation_idempotency",
        ),
        Index("ix_odds_provider_updated_at", "provider_updated_at"),
        Index("ix_odds_captured_at", "captured_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    bookmaker_id: Mapped[str] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    market: Mapped[str] = mapped_column(String(64), nullable=False)
    selection: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    decimal_odds: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    live: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False)
    provider_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_label: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_selection: Mapped[str] = mapped_column(String(64), nullable=False)
    settlement_rule: Mapped[str] = mapped_column(String(128), nullable=False)

    fixture: Mapped[FixtureModel] = relationship(back_populates="odds_observations")


class ProviderEntityMappingModel(Base):
    __tablename__ = "provider_entity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "entity_type",
            "external_id",
            "valid_from",
            name="uq_provider_external_identity",
        ),
        Index("ix_mapping_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawPayloadReferenceModel(Base):
    __tablename__ = "raw_payload_references"
    __table_args__ = (
        UniqueConstraint("provider", "object_uri", "sha256", name="uq_raw_payload_reference"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    object_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DataProvenanceModel(Base):
    __tablename__ = "data_provenance"
    __table_args__ = (
        Index("ix_provenance_event_time", "event_time"),
        Index("ix_provenance_as_of_time", "as_of_time"),
        Index("ix_provenance_layer", "layer"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_id: Mapped[str | None] = mapped_column(ForeignKey("raw_payload_references.id"))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    as_of_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LineupModel(Base):
    __tablename__ = "lineups"
    __table_args__ = (
        UniqueConstraint("fixture_id", "team_id", "player_id", name="uq_lineup_player"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InjuryModel(Base):
    __tablename__ = "injuries"
    __table_args__ = (Index("ix_injuries_as_of_time", "as_of_time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SuspensionModel(Base):
    __tablename__ = "suspensions"
    __table_args__ = (Index("ix_suspensions_as_of_time", "as_of_time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeatherObservationModel(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (Index("ix_weather_observed_at", "observed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))


class TeamRatingModel(Base):
    __tablename__ = "team_ratings"
    __table_args__ = (
        UniqueConstraint("team_id", "as_of_time", name="uq_team_rating_as_of"),
        Index("ix_team_ratings_as_of_time", "as_of_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rating: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class FeatureSnapshotModel(Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint("fixture_id", "as_of_time", name="uq_feature_fixture_as_of"),
        Index("ix_feature_snapshots_as_of_time", "as_of_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    layer: Mapped[str] = mapped_column(String(32), nullable=False)


class ModelRunModel(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    run_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PredictionModel(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "model_run_id",
            "as_of_time",
            name="uq_prediction_fixture_model_as_of",
        ),
        Index("ix_predictions_as_of_time", "as_of_time"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    model_run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), nullable=False)
    as_of_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    probability: Mapped[Decimal] = mapped_column(Numeric(8, 7), nullable=False)


class RecommendationModel(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    prediction_id: Mapped[str | None] = mapped_column(ForeignKey("predictions.id"))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    settlement: Mapped[SettlementModel | None] = relationship(back_populates="recommendation")
    lock: Mapped[RecommendationLockModel | None] = relationship(back_populates="recommendation")


class RecommendationLockModel(Base):
    __tablename__ = "recommendation_locks"
    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_recommendation_lock_once"),
        Index("ix_recommendation_locks_fixture", "fixture_id"),
        Index("ix_recommendation_locks_as_of", "as_of"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    fixture_id: Mapped[str | None] = mapped_column(ForeignKey("fixtures.id"))
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    kickoff_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tier: Mapped[str | None] = mapped_column(String(32))
    pick_side: Mapped[str | None] = mapped_column(String(32))
    pick_line: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    our_fair_ah: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    market_ah: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    home_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    away_price: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    devig_method: Mapped[str | None] = mapped_column(String(64))
    snapshot_payload_json: Mapped[Any | None] = mapped_column(JSON)
    snapshot_payload_hash: Mapped[str | None] = mapped_column(String(64))
    release_sha: Mapped[str | None] = mapped_column(String(64))
    market_timeline_json: Mapped[Any | None] = mapped_column(JSON)
    ah_settlement_distribution_json: Mapped[Any | None] = mapped_column(JSON)
    team_score_home: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    team_score_away: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    factors_json: Mapped[Any | None] = mapped_column(JSON)
    independent_signal_count: Mapped[int | None] = mapped_column(Integer)
    signal_groups: Mapped[Any | None] = mapped_column(JSON)
    missing_sources: Mapped[Any | None] = mapped_column(JSON)
    scoreline_top3_json: Mapped[Any | None] = mapped_column(JSON)
    lineups_status: Mapped[str | None] = mapped_column(String(32))
    xg_status: Mapped[str | None] = mapped_column(String(32))
    model_version: Mapped[str | None] = mapped_column(String(128))
    calibration_version: Mapped[str | None] = mapped_column(String(128))
    coherent: Mapped[bool | None] = mapped_column(Boolean)
    reverse_value: Mapped[bool | None] = mapped_column(Boolean)
    data_profile: Mapped[str | None] = mapped_column(String(64))
    reproducible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legacy_marker_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    snapshot_schema_version: Mapped[str | None] = mapped_column(String(64))

    recommendation: Mapped[RecommendationModel] = relationship(back_populates="lock")
    settlements: Mapped[list[SettlementModel]] = relationship(back_populates="lock")


class ResultModel(Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("fixture_id", name="uq_result_fixture"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    fixture_id: Mapped[str] = mapped_column(ForeignKey("fixtures.id"), nullable=False)
    home_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    away_goals: Mapped[int] = mapped_column(Integer, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    fixture: Mapped[FixtureModel] = relationship(back_populates="result")
    settlements: Mapped[list[SettlementModel]] = relationship(back_populates="result")


class SettlementModel(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("recommendation_id", "result_id", name="uq_settlement_once"),
        Index("ix_settlements_lock", "lock_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), nullable=False)
    lock_id: Mapped[str | None] = mapped_column(ForeignKey("recommendation_locks.id"))
    result_id: Mapped[str] = mapped_column(ForeignKey("results.id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    matched_recommendation: Mapped[bool | None] = mapped_column(Boolean)
    tier: Mapped[str | None] = mapped_column(String(32))
    movement_pattern: Mapped[str | None] = mapped_column(String(64))

    recommendation: Mapped[RecommendationModel] = relationship(back_populates="settlement")
    lock: Mapped[RecommendationLockModel | None] = relationship(back_populates="settlements")
    result: Mapped[ResultModel] = relationship(back_populates="settlements")


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_occurred_at", "occurred_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)


def _prevent_update_delete(_mapper: Any, _connection: Any, target: Any) -> None:
    raise ValueError(f"{target.__class__.__name__} is append-only or immutable")


for immutable_model in (
    RawPayloadReferenceModel,
    RecommendationLockModel,
    SettlementModel,
    AuditEventModel,
):
    event.listen(immutable_model, "before_update", _prevent_update_delete)
    event.listen(immutable_model, "before_delete", _prevent_update_delete)
