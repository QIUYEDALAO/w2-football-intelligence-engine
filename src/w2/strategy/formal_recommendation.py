from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from w2.strategy.simulate import READY, SimulationOutput

FORMAL_EDGE_THRESHOLD = 0.055
FORMAL_MIN_INDEPENDENT_SIGNALS = 3


@dataclass(frozen=True, kw_only=True)
class FormalRecommendationResult:
    tier: str
    recommendation: dict[str, Any] | None
    formal_eligible: bool
    formal_suppressed: bool
    formal_suppressed_reason: str | None
    blockers: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def formal_recommendations_enabled() -> bool:
    return os.getenv("W2_FORMAL_RECOMMENDATION_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def build_formal_recommendation(
    *,
    fixture_status: str,
    simulation: SimulationOutput | None,
    current_odds: dict[str, Any] | None,
    pricing_shadow: dict[str, Any] | None,
    analysis_readiness: dict[str, Any] | None,
    home_team_name: str,
    away_team_name: str,
    enabled: bool | None = None,
) -> FormalRecommendationResult:
    enabled = formal_recommendations_enabled() if enabled is None else enabled
    blockers = _blockers(
        fixture_status=fixture_status,
        simulation=simulation,
        current_odds=current_odds,
        pricing_shadow=pricing_shadow,
        analysis_readiness=analysis_readiness,
    )
    if blockers:
        return FormalRecommendationResult(
            tier="WATCH",
            recommendation=None,
            formal_eligible=False,
            formal_suppressed=False,
            formal_suppressed_reason=None,
            blockers=blockers,
        )
    assert simulation is not None
    odds = current_odds or {}
    raw_ah = odds.get("ah")
    ah: dict[str, Any] = raw_ah if isinstance(raw_ah, dict) else {}
    home_line = _number(ah.get("home_line") or ah.get("line"))
    home_price = _number(ah.get("home_price"))
    away_price = _number(ah.get("away_price"))
    if home_line is None or home_price is None or away_price is None:
        return _watch("MISSING_AH_MARKET")
    prices = {"HOME": home_price, "AWAY": away_price}
    devig = _devig_probabilities(prices)
    home_model = _market_side_probability(simulation, "HOME", home_line)
    away_model = _market_side_probability(simulation, "AWAY", -home_line)
    candidates = [
        ("HOME", home_model - devig["HOME"], home_model, home_line, home_price),
        ("AWAY", away_model - devig["AWAY"], away_model, -home_line, away_price),
    ]
    side, edge, model_probability, line, price = max(candidates, key=lambda item: item[1])
    if edge < FORMAL_EDGE_THRESHOLD:
        return _watch("EDGE_BELOW_FORMAL_THRESHOLD")
    factor_side = _factor_leader(pricing_shadow)
    reverse = factor_side in {"HOME", "AWAY"} and factor_side != side
    fair_side = _fair_side(simulation)
    if side != fair_side and not reverse:
        return _watch("SIMULATION_DIRECTION_CONTRADICTION")
    reason = _reason(
        side=side,
        reverse=reverse,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        fair_ah=simulation.fair_ah,
        market_line=line,
        edge=edge,
        model_probability=model_probability,
        devig_probability=devig[side],
    )
    recommendation = {
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "market_label_cn": "让球",
        "selection": f"{side}_AH",
        "selection_label_cn": _selection_label(side, home_team_name, away_team_name),
        "line": _format_line(line),
        "odds": _format_price(price),
        "model_probability": round(model_probability, 6),
        "fair_odds": _format_price(1 / model_probability) if model_probability > 0 else None,
        "risk_adjusted_ev": _format_edge(edge),
        "confidence": round(min(max(0.50 + edge, 0.0), 0.92), 4),
        "confidence_label": "策略自洽",
        "reasons": [reason],
        "risks": ["阵容、红牌、临场跳线会改变赛前判断。"],
        "value_explanation": reason,
        "reverse_factor_value": reverse,
        "devig_probability": round(devig[side], 6),
        "candidate": False,
        "formal_recommendation": True,
        "beats_market_required": False,
    }
    if not enabled:
        return FormalRecommendationResult(
            tier="WATCH",
            recommendation=None,
            formal_eligible=True,
            formal_suppressed=True,
            formal_suppressed_reason="W2_FORMAL_RECOMMENDATION_ENABLED=false",
            blockers=[],
        )
    return FormalRecommendationResult(
        tier="FORMAL",
        recommendation=recommendation,
        formal_eligible=True,
        formal_suppressed=False,
        formal_suppressed_reason=None,
        blockers=[],
    )


def _blockers(
    *,
    fixture_status: str,
    simulation: SimulationOutput | None,
    current_odds: dict[str, Any] | None,
    pricing_shadow: dict[str, Any] | None,
    analysis_readiness: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    if str(fixture_status).upper() not in {"UPCOMING", "NS", "TBD"}:
        blockers.append("FIXTURE_NOT_PREMATCH")
    if simulation is None or simulation.status != READY:
        blockers.append("SIMULATION_NOT_READY")
    if not isinstance(current_odds, dict) or not isinstance(current_odds.get("ah"), dict):
        blockers.append("MISSING_AH_MARKET")
    signal_count = _number((pricing_shadow or {}).get("independent_signal_count"))
    if signal_count is None or signal_count < FORMAL_MIN_INDEPENDENT_SIGNALS:
        blockers.append("INSUFFICIENT_INDEPENDENT_SIGNALS")
    readiness_blockers = []
    if isinstance(analysis_readiness, dict):
        readiness_blockers = [
            str(item)
            for item in analysis_readiness.get("blockers", [])
            if str(item) in {"AS_OF_BLOCKED", "LEAKAGE_BLOCKED"}
        ]
    blockers.extend(readiness_blockers)
    return blockers


def _watch(reason: str) -> FormalRecommendationResult:
    return FormalRecommendationResult(
        tier="WATCH",
        recommendation=None,
        formal_eligible=False,
        formal_suppressed=False,
        formal_suppressed_reason=None,
        blockers=[reason],
    )


def _market_side_probability(simulation: SimulationOutput, side: str, line: float) -> float:
    ladder = (
        simulation.ah_probabilities.get("ladder")
        if isinstance(simulation.ah_probabilities, dict)
        else None
    )
    lookup_line = line if side == "HOME" else -line
    if isinstance(ladder, list):
        for row in ladder:
            if not isinstance(row, dict):
                continue
            row_line = _number(row.get("home_line"))
            if row_line is None or abs(row_line - lookup_line) > 0.001:
                continue
            home_cover = _number(row.get("home_cover"))
            if home_cover is None:
                break
            return home_cover if side == "HOME" else round(1 - home_cover, 6)
    fair = _number(simulation.fair_ah) or 0.0
    if side == "HOME":
        return 0.5 + max(min((line - fair) * 0.08, 0.18), -0.18)
    return 0.5 + max(min((fair - line) * 0.08, 0.18), -0.18)


def _devig_probabilities(prices: dict[str, float]) -> dict[str, float]:
    implied = {side: 1 / price for side, price in prices.items() if price > 1}
    total = sum(implied.values()) or 1.0
    return {side: probability / total for side, probability in implied.items()}


def _factor_leader(pricing_shadow: dict[str, Any] | None) -> str:
    score = pricing_shadow.get("team_score") if isinstance(pricing_shadow, dict) else None
    if not isinstance(score, dict):
        return "UNKNOWN"
    home = _number(score.get("home"))
    away = _number(score.get("away"))
    if home is None or away is None:
        return "UNKNOWN"
    if abs(home - away) < 0.05:
        return "NEUTRAL"
    return "HOME" if home > away else "AWAY"


def _fair_side(simulation: SimulationOutput) -> str:
    fair = simulation.fair_ah
    if fair is None or abs(fair) < 0.25:
        return "NEUTRAL"
    return "HOME" if fair < 0 else "AWAY"


def _reason(
    *,
    side: str,
    reverse: bool,
    home_team_name: str,
    away_team_name: str,
    fair_ah: float | None,
    market_line: float,
    edge: float,
    model_probability: float,
    devig_probability: float,
) -> str:
    team = home_team_name if side == "HOME" else away_team_name
    base = (
        f"模拟公平盘 { _format_line(fair_ah) }，市场盘 { _format_line(market_line) }，"
        f"{team} 覆盖概率 {round(model_probability * 100)}% 高于 devig 基准 "
        f"{round(devig_probability * 100)}%，value gap {round(edge * 100)}pct。"
    )
    if reverse:
        return f"盘口价值：{base} 因子方向与价格方向不同，按价格/value 输出。"
    return base


def _selection_label(side: str, home_team_name: str, away_team_name: str) -> str:
    return f"{home_team_name} 让球" if side == "HOME" else f"{away_team_name} 让球"


def _format_line(value: float | None) -> str | None:
    if value is None:
        return None
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _format_price(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{float(value):.2f}"


def _format_edge(value: float) -> str:
    return f"{round(value * 100, 2)}pct"


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
