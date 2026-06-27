from __future__ import annotations

from typing import Any

from w2.pricing.supremacy import fair_handicap_from_supremacy, fair_total_from_coverage
from w2.pricing.team_score import independent_team_scores
from w2.pricing.value_vs_market import edge, market_lines, pricing_status

PRICING_SHADOW_VERSION = "w2.s1.shadow.v1"
UNCALIBRATED_STATUS = "RULE_BASED_UNCALIBRATED"


def build_pricing_shadow(
    *,
    fixture_id: str,
    model_probabilities: dict[str, Any] | None,
    market_probabilities: dict[str, Any] | None = None,
    current_odds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    team_scores = independent_team_scores(
        model_probabilities=model_probabilities,
        market_probabilities=market_probabilities,
        current_odds=current_odds,
    )
    fair_ah = fair_handicap_from_supremacy(
        team_scores["home_score"],
        team_scores["away_score"],
    )
    fair_ou = fair_total_from_coverage(team_scores["coverage"])
    lines = market_lines(current_odds)
    edge_ah = edge(fair_ah, lines["market_ah"])
    edge_ou = edge(fair_ou, lines["market_ou"])
    return {
        "fixture_id": fixture_id,
        "status": pricing_status(
            coverage=team_scores["coverage"],
            edge_ah=edge_ah,
            edge_ou=edge_ou,
        ),
        "model_version": PRICING_SHADOW_VERSION,
        "calibration_version": "UNVALIDATED",
        "factors": team_scores["factors"],
        "team_score": {
            "home": team_scores["home_score"],
            "away": team_scores["away_score"],
        },
        "fair_ah": fair_ah,
        "fair_ou": fair_ou,
        "market_ah": lines["market_ah"],
        "market_ou": lines["market_ou"],
        "edge_ah": edge_ah,
        "edge_ou": edge_ou,
        "coverage": team_scores["coverage"],
        "asof_market_snapshot_id": None,
        "devig_method": None,
        "settlement_outcome": None,
        "beats_market": False,
        "formal_enabled": False,
        "candidate_enabled": False,
        "s2_gate": {
            "n_min": 200,
            "beats_market": False,
        },
    }
