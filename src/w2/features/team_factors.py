from __future__ import annotations

from dataclasses import dataclass, field
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
    source: str = "team_fixture_history"
    source_group: str = "team_fixture_history"
    is_independent_signal: bool = True
    proxy_of: str | None = None
    collection_status: str = "READY"

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
    source: str = "internal_elo_v1"
    source_group: str = "ratings"
    is_independent_signal: bool = True
    proxy_of: str | None = None
    collection_status: str = "READY"
    artifact_provenance: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class TeamValueSnapshot:
    team_id: str
    observed_at: datetime
    squad_value_eur: float
    source_system: str
    confidence: float
    source_group: str = "squad_value"
    is_independent_signal: bool = True
    proxy_of: str | None = None
    collection_status: str = "READY"
    artifact_provenance: dict[str, str] = field(default_factory=dict)


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
        source=home_last.source if home_last.source == away_last.source else "mixed_history",
        source_group=home_last.source_group
        if home_last.source_group == away_last.source_group
        else "mixed_history",
        is_independent_signal=home_last.is_independent_signal and away_last.is_independent_signal,
        proxy_of=home_last.proxy_of or away_last.proxy_of,
        collection_status=home_last.collection_status
        if home_last.collection_status == away_last.collection_status
        else "MIXED_HISTORY",
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
        source="competition_config",
        source_group="match_importance",
        is_independent_signal=False,
        collection_status="READY",
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
        home_status = _history_collection_status(home_history)
        away_status = _history_collection_status(away_history)
        return FeatureContribution(
            feature_id="F5_RECENT_AH_COVER",
            label="近期赢盘率",
            status=FeatureStatus.INSUFFICIENT_DATA,
            score=None,
            weight=weight,
            reason="MISSING_AH_EVIDENCE",
            coverage_key="settled_ah",
            source="team_fixture_history",
            source_group="team_fixture_history",
            is_independent_signal=False,
            collection_status=home_status if home_status == away_status else "MISSING_AH_EVIDENCE",
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
        source=home[0].source if home[0].source == away[0].source else "mixed_history",
        source_group="team_fixture_history",
        is_independent_signal=True,
        collection_status="READY",
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
            reason="NO_H2H_HISTORY",
            coverage_key="h2h",
            source="api_football_h2h",
            source_group="h2h",
            is_independent_signal=False,
            collection_status="NO_H2H_HISTORY",
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
        source=prior[0].source,
        source_group="h2h",
        is_independent_signal=True,
        collection_status="READY",
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
            source="internal_elo_v1",
            source_group="ratings",
            is_independent_signal=False,
            collection_status="INSUFFICIENT_RATING_HISTORY",
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
            "home_artifact_provenance": home.artifact_provenance,
            "away_artifact_provenance": away.artifact_provenance,
        },
        source=home.source if home.source == away.source else "mixed_ratings",
        source_group=home.source_group
        if home.source_group == away.source_group
        else "mixed_ratings",
        is_independent_signal=home.is_independent_signal and away.is_independent_signal,
        proxy_of=home.proxy_of or away.proxy_of,
        collection_status=home.collection_status
        if home.collection_status == away.collection_status
        else "MIXED_RATINGS",
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
            source="team_value_mapping",
            source_group="squad_value",
            is_independent_signal=False,
            collection_status="MAPPING_MISSING",
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
            "home_artifact_provenance": home.artifact_provenance,
            "away_artifact_provenance": away.artifact_provenance,
        },
        source=home.source_system,
        source_group="squad_value",
        is_independent_signal=True,
        collection_status="READY",
    )


def _history_collection_status(history: list[TeamMatchHistory]) -> str:
    if not history:
        return "NO_HISTORY"
    if any(row.collection_status == "QUOTA_BLOCKED" for row in history):
        return "QUOTA_BLOCKED"
    return "MISSING_AH_EVIDENCE"
