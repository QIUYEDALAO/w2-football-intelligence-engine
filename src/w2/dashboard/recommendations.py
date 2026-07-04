from __future__ import annotations

from enum import StrEnum
from typing import Any

from w2.domain.decision_policy import compute_outcome_tracked
from w2.domain.enums import DecisionTier
from w2.domain.legacy_decision_shim import legacy_decision_view


class RecommendationTier(StrEnum):
    """Deprecated dashboard compatibility view; DecisionTier is the source of truth."""

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
    decision_tier = _decision_tier_from_payload(card, market)
    if decision_tier is not None:
        return _recommendation_tier_from_decision_tier(decision_tier)

    # Historical compatibility only. New DecisionCard output must provide
    # decision_tier instead of asking dashboard to infer product semantics from
    # formal_recommendation/candidate/decision/analysis_decision.
    legacy = legacy_decision_view(card, market)
    if legacy.legacy_formal and legacy.lock_eligible:
        return RecommendationTier.FORMAL
    return _recommendation_tier_from_decision_tier(legacy.decision_tier)


def build_recommendation(
    card: dict[str, Any],
    market: dict[str, Any] | None,
) -> dict[str, Any] | None:
    tier = derive_recommendation_tier(card, market)
    decision_tier = _decision_tier_for_output(card, market, tier)
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

    recommendation = {
        "tier": tier.value,
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
        "candidate": truthy(card.get("candidate")) or truthy(market.get("candidate")),
        "formal_recommendation": truthy(card.get("formal_recommendation"))
        or truthy(market.get("formal_recommendation")),
    }
    if tier is not RecommendationTier.FORMAL:
        return _non_formal_recommendation_shell(recommendation)
    return recommendation


def _non_formal_recommendation_shell(recommendation: dict[str, Any]) -> dict[str, Any]:
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
    stripped["candidate"] = False
    stripped["formal_recommendation"] = False
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


def _recommendation_tier_from_decision_tier(decision_tier: DecisionTier) -> RecommendationTier:
    if decision_tier is DecisionTier.RECOMMEND:
        return RecommendationTier.FORMAL
    if decision_tier is DecisionTier.ANALYSIS_PICK:
        return RecommendationTier.ANALYSIS_PICK
    if decision_tier is DecisionTier.WATCH:
        return RecommendationTier.WATCH
    return RecommendationTier.NO_RECOMMENDATION


def _decision_tier_for_output(
    card: dict[str, Any],
    market: dict[str, Any] | None,
    tier: RecommendationTier,
) -> DecisionTier:
    decision_tier = _decision_tier_from_payload(card, market)
    if decision_tier is not None:
        return decision_tier
    if tier is RecommendationTier.FORMAL:
        return legacy_decision_view(card, market).decision_tier
    if tier is RecommendationTier.ANALYSIS_PICK:
        return DecisionTier.ANALYSIS_PICK
    if tier is RecommendationTier.WATCH:
        return DecisionTier.WATCH
    return DecisionTier.SKIP
