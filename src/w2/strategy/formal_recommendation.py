from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from w2.strategy.simulate import (
    READY,
    SimulationOutput,
    ah_expected_value,
    ah_expected_value_uncertainty_from_lambdas,
)

FORMAL_EV_THRESHOLD = 0.035
REVERSE_FACTOR_EV_THRESHOLD = 0.08
FORMAL_MIN_INDEPENDENT_SIGNALS = 3
AH_PRICE_MIN = 1.40
AH_PRICE_MAX = 4.00
AH_IMPLIED_SUM_MIN = 0.98
AH_IMPLIED_SUM_MAX = 1.30
AH_MAX_PRICE_GAP = 0.90


@dataclass(frozen=True, kw_only=True)
class CanonicalAhMarket:
    home_line: float
    away_line: float
    home_price: float
    away_price: float
    source: str | None
    as_of: str | None
    bookmaker_count: int | None
    validation_status: str
    blocker: str | None
    raw_home_line: float | None = None
    raw_away_line: float | None = None
    raw_abs_line: float | None = None
    canonical_home_line: float | None = None
    canonical_away_line: float | None = None
    line_normalization_status: str | None = None
    line_normalization_warning: str | None = None
    display_line_cn: str | None = None
    home_display_line_cn: str | None = None
    away_display_line_cn: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, kw_only=True)
class FormalRecommendationResult:
    tier: str
    recommendation: dict[str, Any] | None
    formal_eligible: bool
    formal_suppressed: bool
    formal_suppressed_reason: str | None
    blockers: list[str]
    canonical_ah_market: dict[str, Any] | None = None

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
    ah = canonical_ah_market(current_odds=current_odds, pricing_shadow=pricing_shadow)
    blockers = _blockers(
        fixture_status=fixture_status,
        simulation=simulation,
        canonical_market=ah,
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
            canonical_ah_market=ah.as_dict() if ah else None,
        )
    assert simulation is not None
    if ah is None or ah.validation_status != "READY":
        return _watch((ah.blocker if ah else None) or "MISSING_AH_MARKET", canonical_ah_market=ah)
    home_distribution, home_ev, home_ev_se = _settlement_distribution_with_ev_se(
        simulation,
        "HOME",
        ah.home_line,
        ah.home_price,
    )
    away_distribution, away_ev, away_ev_se = _settlement_distribution_with_ev_se(
        simulation,
        "AWAY",
        ah.away_line,
        ah.away_price,
    )
    if home_distribution is None or away_distribution is None:
        return _watch("MISSING_AH_SETTLEMENT_DISTRIBUTION", canonical_ah_market=ah)
    if home_ev is None or away_ev is None:
        return _watch("INVALID_AH_EV_INPUTS", canonical_ah_market=ah)
    home_model = _effective_cover_probability(home_distribution)
    away_model = _effective_cover_probability(away_distribution)
    if home_model is None or away_model is None:
        return _watch("INVALID_AH_SETTLEMENT_DISTRIBUTION", canonical_ah_market=ah)
    prices = {"HOME": ah.home_price, "AWAY": ah.away_price}
    devig = _devig_probabilities(prices)
    candidates = [
        ("HOME", home_ev, home_ev_se, home_model, ah.home_line, ah.home_price, home_distribution),
        ("AWAY", away_ev, away_ev_se, away_model, ah.away_line, ah.away_price, away_distribution),
    ]
    side, ev, ev_se, model_probability, line, price, distribution = max(
        candidates,
        key=lambda item: item[1],
    )
    if ev < FORMAL_EV_THRESHOLD:
        return _watch("AH_EV_BELOW_FORMAL_THRESHOLD", canonical_ah_market=ah)
    factor_side = _factor_leader(pricing_shadow)
    reverse = is_reverse_value_recommendation(
        selected_side=side,
        fair_ah=simulation.fair_ah,
        score_matrix_summary=simulation.score_matrix_summary,
        factor_side=factor_side,
    )
    fair_side = _fair_side(simulation)
    if not _direction_supported(side=side, fair_side=fair_side, reverse=reverse):
        return _watch("SIMULATION_DIRECTION_CONTRADICTION", canonical_ah_market=ah)
    if reverse and not _reverse_value_supported(line=line, expected_value=ev):
        return _watch("REVERSE_FACTOR_VALUE_NOT_STRONG_ENOUGH", canonical_ah_market=ah)
    if _scoreline_winner(simulation) not in {side, "NEUTRAL"} and not reverse:
        return _watch("SCORELINE_DIRECTION_CONTRADICTION", canonical_ah_market=ah)
    reason = _reason(
        side=side,
        reverse=reverse,
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        fair_ah=simulation.fair_ah,
        market_line=line,
        expected_value=ev,
        model_probability=model_probability,
        devig_probability=devig[side],
    )
    recommendation = {
        "tier": "FORMAL",
        "market": "ASIAN_HANDICAP",
        "market_label_cn": "让球",
        "selection": f"{side}_AH",
        "selection_label_cn": _selection_label(
            side,
            home_team_name,
            away_team_name,
            line,
        ),
        "line": _format_line(line),
        "odds": _format_price(price),
        "model_probability": round(model_probability, 6),
        "fair_odds": _format_price(1 / model_probability) if model_probability > 0 else None,
        "risk_adjusted_ev": _format_edge(ev),
        "expected_value": round(ev, 6),
        "ev_se": ev_se,
        "ah_settlement_distribution": distribution,
        "confidence": round(min(max(0.50 + ev, 0.0), 0.92), 4),
        "confidence_label": "策略自洽",
        "reasons": [reason],
        "risks": ["阵容、红牌、临场跳线会改变赛前判断。"],
        "value_explanation": reason,
        "reverse_factor_value": reverse,
        "devig_probability": round(devig[side], 6),
        "canonical_ah_market": ah.as_dict(),
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
            canonical_ah_market=ah.as_dict(),
        )
    return FormalRecommendationResult(
        tier="FORMAL",
        recommendation=recommendation,
        formal_eligible=True,
        formal_suppressed=False,
        formal_suppressed_reason=None,
        blockers=[],
        canonical_ah_market=ah.as_dict(),
    )

def _blockers(
    *,
    fixture_status: str,
    simulation: SimulationOutput | None,
    canonical_market: CanonicalAhMarket | None,
    pricing_shadow: dict[str, Any] | None,
    analysis_readiness: dict[str, Any] | None,
) -> list[str]:
    blockers: list[str] = []
    if str(fixture_status).upper() not in {"UPCOMING", "NS", "TBD"}:
        blockers.append("FIXTURE_NOT_PREMATCH")
    if simulation is None or simulation.status != READY:
        blockers.append("SIMULATION_NOT_READY")
    if canonical_market is None:
        blockers.append("MISSING_AH_MARKET")
    elif canonical_market.validation_status != "READY":
        blockers.append(canonical_market.blocker or "INVALID_AH_MARKET")
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


def canonical_ah_market(
    *,
    current_odds: dict[str, Any] | None,
    pricing_shadow: dict[str, Any] | None,
) -> CanonicalAhMarket | None:
    odds = current_odds if isinstance(current_odds, dict) else {}
    raw_ah = odds.get("ah")
    ah: dict[str, Any] = raw_ah if isinstance(raw_ah, dict) else {}
    pricing = pricing_shadow if isinstance(pricing_shadow, dict) else {}
    raw_home_line = _number(ah.get("home_line"))
    raw_away_line = _number(ah.get("away_line"))
    raw_abs_line = _number(ah.get("line"))
    market_ah = _number(pricing.get("market_ah"))
    home_line = market_ah if market_ah is not None else raw_home_line
    away_line = -home_line if home_line is not None else None
    home_price = _number(ah.get("home_price"))
    away_price = _number(ah.get("away_price"))
    source = str(ah.get("source")) if ah.get("source") is not None else None
    as_of = str(ah.get("as_of") or ah.get("captured_at") or ah.get("locked_at") or "") or None
    bookmaker_count = _int_or_none(ah.get("bookmaker_count"))
    if home_line is None or away_line is None or home_price is None or away_price is None:
        return None
    display = ah_display_contract(home_line)
    blocker = _canonical_ah_blocker(
        home_line=home_line,
        away_line=away_line,
        raw_home_line=raw_home_line,
        raw_away_line=raw_away_line,
        raw_abs_line=raw_abs_line,
        home_price=home_price,
        away_price=away_price,
        market_ah=market_ah,
    )
    warning = _canonical_ah_line_warning(
        canonical_home_line=home_line,
        raw_home_line=raw_home_line,
        raw_away_line=raw_away_line,
    )
    return CanonicalAhMarket(
        home_line=home_line,
        away_line=away_line,
        home_price=home_price,
        away_price=away_price,
        raw_home_line=raw_home_line,
        raw_away_line=raw_away_line,
        raw_abs_line=raw_abs_line,
        canonical_home_line=home_line,
        canonical_away_line=away_line,
        line_normalization_status="BLOCKED" if blocker else "READY",
        line_normalization_warning=warning,
        display_line_cn=display["display_line_cn"],
        home_display_line_cn=display["home_display_line_cn"],
        away_display_line_cn=display["away_display_line_cn"],
        source=source,
        as_of=as_of,
        bookmaker_count=bookmaker_count,
        validation_status="BLOCKED" if blocker else "READY",
        blocker=blocker,
    )


def ah_display_contract(home_line: float | int | str | None) -> dict[str, str | None]:
    canonical_home_line = _number(home_line)
    if canonical_home_line is None:
        return {
            "display_line_cn": None,
            "home_display_line_cn": None,
            "away_display_line_cn": None,
        }
    home_display = f"主队 {_format_signed_line(canonical_home_line)}"
    away_display = f"客队 {_format_signed_line(-canonical_home_line)}"
    if abs(canonical_home_line) < 0.005:
        display = "平手 0"
    elif canonical_home_line < 0:
        display = f"主队 -{_format_abs_line(canonical_home_line)}"
    else:
        display = f"客队 -{_format_abs_line(canonical_home_line)}"
    return {
        "display_line_cn": display,
        "home_display_line_cn": home_display,
        "away_display_line_cn": away_display,
    }


def _format_signed_line(value: float) -> str:
    if abs(value) < 0.005:
        return "0"
    sign = "+" if value > 0 else "-"
    return f"{sign}{_format_abs_line(value)}"


def _format_abs_line(value: float) -> str:
    text = f"{abs(float(value)):.2f}"
    return text.rstrip("0").rstrip(".")


def _watch(
    reason: str,
    *,
    canonical_ah_market: CanonicalAhMarket | None = None,
) -> FormalRecommendationResult:
    return FormalRecommendationResult(
        tier="WATCH",
        recommendation=None,
        formal_eligible=False,
        formal_suppressed=False,
        formal_suppressed_reason=None,
        blockers=[reason],
        canonical_ah_market=canonical_ah_market.as_dict() if canonical_ah_market else None,
    )


def _settlement_distribution_from_ladder(
    simulation: SimulationOutput,
    side: str,
    line: float,
) -> dict[str, Any] | None:
    ladder = (
        simulation.ah_probabilities.get("ladder")
        if isinstance(simulation.ah_probabilities, dict)
        else None
    )
    if isinstance(ladder, list):
        for row in ladder:
            if not isinstance(row, dict):
                continue
            row_line = _number(row.get("home_line"))
            if row_line is None or abs(row_line - (line if side == "HOME" else -line)) > 0.001:
                continue
            key = (
                "home_settlement_distribution"
                if side == "HOME"
                else "away_settlement_distribution"
            )
            distribution = row.get(key)
            if isinstance(distribution, dict):
                return distribution
    return None


def _settlement_distribution_with_ev_se(
    simulation: SimulationOutput,
    side: str,
    line: float,
    price: float,
) -> tuple[dict[str, Any] | None, float | None, float | None]:
    ladder_distribution = _settlement_distribution_from_ladder(simulation, side, line)
    scenario_distribution, scenario_ev, ev_se = ah_expected_value_uncertainty_from_lambdas(
        lambda_home=simulation.lambda_home,
        lambda_away=simulation.lambda_away,
        lambda_sigma_home=simulation.lambda_sigma_home or 0.0,
        lambda_sigma_away=simulation.lambda_sigma_away or 0.0,
        rho=_simulation_rho(simulation),
        selection=side,
        line=line,
        decimal_price=price,
    )
    if ladder_distribution is not None:
        return (
            ladder_distribution,
            ah_expected_value(ladder_distribution, decimal_price=price),
            ev_se,
        )
    return scenario_distribution, scenario_ev, ev_se


def _simulation_rho(simulation: SimulationOutput) -> float:
    calibration = simulation.calibration if isinstance(simulation.calibration, dict) else {}
    params = calibration.get("params")
    if not isinstance(params, dict):
        return 0.0
    return _number(params.get("dixon_coles_rho")) or 0.0


def _effective_cover_probability(distribution: dict[str, Any]) -> float | None:
    win = _number(distribution.get("WIN")) or 0.0
    half_win = _number(distribution.get("HALF_WIN")) or 0.0
    push = _number(distribution.get("PUSH")) or 0.0
    half_loss = _number(distribution.get("HALF_LOSS")) or 0.0
    loss = _number(distribution.get("LOSS")) or 0.0
    total = win + half_win + push + half_loss + loss
    if abs(total - 1.0) > 0.02:
        return None
    return round(win + half_win * 0.5 + push * 0.5, 6)


def _devig_probabilities(prices: dict[str, float]) -> dict[str, float]:
    implied = {side: 1 / price for side, price in prices.items() if price > 1}
    total = sum(implied.values()) or 1.0
    return {side: probability / total for side, probability in implied.items()}


def _canonical_ah_blocker(
    *,
    home_line: float,
    away_line: float,
    raw_home_line: float | None,
    raw_away_line: float | None,
    raw_abs_line: float | None,
    home_price: float,
    away_price: float,
    market_ah: float | None,
) -> str | None:
    if raw_abs_line is not None and abs(abs(raw_abs_line) - abs(home_line)) > 0.001:
        return "AH_MARKET_ABS_LINE_MISMATCH"
    if raw_home_line is not None and abs(abs(raw_home_line) - abs(home_line)) > 0.001:
        return "AH_MARKET_HOME_LINE_MAGNITUDE_MISMATCH"
    if raw_away_line is not None and abs(abs(raw_away_line) - abs(home_line)) > 0.001:
        return "AH_MARKET_LINE_MAGNITUDE_MISMATCH"
    if market_ah is not None and abs(home_line - market_ah) > 0.001:
        return "AH_MARKET_LINE_NOT_CANONICAL"
    if not _is_quarter_line(home_line) or not _is_quarter_line(away_line):
        return "AH_MARKET_LINE_NOT_QUARTER"
    if not (
        AH_PRICE_MIN <= home_price <= AH_PRICE_MAX
        and AH_PRICE_MIN <= away_price <= AH_PRICE_MAX
    ):
        return "AH_MARKET_PRICE_OUT_OF_RANGE"
    if abs(home_price - away_price) > AH_MAX_PRICE_GAP:
        return "AH_MARKET_PRICE_GAP_TOO_WIDE"
    implied_sum = (1 / home_price) + (1 / away_price)
    if implied_sum < AH_IMPLIED_SUM_MIN or implied_sum > AH_IMPLIED_SUM_MAX:
        return "AH_MARKET_UNDERROUND_OR_OVERROUND"
    return None


def _canonical_ah_line_warning(
    *,
    canonical_home_line: float,
    raw_home_line: float | None,
    raw_away_line: float | None,
) -> str | None:
    if raw_home_line is not None:
        if abs(abs(raw_home_line) - abs(canonical_home_line)) > 0.001:
            return None
        if abs(raw_home_line - canonical_home_line) > 0.001:
            return "AH_RAW_HOME_LINE_SIGN_NORMALIZED"
    canonical_away_line = -canonical_home_line
    if raw_away_line is None:
        return None
    if abs(abs(raw_away_line) - abs(canonical_home_line)) > 0.001:
        return None
    if abs(raw_away_line - canonical_away_line) > 0.001:
        return "AH_RAW_AWAY_LINE_SIGN_NORMALIZED"
    return None


def _is_quarter_line(line: float) -> bool:
    return abs(line * 4 - round(line * 4)) < 0.001


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


def is_reverse_value_recommendation(
    *,
    selected_side: str,
    fair_ah: float | None,
    score_matrix_summary: dict[str, Any] | None,
    factor_side: str = "UNKNOWN",
    min_direction_margin: float = 0.03,
) -> bool:
    fair_side = _side_from_fair_ah(fair_ah, min_line=0.25)
    scoreline_side = _scoreline_dominant_side(
        score_matrix_summary,
        min_direction_margin=min_direction_margin,
    )
    return any(
        side in {"HOME", "AWAY"} and side != selected_side
        for side in (factor_side, fair_side, scoreline_side)
    )


def _side_from_fair_ah(fair_ah: float | None, *, min_line: float) -> str:
    if fair_ah is None or abs(fair_ah) < min_line:
        return "NEUTRAL"
    return "HOME" if fair_ah < 0 else "AWAY"


def _fair_side(simulation: SimulationOutput) -> str:
    return _side_from_fair_ah(simulation.fair_ah, min_line=0.25)


def _direction_supported(*, side: str, fair_side: str, reverse: bool) -> bool:
    if reverse:
        return True
    if fair_side == "NEUTRAL":
        return True
    return side == fair_side


def _reverse_value_supported(*, line: float, expected_value: float) -> bool:
    return line > 0 and expected_value >= REVERSE_FACTOR_EV_THRESHOLD


def _scoreline_winner(simulation: SimulationOutput) -> str:
    return _scoreline_dominant_side(simulation.score_matrix_summary, min_direction_margin=0.08)


def _scoreline_dominant_side(
    score_matrix_summary: dict[str, Any] | None,
    *,
    min_direction_margin: float,
) -> str:
    summary = (
        score_matrix_summary
        if isinstance(score_matrix_summary, dict)
        else {}
    )
    home = _number(summary.get("home_win"))
    away = _number(summary.get("away_win"))
    if home is None or away is None:
        return "NEUTRAL"
    if abs(home - away) < min_direction_margin:
        return "NEUTRAL"
    return "HOME" if home > away else "AWAY"


def _reason(
    *,
    side: str,
    reverse: bool,
    home_team_name: str,
    away_team_name: str,
    fair_ah: float | None,
    market_line: float,
    expected_value: float,
    model_probability: float,
    devig_probability: float,
) -> str:
    team = home_team_name if side == "HOME" else away_team_name
    base = (
        f"模拟公平盘 { _format_line(fair_ah) }，市场盘 { _format_line(market_line) }，"
        f"{team} 亚洲让球结算期望为 {round(expected_value * 100)}pct；"
        f"有效覆盖概率 {round(model_probability * 100)}%，市场基准 "
        f"{round(devig_probability * 100)}%。"
    )
    if reverse:
        return (
            f"盘口价值逆因子：{base} "
            "模拟比分和因子方向不完全同向，但受让盘口 EV 达标，仅按同源主线价格输出。"
        )
    return base


def _selection_label(
    side: str,
    home_team_name: str,
    away_team_name: str,
    line: float,
) -> str:
    team = home_team_name if side == "HOME" else away_team_name
    if abs(line) < 0.001:
        return f"{team} 平手"
    return f"{team} 让球" if line < 0 else f"{team} 受让"


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


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
