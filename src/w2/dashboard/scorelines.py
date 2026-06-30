from __future__ import annotations

import math
from typing import Any


def scoreline_picks_from_card(card: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    simulation_picks = _simulation_scoreline_picks(card)
    if simulation_picks:
        return simulation_picks[:limit]
    markets = [item for item in card.get("markets", []) if isinstance(item, dict)]
    score_market = next((item for item in markets if item.get("market") == "SCORE"), {})
    references = score_market.get("reference_scores", []) if isinstance(score_market, dict) else []
    if not isinstance(references, list):
        return []
    picks: list[dict[str, Any]] = []
    for item in references:
        if not isinstance(item, dict) or not item.get("scoreline"):
            continue
        scoreline = str(item["scoreline"])
        probability = _probability(item.get("conditional_probability") or item.get("probability"))
        picks.append(
            {
                "scoreline": scoreline,
                "home_goals": _score_part(scoreline, 0),
                "away_goals": _score_part(scoreline, 1),
                "probability": probability,
                "probability_label": _probability_label(
                    item.get("probability_label"),
                    probability,
                ),
            }
        )
    return picks[:limit]


def scoreline_reference_from_card(
    card: dict[str, Any],
    *,
    recommendation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    simulation = _simulation_from_card(card)
    if not isinstance(simulation, dict) or simulation.get("status") != "READY":
        return None
    top_scorelines = scoreline_picks_from_card(card)
    high_total_probability = _over_probability(simulation, 3.5)
    very_high_total_probability = _over_probability(simulation, 4.5)
    return {
        "source": "formal_simulation",
        "label": "模拟比分参考",
        "top_scorelines": top_scorelines,
        "high_total": {
            "threshold": 4,
            "probability": high_total_probability,
            "probability_label": _probability_label(None, high_total_probability),
            "representative_scoreline": _representative_high_total_scoreline(
                simulation,
                minimum_total=4,
            ),
        },
        "very_high_total": {
            "threshold": 5,
            "probability": very_high_total_probability,
            "probability_label": _probability_label(None, very_high_total_probability),
        },
        "ah_key_scorelines": _ah_key_scorelines(simulation, recommendation=recommendation),
    }


def _simulation_from_card(card: dict[str, Any]) -> dict[str, Any] | None:
    simulation = card.get("simulation")
    if isinstance(simulation, dict):
        return simulation
    shadow = card.get("pricing_shadow")
    if isinstance(shadow, dict):
        simulation = shadow.get("simulation")
        if isinstance(simulation, dict):
            return simulation
    return None


def _simulation_scoreline_picks(card: dict[str, Any]) -> list[dict[str, Any]]:
    simulation = _simulation_from_card(card)
    if not isinstance(simulation, dict) or simulation.get("status") != "READY":
        return []
    raw_picks = simulation.get("scoreline_picks")
    if not isinstance(raw_picks, list):
        return []
    picks: list[dict[str, Any]] = []
    for item in raw_picks:
        if not isinstance(item, dict) or not item.get("scoreline"):
            continue
        scoreline = str(item["scoreline"])
        probability = _probability(item.get("probability"))
        picks.append(
            {
                "scoreline": scoreline,
                "home_goals": _score_part(scoreline, 0),
                "away_goals": _score_part(scoreline, 1),
                "probability": probability,
                "probability_label": _probability_label(
                    item.get("probability_label"),
                    probability,
                ),
            }
        )
    return picks


def _over_probability(simulation: dict[str, Any], line: float) -> float | None:
    ou = simulation.get("ou_probabilities")
    ladder = ou.get("ladder") if isinstance(ou, dict) else None
    if not isinstance(ladder, list):
        return None
    for item in ladder:
        if not isinstance(item, dict):
            continue
        item_line = _number(item.get("line"))
        if item_line is not None and math.isclose(item_line, line, abs_tol=1e-9):
            return _probability(item.get("over"))
    return None


def _representative_high_total_scoreline(
    simulation: dict[str, Any],
    *,
    minimum_total: int,
) -> dict[str, Any] | None:
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if lambda_home is None or lambda_away is None:
        return None
    best: tuple[float, int, int] | None = None
    for home in range(0, 7):
        for away in range(0, 7):
            if home + away < minimum_total:
                continue
            probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                lambda_away,
                away,
            )
            if best is None or probability > best[0]:
                best = (probability, home, away)
    if best is None:
        return None
    probability, home, away = best
    return {
        "scoreline": f"{home}-{away}",
        "home_goals": home,
        "away_goals": away,
        "probability": round(probability, 6),
        "probability_label": _probability_label(None, probability),
        "source": "exact_poisson_from_lambda",
    }


def _ah_key_scorelines(
    simulation: dict[str, Any],
    *,
    recommendation: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(recommendation, dict):
        return []
    if recommendation.get("market") != "ASIAN_HANDICAP":
        return []
    selection = str(recommendation.get("selection") or "")
    selected_line = _number(recommendation.get("line"))
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if selected_line is None or lambda_home is None or lambda_away is None:
        return []
    if selection == "HOME_AH":
        side = "HOME"
        home_line = selected_line
    elif selection == "AWAY_AH":
        side = "AWAY"
        home_line = -selected_line
    else:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    totals: dict[str, float] = {}
    for home in range(0, 8):
        for away in range(0, 8):
            outcome = _ah_outcome_for_scoreline(
                side=side,
                home_line=home_line,
                home_goals=home,
                away_goals=away,
            )
            probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                lambda_away,
                away,
            )
            totals[outcome] = totals.get(outcome, 0.0) + probability
            current = grouped.get(outcome)
            if current is not None and probability <= float(current["representative_probability"]):
                continue
            grouped[outcome] = {
                "outcome": outcome,
                "label": _ah_outcome_label(outcome),
                "scoreline": f"{home}-{away}",
                "home_goals": home,
                "away_goals": away,
                "representative_probability": round(probability, 6),
                "representative_probability_label": _probability_label(None, probability),
                "settlement_probability": None,
                "settlement_probability_label": None,
                "source": "exact_poisson_from_lambda",
            }

    ordered: list[dict[str, Any]] = []
    for outcome in ("WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "LOSS"):
        item = grouped.get(outcome)
        if item is None:
            continue
        settlement_probability = totals.get(outcome)
        item["settlement_probability"] = (
            round(settlement_probability, 6)
            if settlement_probability is not None
            else None
        )
        item["settlement_probability_label"] = _probability_label(None, settlement_probability)
        ordered.append(item)
    return ordered


def _ah_outcome_for_scoreline(
    *,
    side: str,
    home_line: float,
    home_goals: int,
    away_goals: int,
) -> str:
    selected_line = home_line if side == "HOME" else -home_line
    goal_margin = home_goals - away_goals if side == "HOME" else away_goals - home_goals
    parts = _quarter_line_parts(selected_line)
    outcomes = [_single_ah_outcome(goal_margin + part) for part in parts]
    if outcomes[0] == outcomes[1]:
        return outcomes[0]
    if set(outcomes) == {"WIN", "PUSH"}:
        return "HALF_WIN"
    if set(outcomes) == {"LOSS", "PUSH"}:
        return "HALF_LOSS"
    return "PUSH"


def _quarter_line_parts(line: float) -> tuple[float, float]:
    doubled = round(line * 2) / 2
    if math.isclose(line, doubled, abs_tol=1e-9):
        return (doubled, doubled)
    lower = math.floor(line * 2) / 2
    upper = math.ceil(line * 2) / 2
    return (lower, upper)


def _single_ah_outcome(adjusted_margin: float) -> str:
    if adjusted_margin > 0:
        return "WIN"
    if adjusted_margin < 0:
        return "LOSS"
    return "PUSH"


def _ah_outcome_label(outcome: str) -> str:
    labels = {
        "WIN": "全赢",
        "HALF_WIN": "半赢",
        "PUSH": "走水",
        "HALF_LOSS": "半输",
        "LOSS": "全输",
    }
    return labels.get(outcome, outcome)


def _poisson_probability(rate: float, goals: int) -> float:
    return math.exp(-rate) * rate**goals / math.factorial(goals)


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value)
        except ValueError:
            return None
    else:
        return None
    return numeric if math.isfinite(numeric) else None


def _probability(value: Any) -> float | None:
    if isinstance(value, int | float):
        numeric = float(value)
    elif isinstance(value, str):
        try:
            numeric = float(value.strip().rstrip("%"))
            if value.strip().endswith("%"):
                numeric /= 100
        except ValueError:
            return None
    else:
        return None
    if numeric > 1:
        numeric /= 100
    if numeric < 0:
        return None
    return numeric


def _probability_label(existing: Any, probability: float | None) -> str | None:
    if isinstance(existing, str) and existing.strip():
        return existing
    if probability is None:
        return None
    return f"{round(probability * 100)}%"


def _score_part(scoreline: str, index: int) -> int | None:
    parts = scoreline.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        return int(parts[index])
    except ValueError:
        return None
