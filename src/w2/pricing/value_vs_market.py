from __future__ import annotations

from typing import Any

EDGE_WATCH_THRESHOLD = 0.25
COVERAGE_WATCH_THRESHOLD = 0.5


def market_lines(current_odds: dict[str, Any] | None) -> dict[str, float | None]:
    current = current_odds if isinstance(current_odds, dict) else {}
    ah = current.get("ah")
    ou = current.get("ou")
    return {
        "market_ah": _line(ah, "home_line"),
        "market_ou": _line(ou, "line"),
    }


def pricing_status(
    *,
    coverage: float,
    edge_ah: float | None,
    edge_ou: float | None,
) -> str:
    if coverage < COVERAGE_WATCH_THRESHOLD:
        return "WATCH"
    if max(abs(edge_ah or 0.0), abs(edge_ou or 0.0)) < EDGE_WATCH_THRESHOLD:
        return "WATCH"
    return "RULE_BASED_UNCALIBRATED"


def edge(fair_line: float | None, market_line: float | None) -> float | None:
    if fair_line is None or market_line is None:
        return None
    return round(fair_line - market_line, 6)


def _line(payload: Any, key: str) -> float | None:
    if not isinstance(payload, dict):
        return None
    try:
        return float(payload[key])
    except (KeyError, TypeError, ValueError):
        return None
