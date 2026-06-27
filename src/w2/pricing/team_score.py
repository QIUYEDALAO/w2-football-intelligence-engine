from __future__ import annotations

from typing import Any

ALLOWED_INDEPENDENT_FACTORS = frozenset(
    {
        "F3_REST_FITNESS",
        "F4_MATCH_IMPORTANCE",
        "F5_RECENT_AH_COVER",
        "F6_H2H",
        "F7_STRENGTH_FORM",
        "F8_SQUAD_VALUE",
        "F9_TRUE_XG",
    }
)
AUTHORITATIVE_SIGNAL_GROUPS = frozenset(
    {"xg", "team_fixture_history", "h2h", "squad_value", "ratings"}
)
REQUIRED_SIGNAL_GROUPS = ("xg", "team_fixture_history", "h2h", "squad_value", "ratings")
NON_SCORING_GROUPS = frozenset({"match_importance"})


def independent_team_scores(
    *,
    feature_contributions: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> dict[str, Any]:
    all_factors = [
        _factor(item)
        for item in feature_contributions or []
        if _factor_id(item) in ALLOWED_INDEPENDENT_FACTORS
    ]
    factors = [factor for factor in all_factors if factor["status"] == "READY"]
    scoring_factors = [
        factor
        for factor in factors
        if factor["is_independent_signal"] is True
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
    return {
        "home_score": _weighted_score(scoring_factors, side="HOME"),
        "away_score": _weighted_score(scoring_factors, side="AWAY"),
        "factors": factors,
        "coverage": coverage,
        "independent_signal_count": len(signal_groups),
        "independent_signal_groups": signal_groups,
        "xg_derived_factor_count": sum(1 for factor in factors if factor["source_group"] == "xg"),
        "missing_independent_sources": [
            group for group in REQUIRED_SIGNAL_GROUPS if group not in signal_groups
        ],
        "factor_source_summary": source_summary,
    }


def _factor(item: dict[str, Any]) -> dict[str, Any]:
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
        "is_independent_signal": bool(item.get("is_independent_signal") is True),
        "proxy_of": _optional_text(item.get("proxy_of")),
        "collection_status": _optional_text(item.get("collection_status")) or "READY",
        "inputs": item.get("inputs") if isinstance(item.get("inputs"), dict) else {},
    }


def _factor_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("feature_id") or "")


def _weighted_score(factors: list[dict[str, Any]], *, side: str) -> float:
    total = 0.0
    for factor in factors:
        if factor["source_group"] in NON_SCORING_GROUPS:
            continue
        score = float(factor["score"])
        weight = float(factor["weight"])
        if factor["side"] == side:
            total += weight * score
        elif factor["side"] == "NEUTRAL":
            total += weight * score * 0.5
    return round(total, 6)


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
