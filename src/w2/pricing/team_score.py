from __future__ import annotations

from typing import Any

ALLOWED_INDEPENDENT_FACTORS = frozenset(
    {
        "F3_REST_FITNESS",
        "F4_MATCH_IMPORTANCE",
        "F5_RECENT_AH_COVER",
        "F6_H2H",
        "F7_STRENGTH_FORM",
        "F8_SQUAD_VALUE",
        "F9_TRUE_XG",
    }
)


def independent_team_scores(
    *,
    feature_contributions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    factors = [
        _factor(item)
        for item in feature_contributions or []
        if _factor_id(item) in ALLOWED_INDEPENDENT_FACTORS
        and str(item.get("status") or "") == "READY"
    ]
    coverage = round(len(factors) / len(ALLOWED_INDEPENDENT_FACTORS), 6)
    return {
        "home_score": _weighted_score(factors, side="HOME"),
        "away_score": _weighted_score(factors, side="AWAY"),
        "factors": factors,
        "coverage": coverage,
    }


def _factor(item: dict[str, Any]) -> dict[str, Any]:
    side = str(item.get("side") or "NEUTRAL")
    if side not in {"HOME", "AWAY", "NEUTRAL"}:
        side = "UNKNOWN"
    return {
        "id": _factor_id(item),
        "side": side,
        "weight": _number(item.get("weight")),
        "score": max(min(_number(item.get("score")), 1.0), 0.0),
        "status": "READY",
    }


def _factor_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("feature_id") or "")


def _weighted_score(factors: list[dict[str, Any]], *, side: str) -> float:
    total = 0.0
    for factor in factors:
        score = float(factor["score"])
        weight = float(factor["weight"])
        if factor["side"] == side:
            total += weight * score
        elif factor["side"] == "NEUTRAL":
            total += weight * score * 0.5
    return round(total, 6)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
