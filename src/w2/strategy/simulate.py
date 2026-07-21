from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from math import exp
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap
from w2.markets.poisson import round_to_quarter
from w2.models.dixon_coles import tau_correction
from w2.strategy.calibration import calibrate_lambdas

SIMULATION_MODEL_VERSION = "w2.formal.exact_dc_poisson.v1"
READY = "READY"
INSUFFICIENT_INPUTS = "INSUFFICIENT_INPUTS"


@dataclass(frozen=True, kw_only=True)
class SimulationInputs:
    fixture_id: str
    home_team_id: str
    away_team_id: str
    home_xg_for: float | None
    home_xg_against: float | None
    away_xg_for: float | None
    away_xg_against: float | None
    home_elo: float | None = None
    away_elo: float | None = None
    home_elo_source: str | None = None
    away_elo_source: str | None = None
    home_elo_collection_status: str | None = None
    away_elo_collection_status: str | None = None
    home_squad_value_eur: float | None = None
    away_squad_value_eur: float | None = None
    lineup_strength_adjustment: float = 0.0
    lineup_ah_adjustment: float = 0.0
    lineup_totals_adjustment: float = 0.0
    lineup_ah_evidence_enabled: bool = False
    lineup_totals_evidence_enabled: bool = False
    lambda_sigma_home: float = 0.0
    lambda_sigma_away: float = 0.0
    lambda_uncertainty_method: str | None = None
    lambda_uncertainty_status: str | None = None
    lambda_uncertainty_audit: dict[str, Any] = field(default_factory=dict)
    neutral_site: bool = False
    input_readiness: dict[str, bool | str | int | float | None] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SimulationOutput:
    model_version: str
    calibration_version: str | None
    calibration_status: str | None
    lambda_home: float | None
    lambda_away: float | None
    lambda_sigma_home: float | None
    lambda_sigma_away: float | None
    fair_ah: float | None
    fair_ou: float | None
    scoreline_picks: list[dict[str, Any]]
    score_matrix_summary: dict[str, Any]
    ah_probabilities: dict[str, Any]
    ou_probabilities: dict[str, Any]
    input_readiness: dict[str, Any]
    status: str
    simulations: int
    seed: int
    calibration: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_simulation(
    inputs: SimulationInputs,
    *,
    simulations: int = 10_000,
    max_goals: int = 12,
) -> SimulationOutput:
    seed = _seed(inputs.fixture_id, SIMULATION_MODEL_VERSION)
    readiness = _input_readiness(inputs)
    if not readiness["xg_ready"]:
        return SimulationOutput(
            model_version=SIMULATION_MODEL_VERSION,
            calibration_version=None,
            calibration_status=None,
            lambda_home=None,
            lambda_away=None,
            lambda_sigma_home=None,
            lambda_sigma_away=None,
            fair_ah=None,
            fair_ou=None,
            scoreline_picks=[],
            score_matrix_summary={
                "top_scorelines": [],
                "home_win": None,
                "draw": None,
                "away_win": None,
            },
            ah_probabilities={},
            ou_probabilities={},
            input_readiness=readiness,
            status=INSUFFICIENT_INPUTS,
            simulations=simulations,
            seed=seed,
        )
    eligible_home_elo = _eligible_elo(
        inputs.home_elo,
        source=inputs.home_elo_source,
        collection_status=inputs.home_elo_collection_status,
    )
    eligible_away_elo = _eligible_elo(
        inputs.away_elo,
        source=inputs.away_elo_source,
        collection_status=inputs.away_elo_collection_status,
    )
    calibration = calibrate_lambdas(
        home_xg_for=_required_float(inputs.home_xg_for),
        home_xg_against=_required_float(inputs.home_xg_against),
        away_xg_for=_required_float(inputs.away_xg_for),
        away_xg_against=_required_float(inputs.away_xg_against),
        home_elo=eligible_home_elo,
        away_elo=eligible_away_elo,
        home_squad_value_eur=inputs.home_squad_value_eur,
        away_squad_value_eur=inputs.away_squad_value_eur,
        lineup_strength_adjustment=inputs.lineup_strength_adjustment,
        lineup_ah_adjustment=inputs.lineup_ah_adjustment,
        lineup_totals_adjustment=inputs.lineup_totals_adjustment,
        lineup_ah_evidence_enabled=inputs.lineup_ah_evidence_enabled,
        lineup_totals_evidence_enabled=inputs.lineup_totals_evidence_enabled,
        apply_home_advantage=not inputs.neutral_site,
    )
    sigma_home = max(float(inputs.lambda_sigma_home), 0.0)
    sigma_away = max(float(inputs.lambda_sigma_away), 0.0)
    uncertainty_method = (
        "none"
        if sigma_home == 0 and sigma_away == 0
        else inputs.lambda_uncertainty_method or "deterministic_three_point"
    )
    uncertainty_status = (
        inputs.lambda_uncertainty_status
        if sigma_home > 0 or sigma_away > 0
        else "NOT_READY"
    )
    score_counts = _exact_score_matrix_with_uncertainty(
        calibration.lambda_home,
        calibration.lambda_away,
        sigma_home=sigma_home,
        sigma_away=sigma_away,
        rho=float(calibration.params.get("dixon_coles_rho") or 0.0),
        max_goals=max_goals,
    )
    total_counts: dict[int, float] = {}
    diff_counts: dict[int, float] = {}
    for (home_goals, away_goals), probability in score_counts.items():
        total_counts[home_goals + away_goals] = (
            total_counts.get(home_goals + away_goals, 0.0) + probability
        )
        diff_counts[home_goals - away_goals] = (
            diff_counts.get(home_goals - away_goals, 0.0) + probability
        )
    fair_ah, ah_probabilities = _fair_ah(score_counts, 1)
    fair_ou, ou_probabilities = _fair_ou(total_counts, 1)
    top_scorelines = [
        {
            "scoreline": f"{home}-{away}",
            "home_goals": home,
            "away_goals": away,
            "probability": round(probability, 6),
            "probability_label": f"{round(probability * 100)}%",
        }
        for (home, away), probability in sorted(
            score_counts.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
    ]
    home_win = sum(probability for diff, probability in diff_counts.items() if diff > 0)
    draw = diff_counts.get(0, 0.0)
    away_win = sum(probability for diff, probability in diff_counts.items() if diff < 0)
    return SimulationOutput(
        model_version=SIMULATION_MODEL_VERSION,
        calibration_version=calibration.calibration_version,
        calibration_status=calibration.calibration_status,
        lambda_home=calibration.lambda_home,
        lambda_away=calibration.lambda_away,
        lambda_sigma_home=round(sigma_home, 6),
        lambda_sigma_away=round(sigma_away, 6),
        fair_ah=fair_ah,
        fair_ou=fair_ou,
        scoreline_picks=top_scorelines,
        score_matrix_summary={
            "top_scorelines": top_scorelines,
            "home_win": round(home_win, 6),
            "draw": round(draw, 6),
            "away_win": round(away_win, 6),
        },
        ah_probabilities=ah_probabilities,
        ou_probabilities=ou_probabilities,
        input_readiness=readiness,
        status=READY,
        simulations=simulations,
        seed=seed,
        calibration={
            "params": calibration.params,
            "input_weights": calibration.input_weights,
            "seed_policy": "unused_exact_solution",
            "max_goals": max_goals,
            "lambda_uncertainty_method": uncertainty_method,
            "lambda_uncertainty_status": uncertainty_status,
            "lambda_uncertainty_audit": inputs.lambda_uncertainty_audit,
        },
    )


def ah_cover_probability(
    score_counts: Counter[tuple[int, int]] | dict[tuple[int, int], int | float],
    *,
    simulations: int,
    selection: str,
    line: float,
) -> float:
    total = 0.0
    decimal_line = Decimal(str(line))
    for (home_goals, away_goals), count in score_counts.items():
        outcome = settle_asian_handicap(home_goals, away_goals, selection, decimal_line)
        total += count * _effective_probability_score(outcome)
    return round(total / max(simulations, 1), 6)


def ah_settlement_distribution(
    score_counts: Counter[tuple[int, int]] | dict[tuple[int, int], int | float],
    *,
    simulations: int,
    selection: str,
    line: float,
) -> dict[str, float]:
    counts = {
        SettlementOutcome.WIN: 0.0,
        SettlementOutcome.HALF_WIN: 0.0,
        SettlementOutcome.PUSH: 0.0,
        SettlementOutcome.HALF_LOSS: 0.0,
        SettlementOutcome.LOSS: 0.0,
    }
    decimal_line = Decimal(str(line))
    denominator = max(simulations, 1)
    for (home_goals, away_goals), count in score_counts.items():
        outcome = settle_asian_handicap(home_goals, away_goals, selection, decimal_line)
        counts[outcome] += count
    return {outcome.value: round(value / denominator, 6) for outcome, value in counts.items()}


def ah_expected_value(distribution: dict[str, Any], *, decimal_price: float) -> float | None:
    if decimal_price <= 1:
        return None
    win = _distribution_value(distribution, SettlementOutcome.WIN)
    half_win = _distribution_value(distribution, SettlementOutcome.HALF_WIN)
    push = _distribution_value(distribution, SettlementOutcome.PUSH)
    half_loss = _distribution_value(distribution, SettlementOutcome.HALF_LOSS)
    loss = _distribution_value(distribution, SettlementOutcome.LOSS)
    if (
        win is None
        or half_win is None
        or push is None
        or half_loss is None
        or loss is None
    ):
        return None
    profit = decimal_price - 1
    ev = (
        win * profit
        + half_win * (profit / 2)
        + push * 0
        - half_loss * 0.5
        - loss
    )
    return round(ev, 6)


def ah_settlement_distribution_from_lambdas(
    *,
    lambda_home: float | None,
    lambda_away: float | None,
    selection: str,
    line: float,
    max_goals: int = 12,
) -> dict[str, float] | None:
    result = ah_expected_value_uncertainty_from_lambdas(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        selection=selection,
        line=line,
        decimal_price=2.0,
        max_goals=max_goals,
    )
    return result[0]


def ah_expected_value_uncertainty_from_lambdas(
    *,
    lambda_home: float | None,
    lambda_away: float | None,
    selection: str,
    line: float,
    decimal_price: float,
    lambda_sigma_home: float = 0.0,
    lambda_sigma_away: float = 0.0,
    rho: float = 0.0,
    max_goals: int = 12,
) -> tuple[dict[str, float] | None, float | None, float | None]:
    if (
        lambda_home is None
        or lambda_away is None
        or lambda_home <= 0
        or lambda_away <= 0
        or decimal_price <= 1
    ):
        return None, None, None
    scenario_rows: list[tuple[float, dict[str, float], float]] = []
    for scenario_home_lambda, home_weight in _lambda_quadrature(
        lambda_home,
        max(float(lambda_sigma_home), 0.0),
    ):
        for scenario_away_lambda, away_weight in _lambda_quadrature(
            lambda_away,
            max(float(lambda_sigma_away), 0.0),
        ):
            distribution = ah_settlement_distribution(
                _exact_score_matrix(
                    scenario_home_lambda,
                    scenario_away_lambda,
                    rho=rho,
                    max_goals=max_goals,
                ),
                simulations=1,
                selection=selection,
                line=line,
            )
            scenario_ev = ah_expected_value(distribution, decimal_price=decimal_price)
            if scenario_ev is None:
                return distribution, None, None
            scenario_rows.append((home_weight * away_weight, distribution, scenario_ev))
    total_weight = sum(weight for weight, _, _ in scenario_rows)
    if total_weight <= 0:
        return None, None, None
    mixed_distribution = {
        outcome.value: 0.0
        for outcome in (
            SettlementOutcome.WIN,
            SettlementOutcome.HALF_WIN,
            SettlementOutcome.PUSH,
            SettlementOutcome.HALF_LOSS,
            SettlementOutcome.LOSS,
        )
    }
    normalized_rows: list[tuple[float, dict[str, float], float]] = []
    for weight, distribution, scenario_ev in scenario_rows:
        normalized_weight = weight / total_weight
        normalized_rows.append((normalized_weight, distribution, scenario_ev))
        for outcome in mixed_distribution:
            mixed_distribution[outcome] += normalized_weight * distribution.get(outcome, 0.0)
    rounded_distribution = {
        outcome: round(probability, 6)
        for outcome, probability in mixed_distribution.items()
    }
    mixed_ev = ah_expected_value(rounded_distribution, decimal_price=decimal_price)
    if mixed_ev is None:
        return rounded_distribution, None, None
    variance = sum(
        weight * ((scenario_ev - mixed_ev) ** 2)
        for weight, _, scenario_ev in normalized_rows
    )
    return rounded_distribution, mixed_ev, float(round(max(variance, 0.0) ** 0.5, 6))


def _input_readiness(inputs: SimulationInputs) -> dict[str, Any]:
    xg_ready = all(
        value is not None
        for value in (
            inputs.home_xg_for,
            inputs.home_xg_against,
            inputs.away_xg_for,
            inputs.away_xg_against,
        )
    )
    eligible_home_elo = _eligible_elo(
        inputs.home_elo,
        source=inputs.home_elo_source,
        collection_status=inputs.home_elo_collection_status,
    )
    eligible_away_elo = _eligible_elo(
        inputs.away_elo,
        source=inputs.away_elo_source,
        collection_status=inputs.away_elo_collection_status,
    )
    home_proxy_elo = _is_proxy_elo_source(
        source=inputs.home_elo_source,
        collection_status=inputs.home_elo_collection_status,
    )
    away_proxy_elo = _is_proxy_elo_source(
        source=inputs.away_elo_source,
        collection_status=inputs.away_elo_collection_status,
    )
    proxy_elo_excluded = (
        (inputs.home_elo is not None and home_proxy_elo)
        or (inputs.away_elo is not None and away_proxy_elo)
    )
    readiness = dict(inputs.input_readiness)
    readiness.update(
        {
            "xg_ready": xg_ready,
            "elo_ready": eligible_home_elo is not None and eligible_away_elo is not None,
            "ratings_used_in_lambda": eligible_home_elo is not None
            and eligible_away_elo is not None,
            "proxy_elo_excluded": proxy_elo_excluded,
            "home_elo_source": inputs.home_elo_source,
            "away_elo_source": inputs.away_elo_source,
            "home_elo_collection_status": inputs.home_elo_collection_status,
            "away_elo_collection_status": inputs.away_elo_collection_status,
            "neutral_site": inputs.neutral_site,
            "home_advantage_applied": not inputs.neutral_site,
            "lambda_sigma_home": inputs.lambda_sigma_home,
            "lambda_sigma_away": inputs.lambda_sigma_away,
            "squad_value_ready": inputs.home_squad_value_eur is not None
            and inputs.away_squad_value_eur is not None,
        }
    )
    return readiness


def _eligible_elo(
    value: float | None,
    *,
    source: str | None,
    collection_status: str | None,
) -> float | None:
    if value is None:
        return None
    if _is_proxy_elo_source(source=source, collection_status=collection_status):
        return None
    return value


def _is_proxy_elo_source(*, source: str | None, collection_status: str | None) -> bool:
    return (
        str(collection_status or "").upper() == "PROXY_ONLY"
        or str(source or "").lower() == "rolling_xg_proxy"
    )


def _fair_ah(
    score_counts: Counter[tuple[int, int]] | dict[tuple[int, int], int | float],
    simulations: int,
) -> tuple[float, dict[str, Any]]:
    ladder = [round(step * 0.25, 2) for step in range(-12, 13)]
    rows: list[dict[str, Any]] = []
    for line in ladder:
        home_cover = ah_cover_probability(
            score_counts,
            simulations=simulations,
            selection="HOME",
            line=line,
        )
        home_distribution = ah_settlement_distribution(
            score_counts,
            simulations=simulations,
            selection="HOME",
            line=line,
        )
        away_distribution = ah_settlement_distribution(
            score_counts,
            simulations=simulations,
            selection="AWAY",
            line=-line,
        )
        rows.append(
            {
                "home_line": line,
                "home_cover": home_cover,
                "away_cover": round(1 - home_cover, 6),
                "home_settlement_distribution": home_distribution,
                "away_settlement_distribution": away_distribution,
            }
        )
    fair = min(
        rows,
        key=lambda row: (
            abs(float(row["home_cover"]) - 0.5),
            abs(float(row["home_line"])),
        ),
    )
    return float(fair["home_line"]), {"fair_home_cover": fair["home_cover"], "ladder": rows}


def _fair_ou(
    total_counts: Counter[int] | dict[int, int | float],
    simulations: int,
) -> tuple[float, dict[str, Any]]:
    total_mean = sum(total * count for total, count in total_counts.items()) / max(simulations, 1)
    fair_line = round_to_quarter(total_mean)
    ladder = []
    for step in range(4, 21):
        line = step * 0.25
        over = sum(count for total, count in total_counts.items() if total > line) / simulations
        under = sum(count for total, count in total_counts.items() if total < line) / simulations
        push = sum(count for total, count in total_counts.items() if total == line) / simulations
        ladder.append(
            {
                "line": line,
                "over": round(over, 6),
                "under": round(under, 6),
                "push": round(push, 6),
            }
        )
    return float(fair_line), {"fair_total_goals": round(total_mean, 6), "ladder": ladder}


def _poisson_probabilities(mu: float, *, max_goals: int) -> list[float]:
    values: list[float] = []
    probability = exp(-mu)
    for goals in range(max_goals + 1):
        if goals == 0:
            probability = exp(-mu)
        elif goals > 0:
            probability *= mu / goals
        values.append(probability)
    return values


def _exact_score_matrix(
    lambda_home: float,
    lambda_away: float,
    *,
    rho: float,
    max_goals: int,
) -> dict[tuple[int, int], float]:
    home_probs = _poisson_probabilities(lambda_home, max_goals=max_goals)
    away_probs = _poisson_probabilities(lambda_away, max_goals=max_goals)
    weights: dict[tuple[int, int], float] = {}
    for home_goals, home_prob in enumerate(home_probs):
        for away_goals, away_prob in enumerate(away_probs):
            correction = tau_correction(
                home_goals,
                away_goals,
                lambda_home,
                lambda_away,
                rho,
            )
            weights[(home_goals, away_goals)] = max(home_prob * away_prob * correction, 0.0)
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("exact score matrix has no positive probability")
    return {score: probability / total for score, probability in weights.items()}


def _exact_score_matrix_with_uncertainty(
    lambda_home: float,
    lambda_away: float,
    *,
    sigma_home: float,
    sigma_away: float,
    rho: float,
    max_goals: int,
) -> dict[tuple[int, int], float]:
    if sigma_home <= 0 and sigma_away <= 0:
        return _exact_score_matrix(lambda_home, lambda_away, rho=rho, max_goals=max_goals)
    weights: dict[tuple[int, int], float] = {}
    for home_lambda, home_weight in _lambda_quadrature(lambda_home, sigma_home):
        for away_lambda, away_weight in _lambda_quadrature(lambda_away, sigma_away):
            matrix = _exact_score_matrix(home_lambda, away_lambda, rho=rho, max_goals=max_goals)
            scenario_weight = home_weight * away_weight
            for score, probability in matrix.items():
                weights[score] = weights.get(score, 0.0) + scenario_weight * probability
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("uncertain score matrix has no positive probability")
    return {score: probability / total for score, probability in weights.items()}


def _lambda_quadrature(mu: float, sigma: float) -> tuple[tuple[float, float], ...]:
    if sigma <= 0:
        return ((max(mu, 0.01), 1.0),)
    return (
        (max(mu - sigma, 0.01), 0.158655),
        (max(mu, 0.01), 0.68269),
        (max(mu + sigma, 0.01), 0.158655),
    )


def _effective_probability_score(outcome: SettlementOutcome) -> float:
    return {
        SettlementOutcome.WIN: 1.0,
        SettlementOutcome.HALF_WIN: 0.5,
        SettlementOutcome.PUSH: 0.5,
        SettlementOutcome.HALF_LOSS: 0.0,
        SettlementOutcome.LOSS: 0.0,
    }[outcome]


def _distribution_value(distribution: dict[str, Any], outcome: SettlementOutcome) -> float | None:
    try:
        value = distribution.get(outcome.value, 0.0)
        return float(value)
    except (TypeError, ValueError):
        return None


def _seed(fixture_id: str, model_version: str) -> int:
    digest = hashlib.sha256(f"{fixture_id}:{model_version}".encode()).hexdigest()
    return int(digest[:16], 16)


def _required_float(value: float | None) -> float:
    if value is None:
        raise ValueError("simulation input unexpectedly missing after readiness check")
    return float(value)
