from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorPayload(BaseModel):
    request_id: str
    code: str
    message: str


class PageMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int


class FixtureSummary(BaseModel):
    fixture_id: str
    competition_id: str
    competition_name: str
    kickoff_utc: datetime
    kickoff_display: str
    status: str
    home_team_id: str
    away_team_id: str
    lifecycle_state: str
    data_state: str


class FixtureListResponse(BaseModel):
    request_id: str
    meta: PageMeta
    items: list[FixtureSummary]


class FixtureDetailResponse(FixtureSummary):
    request_id: str
    venue: str | None
    bookmaker_count: int
    market_coverage: dict[str, bool]
    forward_decision: str
    provenance: dict[str, str]
    risk_notes: list[str]


class OddsPoint(BaseModel):
    captured_at: datetime
    snapshot_semantics: str
    market: str
    selection: str
    line: str | None
    decimal_odds: str | None
    bookmaker_count: int
    first_seen: bool
    closing: bool


class OddsTimelineResponse(BaseModel):
    request_id: str
    fixture_id: str
    items: list[OddsPoint]


class ProbabilityResponse(BaseModel):
    request_id: str
    fixture_id: str
    probability_type: str
    probabilities: dict[str, float]
    calibrated: bool = False
    source: str
    as_of_time: datetime | None = None
    quality: str


class DataHealthResponse(BaseModel):
    request_id: str
    stale_data_count: int
    provider_status: str
    forward_cycle_age_seconds: int | None
    gate4_progress: dict[str, Any]
    generated_at: datetime


class ProviderStatusResponse(BaseModel):
    request_id: str
    provider: str
    status: str
    remaining_quota: int | None
    credential_status: str
    last_request_status: int | None


class BacktestLatestResponse(BaseModel):
    request_id: str
    status: str
    gate4_national_1x2: str
    metrics: dict[str, Any]


class ForwardHoldoutStatusResponse(BaseModel):
    request_id: str
    status: str
    locks: int
    market_comparable: int
    current_settled_n: int
    target_n: int


class OperationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    status: str
    payload: dict[str, Any]


class OperationListResponse(BaseModel):
    request_id: str
    items: list[OperationItem]
