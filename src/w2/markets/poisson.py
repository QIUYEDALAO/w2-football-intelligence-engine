from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import exp, factorial, log

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap

ScoreMatrix = dict[tuple[int, int], float]


def poisson_pmf(mu: float, goals: int) -> float:
    return exp(-mu) * (mu**goals) / factorial(goals)


def total_under_probability(mu: float, line: Decimal, max_goals: int = 12) -> float:
    threshold = float(line)
    probability = 0.0
    for goals in range(max_goals + 1):
        if goals < threshold:
            probability += poisson_pmf(mu, goals)
        elif goals == threshold:
            probability += 0.5 * poisson_pmf(mu, goals)
    return min(max(probability, 0.0), 1.0)


@dataclass(frozen=True, kw_only=True)
class OULadderFit:
    mu: float
    total_error: float
    residuals: dict[str, float]
    status: str
    fallback_reason: str | None = None


def fit_total_goals_mu(line_probabilities: dict[Decimal, float]) -> OULadderFit:
    if not line_probabilities:
        return OULadderFit(
            mu=2.50,
            total_error=0.0,
            residuals={},
            status="FALLBACK",
            fallback_reason="NO_OU_LINES",
        )
    best_mu = 2.50
    best_error = float("inf")
    best_residuals: dict[str, float] = {}
    for step in range(50, 651):
        mu = step / 100
        residuals = {
            str(line): total_under_probability(mu, line) - probability
            for line, probability in line_probabilities.items()
        }
        error = sum(value * value for value in residuals.values())
        if error < best_error:
            best_mu = mu
            best_error = error
            best_residuals = residuals
    status = "READY" if best_error <= 0.25 else "WATCH_ONLY"
    return OULadderFit(mu=best_mu, total_error=best_error, residuals=best_residuals, status=status)


def median_line_mu(line_probabilities: dict[Decimal, float]) -> float:
    if not line_probabilities:
        return 2.50
    line, _ = min(line_probabilities.items(), key=lambda item: abs(item[1] - 0.5))
    return float(line)


@dataclass(frozen=True, kw_only=True)
class BaselineOutput:
    lambda_home: float
    lambda_away: float
    score_matrix: ScoreMatrix
    one_x_two: dict[str, float]
    totals: dict[str, float]
    asian_handicap: dict[str, float]
    btts: dict[str, float]
    residual: float


class DixonColesBaseline:
    def __init__(self, *, max_goals: int = 10, rho_reference: float = 0.0) -> None:
        self.max_goals = max_goals
        self.rho_reference = rho_reference

    def build(
        self,
        *,
        one_x_two_probabilities: dict[str, float],
        total_mu: float | Decimal,
        asian_line: Decimal = Decimal("0"),
        total_line: Decimal = Decimal("2.5"),
    ) -> BaselineOutput:
        total_mu_value = float(total_mu)
        home = max(one_x_two_probabilities.get("HOME", 0.33), 1e-6)
        away = max(one_x_two_probabilities.get("AWAY", 0.33), 1e-6)
        supremacy = max(
            min(log(home / away) * 0.75, total_mu_value - 0.10),
            -total_mu_value + 0.10,
        )
        lambda_home = max((total_mu_value + supremacy) / 2, 0.05)
        lambda_away = max((total_mu_value - supremacy) / 2, 0.05)
        matrix: ScoreMatrix = {}
        for home_goals in range(self.max_goals + 1):
            for away_goals in range(self.max_goals + 1):
                probability = poisson_pmf(lambda_home, home_goals) * poisson_pmf(
                    lambda_away,
                    away_goals,
                )
                if self.rho_reference and home_goals <= 1 and away_goals <= 1:
                    probability *= 1 + self.rho_reference
                matrix[(home_goals, away_goals)] = max(probability, 0.0)
        total_probability = sum(matrix.values())
        matrix = {score: probability / total_probability for score, probability in matrix.items()}
        one_x_two = {
            "HOME": sum(p for (h, a), p in matrix.items() if h > a),
            "DRAW": sum(p for (h, a), p in matrix.items() if h == a),
            "AWAY": sum(p for (h, a), p in matrix.items() if h < a),
        }
        totals = {
            "OVER": sum(p for (h, a), p in matrix.items() if Decimal(h + a) > total_line),
            "UNDER": sum(p for (h, a), p in matrix.items() if Decimal(h + a) < total_line),
        }
        btts = {
            "YES": sum(p for (h, a), p in matrix.items() if h > 0 and a > 0),
            "NO": sum(p for (h, a), p in matrix.items() if h == 0 or a == 0),
        }
        ah_home = 0.0
        ah_away = 0.0
        for (home_goals, away_goals), probability in matrix.items():
            home_outcome = settle_asian_handicap(home_goals, away_goals, "HOME", asian_line)
            away_outcome = settle_asian_handicap(home_goals, away_goals, "AWAY", -asian_line)
            ah_home += probability * _settlement_score(home_outcome)
            ah_away += probability * _settlement_score(away_outcome)
        asian_handicap = {"HOME_EXPECTED_RETURN": ah_home, "AWAY_EXPECTED_RETURN": ah_away}
        residual = sum(
            abs(one_x_two.get(key, 0.0) - one_x_two_probabilities.get(key, 0.0))
            for key in one_x_two
        )
        return BaselineOutput(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            score_matrix=matrix,
            one_x_two=one_x_two,
            totals=totals,
            asian_handicap=asian_handicap,
            btts=btts,
            residual=residual,
        )


def _settlement_score(outcome: SettlementOutcome) -> float:
    return {
        SettlementOutcome.WIN: 1.0,
        SettlementOutcome.HALF_WIN: 0.5,
        SettlementOutcome.PUSH: 0.0,
        SettlementOutcome.HALF_LOSS: -0.5,
        SettlementOutcome.LOSS: -1.0,
    }[outcome]
