from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from uuid import UUID, uuid4

from w2.domain.enums import DataLayer, FixtureStatus, MarketType, RecommendationStatus
from w2.domain.odds import canonicalize_selection
from w2.domain.time import require_utc


def new_id() -> UUID:
    return uuid4()


@dataclass(frozen=True, kw_only=True)
class Entity:
    id: UUID = field(default_factory=new_id)


@dataclass(frozen=True, kw_only=True)
class Competition(Entity):
    name: str
    country: str | None = None


@dataclass(frozen=True, kw_only=True)
class Season(Entity):
    competition_id: UUID
    name: str
    start_date: datetime
    end_date: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_date", require_utc(self.start_date, "start_date"))
        object.__setattr__(self, "end_date", require_utc(self.end_date, "end_date"))


@dataclass(frozen=True, kw_only=True)
class Stage(Entity):
    season_id: UUID
    name: str
    order_index: int


@dataclass(frozen=True, kw_only=True)
class Team(Entity):
    name: str
    country: str | None = None


@dataclass(frozen=True, kw_only=True)
class Player(Entity):
    name: str
    birth_date: datetime | None = None

    def __post_init__(self) -> None:
        if self.birth_date is not None:
            object.__setattr__(self, "birth_date", require_utc(self.birth_date, "birth_date"))


@dataclass(frozen=True, kw_only=True)
class Squad(Entity):
    team_id: UUID
    player_id: UUID
    season_id: UUID
    shirt_number: int | None = None


@dataclass(frozen=True, kw_only=True)
class Venue(Entity):
    name: str
    city: str | None = None


@dataclass(frozen=True, kw_only=True)
class Referee(Entity):
    name: str
    country: str | None = None


@dataclass(frozen=True, kw_only=True)
class Fixture(Entity):
    competition_id: UUID
    season_id: UUID
    stage_id: UUID
    home_team_id: UUID
    away_team_id: UUID
    kickoff_at: datetime
    status: FixtureStatus = FixtureStatus.SCHEDULED
    venue_id: UUID | None = None
    referee_id: UUID | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_at", require_utc(self.kickoff_at, "kickoff_at"))


@dataclass(frozen=True, kw_only=True)
class Bookmaker(Entity):
    name: str


@dataclass(frozen=True, kw_only=True)
class Market(Entity):
    fixture_id: UUID
    market: MarketType
    settlement_rule: str


@dataclass(frozen=True, kw_only=True)
class OddsObservation(Entity):
    fixture_id: UUID
    bookmaker_id: UUID
    market: MarketType
    selection: str
    line: Decimal | None
    decimal_odds: Decimal
    suspended: bool
    live: bool
    stale: bool
    provider_updated_at: datetime
    captured_at: datetime
    raw_label: str
    settlement_rule: str
    canonical_selection: str = field(init=False)

    def __post_init__(self) -> None:
        if self.decimal_odds <= Decimal("1"):
            raise ValueError("decimal_odds must be greater than 1")
        if (
            self.line is not None
            and self.line * Decimal("4") != (self.line * Decimal("4")).to_integral_value()
        ):
            raise ValueError("line must use quarter increments")
        object.__setattr__(
            self,
            "canonical_selection",
            canonicalize_selection(self.market, self.selection),
        )
        object.__setattr__(
            self,
            "provider_updated_at",
            require_utc(self.provider_updated_at, "provider_updated_at"),
        )
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True, kw_only=True)
class ProviderEntityMapping(Entity):
    entity_type: str
    entity_id: UUID
    provider: str
    external_id: str
    source: str
    confidence: Decimal
    valid_from: datetime
    valid_to: datetime | None = None

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "valid_from", require_utc(self.valid_from, "valid_from"))
        if self.valid_to is not None:
            object.__setattr__(self, "valid_to", require_utc(self.valid_to, "valid_to"))


@dataclass(frozen=True, kw_only=True)
class RawPayloadReference(Entity):
    provider: str
    object_uri: str
    sha256: str
    captured_at: datetime
    immutable: bool = True

    def __post_init__(self) -> None:
        if not self.immutable:
            raise ValueError("raw payload references are immutable")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character digest")
        object.__setattr__(self, "captured_at", require_utc(self.captured_at, "captured_at"))


@dataclass(frozen=True, kw_only=True)
class DataProvenance(Entity):
    entity_type: str
    entity_id: UUID
    layer: DataLayer
    source_ref_id: UUID | None
    event_time: datetime
    provider_updated_at: datetime | None
    ingested_at: datetime
    as_of_time: datetime | None = None
    confirmed_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in ("event_time", "ingested_at"):
            object.__setattr__(self, field_name, require_utc(getattr(self, field_name), field_name))
        for field_name in ("provider_updated_at", "as_of_time", "confirmed_at"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, require_utc(value, field_name))


@dataclass(frozen=True, kw_only=True)
class Lineup(Entity):
    fixture_id: UUID
    team_id: UUID
    player_id: UUID
    confirmed_at: datetime | None

    def __post_init__(self) -> None:
        if self.confirmed_at is not None:
            object.__setattr__(self, "confirmed_at", require_utc(self.confirmed_at, "confirmed_at"))


@dataclass(frozen=True, kw_only=True)
class Injury(Entity):
    player_id: UUID
    team_id: UUID
    status: str
    as_of_time: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_time", require_utc(self.as_of_time, "as_of_time"))


@dataclass(frozen=True, kw_only=True)
class Suspension(Injury):
    pass


@dataclass(frozen=True, kw_only=True)
class WeatherObservation(Entity):
    fixture_id: UUID
    observed_at: datetime
    temperature_c: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "observed_at", require_utc(self.observed_at, "observed_at"))


@dataclass(frozen=True, kw_only=True)
class TeamRating(Entity):
    team_id: UUID
    as_of_time: datetime
    rating: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_time", require_utc(self.as_of_time, "as_of_time"))


@dataclass(frozen=True, kw_only=True)
class FeatureSnapshot(Entity):
    fixture_id: UUID
    as_of_time: datetime
    features: Mapping[str, Decimal]
    layer: DataLayer = DataLayer.FEATURE

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of_time", require_utc(self.as_of_time, "as_of_time"))
        forbidden = {"home_goals", "away_goals", "result", "settlement", "final_score"}
        if forbidden & set(self.features):
            raise ValueError("pre-match feature snapshots must not contain result fields")
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))


@dataclass(frozen=True, kw_only=True)
class ModelRun(Entity):
    name: str
    run_time: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_time", require_utc(self.run_time, "run_time"))


@dataclass(frozen=True, kw_only=True)
class Prediction(Entity):
    fixture_id: UUID
    model_run_id: UUID
    as_of_time: datetime
    probability: Decimal

    def __post_init__(self) -> None:
        if not Decimal("0") <= self.probability <= Decimal("1"):
            raise ValueError("probability must be between 0 and 1")
        object.__setattr__(self, "as_of_time", require_utc(self.as_of_time, "as_of_time"))


@dataclass(frozen=True, kw_only=True)
class Recommendation(Entity):
    fixture_id: UUID
    prediction_id: UUID | None
    status: RecommendationStatus
    created_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "created_at", require_utc(self.created_at, "created_at"))


@dataclass(frozen=True, kw_only=True)
class RecommendationLock(Entity):
    recommendation_id: UUID
    status: RecommendationStatus
    locked_at: datetime
    reason: str

    def __post_init__(self) -> None:
        if self.status != RecommendationStatus.LOCKED:
            raise ValueError("RecommendationLock only represents LOCKED state")
        object.__setattr__(self, "locked_at", require_utc(self.locked_at, "locked_at"))


@dataclass(frozen=True, kw_only=True)
class Result(Entity):
    fixture_id: UUID
    home_goals: int
    away_goals: int
    confirmed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "confirmed_at", require_utc(self.confirmed_at, "confirmed_at"))


@dataclass(frozen=True, kw_only=True)
class Settlement(Entity):
    recommendation_id: UUID
    result_id: UUID
    outcome: str
    settled_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "settled_at", require_utc(self.settled_at, "settled_at"))


@dataclass(frozen=True, kw_only=True)
class AuditEvent(Entity):
    entity_type: str
    entity_id: UUID
    action: str
    occurred_at: datetime
    actor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", require_utc(self.occurred_at, "occurred_at"))
