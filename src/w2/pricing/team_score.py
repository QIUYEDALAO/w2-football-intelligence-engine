from __future__ import annotations

from typing import Any

from w2.domain.factor_registry import (
    ALLOWED_INDEPENDENT_FACTORS,
    AUTHORITATIVE_SIGNAL_GROUPS,
    NON_SCORING_GROUPS,
    REQUIRED_SIGNAL_GROUPS,
    factor_policy,
    is_scoring_factor,
)
from w2.pricing.scale import DEFAULT_FACTOR_SCALE_PARAMS, FactorScaleParams

# Re-exported for backward compatibility — w2.domain.factor_registry is the
# canonical source (see there for why); existing importers of these four
# names from this module keep working unchanged.
__all__ = [
    "ALLOWED_INDEPENDENT_FACTORS",
    "AUTHORITATIVE_SIGNAL_GROUPS",
    "NON_SCORING_GROUPS",
    "REQUIRED_SIGNAL_GROUPS",
    "independent_team_scores",
    "independent_team_scores_from_contributions",
]


def independent_team_scores(
    *,
    feature_contributions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
    scale: FactorScaleParams | None = None,
) -> dict[str, Any]:
    scale = scale or DEFAULT_FACTOR_SCALE_PARAMS
    all_factors = [
        _factor(item, scale=scale)
        for item in feature_contributions or []
        if _factor_id(item) in ALLOWED_INDEPENDENT_FACTORS
    ]
    factors = [factor for factor in all_factors if factor["status"] == "READY"]
    scoring_factors = [
        factor
        for factor in factors
        if is_scoring_factor(str(factor["id"]))
        and factor["is_independent_signal"] is True
        and str(factor["source_group"]) in AUTHORITATIVE_SIGNAL_GROUPS
    ]
    signal_groups = sorted(
        {
            str(factor["source_group"])
            for factor in scoring_factors
            if str(factor["source_group"]) in AUTHORITATIVE_SIGNAL_GROUPS
        }
    )
    source_summary = {
        factor["id"]: {
            "source": factor["source"],
            "source_group": factor["source_group"],
            "is_independent_signal": factor["is_independent_signal"],
            "proxy_of": factor["proxy_of"],
            "collection_status": factor["collection_status"],
        }
        for factor in all_factors
    }
    coverage = round(len(factors) / len(ALLOWED_INDEPENDENT_FACTORS), 6)
    score_meta = _weighted_scores(scoring_factors)
    weight_sum_used = float(score_meta["weight_sum_used"])
    scoring_factor_breakdown = [
        {
            "id": factor["id"],
            "side": factor["side"],
            "weight": factor["weight"],
            "score": factor["score"],
            "share": round(factor["weight"] / weight_sum_used, 6) if weight_sum_used > 0 else 0.0,
            "source": factor["source"],
            "source_group": factor["source_group"],
        }
        for factor in score_meta["scoring"]
    ]
    return {
        "home_score": score_meta["home_score"],
        "away_score": score_meta["away_score"],
        "factors": factors,
        "coverage": coverage,
        "independent_signal_count": len(signal_groups),
        "distinct_evidence_group_count": len(signal_groups),
        "threshold_validation_status": "POLICY_THRESHOLD_UNVALIDATED",
        "independent_signal_groups": signal_groups,
        "xg_derived_factor_count": sum(1 for factor in factors if factor["source_group"] == "xg"),
        "missing_independent_sources": [
            group for group in REQUIRED_SIGNAL_GROUPS if group not in signal_groups
        ],
        "factor_source_summary": source_summary,
        "weight_sum_used": score_meta["weight_sum_used"],
        "weight_sum_possible": score_meta["weight_sum_possible"],
        "factor_count_used": score_meta["factor_count_used"],
        "factor_scale": scale.snapshot(),
        # The exact set of factors whose weight/score actually entered
        # home_score/away_score, with each factor's share of weight_sum_used.
        # This is the canonical breakdown other consumers (e.g. the
        # recommendation-driving factor score) must reuse instead of
        # re-deriving the same eligibility filter independently.
        "scoring_factors": scoring_factor_breakdown,
    }


def independent_team_scores_from_contributions(
    contributions: Any,
    *,
    scale: FactorScaleParams | None = None,
) -> dict[str, Any]:
    """Same computation as `independent_team_scores`, but accepts
    `FeatureContribution` objects (e.g. `feature_set.contributions`) directly
    instead of pre-shaped dicts, so callers never need their own
    FeatureContribution -> dict conversion that could drift from this one."""
    return independent_team_scores(
        feature_contributions=[_contribution_to_dict(item) for item in contributions or []],
        scale=scale,
    )


def _contribution_to_dict(item: Any) -> dict[str, Any]:
    side = getattr(item, "side", None)
    status = getattr(item, "status", None)
    return {
        "id": getattr(item, "feature_id", None),
        "side": getattr(side, "value", side),
        "weight": getattr(item, "weight", 0.0),
        "score": getattr(item, "score", None),
        "status": getattr(status, "value", status),
        "source": getattr(item, "source", None),
        "source_group": getattr(item, "source_group", None),
        "is_independent_signal": getattr(item, "is_independent_signal", False),
        "proxy_of": getattr(item, "proxy_of", None),
        "collection_status": getattr(item, "collection_status", None),
        "inputs": getattr(item, "inputs", {}),
    }


def _factor(item: dict[str, Any], *, scale: FactorScaleParams) -> dict[str, Any]:
    policy = factor_policy(_factor_id(item))
    side = str(item.get("side") or "NEUTRAL")
    if side not in {"HOME", "AWAY", "NEUTRAL"}:
        side = "UNKNOWN"
    return {
        "id": _factor_id(item),
        "side": side,
        "weight": _number(item.get("weight")),
        "score": abs(max(min(_number(item.get("score")), 1.0), -1.0)),
        "status": str(item.get("status") or "UNKNOWN"),
        "source": _optional_text(item.get("source")),
        "source_group": _optional_text(item.get("source_group")),
        "is_independent_signal": bool(item.get("is_independent_signal") is True)
        and bool(policy.get("independent_evidence_eligible")),
        "proxy_of": _optional_text(item.get("proxy_of")),
        "collection_status": _optional_text(item.get("collection_status")) or "READY",
        "inputs": item.get("inputs") if isinstance(item.get("inputs"), dict) else {},
        "sigma": _sigma(item, side=side, scale=scale),
    }


def _factor_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("feature_id") or "")


def _weighted_scores(factors: list[dict[str, Any]]) -> dict[str, Any]:
    scoring = [
        factor
        for factor in factors
        if factor["source_group"] not in NON_SCORING_GROUPS and factor["weight"] > 0
    ]
    weight_sum_used = sum(float(factor["weight"]) for factor in scoring)
    if weight_sum_used <= 0:
        return {
            "home_score": 0.0,
            "away_score": 0.0,
            "weight_sum_used": 0.0,
            "weight_sum_possible": 0.0,
            "factor_count_used": 0,
            "scoring": [],
        }
    return {
        "home_score": _weighted_score(scoring, side="HOME", denominator=weight_sum_used),
        "away_score": _weighted_score(scoring, side="AWAY", denominator=weight_sum_used),
        "weight_sum_used": round(weight_sum_used, 6),
        "weight_sum_possible": round(
            sum(
                float(factor["weight"])
                for factor in factors
                if factor["source_group"] not in NON_SCORING_GROUPS
            ),
            6,
        ),
        "factor_count_used": len(scoring),
        "scoring": scoring,
    }


def _weighted_score(
    factors: list[dict[str, Any]],
    *,
    side: str,
    denominator: float,
) -> float:
    total = 0.0
    for factor in factors:
        score = float(factor["score"])
        weight = float(factor["weight"])
        if factor["side"] == side:
            total += weight * score
        elif factor["side"] == "NEUTRAL":
            total += weight * score * 0.5
    return round(total / denominator, 6)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text or None


def _sigma(item: dict[str, Any], *, side: str, scale: FactorScaleParams) -> float:
    explicit = item.get("sigma")
    if explicit is not None:
        return _number(explicit)
    if (
        _optional_text(item.get("proxy_of"))
        or str(item.get("collection_status") or "").upper() == "PROXY_ONLY"
    ):
        return scale.factor_sigma_proxy
    if side == "NEUTRAL":
        return scale.factor_sigma_neutral
    if side == "UNKNOWN":
        return scale.factor_sigma_unknown
    return scale.factor_sigma_default
