from __future__ import annotations

from w2.pricing.scale import DEFAULT_FACTOR_SCALE_PARAMS, FactorScaleParams


def fair_handicap_from_supremacy(
    home_score: float,
    away_score: float,
    *,
    scale: FactorScaleParams | None = None,
) -> float:
    scale = scale or DEFAULT_FACTOR_SCALE_PARAMS
    supremacy = home_score - away_score
    if abs(supremacy) < scale.supremacy_deadband:
        return 0.0
    raw_line = round(supremacy / scale.supremacy_score_per_quarter_line * 0.25, 2)
    quarter_line = round(raw_line * 4) / 4
    return -quarter_line
