from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from w2.competitions.registry import CoverageProfile
from w2.features.asof import latest_as_of
from w2.features.framework import (
    FeatureContext,
    FeatureContribution,
    FeatureStatus,
    TeamSide,
    coverage_or_unavailable,
)


@dataclass(frozen=True, kw_only=True)
class TeamMatchHistory:
    team_id: str
    opponent_id: str
    kickoff_at: datetime
    goals_for: int
    goals_against: int
    opponent_rating: float | None = None
    ah_line: float | None = None
    ah_result: str | None = None

    @property
    def observed_at(self) -> datetime:
        return self.kickoff_at


@dataclass(frozen=True, kw_only=True)
class TeamRatingSnapshot:
    team_id: str
    observed_at: datetime
    elo: float
    attack_strength: float
    defence_strength: float
    form_index: float


@dataclass(frozen=True, kw_only=True)
class TeamValueSnapshot:
    team_id: str
    observed_at: datetime
    squad_value_eur: float
    source_system: str
    confidence: float


@dataclass(frozen=True, kw_only=True)
class MatchImportanceConfig:
    stage_weights: dict[str, float]
    default_weight: float = 0.5

    def score_for_stage(self, stage_id: str | None) -> float:
        if stage_id is None:
            return self.default_weight
        return self.stage_weights.get(stage_id, self.default_weight)


def rest_fitness_factor(
    *,
    context: FeatureContext,
    home_history: list[TeamMatchHistory],
    away_history: list[TeamMatchHistory],
    weight: float = 0.10,
) -> FeatureContribution:
    home_last = latest_as_of(home_history, context.as_of)
    away_last = latest_as_of(away_history, context.as_of)
    if home_last is None or away_last is None:
        return FeatureContribution(
            feature_id="F3_REST_FITNESS",
            label="体能/休息差",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="REST_HISTORY_UNAVAILABLE",
        )
    home_rest = (context.kickoff_at - home_last.kickoff_at).total_seconds() / 86400
    away_rest = (context.kickoff_at - away_last.kickoff_at).total_seconds() / 86400
    diff = home_rest - away_rest
    score = max(min(diff / 4.0, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F3_REST_FITNESS",
        label="体能/休息差",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="REST_DAYS_DIFF_COMPUTED",
        observed_at=max(home_last.kickoff_at, away_last.kickoff_at),
        inputs={"home_rest_days": home_rest, "away_rest_days": away_rest},
    )


def match_importance_factor(
    *,
    context: FeatureContext,
    importance: MatchImportanceConfig,
    weight: float = 0.08,
) -> FeatureContribution:
    score = importance.score_for_stage(context.stage_id)
    return FeatureContribution(
        feature_id="F4_MATCH_IMPORTANCE",
        label="赛事重要性",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        reason="CONFIG_DRIVEN_STAGE_IMPORTANCE",
        risk="重要性来自赛事配置，不从名称字符串推断。",
        inputs={"stage_id": context.stage_id, "importance_score": score},
    )


def recent_ah_cover_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    home_history: list[TeamMatchHistory],
    away_history: list[TeamMatchHistory],
    weight: float = 0.05,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="settled_ah",
        feature_id="F5_RECENT_AH_COVER",
        label="近期赢盘率",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    home = [row for row in home_history if row.kickoff_at <= context.as_of and row.ah_result]
    away = [row for row in away_history if row.kickoff_at <= context.as_of and row.ah_result]
    if not home or not away:
        return FeatureContribution(
            feature_id="F5_RECENT_AH_COVER",
            label="近期赢盘率",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="SETTLED_AH_HISTORY_UNAVAILABLE",
            coverage_key="settled_ah",
        )
    home_rate = sum(1 for row in home if row.ah_result == "COVER") / len(home)
    away_rate = sum(1 for row in away if row.ah_result == "COVER") / len(away)
    score = max(min(home_rate - away_rate, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F5_RECENT_AH_COVER",
        label="近期赢盘率",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="SETTLED_AH_COVER_RATE_DIFF",
        risk="赢盘率是弱信号，低权重，仅作解释因子。",
        coverage_key="settled_ah",
        observed_at=max([row.kickoff_at for row in home + away]),
        inputs={"home_cover_rate": home_rate, "away_cover_rate": away_rate},
    )


def h2h_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    meetings: list[TeamMatchHistory],
    weight: float = 0.05,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="h2h",
        feature_id="F6_H2H",
        label="历史交锋",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    prior = [row for row in meetings if row.kickoff_at <= context.as_of]
    if not prior:
        return FeatureContribution(
            feature_id="F6_H2H",
            label="历史交锋",
            status=FeatureStatus.UNAVAILABLE,
            score=None,
            weight=weight,
            reason="H2H_UNAVAILABLE",
            coverage_key="h2h",
        )
    diff = sum(row.goals_for - row.goals_against for row in prior) / len(prior)
    score = max(min(diff / 2.0, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F6_H2H",
        label="历史交锋",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="INTERNAL_FIXTURE_H2H_DIFF",
        coverage_key="h2h",
        observed_at=max(row.kickoff_at for row in prior),
        inputs={"meeting_count": len(prior), "avg_goal_diff": diff},
    )


def strength_form_factor(
    *,
    context: FeatureContext,
    home_ratings: list[TeamRatingSnapshot],
    away_ratings: list[TeamRatingSnapshot],
    weight: float = 0.18,
) -> FeatureContribution:
    home = latest_as_of(home_ratings, context.as_of)
    away = latest_as_of(away_ratings, context.as_of)
    if home is None or away is None:
        return FeatureContribution(
            feature_id="F7_STRENGTH_FORM",
            label="强度/状态/攻防",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="TEAM_RATING_UNAVAILABLE",
        )
    rating_gap = (home.elo - away.elo) / 300.0
    attack_defence_gap = (home.attack_strength - away.defence_strength) - (
        away.attack_strength - home.defence_strength
    )
    form_gap = home.form_index - away.form_index
    score = max(min(0.55 * rating_gap + 0.30 * attack_defence_gap + 0.15 * form_gap, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F7_STRENGTH_FORM",
        label="强度/状态/攻防",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="OPPONENT_ADJUSTED_STRENGTH_FORM",
        observed_at=max(home.observed_at, away.observed_at),
        inputs={
            "home_elo": home.elo,
            "away_elo": away.elo,
            "attack_defence_gap": attack_defence_gap,
            "form_gap": form_gap,
        },
    )


def squad_value_factor(
    *,
    context: FeatureContext,
    profile: CoverageProfile,
    home_values: list[TeamValueSnapshot],
    away_values: list[TeamValueSnapshot],
    weight: float = 0.06,
) -> FeatureContribution:
    blocked = coverage_or_unavailable(
        profile=profile,
        key="squad_value",
        feature_id="F8_SQUAD_VALUE",
        label="球队身价",
        weight=weight,
    )
    if blocked is not None:
        return blocked
    home = latest_as_of(home_values, context.as_of)
    away = latest_as_of(away_values, context.as_of)
    if home is None or away is None:
        return FeatureContribution(
            feature_id="F8_SQUAD_VALUE",
            label="球队身价",
            status=FeatureStatus.UNAVAILABLE,
            score=None,
            weight=weight,
            reason="VALUE_DATA_UNAVAILABLE",
            coverage_key="squad_value",
        )
    total = max(home.squad_value_eur + away.squad_value_eur, 1.0)
    score = max(min((home.squad_value_eur - away.squad_value_eur) / total, 1.0), -1.0)
    return FeatureContribution(
        feature_id="F8_SQUAD_VALUE",
        label="球队身价",
        status=FeatureStatus.READY,
        score=score,
        weight=weight,
        side=TeamSide.HOME if score > 0 else TeamSide.AWAY if score < 0 else TeamSide.NEUTRAL,
        reason="AS_OF_SQUAD_VALUE_DIFF",
        risk="身价通常已被赔率消化，低权重。",
        coverage_key="squad_value",
        observed_at=max(home.observed_at, away.observed_at),
        inputs={
            "home_value_eur": home.squad_value_eur,
            "away_value_eur": away.squad_value_eur,
            "source_system": home.source_system,
        },
    )
