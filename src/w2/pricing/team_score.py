from __future__ import annotations

from typing import Any

FACTOR_WEIGHTS = {
    "F3_MODEL_HOME_PROBABILITY": 0.24,
    "F4_MODEL_AWAY_PROBABILITY": 0.24,
    "F5_DRAW_SUPPRESSION": 0.12,
    "F6_MARKET_HOME_BASELINE": 0.12,
    "F7_MARKET_AWAY_BASELINE": 0.12,
    "F8_PRICE_COVERAGE": 0.08,
    "F9_MODEL_MARKET_DIVERGENCE": 0.08,
}


def independent_team_scores(
    *,
    model_probabilities: dict[str, Any] | None,
    market_probabilities: dict[str, Any] | None,
    current_odds: dict[str, Any] | None,
) -> dict[str, Any]:
    model = _probabilities(model_probabilities)
    market = _probabilities(market_probabilities)
    price_coverage = _price_coverage(current_odds)
    factors = [
        _factor("F3_MODEL_HOME_PROBABILITY", "HOME", model["HOME"]),
        _factor("F4_MODEL_AWAY_PROBABILITY", "AWAY", model["AWAY"]),
        _factor("F5_DRAW_SUPPRESSION", "NEUTRAL", 1.0 - model["DRAW"]),
        _factor("F6_MARKET_HOME_BASELINE", "HOME", market["HOME"]),
        _factor("F7_MARKET_AWAY_BASELINE", "AWAY", market["AWAY"]),
        _factor("F8_PRICE_COVERAGE", "NEUTRAL", price_coverage),
        _factor("F9_MODEL_MARKET_DIVERGENCE", "NEUTRAL", _divergence(model, market)),
    ]
    return {
        "home_score": _weighted_score(factors, side="HOME"),
        "away_score": _weighted_score(factors, side="AWAY"),
        "factors": factors,
        "coverage": _coverage(model_probabilities, market_probabilities, price_coverage),
    }


def _factor(factor_id: str, side: str, score: float) -> dict[str, Any]:
    return {
        "id": factor_id,
        "side": side,
        "weight": FACTOR_WEIGHTS[factor_id],
        "score": max(min(score, 1.0), 0.0),
        "status": "READY",
    }


def _weighted_score(factors: list[dict[str, Any]], *, side: str) -> float:
    total = 0.0
    for factor in factors:
        score = float(factor["score"])
        if factor["side"] == side:
            total += float(factor["weight"]) * score
        elif factor["side"] == "NEUTRAL":
            total += float(factor["weight"]) * score * 0.5
    return round(total, 6)


def _probabilities(payload: dict[str, Any] | None) -> dict[str, float]:
    if not payload:
        return {"HOME": 0.0, "DRAW": 0.0, "AWAY": 0.0}
    home = _number(payload.get("HOME") or payload.get("HOME_WIN"))
    draw = _number(payload.get("DRAW"))
    away = _number(payload.get("AWAY") or payload.get("AWAY_WIN"))
    total = home + draw + away
    if total <= 0:
        return {"HOME": 0.0, "DRAW": 0.0, "AWAY": 0.0}
    return {"HOME": home / total, "DRAW": draw / total, "AWAY": away / total}


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _price_coverage(current_odds: dict[str, Any] | None) -> float:
    if not isinstance(current_odds, dict):
        return 0.0
    ready = sum(1 for key in ("ah", "ou") if isinstance(current_odds.get(key), dict))
    return ready / 2


def _divergence(model: dict[str, float], market: dict[str, float]) -> float:
    if not any(market.values()):
        return 0.0
    return abs(model["HOME"] - market["HOME"]) + abs(model["AWAY"] - market["AWAY"])


def _coverage(
    model_probabilities: dict[str, Any] | None,
    market_probabilities: dict[str, Any] | None,
    price_coverage: float,
) -> float:
    ready = 0.0
    ready += 0.4 if model_probabilities else 0.0
    ready += 0.4 if market_probabilities else 0.0
    ready += 0.2 * price_coverage
    return round(ready, 6)
