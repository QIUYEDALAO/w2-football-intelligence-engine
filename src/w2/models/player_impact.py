from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

PlayerImpactStatus = Literal["READY", "INSUFFICIENT", "NOT_SUPPORTED"]


@dataclass(frozen=True, kw_only=True)
class PlayerImpactEstimate:
    status: PlayerImpactStatus
    model_version: str
    home_starting_strength: float | None
    away_starting_strength: float | None
    net_adjustment: float
    starters_mapped_home: int
    starters_mapped_away: int
    source: str | None
    feature_as_of: datetime | None
    fallback_reason: str | None

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["feature_as_of"] = (
            self.feature_as_of.isoformat() if self.feature_as_of is not None else None
        )
        return payload


def unsupported_player_impact() -> PlayerImpactEstimate:
    return PlayerImpactEstimate(
        status="NOT_SUPPORTED",
        model_version="w2.player_impact.not_supported.v1",
        home_starting_strength=None,
        away_starting_strength=None,
        net_adjustment=0.0,
        starters_mapped_home=0,
        starters_mapped_away=0,
        source=None,
        feature_as_of=None,
        fallback_reason="PLAYER_IMPACT_MODEL_NOT_VALIDATED",
    )
