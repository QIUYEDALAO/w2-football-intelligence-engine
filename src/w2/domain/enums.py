from __future__ import annotations

from enum import StrEnum


class DataLayer(StrEnum):
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    FEATURE = "FEATURE"
    PREDICTION_STRATEGY = "PREDICTION_STRATEGY"


class MarketType(StrEnum):
    ONE_X_TWO = "ONE_X_TWO"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    TOTALS = "TOTALS"
    BTTS = "BTTS"


class SettlementOutcome(StrEnum):
    WIN = "WIN"
    HALF_WIN = "HALF_WIN"
    PUSH = "PUSH"
    HALF_LOSS = "HALF_LOSS"
    LOSS = "LOSS"


class RecommendationStatus(StrEnum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class FixtureStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINISHED = "FINISHED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"


class Side(StrEnum):
    HOME = "HOME"
    AWAY = "AWAY"

