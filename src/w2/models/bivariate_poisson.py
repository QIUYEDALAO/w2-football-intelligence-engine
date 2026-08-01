from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from w2.domain.time import require_utc
from w2.models.dixon_coles import ScoreMatrix, expected_goals_for, one_x_two_from_matrix


@dataclass(frozen=True, kw_only=True)
class BivariatePoissonMatch:
    fixture_id: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    market_probabilities: dict[str, float]
    competition: str
    season: str
    neutral_site: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "kickoff_utc", require_utc(self.kickoff_utc, "kickoff_utc"))
        if abs(sum(self.market_probabilities.values()) - 1.0) > 1e-6:
            raise ValueError("market probabilities must sum to one")

    @property
    def actual_1x2(self) -> str:
        if self.home_goals > self.away_goals:
            return "HOME"
        if self.home_goals == self.away_goals:
            return "DRAW"
        return "AWAY"


@dataclass(frozen=True, kw_only=True)
class BivariatePoissonParameters:
    fitted_match_count: int
    training_cutoff: datetime
    home_goal_baseline: float
    away_goal_baseline: float
    attack: dict[str, float]
    defence: dict[str, float]
    shared_lambda: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "training_cutoff",
            require_utc(self.training_cutoff, "training_cutoff"),
        )


def poisson_pmf(mu: float, goals: int) -> float:
    return math.exp(-mu) * (mu**goals) / math.factorial(goals)


def bivariate_score_probability(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    shared_lambda: float,
) -> float:
    home_component = max(home_mu - shared_lambda, 0.05)
    away_component = max(away_mu - shared_lambda, 0.05)
    shared = max(shared_lambda, 0.0)
    probability = 0.0
    for shared_goals in range(min(home_goals, away_goals) + 1):
        probability += (
            poisson_pmf(home_component, home_goals - shared_goals)
            * poisson_pmf(away_component, away_goals - shared_goals)
            * poisson_pmf(shared, shared_goals)
        )
    return max(probability, 0.0)


def fit_bivariate_poisson(
    matches: list[BivariatePoissonMatch],
    *,
    shared_lambda_grid: tuple[float, ...] | None = None,
) -> BivariatePoissonParameters:
    if len(matches) < 4:
        raise ValueError("bivariate Poisson fit requires at least four historical matches")
    ordered = sorted(matches, key=lambda item: (item.kickoff_utc, item.fixture_id))
    teams = sorted({match.home_team for match in ordered} | {match.away_team for match in ordered})
    home_goal_baseline = max(sum(match.home_goals for match in ordered) / len(ordered), 0.05)
    away_goal_baseline = max(sum(match.away_goals for match in ordered) / len(ordered), 0.05)
    league_goal_baseline = max((home_goal_baseline + away_goal_baseline) / 2, 0.05)

    attack: dict[str, float] = {}
    defence: dict[str, float] = {}
    for team in teams:
        scored: list[int] = []
        conceded: list[int] = []
        for match in ordered:
            if match.home_team == team:
                scored.append(match.home_goals)
                conceded.append(match.away_goals)
            if match.away_team == team:
                scored.append(match.away_goals)
                conceded.append(match.home_goals)
        attack[team] = max((sum(scored) + league_goal_baseline * 2) / (len(scored) + 2), 0.05)
        defence[team] = max(
            (sum(conceded) + league_goal_baseline * 2) / (len(conceded) + 2),
            0.05,
        )
    attack = {team: value / league_goal_baseline for team, value in attack.items()}
    defence = {team: value / league_goal_baseline for team, value in defence.items()}

    candidate_shared = (
        shared_lambda_grid
        if shared_lambda_grid is not None
        else tuple(round(step * 0.02, 2) for step in range(16))
    )
    best_shared = 0.0
    best_loss = float("inf")
    for shared_lambda in candidate_shared:
        loss = 0.0
        for match in ordered:
            home_mu, away_mu = expected_goals_for(
                match.home_team,
                match.away_team,
                attack,
                defence,
                home_goal_baseline,
                away_goal_baseline,
            )
            probability = bivariate_score_probability(
                match.home_goals,
                match.away_goals,
                home_mu,
                away_mu,
                shared_lambda,
            )
            loss += -math.log(max(probability, 1e-12))
        if loss < best_loss:
            best_loss = loss
            best_shared = shared_lambda

    return BivariatePoissonParameters(
        fitted_match_count=len(ordered),
        training_cutoff=ordered[-1].kickoff_utc,
        home_goal_baseline=home_goal_baseline,
        away_goal_baseline=away_goal_baseline,
        attack=attack,
        defence=defence,
        shared_lambda=best_shared,
    )


def predict_score_matrix(
    parameters: BivariatePoissonParameters,
    home_team: str,
    away_team: str,
    *,
    max_goals: int = 10,
) -> ScoreMatrix:
    home_mu, away_mu = expected_goals_for(
        home_team,
        away_team,
        parameters.attack,
        parameters.defence,
        parameters.home_goal_baseline,
        parameters.away_goal_baseline,
    )
    matrix = {
        (home, away): bivariate_score_probability(
            home,
            away,
            home_mu,
            away_mu,
            parameters.shared_lambda,
        )
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    if total <= 0:
        raise ValueError("bivariate Poisson score matrix has no positive probability")
    return {score: probability / total for score, probability in matrix.items()}


def one_x_two_probabilities(
    parameters: BivariatePoissonParameters,
    home_team: str,
    away_team: str,
    *,
    max_goals: int = 10,
) -> dict[str, float]:
    return one_x_two_from_matrix(
        predict_score_matrix(parameters, home_team, away_team, max_goals=max_goals)
    )
