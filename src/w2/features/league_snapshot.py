from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from w2.features.live_factors import TeamXgSnapshot
from w2.features.team_factors import TeamRatingSnapshot, TeamValueSnapshot
from w2.models.r4_1_features import r4_1_strength_features_from_rolling

LEAGUE_FEATURE_SNAPSHOT_SCHEMA = "w2.league_feature_snapshot.v1"


@dataclass(frozen=True, kw_only=True)
class LeagueFeatureSnapshot:
    competition_id: str
    team_id: str
    feature_as_of: datetime
    rolling_xg_for: float
    rolling_xg_against: float
    rolling_goals_for: float
    rolling_goals_against: float
    opponent_adjusted_strength: float
    opponent_adjusted_defence: float
    elo: float | None
    squad_value: float | None
    rest_days: float | None
    sample_count: int
    source: str
    freshness: str
    schema_version: str = LEAGUE_FEATURE_SNAPSHOT_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["feature_as_of"] = _iso_utc(self.feature_as_of)
        return payload


def build_league_feature_pair(
    *,
    competition_id: str,
    kickoff_utc: datetime,
    home_xg: TeamXgSnapshot,
    away_xg: TeamXgSnapshot,
    home_rating: TeamRatingSnapshot | None,
    away_rating: TeamRatingSnapshot | None,
    home_value: TeamValueSnapshot | None = None,
    away_value: TeamValueSnapshot | None = None,
    home_sample_count: int = 0,
    away_sample_count: int = 0,
    home_rolling_goals_for: float | None = None,
    home_rolling_goals_against: float | None = None,
    away_rolling_goals_for: float | None = None,
    away_rolling_goals_against: float | None = None,
    home_rest_days: float | None = None,
    away_rest_days: float | None = None,
) -> tuple[LeagueFeatureSnapshot, LeagueFeatureSnapshot] | None:
    kickoff = _aware_utc(kickoff_utc)
    observed = [home_xg.observed_at, away_xg.observed_at]
    observed.extend(
        value.observed_at
        for value in (home_rating, away_rating, home_value, away_value)
        if value is not None
    )
    if any(_aware_utc(value) > kickoff for value in observed):
        return None
    strengths = r4_1_strength_features_from_rolling(
        home_for=home_xg.xg_for,
        home_against=home_xg.xg_against,
        away_for=away_xg.xg_for,
        away_against=away_xg.xg_against,
    )
    source = _source(home_rating, away_rating)
    return (
        LeagueFeatureSnapshot(
            competition_id=competition_id,
            team_id=home_xg.team_id,
            feature_as_of=max(_aware_utc(value) for value in observed),
            rolling_xg_for=home_xg.xg_for,
            rolling_xg_against=home_xg.xg_against,
            rolling_goals_for=_number(home_rolling_goals_for, home_xg.goals_for),
            rolling_goals_against=_number(home_rolling_goals_against, home_xg.goals_against),
            opponent_adjusted_strength=strengths["home_attack_strength"],
            opponent_adjusted_defence=strengths["home_defence_strength"],
            elo=home_rating.elo if home_rating is not None else None,
            squad_value=home_value.squad_value_eur if home_value is not None else None,
            rest_days=home_rest_days,
            sample_count=home_sample_count,
            source=source,
            freshness="AS_OF_MATERIALIZED",
        ),
        LeagueFeatureSnapshot(
            competition_id=competition_id,
            team_id=away_xg.team_id,
            feature_as_of=max(_aware_utc(value) for value in observed),
            rolling_xg_for=away_xg.xg_for,
            rolling_xg_against=away_xg.xg_against,
            rolling_goals_for=_number(away_rolling_goals_for, away_xg.goals_for),
            rolling_goals_against=_number(away_rolling_goals_against, away_xg.goals_against),
            opponent_adjusted_strength=strengths["away_attack_strength"],
            opponent_adjusted_defence=strengths["away_defence_strength"],
            elo=away_rating.elo if away_rating is not None else None,
            squad_value=away_value.squad_value_eur if away_value is not None else None,
            rest_days=away_rest_days,
            sample_count=away_sample_count,
            source=source,
            freshness="AS_OF_MATERIALIZED",
        ),
    )


def _source(
    home_rating: TeamRatingSnapshot | None,
    away_rating: TeamRatingSnapshot | None,
) -> str:
    rating_sources = {
        value.source for value in (home_rating, away_rating) if value is not None
    }
    rating_label = next(iter(rating_sources)) if len(rating_sources) == 1 else "mixed_ratings"
    return f"rolling_xg+{rating_label}"


def _number(value: float | None, fallback: int) -> float:
    return float(value) if value is not None else float(fallback)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("feature timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _iso_utc(value: datetime) -> str:
    return _aware_utc(value).isoformat().replace("+00:00", "Z")
