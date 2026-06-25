from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from w2.domain.time import require_utc

ScoreMatrix = dict[tuple[int, int], float]


@dataclass(frozen=True, kw_only=True)
class DixonColesMatch:
    fixture_id: str
    kickoff_utc: datetime
    home_team: str
    away_team: str
    home_goals: int
    away_goals: int
    market_probabilities: dict[str, float]

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
class DixonColesParameters:
    fitted_match_count: int
    training_cutoff: datetime
    home_goal_baseline: float
    away_goal_baseline: float
    attack: dict[str, float]
    defence: dict[str, float]
    rho: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "training_cutoff",
            require_utc(self.training_cutoff, "training_cutoff"),
        )


def poisson_pmf(mu: float, goals: int) -> float:
    return math.exp(-mu) * (mu**goals) / math.factorial(goals)


def tau_correction(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - home_mu * away_mu * rho
    if home_goals == 0 and away_goals == 1:
        return 1.0 + home_mu * rho
    if home_goals == 1 and away_goals == 0:
        return 1.0 + away_mu * rho
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


def fit_dixon_coles(
    matches: list[DixonColesMatch],
    *,
    rho_grid: tuple[float, ...] | None = None,
) -> DixonColesParameters:
    if len(matches) < 4:
        raise ValueError("Dixon-Coles fit requires at least four historical matches")
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
        # Empirical Bayes shrinkage keeps sparse teams stable without hard-coded strengths.
        attack[team] = max((sum(scored) + league_goal_baseline * 2) / (len(scored) + 2), 0.05)
        defence[team] = max(
            (sum(conceded) + league_goal_baseline * 2) / (len(conceded) + 2),
            0.05,
        )
    attack = {team: value / league_goal_baseline for team, value in attack.items()}
    defence = {team: value / league_goal_baseline for team, value in defence.items()}
    candidate_rhos = (
        rho_grid
        if rho_grid is not None
        else tuple(round(-0.20 + step * 0.01, 2) for step in range(41))
    )

    best_rho = 0.0
    best_loss = float("inf")
    for rho in candidate_rhos:
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
            probability = score_probability(
                match.home_goals,
                match.away_goals,
                home_mu,
                away_mu,
                rho,
            )
            loss += -math.log(max(probability, 1e-12))
        if loss < best_loss:
            best_loss = loss
            best_rho = rho
    return DixonColesParameters(
        fitted_match_count=len(ordered),
        training_cutoff=ordered[-1].kickoff_utc,
        home_goal_baseline=home_goal_baseline,
        away_goal_baseline=away_goal_baseline,
        attack=attack,
        defence=defence,
        rho=best_rho,
    )


def expected_goals_for(
    home_team: str,
    away_team: str,
    attack: dict[str, float],
    defence: dict[str, float],
    home_goal_baseline: float,
    away_goal_baseline: float,
) -> tuple[float, float]:
    home_mu = home_goal_baseline * attack.get(home_team, 1.0) * defence.get(away_team, 1.0)
    away_mu = away_goal_baseline * attack.get(away_team, 1.0) * defence.get(home_team, 1.0)
    return max(home_mu, 0.05), max(away_mu, 0.05)


def score_probability(
    home_goals: int,
    away_goals: int,
    home_mu: float,
    away_mu: float,
    rho: float,
) -> float:
    base = poisson_pmf(home_mu, home_goals) * poisson_pmf(away_mu, away_goals)
    return max(base * tau_correction(home_goals, away_goals, home_mu, away_mu, rho), 0.0)


def predict_score_matrix(
    parameters: DixonColesParameters,
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
        (home, away): score_probability(home, away, home_mu, away_mu, parameters.rho)
        for home in range(max_goals + 1)
        for away in range(max_goals + 1)
    }
    total = sum(matrix.values())
    if total <= 0:
        raise ValueError("Dixon-Coles score matrix has no positive probability")
    return {score: probability / total for score, probability in matrix.items()}


def one_x_two_from_matrix(matrix: ScoreMatrix) -> dict[str, float]:
    probabilities = {
        "HOME": sum(probability for (home, away), probability in matrix.items() if home > away),
        "DRAW": sum(probability for (home, away), probability in matrix.items() if home == away),
        "AWAY": sum(probability for (home, away), probability in matrix.items() if home < away),
    }
    total = sum(probabilities.values())
    return {key: value / total for key, value in probabilities.items()}
