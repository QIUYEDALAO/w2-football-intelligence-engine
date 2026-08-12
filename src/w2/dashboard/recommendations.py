from __future__ import annotations

from typing import Any

from w2.domain.decision_policy import compute_outcome_tracked
from w2.domain.enums import DecisionTier

MARKET_LABELS_CN = {
    "ASIAN_HANDICAP": "让球",
    "TOTALS": "大小球",
    "FIRST_HALF_GOALS": "半场进球",
    "SCORE": "比分",
}


def build_recommendation(
    card: dict[str, Any],
    market: dict[str, Any] | None,
) -> dict[str, Any] | None:
    decision_tier = _decision_tier_from_payload(card, market)
    if market is None or decision_tier not in {
        DecisionTier.ANALYSIS_PICK,
        DecisionTier.RECOMMEND,
    }:
        return None

    market_code = str(market.get("market") or "")
    reasons = _string_list(market.get("reasons"))
    if not reasons:
        reason = market.get("reason_cn") or market.get("reason")
        reasons = [str(reason)] if reason else ["多因素输入已纳入。"]
    risks = _string_list(market.get("risks_cn") or market.get("risks"))
    if not risks:
        risks = _string_list(card.get("risks_cn") or card.get("risks"))

    recommendation = {
        "decision_tier": decision_tier.value,
        "outcome_tracked": card.get("outcome_tracked", compute_outcome_tracked(decision_tier)),
        "lock_eligible": card.get("lock_eligible"),
        "market": market_code,
        "market_label_cn": market.get("label_cn")
        or MARKET_LABELS_CN.get(market_code)
        or market_code,
        "selection": market.get("tendency") or market.get("lean"),
        "selection_label_cn": market.get("lean_cn") or market.get("lean"),
        "line": _optional_string(market.get("line")),
        "odds": _optional_string(market.get("odds")),
        "hong_kong_odds": _optional_string(market.get("hong_kong_odds")),
        "model_probability": _optional_number(market.get("model_probability")),
        "fair_odds": _optional_string(market.get("fair_odds")),
        "risk_adjusted_ev": _optional_string(market.get("risk_adjusted_ev")),
        "confidence": _optional_number(market.get("confidence")),
        "reasons": reasons,
        "risks": risks,
        "generated_at": card.get("generated_at"),
        "locked_before_kickoff": market.get("locked_before_kickoff"),
        "is_live_line": market.get("is_live_line"),
    }
    if decision_tier is not DecisionTier.RECOMMEND:
        return _display_only_recommendation_view(recommendation)
    return recommendation


def _display_only_recommendation_view(recommendation: dict[str, Any]) -> dict[str, Any]:
    """Keep analysis metadata, but never expose actionable direction fields."""
    stripped = dict(recommendation)
    for key in (
        "selection",
        "selection_label_cn",
        "line",
        "odds",
        "hong_kong_odds",
        "model_probability",
        "fair_odds",
        "risk_adjusted_ev",
        "expected_value",
        "ev_se",
        "reasons",
        "risks",
        "value_explanation",
        "value_explanation_cn",
        "explanation",
        "explanation_cn",
    ):
        stripped.pop(key, None)
    return stripped


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _decision_tier_from_payload(
    card: dict[str, Any],
    market: dict[str, Any] | None,
) -> DecisionTier | None:
    for value in (card.get("decision_tier"), market.get("decision_tier") if market else None):
        if value is None:
            continue
        try:
            return value if isinstance(value, DecisionTier) else DecisionTier(str(value))
        except ValueError:
            return None
    return None
