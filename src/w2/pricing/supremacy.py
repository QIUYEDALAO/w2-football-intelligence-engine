from __future__ import annotations


def fair_handicap_from_supremacy(home_score: float, away_score: float) -> float:
    supremacy = home_score - away_score
    if abs(supremacy) < 0.04:
        return 0.0
    raw_line = round(supremacy / 0.16 * 0.25, 2)
    quarter_line = round(raw_line * 4) / 4
    return -quarter_line


def fair_total_from_coverage(coverage: float) -> float | None:
    if coverage < 0.5:
        return None
    return 2.5
