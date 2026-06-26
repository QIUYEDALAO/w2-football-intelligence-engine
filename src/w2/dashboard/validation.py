from __future__ import annotations

from decimal import InvalidOperation
from typing import Any

from w2.dashboard.recommendations import RecommendationTier
from w2.settlement.settle import WIN_UNITS, settle_market

VALIDATED_TIERS = {
    RecommendationTier.FORMAL.value,
    RecommendationTier.CANDIDATE.value,
    RecommendationTier.ANALYSIS_PICK.value,
}


def validate_recommendation(
    *,
    fixture_id: str,
    recommendation: dict[str, Any] | None,
    result: dict[str, Any] | None,
    scoreline_picks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if result is None:
        return None
    if recommendation is None:
        return {
            "settlement": "NO_BET",
            "validation_notes": ["无正式/候选/分析倾向，不计入命中率。"],
        }
    tier = str(recommendation.get("tier") or "")
    if tier not in VALIDATED_TIERS:
        return {
            "settlement": "NO_BET",
            "validation_notes": [f"{tier or 'NO_RECOMMENDATION'} 不计入验证。"],
        }
    home_goals = _int_or_none(result.get("home_goals"))
    away_goals = _int_or_none(result.get("away_goals"))
    if home_goals is None or away_goals is None:
        return {
            "settlement": "UNKNOWN",
            "validation_notes": ["完场比分尚未归一化，无法结算。"],
        }

    notes: list[str] = []
    market = str(recommendation.get("market") or "")
    selection = _canonical_selection(market, recommendation)
    line = _line(recommendation.get("line"))
    settlement = "UNKNOWN"
    profit_units: float | None = None
    market_hit: bool | None = None
    total_goals_hit: bool | None = None
    if market in {"ASIAN_HANDICAP", "TOTALS", "ONE_X_TWO", "BTTS"} and selection:
        try:
            outcome = settle_market(
                market=market,
                selection=selection,
                line=line,
                home_goals_90=home_goals,
                away_goals_90=away_goals,
            )
            settlement = _settlement_label(outcome)
            profit_units = float(WIN_UNITS[outcome])
            market_hit = settlement == "HIT"
            if market == "TOTALS":
                total_goals_hit = market_hit
            notes.append("后端按 raw fixture final score 完成结算。")
        except (ValueError, InvalidOperation) as exc:
            notes.append(f"市场结算条件不足：{exc}")
    else:
        notes.append(f"{market or 'UNKNOWN'} 暂无可结算规则。")

    exact_hit, direction_hit = _score_hits(scoreline_picks, home_goals, away_goals)
    return {
        "settlement": settlement,
        "market_hit": market_hit,
        "score_exact_hit": exact_hit,
        "score_direction_hit": direction_hit,
        "total_goals_hit": total_goals_hit,
        "profit_units": profit_units,
        "closing_line_value": None,
        "validation_notes": notes,
        "tier": tier,
        "counted_in_official": tier
        in {RecommendationTier.FORMAL.value, RecommendationTier.CANDIDATE.value},
        "counted_in_analysis_shadow": tier == RecommendationTier.ANALYSIS_PICK.value,
        "fixture_id": fixture_id,
    }


def _canonical_selection(market: str, recommendation: dict[str, Any]) -> str | None:
    raw = str(
        recommendation.get("selection")
        or recommendation.get("selection_label_cn")
        or ""
    ).upper()
    label = str(recommendation.get("selection_label_cn") or "")
    if market == "ASIAN_HANDICAP":
        if "HOME" in raw or "主" in label:
            return "HOME"
        if "AWAY" in raw or "客" in label:
            return "AWAY"
    if market == "TOTALS":
        if "OVER" in raw or "大" in label:
            return "OVER"
        if "UNDER" in raw or "小" in label:
            return "UNDER"
    if market == "ONE_X_TWO":
        for selection in ("HOME", "DRAW", "AWAY"):
            if selection in raw:
                return selection
    if market == "BTTS":
        if "YES" in raw:
            return "YES"
        if "NO" in raw:
            return "NO"
    return None


def _line(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _settlement_label(outcome: str) -> str:
    if outcome in {"WIN", "HALF_WIN"}:
        return "HIT"
    if outcome in {"LOSS", "HALF_LOSS"}:
        return "MISS"
    if outcome == "PUSH":
        return "PUSH"
    return "UNKNOWN"


def _score_hits(
    scoreline_picks: list[dict[str, Any]],
    home_goals: int,
    away_goals: int,
) -> tuple[bool | None, bool | None]:
    if not scoreline_picks:
        return None, None
    final = f"{home_goals}-{away_goals}"
    exact = any(str(item.get("scoreline")) == final for item in scoreline_picks)
    actual_direction = _direction(home_goals, away_goals)
    direction = any(
        _direction(_int_or_none(item.get("home_goals")), _int_or_none(item.get("away_goals")))
        == actual_direction
        for item in scoreline_picks
    )
    return exact, direction


def _direction(home_goals: int | None, away_goals: int | None) -> str | None:
    if home_goals is None or away_goals is None:
        return None
    if home_goals > away_goals:
        return "HOME"
    if home_goals < away_goals:
        return "AWAY"
    return "DRAW"


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None

