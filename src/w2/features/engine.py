from __future__ import annotations

from dataclasses import dataclass, field

from w2.competitions.registry import CompetitionRegistry
from w2.features.framework import (
    FeatureContext,
    FeatureContribution,
    FeatureSet,
    FeatureStatus,
    require_competition_enabled,
)
from w2.features.live_factors import TeamXgSnapshot, true_xg_factor
from w2.features.market_factors import (
    BookmakerQuote,
    bookmaker_divergence_factor,
    market_movement_factor,
)
from w2.features.team_factors import (
    MatchImportanceConfig,
    TeamMatchHistory,
    TeamRatingSnapshot,
    TeamValueSnapshot,
    h2h_factor,
    match_importance_factor,
    recent_ah_cover_factor,
    rest_fitness_factor,
    squad_value_factor,
    strength_form_factor,
)
from w2.markets.movement import MarketSnapshot


@dataclass(frozen=True, kw_only=True)
class FeatureInputs:
    market_snapshots: list[MarketSnapshot] = field(default_factory=list)
    bookmaker_quotes: list[BookmakerQuote] = field(default_factory=list)
    home_history: list[TeamMatchHistory] = field(default_factory=list)
    away_history: list[TeamMatchHistory] = field(default_factory=list)
    h2h_meetings: list[TeamMatchHistory] = field(default_factory=list)
    home_ratings: list[TeamRatingSnapshot] = field(default_factory=list)
    away_ratings: list[TeamRatingSnapshot] = field(default_factory=list)
    home_values: list[TeamValueSnapshot] = field(default_factory=list)
    away_values: list[TeamValueSnapshot] = field(default_factory=list)
    home_xg: list[TeamXgSnapshot] = field(default_factory=list)
    away_xg: list[TeamXgSnapshot] = field(default_factory=list)


def build_feature_set(
    *,
    context: FeatureContext,
    inputs: FeatureInputs,
    registry: CompetitionRegistry | None = None,
) -> FeatureSet:
    resolved_registry = registry or CompetitionRegistry()
    coverage = require_competition_enabled(context, resolved_registry)
    if isinstance(coverage, FeatureContribution):
        return FeatureSet(
            fixture_id=context.fixture_id,
            competition_id=context.competition_id,
            as_of=context.as_of,
            contributions=(coverage,),
            status=FeatureStatus.NOT_WHITELISTED,
        )
    importance = load_importance_config(context.competition_id, registry=resolved_registry)
    contributions = (
        market_movement_factor(
            context=context,
            profile=coverage,
            snapshots=inputs.market_snapshots,
        ),
        bookmaker_divergence_factor(
            context=context,
            profile=coverage,
            quotes=inputs.bookmaker_quotes,
        ),
        rest_fitness_factor(
            context=context,
            home_history=inputs.home_history,
            away_history=inputs.away_history,
        ),
        match_importance_factor(context=context, importance=importance),
        recent_ah_cover_factor(
            context=context,
            profile=coverage,
            home_history=inputs.home_history,
            away_history=inputs.away_history,
        ),
        h2h_factor(context=context, profile=coverage, meetings=inputs.h2h_meetings),
        strength_form_factor(
            context=context,
            home_ratings=inputs.home_ratings,
            away_ratings=inputs.away_ratings,
        ),
        squad_value_factor(
            context=context,
            profile=coverage,
            home_values=inputs.home_values,
            away_values=inputs.away_values,
        ),
        true_xg_factor(
            context=context,
            profile=coverage,
            home_xg=inputs.home_xg,
            away_xg=inputs.away_xg,
        ),
    )
    status = (
        FeatureStatus.READY
        if any(item.status == FeatureStatus.READY for item in contributions)
        else FeatureStatus.INSUFFICIENT_DATA
    )
    return FeatureSet(
        fixture_id=context.fixture_id,
        competition_id=context.competition_id,
        as_of=context.as_of,
        contributions=contributions,
        status=status,
    )


def load_importance_config(
    competition_id: str,
    *,
    registry: CompetitionRegistry | None = None,
) -> MatchImportanceConfig:
    entry = (registry or CompetitionRegistry()).entries().get(competition_id)
    profile = entry.profile_payload.get("importance_profile") if entry else None
    if not isinstance(profile, dict):
        return MatchImportanceConfig(stage_weights={}, default_weight=0.5)
    raw_weights = profile.get("stage_weights")
    weights: dict[str, float] = {}
    if isinstance(raw_weights, dict):
        weights = {
            str(key): float(value)
            for key, value in raw_weights.items()
            if isinstance(value, int | float)
        }
    default = profile.get("default_weight", 0.5)
    return MatchImportanceConfig(
        stage_weights=weights,
        default_weight=float(default) if isinstance(default, int | float) else 0.5,
    )
