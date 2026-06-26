from __future__ import annotations

from enum import StrEnum
from typing import Any


class RecommendationTier(StrEnum):
    FORMAL = "FORMAL"
    CANDIDATE = "CANDIDATE"
    ANALYSIS_PICK = "ANALYSIS_PICK"
    WATCH = "WATCH"
    NO_RECOMMENDATION = "NO_RECOMMENDATION"


MARKET_LABELS_CN = {
    "ASIAN_HANDICAP": "让球",
    "TOTALS": "大小球",
    "FIRST_HALF_GOALS": "半场进球",
    "SCORE": "比分",
}


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False


def derive_recommendation_tier(
    card: dict[str, Any],
    market: dict[str, Any] | None,
) -> RecommendationTier:
    if truthy(card.get("formal_recommendation")) or (
        market is not None and truthy(market.get("formal_recommendation"))
    ):
        return RecommendationTier.FORMAL
    if truthy(card.get("candidate")) or (
        market is not None and truthy(market.get("candidate"))
    ):
        return RecommendationTier.CANDIDATE
    if market is not None:
        decision = str(market.get("decision") or "").upper()
        analysis_decision = str(market.get("analysis_decision") or "").upper()
        if decision == "PICK" or analysis_decision == "ANALYSIS_PICK":
            return RecommendationTier.ANALYSIS_PICK
        if decision == "WATCH" or analysis_decision == "WATCH":
            return RecommendationTier.WATCH
    card_decision = str(card.get("decision") or "").upper()
    if card_decision == "WATCH":
        return RecommendationTier.WATCH
    return RecommendationTier.NO_RECOMMENDATION


def build_recommendation(
    card: dict[str, Any],
    market: dict[str, Any] | None,
) -> dict[str, Any] | None:
    tier = derive_recommendation_tier(card, market)
    if market is None or tier in {
        RecommendationTier.WATCH,
        RecommendationTier.NO_RECOMMENDATION,
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

    return {
        "tier": tier.value,
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
        "candidate": truthy(card.get("candidate")) or truthy(market.get("candidate")),
        "formal_recommendation": truthy(card.get("formal_recommendation"))
        or truthy(market.get("formal_recommendation")),
    }


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

