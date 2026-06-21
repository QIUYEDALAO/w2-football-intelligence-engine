from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from w2.domain.enums import DataLayer, FixtureStatus, MarketType, RecommendationStatus
from w2.domain.odds import canonicalize_selection
from w2.domain.time import require_utc


class DomainSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompetitionSchema(DomainSchema):
    id: UUID
    name: str
    country: str | None = None


class SeasonSchema(DomainSchema):
    id: UUID
    competition_id: UUID
    name: str
    start_date: datetime
    end_date: datetime

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value)


class FixtureSchema(DomainSchema):
    id: UUID
    competition_id: UUID
    season_id: UUID
    stage_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    kickoff_at: datetime
    status: FixtureStatus

    @field_validator("kickoff_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "kickoff_at")


class ProviderEntityMappingSchema(DomainSchema):
    id: UUID
    entity_type: str
    entity_id: UUID
    provider: str
    external_id: str
    source: str
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    valid_from: datetime
    valid_to: datetime | None = None

    @field_validator("valid_from", "valid_to")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc(value) if value is not None else value


class RawPayloadReferenceSchema(DomainSchema):
    id: UUID
    provider: str
    object_uri: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    captured_at: datetime
    immutable: bool = True

    @field_validator("captured_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "captured_at")

    @field_validator("immutable")
    @classmethod
    def validate_immutable(cls, value: bool) -> bool:
        if not value:
            raise ValueError("raw payload references are immutable")
        return value


class DataProvenanceSchema(DomainSchema):
    id: UUID
    entity_type: str
    entity_id: UUID
    layer: DataLayer
    source_ref_id: UUID | None = None
    event_time: datetime
    provider_updated_at: datetime | None = None
    ingested_at: datetime
    as_of_time: datetime | None = None
    confirmed_at: datetime | None = None

    @field_validator(
        "event_time",
        "provider_updated_at",
        "ingested_at",
        "as_of_time",
        "confirmed_at",
    )
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        return require_utc(value) if value is not None else value


class OddsObservationSchema(DomainSchema):
    id: UUID
    fixture_id: UUID
    bookmaker_id: UUID
    market: MarketType
    selection: str
    line: Decimal | None = None
    decimal_odds: Decimal = Field(gt=Decimal("1"))
    suspended: bool
    live: bool
    stale: bool
    provider_updated_at: datetime
    captured_at: datetime
    raw_label: str
    canonical_selection: str | None = None
    settlement_rule: str

    @field_validator("line")
    @classmethod
    def validate_line(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value * Decimal("4") != (value * Decimal("4")).to_integral_value():
            raise ValueError("line must use quarter increments")
        return value

    @field_validator("provider_updated_at", "captured_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value)

    @model_validator(mode="after")
    def fill_canonical_selection(self) -> OddsObservationSchema:
        canonical = canonicalize_selection(self.market, self.selection)
        if self.canonical_selection is not None and self.canonical_selection != canonical:
            raise ValueError("canonical_selection mismatch")
        return self.model_copy(update={"canonical_selection": canonical})


class FeatureSnapshotSchema(DomainSchema):
    id: UUID
    fixture_id: UUID
    as_of_time: datetime
    features: dict[str, Decimal]
    layer: DataLayer = DataLayer.FEATURE

    @field_validator("as_of_time")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "as_of_time")

    @field_validator("features")
    @classmethod
    def reject_result_fields(cls, value: dict[str, Decimal]) -> dict[str, Decimal]:
        forbidden = {"home_goals", "away_goals", "result", "settlement", "final_score"}
        if forbidden & set(value):
            raise ValueError("feature schema must not contain result fields")
        return value


class PredictionSchema(DomainSchema):
    id: UUID
    fixture_id: UUID
    model_run_id: UUID
    as_of_time: datetime
    probability: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @field_validator("as_of_time")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "as_of_time")


class RecommendationSchema(DomainSchema):
    id: UUID
    fixture_id: UUID
    prediction_id: UUID | None
    status: RecommendationStatus
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "created_at")


class ResultSchema(DomainSchema):
    id: UUID
    fixture_id: UUID
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)
    confirmed_at: datetime

    @field_validator("confirmed_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        return require_utc(value, "confirmed_at")


def schema_extra_forbid(schema: type[BaseModel], payload: dict[str, Any]) -> bool:
    schema.model_validate({**payload, "unexpected": "field"})
    return True

