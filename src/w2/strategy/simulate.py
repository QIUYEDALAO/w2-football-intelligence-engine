from __future__ import annotations

import hashlib
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from math import exp
from typing import Any

from w2.domain.enums import SettlementOutcome
from w2.domain.odds import settle_asian_handicap
from w2.markets.poisson import round_to_quarter
from w2.strategy.calibration import calibrate_lambdas

SIMULATION_MODEL_VERSION = "w2.formal.mc_poisson.v1"
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
    home_squad_value_eur: float | None = None
    away_squad_value_eur: float | None = None
    lineup_strength_adjustment: float = 0.0
    input_readiness: dict[str, bool | str | int | float | None] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class SimulationOutput:
    model_version: str
    calibration_version: str | None
    calibration_status: str | None
    lambda_home: float | None
    lambda_away: float | None
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
    max_goals: int = 10,
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
    calibration = calibrate_lambdas(
        home_xg_for=_required_float(inputs.home_xg_for),
        home_xg_against=_required_float(inputs.home_xg_against),
        away_xg_for=_required_float(inputs.away_xg_for),
        away_xg_against=_required_float(inputs.away_xg_against),
        home_elo=inputs.home_elo,
        away_elo=inputs.away_elo,
        home_squad_value_eur=inputs.home_squad_value_eur,
        away_squad_value_eur=inputs.away_squad_value_eur,
        lineup_strength_adjustment=inputs.lineup_strength_adjustment,
    )
    rng = random.Random(seed)  # noqa: S311 - deterministic simulation seed, not security.
    score_counts: Counter[tuple[int, int]] = Counter()
    total_counts: Counter[int] = Counter()
    diff_counts: Counter[int] = Counter()
    for _ in range(simulations):
        home_goals = _sample_poisson(rng, calibration.lambda_home, max_goals=max_goals)
        away_goals = _sample_poisson(rng, calibration.lambda_away, max_goals=max_goals)
        score_counts[(home_goals, away_goals)] += 1
        total_counts[home_goals + away_goals] += 1
        diff_counts[home_goals - away_goals] += 1
    fair_ah, ah_probabilities = _fair_ah(score_counts, simulations)
    fair_ou, ou_probabilities = _fair_ou(total_counts, simulations)
    top_scorelines = [
        {
            "scoreline": f"{home}-{away}",
            "home_goals": home,
            "away_goals": away,
            "probability": round(count / simulations, 6),
            "probability_label": f"{round(count / simulations * 100)}%",
        }
        for (home, away), count in score_counts.most_common(3)
    ]
    home_win = sum(count for diff, count in diff_counts.items() if diff > 0) / simulations
    draw = diff_counts.get(0, 0) / simulations
    away_win = sum(count for diff, count in diff_counts.items() if diff < 0) / simulations
    return SimulationOutput(
        model_version=SIMULATION_MODEL_VERSION,
        calibration_version=calibration.calibration_version,
        calibration_status=calibration.calibration_status,
        lambda_home=calibration.lambda_home,
        lambda_away=calibration.lambda_away,
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
        },
    )


def ah_cover_probability(
    score_counts: Counter[tuple[int, int]] | dict[tuple[int, int], int],
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
    readiness = dict(inputs.input_readiness)
    readiness.update(
        {
            "xg_ready": xg_ready,
            "elo_ready": inputs.home_elo is not None and inputs.away_elo is not None,
            "squad_value_ready": inputs.home_squad_value_eur is not None
            and inputs.away_squad_value_eur is not None,
        }
    )
    return readiness


def _fair_ah(
    score_counts: Counter[tuple[int, int]],
    simulations: int,
) -> tuple[float, dict[str, Any]]:
    ladder = [round(step * 0.25, 2) for step in range(-12, 13)]
    rows = []
    for line in ladder:
        home_cover = ah_cover_probability(
            score_counts,
            simulations=simulations,
            selection="HOME",
            line=line,
        )
        rows.append(
            {
                "home_line": line,
                "home_cover": home_cover,
                "away_cover": round(1 - home_cover, 6),
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


def _fair_ou(total_counts: Counter[int], simulations: int) -> tuple[float, dict[str, Any]]:
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


def _sample_poisson(rng: random.Random, mu: float, *, max_goals: int) -> int:
    threshold = rng.random()
    cumulative = 0.0
    probability = exp(-mu)
    for goals in range(max_goals):
        if goals == 0:
            probability = exp(-mu)
        elif goals > 0:
            probability *= mu / goals
        cumulative += probability
        if threshold <= cumulative:
            return goals
    return max_goals


def _effective_probability_score(outcome: SettlementOutcome) -> float:
    return {
        SettlementOutcome.WIN: 1.0,
        SettlementOutcome.HALF_WIN: 0.5,
        SettlementOutcome.PUSH: 0.5,
        SettlementOutcome.HALF_LOSS: 0.0,
        SettlementOutcome.LOSS: 0.0,
    }[outcome]


def _seed(fixture_id: str, model_version: str) -> int:
    digest = hashlib.sha256(f"{fixture_id}:{model_version}".encode()).hexdigest()
    return int(digest[:16], 16)


def _required_float(value: float | None) -> float:
    if value is None:
        raise ValueError("simulation input unexpectedly missing after readiness check")
    return float(value)
