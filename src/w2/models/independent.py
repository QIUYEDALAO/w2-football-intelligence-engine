from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from w2.domain.time import require_utc

FORBIDDEN_MARKET_FIELDS = frozenset(
    {
        "odds",
        "market",
        "bookmaker",
        "line",
        "price",
        "probability_market",
        "closing",
    }
)

FEATURE_ALLOWLIST = frozenset(
    {
        "elo_home",
        "elo_away",
        "elo_diff",
        "home_field",
        "neutral_site",
        "competition_importance",
        "opponent_strength",
        "tier",
        "home_rest_days",
        "away_rest_days",
        "home_inactivity_decay",
        "away_inactivity_decay",
        "home_sample_size",
        "away_sample_size",
        "new_team_prior",
        "promoted_team_prior",
        "home_attack_strength",
        "away_attack_strength",
        "home_defence_strength",
        "away_defence_strength",
        "rolling_home_form",
        "rolling_away_form",
        "rolling_home_xg",
        "rolling_away_xg",
    }
)


class ModelFamily(StrEnum):
    TIME_DECAY_ELO = "TIME_DECAY_ELO"
    INDEPENDENT_POISSON = "INDEPENDENT_POISSON"
    HISTORICAL_DIXON_COLES = "HISTORICAL_DIXON_COLES"
    BIVARIATE_POISSON = "BIVARIATE_POISSON"
    NEGATIVE_BINOMIAL = "NEGATIVE_BINOMIAL"
    HIERARCHICAL_ATTACK_DEFENCE = "HIERARCHICAL_ATTACK_DEFENCE"
    TIME_DECAY_ATTACK_DEFENCE = "TIME_DECAY_ATTACK_DEFENCE"
    VALIDATION_ENSEMBLE = "VALIDATION_ENSEMBLE"


@dataclass(frozen=True, kw_only=True)
class MatchRecord:
    fixture_id: str
    competition: str
    season: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    neutral_site: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))

    @property
    def outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "HOME"
        if self.home_goals == self.away_goals:
            return "DRAW"
        return "AWAY"


@dataclass(frozen=True, kw_only=True)
class ModelPrediction:
    fixture_id: str
    model_name: str
    model_version: str
    data_cutoff: datetime
    provenance: dict[str, Any]
    one_x_two: dict[str, float]
    expected_home_goals: float
    expected_away_goals: float
    score_matrix: dict[tuple[int, int], float]
    totals: dict[str, float]
    btts: dict[str, float]
    uncertainty_interval: tuple[float, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_cutoff", require_utc(self.data_cutoff, "data_cutoff"))
        if abs(sum(self.one_x_two.values()) - 1.0) > 1e-9:
            raise ValueError("1X2 probabilities must sum to one")
        if abs(sum(self.score_matrix.values()) - 1.0) > 1e-9:
            raise ValueError("score matrix must be normalized")


def assert_feature_allowlist(features: dict[str, Any]) -> None:
    keys = set(features)
    forbidden = {
        key
        for key in keys
        if key not in FEATURE_ALLOWLIST
        or any(field in key.lower() for field in FORBIDDEN_MARKET_FIELDS)
    }
    if forbidden:
        raise ValueError(f"forbidden independent model features: {sorted(forbidden)}")


def artifact_hash(payload: object) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def poisson_pmf(mu: float, goals: int) -> float:
    return math.exp(-mu) * (mu**goals) / math.factorial(goals)


def normalized_score_matrix(
    home_mu: float,
    away_mu: float,
    max_goals: int = 10,
) -> dict[tuple[int, int], float]:
    matrix = {
        (home, away): poisson_pmf(home_mu, home) * poisson_pmf(away_mu, away)
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    return {score: probability / total for score, probability in matrix.items()}


def prediction_from_lambdas(
    *,
    fixture_id: str,
    model_name: str,
    data_cutoff: datetime,
    home_mu: float,
    away_mu: float,
    provenance: dict[str, Any],
) -> ModelPrediction:
    matrix = normalized_score_matrix(max(home_mu, 0.05), max(away_mu, 0.05))
    one_x_two = {
        "HOME": sum(probability for (home, away), probability in matrix.items() if home > away),
        "DRAW": sum(probability for (home, away), probability in matrix.items() if home == away),
        "AWAY": sum(probability for (home, away), probability in matrix.items() if home < away),
    }
    total_probability = sum(one_x_two.values())
    one_x_two = {key: value / total_probability for key, value in one_x_two.items()}
    totals = {
        "OVER_2_5": sum(
            probability for (home, away), probability in matrix.items() if home + away > 2.5
        ),
        "UNDER_2_5": sum(
            probability for (home, away), probability in matrix.items() if home + away < 2.5
        ),
    }
    btts_yes = sum(
        probability for (home, away), probability in matrix.items() if home > 0 and away > 0
    )
    return ModelPrediction(
        fixture_id=fixture_id,
        model_name=model_name,
        model_version="stage7.v1",
        data_cutoff=data_cutoff,
        provenance=provenance,
        one_x_two=one_x_two,
        expected_home_goals=home_mu,
        expected_away_goals=away_mu,
        score_matrix=matrix,
        totals=totals,
        btts={"YES": btts_yes, "NO": 1.0 - btts_yes},
        uncertainty_interval=(max(home_mu + away_mu - 1.0, 0.0), home_mu + away_mu + 1.0),
    )


@dataclass
class TeamState:
    rating: float = 1500.0
    attack: float = 1.25
    defence: float = 1.25
    matches: int = 0
    last_played: datetime | None = None
    form_points: list[float] | None = None


class AsOfFeatureBuilder:
    def __init__(self, *, decay_days: float = 365.0) -> None:
        self.decay_days = decay_days
        self.states: dict[str, TeamState] = {}

    def features(self, match: MatchRecord) -> dict[str, float | bool | str]:
        home = self.states.get(match.home_team, TeamState())
        away = self.states.get(match.away_team, TeamState())
        home_rest = _rest_days(home.last_played, match.kickoff_utc)
        away_rest = _rest_days(away.last_played, match.kickoff_utc)
        features: dict[str, float | bool | str] = {
            "elo_home": home.rating,
            "elo_away": away.rating,
            "elo_diff": home.rating - away.rating,
            "home_field": 0.0 if match.neutral_site else 1.0,
            "neutral_site": match.neutral_site,
            "competition_importance": _competition_importance(match.competition),
            "opponent_strength": away.rating,
            "tier": (
                "national"
                if "World" in match.competition or "Qualifier" in match.competition
                else "club"
            ),
            "home_rest_days": home_rest,
            "away_rest_days": away_rest,
            "home_inactivity_decay": _inactivity_decay(home_rest),
            "away_inactivity_decay": _inactivity_decay(away_rest),
            "home_sample_size": float(home.matches),
            "away_sample_size": float(away.matches),
            "new_team_prior": float(home.matches == 0 or away.matches == 0),
            "promoted_team_prior": 0.0,
            "home_attack_strength": home.attack,
            "away_attack_strength": away.attack,
            "home_defence_strength": home.defence,
            "away_defence_strength": away.defence,
            "rolling_home_form": _rolling_form(home),
            "rolling_away_form": _rolling_form(away),
            "rolling_home_xg": home.attack,
            "rolling_away_xg": away.attack,
        }
        assert_feature_allowlist(features)
        return features

    def update(self, match: MatchRecord) -> None:
        home = self.states.setdefault(match.home_team, TeamState(form_points=[]))
        away = self.states.setdefault(match.away_team, TeamState(form_points=[]))
        expected_home = 1.0 / (1.0 + 10 ** ((away.rating - home.rating) / 400))
        actual_home = (
            1.0
            if match.home_goals > match.away_goals
            else 0.5
            if match.home_goals == match.away_goals
            else 0.0
        )
        margin = max(abs(match.home_goals - match.away_goals), 1)
        k = 18.0 * math.log1p(margin)
        home.rating += k * (actual_home - expected_home)
        away.rating -= k * (actual_home - expected_home)
        shrink_home = min(home.matches / 20, 1.0)
        shrink_away = min(away.matches / 20, 1.0)
        home.attack = (home.attack * shrink_home + match.home_goals * 0.25) / (shrink_home + 0.25)
        away.attack = (away.attack * shrink_away + match.away_goals * 0.25) / (shrink_away + 0.25)
        home.defence = (home.defence * shrink_home + match.away_goals * 0.25) / (shrink_home + 0.25)
        away.defence = (away.defence * shrink_away + match.home_goals * 0.25) / (shrink_away + 0.25)
        home.matches += 1
        away.matches += 1
        home.last_played = match.kickoff_utc
        away.last_played = match.kickoff_utc
        (home.form_points or []).append(
            3.0 if actual_home == 1.0 else 1.0 if actual_home == 0.5 else 0.0
        )
        (away.form_points or []).append(
            3.0 if actual_home == 0.0 else 1.0 if actual_home == 0.5 else 0.0
        )


def _rest_days(last_played: datetime | None, kickoff: datetime) -> float:
    if last_played is None:
        return 999.0
    return max((kickoff - last_played).days, 0)


def _inactivity_decay(rest_days: float) -> float:
    return min(rest_days / 365.0, 1.0)


def _rolling_form(state: TeamState) -> float:
    points = state.form_points or []
    recent = points[-5:]
    return sum(recent) / max(len(recent) * 3, 1)


def _competition_importance(competition: str) -> float:
    if "World Cup 20" in competition:
        return 1.0
    if "Qualifier" in competition:
        return 0.75
    return 0.60


def predict_from_features(
    fixture_id: str,
    model: ModelFamily,
    features: dict[str, Any],
    data_cutoff: datetime,
) -> ModelPrediction:
    assert_feature_allowlist(features)
    elo_diff = float(features["elo_diff"])
    home_field = float(features["home_field"])
    home_attack = float(features["home_attack_strength"])
    away_attack = float(features["away_attack_strength"])
    home_defence = float(features["home_defence_strength"])
    away_defence = float(features["away_defence_strength"])
    base_home = 1.18 + 0.0013 * elo_diff + 0.15 * home_field
    base_away = 1.08 - 0.0011 * elo_diff
    if model == ModelFamily.TIME_DECAY_ELO:
        home_mu = base_home
        away_mu = base_away
    elif model == ModelFamily.INDEPENDENT_POISSON:
        home_mu = 0.55 * base_home + 0.45 * (home_attack + away_defence) / 2
        away_mu = 0.55 * base_away + 0.45 * (away_attack + home_defence) / 2
    elif model == ModelFamily.HISTORICAL_DIXON_COLES:
        home_mu = base_home * 0.98
        away_mu = base_away * 0.98
    elif model == ModelFamily.BIVARIATE_POISSON:
        home_mu = base_home + 0.05
        away_mu = base_away + 0.05
    elif model == ModelFamily.NEGATIVE_BINOMIAL:
        home_mu = 0.92 * base_home + 0.12
        away_mu = 0.92 * base_away + 0.12
    elif model == ModelFamily.HIERARCHICAL_ATTACK_DEFENCE:
        shrink = min(
            (float(features["home_sample_size"]) + float(features["away_sample_size"])) / 40,
            1.0,
        )
        home_mu = (1 - shrink) * 1.25 + shrink * (home_attack + away_defence) / 2
        away_mu = (1 - shrink) * 1.10 + shrink * (away_attack + home_defence) / 2
    elif model == ModelFamily.TIME_DECAY_ATTACK_DEFENCE:
        home_mu = 0.6 * (home_attack + away_defence) / 2 + 0.4 * base_home
        away_mu = 0.6 * (away_attack + home_defence) / 2 + 0.4 * base_away
    else:
        home_mu = base_home
        away_mu = base_away
    return prediction_from_lambdas(
        fixture_id=fixture_id,
        model_name=model.value,
        data_cutoff=data_cutoff,
        home_mu=max(home_mu, 0.05),
        away_mu=max(away_mu, 0.05),
        provenance={"feature_policy": "W2_FEATURE_POLICY_V1", "odds_free": True},
    )
