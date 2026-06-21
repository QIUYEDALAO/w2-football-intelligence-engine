from __future__ import annotations


def independent_minus_market(
    independent: dict[str, float],
    market: dict[str, float],
) -> dict[str, float]:
    return {key: independent[key] - market[key] for key in ("HOME", "DRAW", "AWAY")}


def residual_blend_research_only(
    independent: dict[str, float],
    market: dict[str, float],
    validation_weight: float,
) -> dict[str, float]:
    weight = max(min(validation_weight, 1.0), 0.0)
    blended = {
        key: independent[key] * (1.0 - weight) + market[key] * weight
        for key in ("HOME", "DRAW", "AWAY")
    }
    total = sum(blended.values())
    return {key: value / total for key, value in blended.items()}
