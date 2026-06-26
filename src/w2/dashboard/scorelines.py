from __future__ import annotations

from typing import Any


def scoreline_picks_from_card(card: dict[str, Any], *, limit: int = 3) -> list[dict[str, Any]]:
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

