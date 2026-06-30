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
    return {
        "source": "formal_simulation",
        "label": "模拟中位比分参考",
        "midband_scorelines": _midband_scorelines(simulation),
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


def _midband_scorelines(simulation: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
    picks = _scoreline_distribution(simulation)
    if not picks:
        return []
    ordered = sorted(picks, key=lambda item: float(item["probability"]), reverse=True)
    if len(ordered) <= limit:
        selected = ordered[:limit]
    else:
        low_cutoff = max(0.01, float(ordered[0]["probability"]) * 0.25)
        midband = [
            item
            for index, item in enumerate(ordered)
            if index >= limit and float(item["probability"]) >= low_cutoff
        ]
        if len(midband) < limit:
            midband = [item for item in ordered[limit:] if float(item["probability"]) >= low_cutoff]
        if len(midband) < limit:
            midband = ordered[limit : limit + limit]
        selected = midband[:limit] if midband else ordered[:limit]
    return [
        {
            "scoreline": str(item["scoreline"]),
            "home_goals": item["home_goals"],
            "away_goals": item["away_goals"],
            "source": "formal_simulation_midband",
        }
        for item in selected
        if item.get("scoreline")
    ]


def _scoreline_distribution(simulation: dict[str, Any]) -> list[dict[str, Any]]:
    lambda_home = _number(simulation.get("lambda_home"))
    lambda_away = _number(simulation.get("lambda_away"))
    if lambda_home is not None and lambda_away is not None:
        poisson_rows: list[dict[str, Any]] = []
        for home in range(0, 7):
            for away in range(0, 7):
                probability = _poisson_probability(lambda_home, home) * _poisson_probability(
                    lambda_away,
                    away,
                )
                poisson_rows.append(
                    {
                        "scoreline": f"{home}-{away}",
                        "home_goals": home,
                        "away_goals": away,
                        "probability": probability,
                    }
                )
        return poisson_rows
    raw_picks = simulation.get("scoreline_picks")
    if isinstance(raw_picks, list) and raw_picks:
        pick_rows: list[dict[str, Any]] = []
        for item in raw_picks:
            if not isinstance(item, dict) or not item.get("scoreline"):
                continue
            pick_probability = _probability(item.get("probability"))
            if pick_probability is None:
                continue
            scoreline = str(item["scoreline"])
            pick_rows.append(
                {
                    "scoreline": scoreline,
                    "home_goals": _score_part(scoreline, 0),
                    "away_goals": _score_part(scoreline, 1),
                    "probability": pick_probability,
                }
            )
        if pick_rows:
            return pick_rows
    return []


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
